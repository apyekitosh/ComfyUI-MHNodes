"""Screen-space normal maps from depth gradients, using only torch."""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from comfy_api.latest import io


class DepthToNormal(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_DepthToNormal",
            display_name="Depth to Normal",
            category="MHNodes/image",
            description=(
                "Converts a depth image or batch to RGB normal maps using horizontal and "
                "vertical depth gradients. No camera or 3D reconstruction is needed. "
                "Flat depth becomes (0.5, 0.5, 1). Brighter depth is treated as raised by "
                "default. Output uses +Y up (OpenGL); flip_y switches the green channel "
                "for DirectX-style maps."
            ),
            inputs=[
                io.Image.Input("depth", tooltip="Grayscale depth image or batch. RGB channels "
                               "are averaged; alpha is ignored."),
                io.Float.Input("strength", default=10.0, min=0.0, max=1000.0, step=0.1,
                               tooltip="Scales depth differences per pixel. Higher values make "
                                       "surface slopes stronger. 0 gives a flat normal map."),
                io.Boolean.Input("invert_depth", default=False,
                                 tooltip="Reverse which end of the depth range is raised."),
                io.Boolean.Input("flip_y", default=False,
                                 tooltip="Flip the green channel: off for +Y up (OpenGL), "
                                         "on for DirectX-style normals."),
            ],
            outputs=[io.Image.Output(id="normal", display_name="normal")],
        )

    @classmethod
    def execute(cls, depth, strength, invert_depth, flip_y) -> io.NodeOutput:
        if depth.ndim != 4 or depth.shape[-1] not in (1, 3, 4) or min(depth.shape[:3]) < 1:
            raise ValueError("depth must be a non-empty IMAGE batch [B, H, W, C] "
                             "with 1, 3 or 4 channels.")
        if not math.isfinite(strength) or strength < 0:
            raise ValueError("strength must be a finite, non-negative number.")

        surface = depth[..., :3].float().mean(dim=-1)
        dx = torch.zeros_like(surface)
        dy = torch.zeros_like(surface)
        # Central differences inside, one-sided at edges: a flat surface stays flat all the
        # way to the image border, and ramps retain their slope there. Singleton axes stay 0.
        if surface.shape[2] > 1:
            dx[:, :, 1:-1] = (surface[:, :, 2:] - surface[:, :, :-2]) * 0.5
            dx[:, :, 0] = surface[:, :, 1] - surface[:, :, 0]
            dx[:, :, -1] = surface[:, :, -1] - surface[:, :, -2]
        if surface.shape[1] > 1:
            dy[:, 1:-1, :] = (surface[:, 2:, :] - surface[:, :-2, :]) * 0.5
            dy[:, 0, :] = surface[:, 1, :] - surface[:, 0, :]
            dy[:, -1, :] = surface[:, -1, :] - surface[:, -2, :]

        scale = -strength if invert_depth else strength
        # Image rows point down; using +dy here expresses normal Y in an upward axis.
        normals = torch.stack((-dx * scale, dy * scale * (-1 if flip_y else 1),
                               torch.ones_like(surface)), dim=-1)
        normals = F.normalize(normals, dim=-1)
        return io.NodeOutput((normals * 0.5 + 0.5).contiguous())
