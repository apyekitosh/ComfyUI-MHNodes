"""MHNodes - simple, general-purpose ComfyUI nodes."""

import logging

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes import (
    AnyToPipe,
    CompositeImageMasked,
    CropImageAndMask,
    ErodeDilate,
    ImageMaskFromBatch,
    LinearGradientFromCoords,
    LoadLatentPreview,
    PipeToAny,
    SaveImageSequence,
    SaveLatentPreview,
    TrailMasks,
)

WEB_DIRECTORY = "./js"

log = logging.getLogger("MHNodes")


class MHNodesExtension(ComfyExtension):
    @override
    async def on_load(self) -> None:
        # These are side features. If either fails to start the nodes must still register,
        # so each is isolated rather than allowed to take the pack down with it.
        try:
            from .model_puller import setup

            setup()
        except Exception as exc:
            log.error("model puller did not start: %s", exc)

        try:
            from . import latent_store

            latent_store.setup()
        except Exception as exc:
            log.error("latent store did not start: %s", exc)

    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            SaveImageSequence,
            LinearGradientFromCoords,
            CropImageAndMask,
            CompositeImageMasked,
            TrailMasks,
            ErodeDilate,
            AnyToPipe,
            PipeToAny,
            SaveLatentPreview,
            LoadLatentPreview,
            ImageMaskFromBatch,
        ]


async def comfy_entrypoint() -> MHNodesExtension:
    return MHNodesExtension()
