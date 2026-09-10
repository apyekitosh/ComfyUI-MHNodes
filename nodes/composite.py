"""Compositing nodes."""

from __future__ import annotations

import torch
from comfy_api.latest import io

from .utils import MAX_RESOLUTION, match_batch_size, match_channels, match_mask_to_image


class CompositeImageMasked(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_CompositeImageMasked",
            display_name="Composite Image Masked",
            category="MHNodes/image",
            description=(
                "Pastes a foreground image onto a background at an x/y offset. The background is "
                "the canvas: it sets the output resolution and batch size. Two separate optional "
                "masks control the blend. background_mask is fixed in canvas space and does not "
                "move with the offset; foreground_mask travels with the foreground, as if its "
                "alpha had been applied before pasting. Anything past the canvas edge is cropped, "
                "and the offsets may be negative."
            ),
            inputs=[
                io.Image.Input(
                    "background",
                    tooltip="The canvas. Sets the output resolution and batch size.",
                ),
                io.Image.Input("foreground", tooltip="The image pasted onto the canvas."),
                io.Int.Input("x", default=0, min=-MAX_RESOLUTION, max=MAX_RESOLUTION, step=1,
                             tooltip="Horizontal offset of the foreground's left edge. May be negative."),
                io.Int.Input("y", default=0, min=-MAX_RESOLUTION, max=MAX_RESOLUTION, step=1,
                             tooltip="Vertical offset of the foreground's top edge. May be negative."),
                io.Mask.Input(
                    "background_mask",
                    optional=True,
                    tooltip=(
                        "Stretched to the background's resolution and fixed in canvas space. "
                        "Marks where on the canvas the foreground is allowed to show. Does not "
                        "move with the offset."
                    ),
                ),
                io.Mask.Input(
                    "foreground_mask",
                    optional=True,
                    tooltip=(
                        "Stretched to the foreground's resolution and pasted at the same offset "
                        "as the foreground, like applying its alpha before compositing."
                    ),
                ),
            ],
            outputs=[
                io.Image.Output(id="image", display_name="image"),
                io.Mask.Output(
                    id="mask",
                    display_name="mask",
                    tooltip="The blend actually applied, in canvas space: the two masks multiplied "
                            "together with the foreground mask already moved into position.",
                ),
            ],
        )

    @classmethod
    def execute(cls, background, foreground, x, y,
                background_mask=None, foreground_mask=None) -> io.NodeOutput:
        batch, canvas_h, canvas_w, channels = background.shape

        # The background is the canvas, so everything else conforms to its batch size.
        foreground = match_batch_size(foreground, batch)
        foreground = match_channels(foreground, channels)
        fore_h, fore_w = foreground.shape[1], foreground.shape[2]

        # Each mask is stretched to its own image, which is what makes the two behave differently.
        if background_mask is not None:
            background_mask = match_mask_to_image(background_mask, background).clamp(0.0, 1.0)
        if foreground_mask is not None:
            foreground_mask = match_mask_to_image(foreground_mask, foreground).clamp(0.0, 1.0)

        image_out = background.clone()
        mask_out = torch.zeros(batch, canvas_h, canvas_w,
                               dtype=background.dtype, device=background.device)

        # Region of the canvas the foreground lands on, clipped to the canvas.
        left, top = max(0, x), max(0, y)
        right, bottom = min(canvas_w, x + fore_w), min(canvas_h, y + fore_h)

        # Entirely off-canvas: nothing to composite.
        if right <= left or bottom <= top:
            return io.NodeOutput(image_out, mask_out)

        # Matching region of the foreground.
        src_left, src_top = left - x, top - y
        src_right, src_bottom = src_left + (right - left), src_top + (bottom - top)

        fore_region = foreground[:, src_top:src_bottom, src_left:src_right, :]

        # The foreground mask is sampled in foreground space, so it moves with the paste.
        if foreground_mask is not None:
            alpha = foreground_mask[:, src_top:src_bottom, src_left:src_right]
        else:
            alpha = torch.ones(batch, bottom - top, right - left,
                               dtype=background.dtype, device=background.device)

        # The background mask is sampled in canvas space, so it stays put.
        if background_mask is not None:
            alpha = alpha * background_mask[:, top:bottom, left:right]

        blend = alpha.unsqueeze(-1)
        image_out[:, top:bottom, left:right, :] = (
            background[:, top:bottom, left:right, :] * (1.0 - blend) + fore_region * blend
        )
        mask_out[:, top:bottom, left:right] = alpha

        return io.NodeOutput(image_out, mask_out)
