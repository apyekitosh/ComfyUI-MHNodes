"""Padding a batch out to a frame count a model will accept.

Video models only accept certain frame counts, and the arithmetic is easy to get wrong by one.
These round a batch up to the nearest valid count and add the frames to do it.
"""

from __future__ import annotations

import math

import torch
from comfy_api.latest import io

from .utils import match_batch_size

#: (step, offset) -- a valid count is a multiple of step, plus offset. Free does no rounding.
POLICIES = {
    "Free": None,
    "Wan": (4, 1),
    "LTXV": (8, 1),
    "Minimax": (17, 5),
}

PLACEMENTS = ("Start", "End", "Both")


def round_up(count: int, policy: str) -> int:
    """Smallest count this policy accepts that is not below `count`."""
    rule = POLICIES.get(policy)
    if rule is None:
        return count
    step, offset = rule
    # Below the offset the first valid count is the offset itself, and ceil() of a negative
    # would otherwise walk backwards.
    steps = max(0, math.ceil((count - offset) / step))
    return steps * step + offset


def split_padding(total: int, placement: str) -> tuple[int, int]:
    """How many frames go before and after. An odd split puts the extra frame at the start."""
    if placement == "Start":
        return total, 0
    if placement == "End":
        return 0, total
    start = math.ceil(total / 2)
    return start, total - start


def _hex_to_rgba(value: str) -> tuple[float, float, float, float]:
    text = (value or "").strip().lstrip("#")
    if len(text) not in (6, 8):
        raise ValueError(f"Colour must look like #RRGGBB or #RRGGBBAA, got {value!r}")
    try:
        channels = [int(text[i:i + 2], 16) / 255.0 for i in range(0, len(text), 2)]
    except ValueError:
        raise ValueError(f"Colour must look like #RRGGBB or #RRGGBBAA, got {value!r}") from None
    if len(channels) == 3:
        channels.append(1.0)
    return tuple(channels)


def _image_block(image: torch.Tensor, count: int, edge: str, solid: str | None) -> torch.Tensor:
    """`count` frames to sit at one end of an image batch."""
    if solid is None:
        source = image[:1] if edge == "start" else image[-1:]
        return source.expand(count, -1, -1, -1)

    red, green, blue, alpha = _hex_to_rgba(solid)
    values = [red, green, blue, alpha][: image.shape[3]]
    block = torch.empty(count, image.shape[1], image.shape[2], image.shape[3],
                        dtype=image.dtype, device=image.device)
    for channel, value in enumerate(values):
        block[..., channel] = value
    return block


def _mask_block(mask: torch.Tensor, count: int, edge: str, solid: float | None) -> torch.Tensor:
    if solid is None:
        source = mask[:1] if edge == "start" else mask[-1:]
        return source.expand(count, -1, -1)
    return torch.full((count, mask.shape[1], mask.shape[2]), float(solid),
                      dtype=mask.dtype, device=mask.device)


def pad_batches(image, mask, policy: str, amount: int, add_to: str,
                image_fill: str | None = None, mask_fill: float | None = None):
    """Shared by both nodes. `*_fill` of None means repeat the edge frame instead."""
    if image is None and mask is None:
        raise ValueError("Pad Frame Count needs an image, a mask, or both.")
    if add_to not in PLACEMENTS:
        raise ValueError(f"Unknown placement {add_to!r}")
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy {policy!r}")

    # Counts are matched first, so padding extends an already-aligned pair.
    if image is not None and mask is not None:
        mask = match_batch_size(mask, image.shape[0])

    current = image.shape[0] if image is not None else mask.shape[0]

    # Asking for fewer frames than you have never shortens the batch; the policy is then
    # applied to what is actually there, so the result is still a count the model accepts.
    target = round_up(max(amount, current), policy)
    padding = max(0, target - current)
    before, after = split_padding(padding, add_to)

    if image is not None and padding:
        pieces = []
        if before:
            pieces.append(_image_block(image, before, "start", image_fill))
        pieces.append(image)
        if after:
            pieces.append(_image_block(image, after, "end", image_fill))
        image = torch.cat(pieces, dim=0)

    if mask is not None and padding:
        pieces = []
        if before:
            pieces.append(_mask_block(mask, before, "start", mask_fill))
        pieces.append(mask)
        if after:
            pieces.append(_mask_block(mask, after, "end", mask_fill))
        mask = torch.cat(pieces, dim=0)

    return image, mask, current + padding


def _shared_inputs():
    return [
        io.Image.Input("image", optional=True, tooltip="Image batch to pad."),
        io.Mask.Input("mask", optional=True, tooltip="Mask batch to pad."),
        io.Combo.Input(
            "policy", options=list(POLICIES), default="Free",
            tooltip="Frame counts the model accepts. Wan is 4n+1, LTXV 8n+1, "
                    "Minimax 17n+5. Free rounds to nothing.",
        ),
        io.Int.Input(
            "amount", default=0, min=0, max=0xFFFFFFFF, step=1,
            tooltip="Frame count to reach. Below the batch you already have, the policy is "
                    "applied to that instead, so the batch is never shortened.",
        ),
        io.Combo.Input("add_to", options=list(PLACEMENTS), default="End",
                       tooltip="Which end the new frames go on. Both splits them, with the "
                               "odd frame going to the start."),
    ]


def _shared_outputs():
    return [
        io.Image.Output(id="image", display_name="image"),
        io.Mask.Output(id="mask", display_name="mask"),
        io.Int.Output(id="amount", display_name="amount",
                      tooltip="Frame count after padding."),
    ]


class PadFrameCount(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_PadFrameCount",
            display_name="Pad Frame Count",
            category="MHNodes/batch",
            description=(
                "Rounds a batch up to a frame count the chosen model accepts, repeating the "
                "first or last frame to fill. Wan takes 4n+1 frames, LTXV 8n+1, Minimax 17n+5."
            ),
            inputs=_shared_inputs(),
            outputs=_shared_outputs(),
        )

    @classmethod
    def execute(cls, policy, amount, add_to, image=None, mask=None) -> io.NodeOutput:
        return io.NodeOutput(*pad_batches(image, mask, policy, amount, add_to))


class PadFrameCountAdvanced(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_PadFrameCountAdvanced",
            display_name="Pad Frame Count (Advanced)",
            category="MHNodes/batch",
            description=(
                "Pad Frame Count, with control over what the added frames contain. Set both "
                "rules to Repeat and it behaves exactly like the plain node."
            ),
            inputs=_shared_inputs() + [
                io.Combo.Input("pad_images_rule", options=["Repeat", "Solid Color"],
                               default="Solid Color",
                               tooltip="Repeat the edge frame, or fill with a flat colour."),
                io.Combo.Input("pad_masks_rule", options=["Repeat", "Solid Mask"],
                               default="Solid Mask",
                               tooltip="Repeat the edge mask, or fill with a flat value."),
                io.Color.Input("image_color", default="#808080",
                               tooltip="Colour for added image frames."),
                io.Float.Input("mask_value", default=1.0, min=0.0, max=1.0, step=0.01,
                               tooltip="Value for added mask frames."),
            ],
            outputs=_shared_outputs(),
        )

    @classmethod
    def execute(cls, policy, amount, add_to, pad_images_rule, pad_masks_rule,
                image_color, mask_value, image=None, mask=None) -> io.NodeOutput:
        return io.NodeOutput(*pad_batches(
            image, mask, policy, amount, add_to,
            image_fill=None if pad_images_rule == "Repeat" else image_color,
            mask_fill=None if pad_masks_rule == "Repeat" else mask_value,
        ))
