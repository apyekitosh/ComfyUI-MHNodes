"""Analytical depth surfaces: CPU-only, using the existing ComfyUI environment."""

import importlib.util
from pathlib import Path
import unittest

import torch


spec = importlib.util.spec_from_file_location(
    "mh_depth_normal", Path(__file__).resolve().parents[1] / "nodes" / "depth_normal.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
node = module.DepthToNormal


def convert(depth, strength=10, invert_depth=False, flip_y=False):
    return node.execute(depth, strength, invert_depth, flip_y).result[0]


class DepthToNormalTests(unittest.TestCase):
    def test_flat_depth_and_zero_strength(self):
        for depth, strength in ((torch.full((2, 4, 5, 3), 0.73), 10),
                                (torch.rand(2, 4, 5, 3), 0)):
            result = convert(depth, strength)
            expected = torch.tensor([0.5, 0.5, 1.0]).expand(2, 4, 5, 3)
            torch.testing.assert_close(result, expected)

    def test_known_plane_including_edges_and_batches(self):
        # Height field h = 0.05*x + 0.1*row, so at strength 2, N = (-0.1, 0.2, 1).
        x = torch.arange(5) * 0.05
        y = torch.arange(4) * 0.1
        plane = (y[:, None] + x[None, :])[None, ..., None].expand(1, 4, 5, 3)
        depth = torch.cat((plane, torch.ones_like(plane)), dim=0)
        original = depth.clone()
        result = convert(depth, strength=2)
        expected = torch.tensor([-0.1, 0.2, 1.0])
        expected = expected / expected.norm() * 0.5 + 0.5
        torch.testing.assert_close(result[0], expected.expand(4, 5, 3))
        torch.testing.assert_close(result[1], torch.tensor([0.5, 0.5, 1.0]).expand(4, 5, 3))
        torch.testing.assert_close(depth, original)
        torch.testing.assert_close((result * 2 - 1).norm(dim=-1), torch.ones(2, 4, 5))
        self.assertTrue(((result >= 0) & (result <= 1)).all())

    def test_orientation_controls(self):
        depth = torch.arange(20, dtype=torch.float32).reshape(1, 4, 5, 1) / 20
        normal = convert(depth)
        flipped = convert(depth, flip_y=True)
        inverted = convert(depth, invert_depth=True)
        torch.testing.assert_close(flipped[..., 0], normal[..., 0])
        torch.testing.assert_close(flipped[..., 1], 1 - normal[..., 1])
        torch.testing.assert_close(flipped[..., 2], normal[..., 2])
        torch.testing.assert_close(inverted[..., :2], 1 - normal[..., :2])
        torch.testing.assert_close(inverted[..., 2], normal[..., 2])

    def test_singleton_axes_and_alpha(self):
        for height, width in ((1, 1), (1, 5), (5, 1), (2, 2)):
            with self.subTest(height=height, width=width):
                gray = torch.arange(height * width, dtype=torch.float32).reshape(1, height, width, 1)
                rgb = gray.expand(1, height, width, 3)
                rgba = torch.cat((rgb, torch.rand_like(gray)), dim=-1)
                torch.testing.assert_close(convert(gray), convert(rgb))
                torch.testing.assert_close(convert(gray), convert(rgba))
                result = convert(gray.half())
                self.assertEqual(result.shape, (1, height, width, 3))
                self.assertEqual(result.dtype, torch.float32)
                self.assertTrue(torch.isfinite(result).all())
                if width == 1:
                    torch.testing.assert_close(result[..., 0], torch.full((1, height, width), 0.5))
                if height == 1:
                    torch.testing.assert_close(result[..., 1], torch.full((1, height, width), 0.5))

    def test_invalid_inputs(self):
        for shape in ((1, 4, 5), (1, 4, 5, 2), (1, 0, 5, 3)):
            with self.subTest(shape=shape), self.assertRaisesRegex(ValueError, "IMAGE batch"):
                convert(torch.zeros(shape))
        for strength in (-1, float("inf"), float("nan")):
            with self.subTest(strength=strength), self.assertRaisesRegex(ValueError, "finite"):
                convert(torch.zeros(1, 2, 2, 3), strength=strength)


if __name__ == "__main__":
    unittest.main()
