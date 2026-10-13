"""MiniMax H3 video continuation: guide a new take with the tail of an old one, then join them.

How the H3 video VAE lays out time decides everything here. It encodes in independent reels of
17 frames, each packed as 1 + 4 + 4 + 4 + 4 frames into 5 latent frames. A slice of a latent that
starts on a reel boundary is bit-identical to encoding those frames on their own; a slice from
anywhere else is something no encode would produce. Both nodes therefore only ever cut on reel
boundaries, which for a 17n+5 video means a tail of 5, 22, 39... frames.

Audio has no reels: its encoder remembers everything before each latent frame, so a sliced audio
latent differs from a fresh encode for roughly its first 100 ms, then converges. It still decodes
to the right sound. The guide can optionally re-encode the audio instead, for comparison.
"""

from __future__ import annotations

import math

import torch
from comfy_api.latest import io

#: Pixel frames held by each latent frame of an H3 reel. Mirrors comfy.ldm.minimax.model.
FRAMES_PER_LATENT = (1, 4, 4, 4, 4)
REEL_FRAMES = 17
REEL_LATENTS = 5
VIDEO_CHANNELS = 24
FPS = 24
AUDIO_LATENTS_PER_SECOND = 40
#: Audio latent frames per pixel frame: 40 / 24.
AUDIO_PER_FRAME = AUDIO_LATENTS_PER_SECOND / FPS


def pixel_frames(latent_frames: int) -> int:
    return sum(FRAMES_PER_LATENT[k % REEL_LATENTS] for k in range(latent_frames))


def latent_frames_for(frames: int) -> int:
    """Latent frames holding `frames` pixel frames, for a valid 17n+5 count (or 1)."""
    if frames == 1:
        return 1
    return (frames - 5) // REEL_FRAMES * REEL_LATENTS + 2


def valid_tail(frames: int) -> bool:
    return frames >= 5 and (frames - 5) % REEL_FRAMES == 0


def audio_length(frames: int) -> int:
    """Audio latent frames H3 pairs with a video of `frames` pixel frames."""
    return round(frames * AUDIO_PER_FRAME)


def split(latent: dict, what: str) -> tuple[torch.Tensor, torch.Tensor | None]:
    """(video, audio or None) from an H3 latent, checked."""
    samples = latent["samples"]
    if getattr(samples, "is_nested", False):
        parts = samples.unbind()
        video, audio = parts[0], (parts[1] if len(parts) > 1 else None)
    else:
        video, audio = samples, None
    if video.ndim != 5 or video.shape[1] != VIDEO_CHANNELS:
        raise ValueError(
            f"{what} is not a MiniMax H3 latent: expected video of shape "
            f"[B, {VIDEO_CHANNELS}, T, H, W], got {tuple(video.shape)}."
        )
    return video, audio


def join_parts(video: torch.Tensor, audio: torch.Tensor | None):
    if audio is None:
        return video
    import comfy.nested_tensor

    return comfy.nested_tensor.NestedTensor((video, audio))


def _encode_audio_tail(audio_vae, audio: torch.Tensor, start_frame: int) -> torch.Tensor:
    """Decode the whole audio, cut the waveform at the exact instant, encode the tail fresh.

    The whole track is decoded rather than just the tail because the decoder needs context on
    both sides of every sample; a decoded fragment smears its edges.
    """
    # Comfy's VAE wrapper hands audio over as [B, samples, channels], both ways.
    waveform = audio_vae.decode(audio)
    rate = getattr(audio_vae, "audio_sample_rate", 32000)
    start = round(start_frame / FPS * rate)
    return audio_vae.encode(waveform[:1, start:])


class MiniMaxH3AddLatentGuide(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_MiniMaxH3AddLatentGuide",
            display_name="Add Latent Guide for MiniMax H3",
            category="MHNodes/minimax",
            description=(
                "Add Guide for MiniMax H3, fed from a latent instead of an image: anchors the "
                "end of a previous take at a frame of the new one, without decoding and "
                "re-encoding it.\n\n"
                "The tail is cut on a reel boundary, so it is exactly what encoding those frames "
                "would give: 5, 22, 39... frames. The audio comes along unless switched off."
            ),
            inputs=[
                io.Conditioning.Input("positive"),
                io.Latent.Input("latent", tooltip="The new take's latent. Only its size is read."),
                io.Latent.Input("guide", tooltip="The previous take. Its last frames become the guide."),
                io.Int.Input(
                    "frames", default=22, min=5, max=9999, step=1,
                    tooltip="Frames to take from the end of the guide. Rounded down to a valid "
                            "length (5, 22, 39...) and to what the guide has.",
                ),
                io.Int.Input(
                    "frame_idx", default=0, min=-9999, max=9999,
                    tooltip="Frame of the new take the guide starts at. 0 for continuation. "
                            "Negative counts from the end.",
                ),
                io.Boolean.Input("use_audio", default=True,
                                 tooltip="Guide the audio as well, if the guide has any."),
                io.Vae.Input(
                    "audio_vae", optional=True,
                    tooltip="Optional. Connected, the audio is decoded and its tail encoded "
                            "fresh instead of sliced, as core's Add Guide does with real audio.",
                ),
            ],
            outputs=[
                io.Conditioning.Output(display_name="positive"),
                io.Int.Output(id="overlap", display_name="overlap",
                              tooltip="Frames the guide covers. Feed it to Join MiniMax H3 Latents."),
            ],
        )

    @classmethod
    def execute(cls, positive, latent, guide, frames, frame_idx, use_audio,
                audio_vae=None) -> io.NodeOutput:
        import node_helpers

        target, target_audio = split(latent, "latent")
        source, source_audio = split(guide, "guide")

        if source.shape[3:] != target.shape[3:]:
            raise ValueError(
                f"The guide is {source.shape[4] * 16}x{source.shape[3] * 16} but the new take is "
                f"{target.shape[4] * 16}x{target.shape[3] * 16}. A latent guide can't be resized; "
                f"generate both at the same size."
            )

        source_frames = pixel_frames(source.shape[2])
        target_frames = pixel_frames(target.shape[2])
        if source_frames < 5:
            raise ValueError("The guide has fewer than 5 frames, so there is no tail to take.")

        # Largest valid tail that is no longer than asked for, nor than the guide. Both are at
        # least 5, so this never drops below the shortest tail.
        wanted = min(frames, source_frames)
        overlap = (wanted - 5) // REEL_FRAMES * REEL_FRAMES + 5
        tail = latent_frames_for(overlap)

        resolved = frame_idx if frame_idx >= 0 else target_frames + frame_idx
        if resolved < 0 or resolved + overlap > target_frames:
            raise ValueError(
                f"A {overlap}-frame guide at frame_idx {frame_idx} does not fit in the new take's "
                f"{target_frames} frames."
            )

        keyframe = {
            "resolved_frame_index": resolved,
            "latent": source[:, :, -tail:].clone(),
        }

        if use_audio and source_audio is not None:
            if target_audio is None:
                raise ValueError("The guide has audio but the new take's latent doesn't. Use an "
                                 "AV latent, or switch use_audio off.")
            start_frame = source_frames - overlap
            if audio_vae is not None:
                guide_audio = _encode_audio_tail(audio_vae, source_audio, start_frame)
            else:
                # Audio runs at 40 latent frames a second against 24 video frames, so a reel
                # boundary usually falls between two audio latent frames: rounding puts the
                # audio at most 12.5 ms off the picture.
                guide_audio = source_audio[..., round(start_frame * AUDIO_PER_FRAME):]
            # Same limit as core: the guide audio may not run past the end of the new take.
            room = math.floor(target_audio.shape[-1] - AUDIO_PER_FRAME * resolved)
            if room < 1:
                raise ValueError(f"frame_idx {frame_idx} is past the end of the new take's audio.")
            keyframe["audio_latent"] = guide_audio[..., :room].clone()

        keyframes = list(positive[0][1].get("minimax_keyframes", []))
        keyframes.append(keyframe)
        positive = node_helpers.conditioning_set_values(positive, {"minimax_keyframes": keyframes})
        return io.NodeOutput(positive, overlap)


class MiniMaxH3JoinLatents(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_MiniMaxH3JoinLatents",
            display_name="Join MiniMax H3 Latents",
            category="MHNodes/minimax",
            description=(
                "Joins a take and its continuation into one latent, to be decoded as a unit. "
                "The first take is cut where the guide started and the second appended whole, so "
                "the seam falls on a reel boundary and the decoder blends across it like any "
                "other.\n\n"
                "Expects the continuation to have been guided at frame 0, as Add Latent Guide "
                "for MiniMax H3 does for continuation."
            ),
            inputs=[
                io.Latent.Input("first", tooltip="The earlier take."),
                io.Latent.Input("second", tooltip="The continuation, guided by the end of the first."),
                io.Int.Input(
                    "overlap", default=22, min=5, max=9999, step=1,
                    tooltip="Frames the two share: the overlap output of the guide node.",
                ),
            ],
            outputs=[
                io.Latent.Output(id="samples", display_name="samples"),
                io.Int.Output(id="frames", display_name="frames",
                              tooltip="Pixel frames in the joined latent."),
            ],
        )

    @classmethod
    def execute(cls, first, second, overlap) -> io.NodeOutput:
        video_a, audio_a = split(first, "first")
        video_b, audio_b = split(second, "second")

        if video_a.shape[0] != video_b.shape[0] or video_a.shape[3:] != video_b.shape[3:]:
            raise ValueError(
                f"The takes differ in size: {tuple(video_a.shape)} and {tuple(video_b.shape)}."
            )
        if (audio_a is None) != (audio_b is None):
            raise ValueError("One take has audio and the other doesn't, so they can't be joined.")
        if not valid_tail(overlap):
            raise ValueError(
                f"overlap {overlap} is not a length a guide can have (5, 22, 39...). Connect the "
                f"guide node's overlap output."
            )

        frames_a = pixel_frames(video_a.shape[2])
        frames_b = pixel_frames(video_b.shape[2])
        if overlap > frames_a:
            raise ValueError(f"overlap {overlap} is longer than the first take ({frames_a} frames).")

        # A 17n+5 take minus a 17j+5 tail leaves whole reels, so this cut is a reel boundary.
        keep_frames = frames_a - overlap
        keep = video_a.shape[2] - latent_frames_for(overlap)
        video = torch.cat([video_a[:, :, :keep], video_b], dim=2)
        total = keep_frames + frames_b

        audio = None
        if audio_a is not None:
            # Sized from the total so the result is exactly the length H3 pairs with this many
            # frames, which keeps it decodable and continuable. The second take keeps all of its
            # audio; the first is cut to fit in front of it.
            keep_audio = audio_length(total) - audio_b.shape[-1]
            keep_audio = max(0, min(keep_audio, audio_a.shape[-1]))
            audio = torch.cat([audio_a[..., :keep_audio], audio_b], dim=-1)

        return io.NodeOutput({"samples": join_parts(video, audio)}, total)
