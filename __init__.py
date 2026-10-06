"""MHNodes - simple, general-purpose ComfyUI nodes."""

import logging

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes import (
    CompositeImageMasked,
    CropImageAndMask,
    ErodeDilate,
    LinearGradientFromCoords,
    SaveImageSequence,
    TrailMasks,
)


WEB_DIRECTORY = "./js"


class MHNodesExtension(ComfyExtension):
    @override
    async def on_load(self) -> None:
        # The model puller is a side feature; if it fails to start, the nodes must still load.
        try:
            from .model_puller import setup

            setup()
        except Exception as exc:
            logging.getLogger("MHNodes").error("model puller did not start: %s", exc)

    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            SaveImageSequence,
            LinearGradientFromCoords,
            CropImageAndMask,
            CompositeImageMasked,
            TrailMasks,
            ErodeDilate,
        ]


async def comfy_entrypoint() -> MHNodesExtension:
    return MHNodesExtension()
