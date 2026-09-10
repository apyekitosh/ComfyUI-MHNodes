"""MHNodes - simple, general-purpose ComfyUI nodes."""

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes import (
    CompositeImageMasked,
    CropImageAndMask,
    LinearGradientFromCoords,
    SaveImageSequence,
)


class MHNodesExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            SaveImageSequence,
            LinearGradientFromCoords,
            CropImageAndMask,
            CompositeImageMasked,
        ]


async def comfy_entrypoint() -> MHNodesExtension:
    return MHNodesExtension()
