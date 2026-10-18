"""Video nodes that work on image batches directly, with no VIDEO object to build first.

Encoding goes through core's own pipeline (the same one Save Video uses). Video Preview uses
core's own player; the loaders' range-aware player lives in js/video_loader.js and is mounted
through the frontend's addDOMWidget, which sizes it, rather than drawn by hand.
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


# ---------------------------------------------------------------- loading

def _frame_index(frame, stream, fps: Fraction, origin: int) -> int | None:
    if frame.pts is None:
        return None
    return round((frame.pts - origin) * stream.time_base * fps)


def load_frames(path: str, start: int, frame_cap: int, every_nth: int):
    """Decode only the frames asked for: seek to the keyframe before `start`, then stop as soon
    as the cap is reached instead of reading the whole file."""
    import av
    import numpy as np

    from .. import video_store

    images, last_index = [], None
    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        fps = video_store.frame_rate(stream)
        origin = stream.start_time or 0
        if start > 0:
            container.seek(origin + int(start / fps / stream.time_base), stream=stream, backward=True)

        counter = None
        for frame in container.decode(stream):
            index = _frame_index(frame, stream, fps, origin)
            if index is None:
                counter = 0 if counter is None else counter + 1
                index = counter
            if index < start:
                continue
            if (index - start) % every_nth:
                continue
            images.append(frame.to_ndarray(format="rgb24"))
            last_index = index
            if frame_cap and len(images) >= frame_cap:
                break

    if not images:
        raise ValueError(f"start {start} is past the end of {os.path.basename(path)}.")
    tensor = torch.from_numpy(np.stack(images)).float().div_(255.0)

    # Audio covers the same span the frames do, from the first frame to the end of the last.
    audio = _load_audio(path, Fraction(start) / fps, Fraction(last_index + 1) / fps)
    return tensor, audio, float(fps / every_nth)


def _load_audio(path: str, begin: Fraction, end: Fraction):
    import av
    import numpy as np

    with av.open(path) as container:
        if not container.streams.audio:
            return None
        stream = container.streams.audio[0]
        rate = stream.codec_context.sample_rate
        resampler = av.AudioResampler(format="fltp", rate=rate)
        if begin > 0:
            container.seek(int(begin / stream.time_base), stream=stream, backward=True)

        chunks, first_sample = [], None
        for frame in container.decode(stream):
            for part in resampler.resample(frame):
                if part.pts is None:
                    continue
                if first_sample is None:
                    first_sample = round(part.pts * part.time_base * rate)
                chunks.append(part.to_ndarray())
            if frame.pts is not None and frame.pts * stream.time_base >= end:
                break

    if not chunks:
        return None
    samples = np.concatenate(chunks, axis=1)
    lo = max(0, round(begin * rate) - first_sample)
    hi = max(lo, round(end * rate) - first_sample)
    waveform = torch.from_numpy(samples[:, lo:hi].copy()).unsqueeze(0)
    return {"waveform": waveform, "sample_rate": rate}


def _range_inputs():
    return [
        io.Int.Input("start", default=0, min=0, max=0xFFFFFFFF, step=1,
                     tooltip="First frame to load, counting from 0."),
        io.Int.Input("frame_cap", default=0, min=0, max=0xFFFFFFFF, step=1,
                     tooltip="Most frames to load. 0 loads to the end."),
        io.Int.Input("select_every_nth", default=1, min=1, max=0xFFFF, step=1,
                     tooltip="Keep one frame in every n. The fps output is divided to match."),
    ]


def _loader_outputs():
    return [
        io.Image.Output(id="images", display_name="images"),
        io.Audio.Output(id="audio", display_name="audio",
                        tooltip="The audio under the loaded frames. None if the file has none."),
        io.Float.Output(id="fps", display_name="fps",
                        tooltip="Frame rate of what was loaded: the file's, divided by n."),
        io.Int.Output(id="frame_count", display_name="frame_count"),
    ]


def _file_fingerprint(path: str, *rest) -> str:
    try:
        stat = os.stat(path)
        return f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}|{rest}"
    except OSError:
        return f"missing|{path}|{rest}"


def _load(path, start, frame_cap, select_every_nth) -> io.NodeOutput:
    images, audio, fps = load_frames(path, start, frame_cap, select_every_nth)
    return io.NodeOutput(images, audio, fps, images.shape[0])


class LoadVideoInput(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        from .. import video_store

        return io.Schema(
            node_id="MH_LoadVideoInput",
            display_name="Load Video - Input",
            category="MHNodes/video",
            description=(
                "Loads frames and audio from a video in the input folder, straight to an image "
                "batch. Upload with the button or by dropping a file on the node; for files over "
                "the upload limit use Load Video - Path.\n\n"
                "The preview plays only the frames that will load."
            ),
            inputs=[
                io.Combo.Input("video", options=video_store.input_videos(),
                               tooltip="A video in the input folder."),
                *_range_inputs(),
            ],
            outputs=_loader_outputs(),
        )

    @classmethod
    def execute(cls, video, start, frame_cap, select_every_nth) -> io.NodeOutput:
        import folder_paths

        return _load(folder_paths.get_annotated_filepath(video), start, frame_cap, select_every_nth)

    @classmethod
    def fingerprint_inputs(cls, video, start, frame_cap, select_every_nth):
        import folder_paths

        return _file_fingerprint(folder_paths.get_annotated_filepath(video),
                                 start, frame_cap, select_every_nth)

    @classmethod
    def validate_inputs(cls, video, **_):
        import folder_paths

        if not folder_paths.exists_annotated_filepath(video):
            return f"No video named {video!r} in the input folder."
        return True


class LoadVideoPath(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_LoadVideoPath",
            display_name="Load Video - Path",
            category="MHNodes/video",
            description=(
                "Loads frames and audio from a video anywhere on disk, straight to an image "
                "batch. For files too big to upload. A path pasted with quotes around it, as "
                "Windows' Copy as path gives, works as is.\n\n"
                "The preview plays only the frames that will load. Formats a browser can't play, "
                "such as ProRes, get a small preview copy made once."
            ),
            inputs=[
                io.String.Input("path", default="", tooltip="Full path to the video file."),
                *_range_inputs(),
            ],
            outputs=_loader_outputs(),
        )

    @classmethod
    def execute(cls, path, start, frame_cap, select_every_nth) -> io.NodeOutput:
        from .. import video_store

        clean = video_store.clean_path(path)
        if not os.path.isfile(clean):
            raise FileNotFoundError(f"No video at {clean!r}.")
        return _load(clean, start, frame_cap, select_every_nth)

    @classmethod
    def fingerprint_inputs(cls, path, start, frame_cap, select_every_nth):
        from .. import video_store

        return _file_fingerprint(video_store.clean_path(path), start, frame_cap, select_every_nth)
