"""Snapping a mask onto MiniMax H3's latent grid.

Moving masks can "bleed" in H3: a trace of where the mask was stays visible. Lining every masked
region up with what the model actually sees -- its 32 px spatial cells, and the [1][4][4][4][4]
way it packs each 17-frame reel in time -- is meant to stop that. Spatial and temporal blocking
switch independently, to find which of them a given case needs.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from comfy_api.latest import io

#: H3's spatial cell: 16x VAE compression, then 2x2 patches.
CELL = 32
#: Frames per reel, and how a reel is packed into latent frames, as [start, end).
REEL = 17
GROUPS = ((0, 1), (1, 5), (5, 9), (9, 13), (13, 17))


def trim_frames(count: int) -> int:
    """Largest 17n + 5 frame count not above `count`."""
    if count < 5:
        raise ValueError(f"The mask has {count} frame(s); H3 needs at least 5.")
    return (count - 5) // REEL * REEL + 5


def blockify(mask: torch.Tensor, binarize_threshold: float, cell_threshold: int,
             spatial: bool = True, temporal: bool = True) -> torch.Tensor:
    if mask.ndim == 2:
        mask = mask[None]
    frames = trim_frames(mask.shape[0])
    mask = mask[:frames].float()

    height, width = mask.shape[1] // CELL * CELL, mask.shape[2] // CELL * CELL
    if height == 0 or width == 0:
        raise ValueError(f"The mask is {mask.shape[2]}x{mask.shape[1]}; both sides must be at "
                         f"least {CELL}.")
    if (height, width) != tuple(mask.shape[1:]):
        mask = F.interpolate(mask[:, None], size=(height, width), mode="bilinear",
                             align_corners=False)[:, 0]

    blocks = (mask >= binarize_threshold).float()

    if spatial:
        # White pixels per cell, then each cell all or nothing.
        rows, cols = height // CELL, width // CELL
        counts = blocks.reshape(frames, rows, CELL, cols, CELL).sum(dim=(2, 4))
        blocks = (counts >= cell_threshold).float()

    if temporal:
        # Each group of 4 frames in a reel becomes the union of its frames -- per cell, or per
        # pixel when spatial blocking is off. The single frame opening each reel is left as is.
        for reel in range(0, frames, REEL):
            for begin, end in GROUPS[1:]:
                lo, hi = reel + begin, min(reel + end, frames)
                if hi - lo > 1:
                    blocks[lo:hi] = blocks[lo:hi].amax(dim=0, keepdim=True)

    if spatial:
        blocks = blocks.repeat_interleave(CELL, dim=1).repeat_interleave(CELL, dim=2)
    return blocks


class BlockifyMaskToGrid(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_BlockifyMaskToGrid",
            display_name="Blockify Mask to Grid",
            category="MHNodes/mask",
            description=(
                "Snaps a mask onto MiniMax H3's latent grid, to stop moving masks bleeding. Always "
                "trimmed to 17n + 5 frames, resized down to multiples of 32 and binarised; then, "
                "each switchable: filled or emptied per 32x32 cell, and merged over each 4-frame "
                "group of H3's [1][4][4][4][4] reels."
            ),
            inputs=[
                io.Mask.Input("mask"),
                io.Float.Input("binarize_threshold", display_name="binarize threshold",
                               default=0.5, min=0.0, max=1.0, step=0.01,
                               tooltip="Pixels at or above this are white, below are black."),
                io.Int.Input("cell_threshold", default=4, min=1, max=CELL * CELL,
                             tooltip=f"White pixels needed for a {CELL}x{CELL} cell to fill; "
                                     f"fewer and it empties. Only with spatial blocking."),
                io.Boolean.Input("spatial_blocking", default=True,
                                 tooltip=f"Fill or empty whole {CELL}x{CELL} cells. Off, the mask "
                                         f"stays pixel-accurate after binarising."),
                io.Boolean.Input("temporal_blocking", default=True,
                                 tooltip="Merge each group of 4 frames in H3's [1][4][4][4][4] "
                                         "reels. Off, every frame keeps its own shape."),
            ],
            outputs=[io.Mask.Output(id="mask", display_name="mask")],
        )

    @classmethod
    def execute(cls, mask, binarize_threshold, cell_threshold, spatial_blocking,
                temporal_blocking) -> io.NodeOutput:
        return io.NodeOutput(blockify(mask, binarize_threshold, cell_threshold,
                                      spatial_blocking, temporal_blocking))
