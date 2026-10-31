"""Decoding a whole folder of saved latents in one run."""

from __future__ import annotations

import logging
import os
from fractions import Fraction

import torch
from comfy_api.latest import io

log = logging.getLogger("MHNodes.DecodeDirectory")

OUTPUTS = ("mp4", "image sequence")
OUTPUT_FOLDER = "decoded"


def resolve_directory(value: str) -> str:
    """An absolute path, or one relative to ComfyUI's input folder, where latents are saved."""
    import folder_paths

    from .. import video_store

    path = video_store.clean_path(value)
    if not path:
        raise ValueError("No directory given.")
    if not os.path.isabs(path):
        path = os.path.join(folder_paths.get_input_directory(), path)
    if not os.path.isdir(path):
        raise FileNotFoundError(f"No directory at {path!r}.")
    return os.path.normpath(path)


def latent_files(directory: str) -> list[str]:
    """The .latent files directly in `directory`, in natural name order."""
    from ..video_store import _natural_key

    names = [entry.name for entry in os.scandir(directory)
             if entry.is_file() and entry.name.lower().endswith(".latent")]
    return [os.path.join(directory, name) for name in sorted(names, key=_natural_key)]


def _frame_rate(fps: float) -> Fraction:
    # 23.976 as a float is a long binary fraction; video rates are always over 1 or 1001.
    return Fraction(fps).limit_denominator(1001)


def _remove(path: str) -> None:
    import shutil

    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def _write_mp4(images, audio, fps: float, path: str) -> None:
    from comfy_api.latest import InputImpl, Types

    from .video import _even

    # Written under a temporary name and moved into place only once complete, so a latent that
    # fails halfway leaves nothing behind rather than a broken file.
    partial = path + ".part.mp4"
    try:
        video = InputImpl.VideoFromComponents(
            Types.VideoComponents(images=_even(images), audio=audio, frame_rate=_frame_rate(fps))
        )
        video.save_to(partial, format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264)
        os.replace(partial, path)
    finally:
        _remove(partial)


def _write_sequence(images, audio, folder: str, stem: str) -> None:
    from PIL import Image

    # Built in a temporary folder and swapped in only once every frame is written, so a failure
    # leaves the previous result (or nothing), never half a sequence.
    partial = folder + ".part"
    _remove(partial)
    try:
        os.makedirs(partial)
        frames = images.clamp(0.0, 1.0).mul(255.0).round().to(torch.uint8).cpu().numpy()
        # Saved names already end in "_" (take_00003_), so frames join on a single one.
        prefix = stem.rstrip("_")
        for index, frame in enumerate(frames):
            Image.fromarray(frame[..., :3]).save(os.path.join(partial, f"{prefix}_{index:05}.png"),
                                                 compress_level=4)
        if audio is not None:
            _write_mp3(audio, os.path.join(partial, f"{stem}.mp3"))
        _remove(folder)
        os.replace(partial, folder)
    finally:
        _remove(partial)


def _write_mp3(audio: dict, path: str) -> None:
    import av
    import numpy as np

    wave = audio["waveform"][0].float().clamp(-1.0, 1.0).cpu().numpy()
    rate = int(audio["sample_rate"])
    if wave.shape[0] > 2:
        wave = wave[:2]
    layout = "stereo" if wave.shape[0] == 2 else "mono"
    with av.open(path, "w", format="mp3") as out:
        stream = out.add_stream("libmp3lame", rate=rate, layout=layout)
        stream.bit_rate = 320_000
        frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(wave, dtype=np.float32),
                                           format="fltp", layout=layout)
        frame.sample_rate = rate
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)


def decode_one(path: str, vae, audio_vae):
    """(frames, audio or None) for one saved latent."""
    from comfy_extras.nodes_audio import vae_decode_audio

    from .latent_io import read_latent

    samples = read_latent(path)
    nested = getattr(samples, "is_nested", False)
    video = samples.unbind()[0] if nested else samples

    images = vae.decode(video)
    if images.ndim == 5:  # [B, T, H, W, C] from video VAEs: frames in order
        images = images.reshape(-1, *images.shape[-3:])

    audio = None
    if nested and audio_vae is not None:
        # Core's own audio decode, so the sound matches what VAE Decode Audio gives.
        audio = vae_decode_audio(audio_vae, {"samples": samples})
    return images, audio


class VAEDecodeDirectory(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_VAEDecodeDirectory",
            display_name="VAE Decode Full Directory",
            category="MHNodes/latent",
            description=(
                "Decodes every saved latent in a folder, into a 'decoded' folder beside them: one "
                "mp4 each, or one subfolder of PNGs plus an mp3 each. A latent that won't decode "
                "is skipped with a warning rather than stopping the run."
            ),
            inputs=[
                io.String.Input("directory", default="latents",
                                tooltip="Absolute, or relative to ComfyUI's input folder."),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae", optional=True,
                             tooltip="Decodes the audio of audio-video latents. Without it, "
                                     "only the picture is written."),
                io.Float.Input("fps", default=24.0, min=1.0, max=120.0, step=1.0),
                io.Combo.Input("output", options=list(OUTPUTS), default="mp4",
                               tooltip="mp4: one video per latent, audio inside. image sequence: "
                                       "a subfolder per latent, PNG frames and an mp3."),
            ],
            outputs=[io.String.Output(id="folder", display_name="folder",
                                      tooltip="The 'decoded' folder written to.")],
            hidden=[io.Hidden.unique_id],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, directory, vae, fps, output, audio_vae=None) -> io.NodeOutput:
        import comfy.model_management

        source = resolve_directory(directory)
        files = latent_files(source)
        if not files:
            raise ValueError(f"No .latent files in {source}.")
        target = os.path.join(source, OUTPUT_FOLDER)
        os.makedirs(target, exist_ok=True)

        total, done, skipped = len(files), 0, []
        cls._progress(f"0/{total}")
        for number, path in enumerate(files, start=1):
            comfy.model_management.throw_exception_if_processing_interrupted()
            name = os.path.basename(path)
            stem = os.path.splitext(name)[0]
            try:
                # ComfyUI already runs nodes this way; stating it keeps the node correct when
                # called from anywhere else too.
                with torch.inference_mode():
                    images, audio = decode_one(path, vae, audio_vae)
                    if output == "mp4":
                        _write_mp4(images, audio, fps, os.path.join(target, f"{stem}.mp4"))
                    else:
                        _write_sequence(images, audio, os.path.join(target, stem), stem)
                done += 1
                log.info("decoded %d/%d: %s (%d frames)", number, total, name, images.shape[0])
            except comfy.model_management.InterruptProcessingException:
                raise
            except Exception as exc:
                # By design every latent here is the same kind, but one that isn't shouldn't
                # cost the rest of the folder.
                skipped.append((name, str(exc).splitlines()[0][:160]))
                log.warning("skipped %d/%d: %s (%s)", number, total, name, exc)
            finally:
                images = audio = None
            cls._progress(f"{number}/{total}" + (f" · {len(skipped)} skipped" if skipped else ""))

        summary = [f"Decoded {done} of {total} into {target}"]
        summary += [f"Skipped {name}: {reason}" for name, reason in skipped]
        return io.NodeOutput(target, ui={"text": ["\n".join(summary)]})

    @classmethod
    def _progress(cls, text: str) -> None:
        """'12/47' on the node itself while it works."""
        try:
            from server import PromptServer

            PromptServer.instance.send_progress_text(text, cls.hidden.unique_id)
        except Exception:
            pass

    @classmethod
    def fingerprint_inputs(cls, directory, fps, output, **_):
        # Re-run when the folder gains, loses or rewrites a latent, not only when inputs change.
        try:
            files = latent_files(resolve_directory(directory))
            listing = [(os.path.basename(f), os.stat(f).st_size, os.stat(f).st_mtime_ns)
                       for f in files]
        except Exception:  # a bad path is reported by execute, not here
            listing = None
        return f"{directory}|{fps}|{output}|{listing}"
