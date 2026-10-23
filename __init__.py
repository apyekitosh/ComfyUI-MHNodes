"""MHNodes - simple, general-purpose ComfyUI nodes."""

import logging

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .nodes import (
    AnyList,
    AnyPlot,
    AnyToPipe,
    CompositeImageMasked,
    CropImageAndMask,
    EmptyMask,
    ErodeDilate,
    ExecutionFlowController,
    ImageMaskFromBatch,
    ImageMaskFromTail,
    LinearGradientFromCoords,
    ListSize,
    LoadImagesPath,
    LoadLatentPreview,
    LoadVideoInput,
    LoadVideoPath,
    MaskTrackCrop,
    MaskTrackStitch,
    MiniMaxH3AddLatentGuide,
    MiniMaxH3ExtendLatent,
    MiniMaxH3JoinLatents,
    ModelCompatibleInt,
    PadFrameCount,
    PadFrameCountAdvanced,
    PipeToAny,
    QuickMath,
    SaveImageSequence,
    SaveLatentPreview,
    TrailMasks,
    VideoPreview,
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

        try:
            from . import video_store

            video_store.setup()
        except Exception as exc:
            log.error("video preview routes did not start: %s", exc)

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
            ImageMaskFromTail,
            EmptyMask,
            PadFrameCount,
            PadFrameCountAdvanced,
            ModelCompatibleInt,
            MiniMaxH3AddLatentGuide,
            MiniMaxH3ExtendLatent,
            MiniMaxH3JoinLatents,
            VideoPreview,
            LoadVideoInput,
            LoadVideoPath,
            LoadImagesPath,
            ExecutionFlowController,
            AnyList,
            AnyPlot,
            ListSize,
            QuickMath,
            MaskTrackCrop,
            MaskTrackStitch,
        ]


async def comfy_entrypoint() -> MHNodesExtension:
    return MHNodesExtension()
