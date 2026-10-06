"""Morphological operations."""

from __future__ import annotations

import cv2
import numpy as np
import torch
from comfy_api.latest import io

OPERATIONS = ("dilate", "erode", "open", "close")

SHAPES = {
    "ellipse": cv2.MORPH_ELLIPSE,
    "rect": cv2.MORPH_RECT,
    "cross": cv2.MORPH_CROSS,
}


class ErodeDilate(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_ErodeDilate",
            display_name="Erode / Dilate (RGB)",
            category="MHNodes/image",
            description=(
                "Greyscale morphology applied per channel. dilate takes the local maximum, so "
                "bright areas grow; erode takes the minimum, so dark areas grow. open (erode then "
                "dilate) drops isolated specks without moving the big edges; close (dilate then "
                "erode) seals pinholes without growing the outline.\n\n"
                "Per-channel maxima can tint a boundary between two saturated colours (red beside "
                "blue reads magenta for a pixel or two). Against black it is harmless, since any "
                "real colour already beats 0."
            ),
            inputs=[
                io.Image.Input("image", tooltip="Image or image batch to process."),
                io.Combo.Input("operation", options=list(OPERATIONS), default="dilate",
                               tooltip="dilate grows bright areas, erode grows dark areas."),
                io.Int.Input("radius", default=3, min=0, max=256, step=1,
                             tooltip="Kernel radius in pixels. 0 passes the image through unchanged."),
                io.Int.Input("iterations", default=1, min=1, max=64, step=1,
                             tooltip="How many times to repeat the operation."),
                io.Combo.Input("shape", options=list(SHAPES), default="ellipse",
                               tooltip="Structuring element shape."),
            ],
            outputs=[io.Image.Output(id="image", display_name="image")],
        )

    @classmethod
    def execute(cls, image, operation, radius, iterations, shape) -> io.NodeOutput:
        if radius <= 0 or iterations <= 0:
            return io.NodeOutput(image)

        kernel = cv2.getStructuringElement(SHAPES[shape], (2 * radius + 1, 2 * radius + 1))

        out = []
        for i in range(image.shape[0]):  # IMAGE is a batch: [B,H,W,C]
            arr = np.clip(image[i].detach().cpu().numpy() * 255.0, 0, 255).astype(np.uint8)
            if operation == "dilate":
                res = cv2.dilate(arr, kernel, iterations=iterations)
            elif operation == "erode":
                res = cv2.erode(arr, kernel, iterations=iterations)
            else:
                res = cv2.morphologyEx(
                    arr,
                    cv2.MORPH_OPEN if operation == "open" else cv2.MORPH_CLOSE,
                    kernel,
                    iterations=iterations,
                )
            out.append(torch.from_numpy(res.astype(np.float32) / 255.0))

        return io.NodeOutput(torch.stack(out))
