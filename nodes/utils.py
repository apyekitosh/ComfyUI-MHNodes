"""Shared tensor/PIL helpers for MHNodes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from PIL.PngImagePlugin import PngInfo


#: Upper bound for pixel-dimension widgets, matching ComfyUI's own MAX_RESOLUTION.
MAX_RESOLUTION = 16384

#: Output formats offered by the save nodes, in menu order.
FILETYPES = ("png", "jpg", "jpeg", "webp", "tiff", "bmp")

#: Formats that cannot carry an alpha channel.
_NO_ALPHA = (".jpg", ".jpeg", ".bmp")


def tensor2pil(image: torch.Tensor) -> Image.Image:
    """Convert a single HWC float tensor in [0, 1] to a PIL image."""
    if image.ndim != 3:
        raise ValueError(f"expected a single [H,W,C] image, got shape {tuple(image.shape)}")

    channels = image.shape[2]
    if channels not in (1, 3, 4):
        raise ValueError(f"image must have 1, 3 or 4 channels, got {channels}")

    array = image.clamp(0.0, 1.0).mul(255.0).round().to(torch.uint8).cpu().numpy()
    if channels == 1:
        return Image.fromarray(array[:, :, 0], mode="L")
    return Image.fromarray(array, mode="RGB" if channels == 3 else "RGBA")


def pil2tensor(image: Image.Image) -> torch.Tensor:
    """Convert a PIL image to a [1,H,W,C] float tensor in [0, 1]."""
    array = np.array(image).astype(np.float32) / 255.0
    if array.ndim == 2:
        array = array[:, :, None]
    return torch.from_numpy(array).unsqueeze(0)


def match_mask_to_image(mask: torch.Tensor, image: torch.Tensor) -> torch.Tensor:
    """Reshape a [B,H,W] mask so it lines up with a [B,H,W,C] image batch.

    The mask is stretched to the image's resolution, ignoring aspect ratio. The batch is then
    matched by repeating the last mask if there are too few, or trimming if there are too many.
    """
    image_batch, image_h, image_w = image.shape[0], image.shape[1], image.shape[2]

    if mask.shape[1] != image_h or mask.shape[2] != image_w:
        mask = torch.nn.functional.interpolate(
            mask.unsqueeze(1),  # [B,1,H,W]
            size=(image_h, image_w),
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)

    mask_batch = mask.shape[0]
    if mask_batch > image_batch:
        mask = mask[:image_batch]
    elif mask_batch < image_batch:
        padding = mask[-1:].expand(image_batch - mask_batch, -1, -1)
        mask = torch.cat([mask, padding], dim=0)

    return mask


def build_png_metadata(prompt=None, extra_pnginfo: dict | None = None) -> PngInfo | None:
    """Build the PNG metadata block ComfyUI embeds in saved images."""
    metadata = PngInfo()
    has_data = False

    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))
        has_data = True

    if extra_pnginfo is not None:
        for key, value in extra_pnginfo.items():
            metadata.add_text(key, json.dumps(value))
            has_data = True

    return metadata if has_data else None


def save_image_to_path(
    image: torch.Tensor,
    path: Path,
    prompt=None,
    extra_pnginfo: dict | None = None,
    compress_level: int = 4,
) -> Path:
    """Write a single [H,W,C] image tensor to an arbitrary filesystem path.

    The format is taken from the path's extension; only PNG carries the workflow metadata.
    """
    pil_image = tensor2pil(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix in (".png", ""):
        pil_image.save(path, format="PNG", pnginfo=build_png_metadata(prompt, extra_pnginfo),
                       compress_level=compress_level)
    else:
        if pil_image.mode == "RGBA" and suffix in _NO_ALPHA:
            pil_image = pil_image.convert("RGB")
        pil_image.save(path)

    return path
