"""CPU checks for pixel-space inspection and adding native H3 audio without losing masks."""

import importlib.util
from pathlib import Path
import unittest

import torch
from comfy.nested_tensor import NestedTensor


spec = importlib.util.spec_from_file_location(
    "mh_minimax_h3_tools", Path(__file__).resolve().parents[1] / "nodes" / "minimax_h3.py"
)
h3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h3)


class LatentInfoTests(unittest.TestCase):
    def test_pixel_dimensions_duration_and_ui_for_both_stream_types(self):
        # Includes partial reels so the conversion can't be replaced by a fixed T multiplier.
        for steps, expected_frames in ((1, 1), (2, 5), (5, 17), (7, 22), (12, 39), (37, 124)):
            video = torch.zeros(1, 24, steps, 30, 54)
            for samples in (video, NestedTensor((video, torch.zeros(1, 32, 2, 207)))):
                with self.subTest(steps=steps, av=getattr(samples, "is_nested", False)):
                    latent = {"samples": samples, "metadata": "unchanged"}
                    out = h3.MiniMaxH3LatentInfo.execute(latent)
                    passthrough, width, height, frames, seconds = out.result
                    self.assertIs(passthrough, latent)
                    self.assertEqual((width, height, frames), (864, 480, expected_frames))
                    self.assertEqual(seconds, expected_frames / 24)
                    self.assertEqual(out.ui, {
                        "width": [width], "height": [height], "frames": [frames], "seconds": [seconds],
                    })

    def test_can_execute_without_connected_outputs(self):
        schema = h3.MiniMaxH3LatentInfo.define_schema()
        self.assertTrue(schema.is_output_node)
        self.assertEqual([s.id for s in schema.outputs], ["latent", "width", "height", "frames", "seconds"])


class AddAudioTests(unittest.TestCase):
    def test_native_audio_shape_rounding_dtype_and_metadata(self):
        for steps, audio_steps in ((2, 8), (7, 37), (12, 65), (37, 207)):
            with self.subTest(steps=steps):
                video = torch.randn(2, 24, steps, 2, 3, dtype=torch.float16)
                latent = {"samples": video, "batch_index": [2, 7]}
                out, = h3.MiniMaxH3AddAudio.execute(latent).result
                kept_video, audio = out["samples"].unbind()
                self.assertIs(kept_video, video)
                self.assertEqual(audio.shape, (2, 32, 2, audio_steps))
                self.assertEqual(audio.dtype, video.dtype)
                self.assertEqual(audio.device, video.device)
                self.assertEqual(torch.count_nonzero(audio), 0)
                self.assertEqual(out["batch_index"], [2, 7])
                self.assertNotIn("noise_mask", out)
                self.assertIs(latent["samples"], video)
                self.assertIsNot(out, latent)

    def test_video_masks_survive_while_audio_is_fully_denoisable(self):
        video = torch.randn(2, 24, 12, 2, 3)
        for mask in (torch.rand(2, 1, 12, 2, 3), torch.rand(1, 2, 3)):
            for nested in (False, True):
                with self.subTest(shape=mask.shape, nested=nested):
                    original = mask.clone()
                    noise_mask = NestedTensor((mask,)) if nested else mask
                    samples = NestedTensor((video,)) if nested else video
                    latent = {"samples": samples, "noise_mask": noise_mask}
                    out, = h3.MiniMaxH3AddAudio.execute(latent).result
                    video_mask, audio_mask = out["noise_mask"].unbind()
                    self.assertIs(video_mask, mask)
                    torch.testing.assert_close(video_mask, original)
                    self.assertEqual(audio_mask.shape, (2, 1, 2, 65))
                    self.assertTrue((audio_mask == 1).all())
                    self.assertIs(latent["noise_mask"], noise_mask)

    def test_refine_accepts_added_audio_and_masks_both_streams(self):
        previous, = h3.MiniMaxH3AddAudio.execute({"samples": torch.ones(1, 24, 12, 2, 3)}).result
        current, = h3.MiniMaxH3AddAudio.execute({"samples": torch.zeros(1, 24, 17, 2, 3)}).result
        refined, overlap = h3.MiniMaxH3RefineLatent.execute(previous, current, 22).result
        self.assertEqual(overlap, 22)
        video_mask, audio_mask = refined["noise_mask"].unbind()
        self.assertTrue((video_mask[:, :, :7] == 0).all())
        self.assertTrue((video_mask[:, :, 7:] == 1).all())
        self.assertTrue((audio_mask[..., :37] == 0).all())
        self.assertTrue((audio_mask[..., 37:] == 1).all())

    def test_existing_audio_and_invalid_video_are_rejected(self):
        video = torch.zeros(1, 24, 7, 2, 3)
        av = {"samples": NestedTensor((video, torch.ones(1, 32, 2, 37)))}
        with self.assertRaisesRegex(ValueError, "already has an audio"):
            h3.MiniMaxH3AddAudio.execute(av)
        for node in (h3.MiniMaxH3AddAudio, h3.MiniMaxH3LatentInfo):
            with self.assertRaisesRegex(ValueError, "not a MiniMax H3 latent"):
                node.execute({"samples": torch.zeros(1, 16, 2, 3)})


if __name__ == "__main__":
    unittest.main()
