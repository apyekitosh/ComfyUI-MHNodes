"""Video nodes that work on image batches directly, with no VIDEO object to build first.

Encoding goes through core's own pipeline (the same one Save Video uses), and the preview is
core's own video widget, so there is no custom widget code here to misbehave.
"""

from __future__ import annotations

import os
from fractions import Fraction

import torch
from comfy_api.latest import InputImpl, Types, io, ui


def _even(images: torch.Tensor) -> torch.Tensor:
    """H.264 at 4:2:0 needs even dimensions. Pad by repeating the last row/column rather than
    crop, so nothing in the picture is lost; only the encoded copy is touched."""
    height, width = images.shape[1], images.shape[2]
    if height % 2:
        images = torch.cat([images, images[:, -1:]], dim=1)
    if width % 2:
        images = torch.cat([images, images[:, :, -1:]], dim=2)
    return images


class VideoPreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_VideoPreview",
            display_name="Video Preview",
            category="MHNodes/video",
            description=(
                "Plays an image batch as a video, with optional audio. Written to the temp folder "
                "as H.264, which ComfyUI clears on restart.\n\n"
                "Both inputs pass straight through, so the node can sit in the middle of a graph."
            ),
            inputs=[
                io.Image.Input("images", tooltip="Frames to preview."),
                io.Audio.Input("audio", optional=True, tooltip="Soundtrack to play with them."),
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0, step=1.0),
            ],
            outputs=[
                io.Image.Output(id="images", display_name="images"),
                io.Audio.Output(id="audio", display_name="audio"),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, images, fps, audio=None) -> io.NodeOutput:
        import folder_paths

        frames = _even(images)
        temp = folder_paths.get_temp_directory()
        folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            "MH_preview", temp, frames.shape[2], frames.shape[1]
        )
        file = f"{filename}_{counter:05}_.mp4"

        video = InputImpl.VideoFromComponents(
            Types.VideoComponents(images=frames, audio=audio, frame_rate=Fraction(fps))
        )
        video.save_to(
            os.path.join(folder, file),
            format=Types.VideoContainer.MP4,
            codec=Types.VideoCodec.H264,
            metadata=cls._metadata(),
        )

        return io.NodeOutput(
            images, audio,
            ui=ui.PreviewVideo([ui.SavedResult(file, subfolder, io.FolderType.temp)]),
        )

    @classmethod
    def _metadata(cls) -> dict | None:
        """The workflow, as core's Save Video embeds it, so the clip can be dropped back in."""
        from comfy.cli_args import args

        if args.disable_metadata or cls.hidden is None:
            return None
        metadata = {}
        if cls.hidden.extra_pnginfo is not None:
            metadata.update(cls.hidden.extra_pnginfo)
        if cls.hidden.prompt is not None:
            metadata["prompt"] = cls.hidden.prompt
        return metadata or None
