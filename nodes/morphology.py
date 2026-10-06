"""Morphological operations.

Greyscale morphology is a rank filter: dilation is the local maximum over the structuring
element, erosion the local minimum. Both are expressed here with torch max-pooling, so the
node needs no OpenCV and keeps full float precision.
"""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from comfy_api.latest import io

OPERATIONS = ("dilate", "erode", "open", "close")
SHAPES = ("ellipse", "rect", "cross")

_NEG_INF = float("-inf")


def _ellipse_half_widths(radius: int) -> dict[int, list[int]]:
    """Row offsets of an elliptical structuring element, grouped by half-width.

    Mirrors OpenCV's getStructuringElement(MORPH_ELLIPSE): row dy is a single contiguous run
    centred on the middle column, round(radius * sqrt((radius^2 - dy^2) / radius^2)) either side.
    """
    grouped: dict[int, list[int]] = {}
    for dy in range(-radius, radius + 1):
        half = int(round(radius * math.sqrt((radius * radius - dy * dy) / (radius * radius))))
        grouped.setdefault(half, []).append(dy)
    return grouped


def _dilate(tensor: torch.Tensor, radius: int, shape: str) -> torch.Tensor:
    """Local maximum of a [B,C,H,W] tensor over the structuring element."""
    size = 2 * radius + 1

    # A rectangle is separable, so two 1D passes beat one size*size pool. max_pool2d's implicit
    # padding is already -inf, which is exactly "outside contributes nothing".
    if shape == "rect":
        passed = F.max_pool2d(tensor, (1, size), stride=1, padding=(0, radius))
        return F.max_pool2d(passed, (size, 1), stride=1, padding=(radius, 0))

    # A cross is the union of a row and a column, so the max over it is the max of the two.
    if shape == "cross":
        horizontal = F.max_pool2d(tensor, (1, size), stride=1, padding=(0, radius))
        vertical = F.max_pool2d(tensor, (size, 1), stride=1, padding=(radius, 0))
        return torch.maximum(horizontal, vertical)

    # An ellipse is a stack of centred horizontal runs of differing widths. Rather than pool each
    # row at its own full width, widen one running tensor three pixels at a time: a horizontal
    # dilation of width 3 applied to a half-width of k gives a half-width of k+1. So every row
    # width is reached with a constant-width pool, which keeps the cost linear in the radius
    # instead of quadratic.
    height = tensor.shape[2]
    rows_by_half = _ellipse_half_widths(radius)

    widened = tensor
    result = None
    for half in range(radius + 1):
        if half > 0:
            widened = F.max_pool2d(widened, (1, 3), stride=1, padding=(0, 1))

        offsets = rows_by_half.get(half)
        if not offsets:
            continue

        # Rows beyond the image contribute nothing, which -inf padding expresses directly.
        padded = F.pad(widened, (0, 0, radius, radius), value=_NEG_INF)
        for dy in offsets:
            top = radius + dy
            shifted = padded[:, :, top:top + height, :]
            result = shifted if result is None else torch.maximum(result, shifted)

    return result


def _erode(tensor: torch.Tensor, radius: int, shape: str) -> torch.Tensor:
    """Local minimum, as the dual of dilation."""
    return -_dilate(-tensor, radius, shape)


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

        tensor = image.movedim(-1, 1)  # [B,H,W,C] -> [B,C,H,W]; pooling is per channel

        # open and close are an erode/dilate pair, each run for the full iteration count.
        sequence = {
            "dilate": (_dilate,),
            "erode": (_erode,),
            "open": (_erode, _dilate),
            "close": (_dilate, _erode),
        }[operation]

        for step in sequence:
            for _ in range(iterations):
                tensor = step(tensor, radius, shape)

        return io.NodeOutput(tensor.movedim(1, -1).contiguous())
