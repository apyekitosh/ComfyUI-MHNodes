"""Gradient generator nodes."""

from __future__ import annotations

import torch
from comfy_api.latest import io


class LinearGradientFromCoords(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_LinearGradientFromCoords",
            display_name="Linear Gradient from Coords",
            category="MHNodes/generate",
            description=(
                "Creates a black-to-white linear gradient image. The gradient runs along the "
                "vector from (x1, y1) to (x2, y2): black at the start point, white at the end "
                "point, clamped outside that span."
            ),
            inputs=[
                io.Int.Input("frame_width", default=512, min=16, max=4096, step=1),
                io.Int.Input("frame_height", default=512, min=16, max=4096, step=1),
                io.Int.Input("x1", default=0, min=0, max=4096, step=1,
                             tooltip="Gradient start X (black end)."),
                io.Int.Input("y1", default=256, min=0, max=4096, step=1,
                             tooltip="Gradient start Y (black end)."),
                io.Int.Input("x2", default=512, min=0, max=4096, step=1,
                             tooltip="Gradient end X (white end)."),
                io.Int.Input("y2", default=256, min=0, max=4096, step=1,
                             tooltip="Gradient end Y (white end)."),
                io.Float.Input(
                    "multiplier",
                    default=1.0,
                    min=0.01,
                    max=100.0,
                    step=0.01,
                    tooltip="Scales the ramp before clamping. Higher values make a harder edge.",
                ),
            ],
            outputs=[io.Image.Output("IMAGE")],
        )

    @classmethod
    def execute(cls, frame_width, frame_height, x1, y1, x2, y2, multiplier) -> io.NodeOutput:
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length_sq = dx * dx + dy * dy

        # Degenerate start == end: fall back to a flat black frame rather than dividing by zero.
        if length_sq == 0.0:
            length_sq = 1.0

        px = torch.arange(frame_width, dtype=torch.float32) - x1  # [W]
        py = torch.arange(frame_height, dtype=torch.float32) - y1  # [H]

        # Projection of each pixel onto the gradient vector, normalized to 0-1.
        t = (px[None, :] * dx + py[:, None] * dy) / length_sq  # [H,W]
        t = (t * multiplier).clamp(0.0, 1.0)

        image = t[None, :, :, None].expand(1, frame_height, frame_width, 3).contiguous()
        return io.NodeOutput(image)
