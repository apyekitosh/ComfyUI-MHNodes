"""Cropping nodes."""

from __future__ import annotations

import torch
from comfy_api.latest import io

from .utils import MAX_RESOLUTION, match_mask_to_image

ALIGNMENTS = (
    "top-left",
    "top-center",
    "top-right",
    "right-center",
    "bottom-right",
    "bottom-center",
    "bottom-left",
    "left-center",
    "center",
)


class CropImageAndMask(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_CropImageAndMask",
            display_name="Crop Image and Mask",
            category="MHNodes/image",
            description=(
                "Crops an image and/or a mask to a fixed size, placed by alignment plus an "
                "offset. Both inputs are optional, so it works on an image alone, a mask alone, "
                "or both together. The crop always fits inside the source: the offset is clamped "
                "rather than the output being shrunk. Outputs the x/y of the crop's top-left "
                "corner, ready to paste back at the same place."
            ),
            inputs=[
                io.Image.Input("image", optional=True, tooltip="Image or image batch to crop."),
                io.Mask.Input(
                    "mask",
                    optional=True,
                    tooltip=(
                        "Mask or mask batch to crop. When an image is also connected, the mask "
                        "is resized and batch-matched to it first."
                    ),
                ),
                io.Int.Input("width", default=256, min=1, max=MAX_RESOLUTION, step=1,
                             tooltip="Crop width, before rounding down to a multiple of multiplier."),
                io.Int.Input("height", default=256, min=1, max=MAX_RESOLUTION, step=1,
                             tooltip="Crop height, before rounding down to a multiple of multiplier."),
                io.Combo.Input("alignment", options=list(ALIGNMENTS), default="center",
                               tooltip="Where the crop sits before the offset is applied."),
                io.Int.Input("x_offset", default=0, min=-MAX_RESOLUTION, max=MAX_RESOLUTION, step=1,
                             tooltip="Horizontal nudge from the alignment, clamped to stay in bounds."),
                io.Int.Input("y_offset", default=0, min=-MAX_RESOLUTION, max=MAX_RESOLUTION, step=1,
                             tooltip="Vertical nudge from the alignment, clamped to stay in bounds."),
                io.Int.Input(
                    "multiplier",
                    default=2,
                    min=1,
                    max=256,
                    step=1,
                    tooltip=(
                        "Crop size is rounded down to a multiple of this before cropping, e.g. "
                        "multiplier 8 turns a width of 100 into 96."
                    ),
                ),
            ],
            outputs=[
                io.Image.Output(display_name="image"),
                io.Mask.Output(display_name="mask"),
                io.Int.Output(display_name="x", tooltip="Left edge of the crop in source pixels."),
                io.Int.Output(display_name="y", tooltip="Top edge of the crop in source pixels."),
            ],
        )

    @classmethod
    def execute(cls, width, height, alignment, x_offset, y_offset, multiplier,
                image=None, mask=None) -> io.NodeOutput:
        if image is None and mask is None:
            raise ValueError("Crop Image and Mask needs an image, a mask, or both.")

        # Round the crop size down to a multiple of `multiplier` before anything else.
        crop_w = (width // multiplier) * multiplier
        crop_h = (height // multiplier) * multiplier
        if crop_w <= 0 or crop_h <= 0:
            raise ValueError(
                f"Crop size {width}x{height} rounds down to {crop_w}x{crop_h} at multiplier "
                f"{multiplier}. Raise the size or lower the multiplier."
            )

        if image is not None:
            source_h, source_w = image.shape[1], image.shape[2]
            if mask is not None:
                mask = match_mask_to_image(mask, image)
        else:
            source_h, source_w = mask.shape[1], mask.shape[2]

        if crop_w > source_w or crop_h > source_h:
            raise ValueError(
                f"Crop size {crop_w}x{crop_h} is larger than the source {source_w}x{source_h}."
            )

        x, y = cls._align(alignment, source_w, source_h, crop_w, crop_h)

        # Clamp the offset instead of shrinking the crop, so the output is always crop_w x crop_h.
        x = max(0, min(x + x_offset, source_w - crop_w))
        y = max(0, min(y + y_offset, source_h - crop_h))

        cropped_image = image[:, y:y + crop_h, x:x + crop_w, :] if image is not None else None
        cropped_mask = mask[:, y:y + crop_h, x:x + crop_w] if mask is not None else None

        return io.NodeOutput(cropped_image, cropped_mask, x, y)

    @staticmethod
    def _align(alignment: str, source_w: int, source_h: int, crop_w: int, crop_h: int):
        """Top-left corner of the crop for the given alignment, before any offset."""
        x = round((source_w - crop_w) / 2)
        y = round((source_h - crop_h) / 2)

        if "top" in alignment:
            y = 0
        if "bottom" in alignment:
            y = source_h - crop_h
        if "left" in alignment:
            x = 0
        if "right" in alignment:
            x = source_w - crop_w

        return x, y
