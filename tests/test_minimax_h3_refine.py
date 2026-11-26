"""CPU tensor regressions; run with ComfyUI on PYTHONPATH and its existing environment."""

import importlib.util
from pathlib import Path
import unittest

import torch


spec = importlib.util.spec_from_file_location(
    "mh_minimax_h3", Path(__file__).resolve().parents[1] / "nodes" / "minimax_h3.py"
)
h3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3)


def latent(frames, offset=0, audio=False):
    samples = torch.arange(
        2 * 24 * h3.latent_frames_for(frames) * 2 * 3, dtype=torch.float32
    ).reshape(2, 24, -1, 2, 3) + offset
    sound = None
    if audio:
        sound = torch.arange(2 * 8 * h3.audio_length(frames), dtype=torch.float32)
        sound = sound.reshape(2, 8, -1) + offset
    return {"samples": h3.join_parts(samples, sound)}


class RefineLatentTests(unittest.TestCase):
    def test_video_replacement_mask_and_input_preservation(self):
        previous = latent(73, 10000)
        current = latent(56)
        current["noise_mask"] = torch.zeros(2, 1, 17, 2, 3)
        current["batch_index"] = [3, 4]
        before_previous = previous["samples"].clone()
        before_current = current["samples"].clone()
        out, overlap = h3.MiniMaxH3RefineLatent.execute(previous, current, 38).result
        self.assertEqual(overlap, 22)
        kept = h3.latent_frames_for(overlap)
        torch.testing.assert_close(out["samples"][:, :, :kept], before_previous[:, :, -kept:])
        torch.testing.assert_close(out["samples"][:, :, kept:], before_current[:, :, kept:])
        self.assertEqual(out["samples"].shape, before_current.shape)
        self.assertTrue((out["noise_mask"][:, :, :kept] == 0).all())
        self.assertTrue((out["noise_mask"][:, :, kept:] == 1).all())
        self.assertEqual(out["batch_index"], [3, 4])
        torch.testing.assert_close(previous["samples"], before_previous)
        torch.testing.assert_close(current["samples"], before_current)
        self.assertTrue((current["noise_mask"] == 0).all())

    def test_grid_and_limits(self):
        for previous_frames, current_frames, requested, expected in (
            (73, 56, 5, 5), (73, 56, 22, 22), (73, 56, 39, 39),
            (73, 56, 21, 5), (73, 56, 38, 22), (73, 56, 9999, 56),
            (22, 56, 39, 22), (56, 5, 22, 5),
        ):
            with self.subTest(previous=previous_frames, current=current_frames, overlap=requested):
                out, corrected = h3.MiniMaxH3RefineLatent.execute(
                    latent(previous_frames), latent(current_frames), requested
                ).result
                self.assertEqual(corrected, expected)
                self.assertEqual(h3.pixel_frames(out["samples"].shape[2]), current_frames)

    def test_audio_tail_rounding_and_join(self):
        # Exercise both round-up and round-down at audio boundaries.
        for previous_frames in (22, 39, 56, 73):
            for overlap in (5, 22):
                with self.subTest(previous=previous_frames, overlap=overlap):
                    previous = latent(previous_frames, 10000, audio=True)
                    current = latent(56, audio=True)
                    video_before, audio_before = h3.split(current, "current")
                    source_video, source_audio = h3.split(previous, "previous")
                    out, corrected = h3.MiniMaxH3RefineLatent.execute(
                        previous, current, overlap
                    ).result
                    video, audio = h3.split(out, "output")
                    video_mask, audio_mask = out["noise_mask"].unbind()
                    start = round((previous_frames - corrected) * h3.AUDIO_PER_FRAME)
                    tail = source_audio[..., start:]
                    kept = tail.shape[-1]
                    torch.testing.assert_close(audio[..., :kept], tail)
                    torch.testing.assert_close(audio[..., kept:], audio_before[..., kept:])
                    self.assertEqual(audio.shape, audio_before.shape)
                    self.assertEqual(audio_mask.shape, (2, 1, audio.shape[-1]))
                    self.assertTrue((audio_mask[..., :kept] == 0).all())
                    self.assertTrue((audio_mask[..., kept:] == 1).all())
                    joined, frames = h3.MiniMaxH3JoinLatents.execute(previous, out, corrected).result
                    joined_video, joined_audio = h3.split(joined, "joined")
                    self.assertEqual(frames, previous_frames + 56 - corrected)
                    self.assertEqual(h3.pixel_frames(joined_video.shape[2]), frames)
                    self.assertEqual(joined_audio.shape[-1], h3.audio_length(frames))
                    # Together the kept previous prefix and replaced tail reconstruct previous.
                    torch.testing.assert_close(joined_video[:, :, :source_video.shape[2]], source_video)
                    torch.testing.assert_close(h3.split(current, "current")[1], audio_before)

    def test_rejects_invalid_inputs(self):
        for overlap in (-1, 0, 4):
            with self.subTest(overlap=overlap), self.assertRaisesRegex(ValueError, "at least 5"):
                h3.MiniMaxH3RefineLatent.execute(latent(39), latent(56), overlap)
        with self.assertRaisesRegex(ValueError, "matching batch"):
            h3.MiniMaxH3RefineLatent.execute(
                latent(39), {"samples": torch.zeros(1, 24, 17, 2, 3)}, 22
            )
        with self.assertRaisesRegex(ValueError, "One segment has audio"):
            h3.MiniMaxH3RefineLatent.execute(latent(39, audio=True), latent(56), 22)
        with self.assertRaisesRegex(ValueError, "H3 lengths"):
            h3.MiniMaxH3RefineLatent.execute(
                {"samples": torch.zeros(2, 24, 6, 2, 3)}, latent(56), 5
            )
        with self.assertRaisesRegex(ValueError, "not a MiniMax H3 latent"):
            h3.MiniMaxH3RefineLatent.execute(
                {"samples": torch.zeros(2, 4, 2, 3)}, latent(56), 5
            )

    def test_schema(self):
        schema = h3.MiniMaxH3RefineLatent.define_schema()
        self.assertEqual([item.id for item in schema.inputs], ["previous", "current", "overlap"])
        self.assertEqual([item.id for item in schema.outputs], ["latent", "overlap"])


if __name__ == "__main__":
    unittest.main()
