"""Rounding a number onto a model's grid."""

from __future__ import annotations

from comfy_api.latest import io

from .padding import POLICIES

MODELS = ("Wan", "LTXV", "Minimax")
TYPES = ("Resolution", "Frame Count")

#: Pixels per latent along each side.
RESOLUTION_STEP = {"Wan": 16, "LTXV": 32, "Minimax": 32}


def _round(value: int, step: int, ceil: bool) -> int:
    """value / step, rounded, in integers so large numbers never lose precision to floats."""
    return -(-value // step) if ceil else value // step


def snap_resolution(number: int, model: str, ceil: bool) -> tuple[int, int]:
    step = RESOLUTION_STEP[model]
    # Flooring below one step would give 0, which no model can take, so one step is the floor.
    latent = max(1, _round(number, step, ceil))
    return latent * step, latent


def snap_frames(number: int, model: str, ceil: bool) -> tuple[int, int]:
    step, offset = POLICIES[model]
    # At or below the offset there is only one valid count: the offset itself. This is the
    # 1..5 case for Minimax, and frame 1 for Wan and LTXV, where flooring would go negative.
    pixel = max(offset, _round(number - offset, step, ceil) * step + offset)

    if offset == 1:
        # The first frame gets a latent of its own, then one per `step`: 5 Wan frames are
        # two latents (1 + 4), 9 LTXV frames are two (1 + 8).
        latent = (pixel - 1) // step + 1
    else:
        # Minimax folds its 5 extra frames into the first latent rather than giving them
        # one: 22 frames are a single latent, not 17 + 5. The 5-frame minimum is still one.
        latent = max(1, (pixel - offset) // step)
    return pixel, latent


class ModelCompatibleInt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_ModelCompatibleInt",
            display_name="Model Compatible Int",
            category="MHNodes/utils",
            description=(
                "Rounds a number onto the grid a video model accepts, and says how many latents "
                "that is.\n\n"
                "Resolution: Wan uses multiples of 16, LTXV and Minimax multiples of 32.\n"
                "Frame count: Wan is 4n+1, LTXV 8n+1, Minimax 17n+5."
            ),
            inputs=[
                io.Int.Input("number", default=512, min=1, max=0xFFFFFFFF, step=1,
                             tooltip="The value to round."),
                io.Combo.Input("model", options=list(MODELS), default="Wan",
                               tooltip="Whose grid to round onto."),
                io.Combo.Input("type", options=list(TYPES), default="Resolution",
                               tooltip="Resolution rounds to a multiple; frame count to the "
                                       "model's n+k rule."),
                io.Boolean.Input("rounding", default=False, label_on="Ceil", label_off="Floor",
                                 tooltip="Round down or up. Never rounds below the smallest "
                                         "value the model accepts."),
            ],
            outputs=[
                io.Int.Output(id="pixel_int", display_name="pixel int",
                              tooltip="The rounded value, in pixels or frames."),
                io.Int.Output(id="latent_int", display_name="latent int",
                              tooltip="The same, in latents."),
            ],
        )

    @classmethod
    def execute(cls, number, model, type, rounding) -> io.NodeOutput:
        # A linked number skips the widget's min, so it is checked here as well.
        if number < 1:
            raise ValueError(f"Model Compatible Int needs a number of at least 1, got {number}.")
        if model not in MODELS:
            raise ValueError(f"Unknown model {model!r}")

        if type == "Resolution":
            return io.NodeOutput(*snap_resolution(number, model, rounding))
        if type == "Frame Count":
            return io.NodeOutput(*snap_frames(number, model, rounding))
        raise ValueError(f"Unknown type {type!r}")
