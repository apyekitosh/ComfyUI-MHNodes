"""Crop a fixed-size window that follows an animated mask, and stitch the result back.

Mask Track Crop finds the mask's box on every frame, fills gaps in the animation, smooths the
box's path, and cuts one constant-size window per frame -- sized from the largest box, so a
model gets the same resolution throughout. Mask Track Stitch pastes processed frames back into
the originals at the recorded positions.
"""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from comfy_api.latest import io

from .utils import match_channels, resize_mask

#: Below this a mask pixel counts as empty. Masks are usually thresholded before this node;
#: this only keeps faint noise from a blur far from the subject inflating the box.
THRESHOLD = 0.1
GAP_FILLS = ("none", "blend", "morph")
RESOLUTION_MODES = ("match crop data", "match original frames", "match pasted frames")

CropData = io.Custom("MH_MASK_CROP")


# ---------------------------------------------------------------- crop: finding the boxes

def _boxes(binary: torch.Tensor) -> list[tuple[int, int, int, int] | None]:
    """Per frame, (x0, y0, x1, y1) with exclusive ends, or None for an empty frame."""
    rows, cols = binary.any(dim=2), binary.any(dim=1)
    boxes = []
    for row, col in zip(rows, cols):
        if not row.any():
            boxes.append(None)
            continue
        ys, xs = torch.nonzero(row).flatten(), torch.nonzero(col).flatten()
        boxes.append((int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1))
    return boxes


def _place(patch: torch.Tensor, box, height: int, width: int) -> torch.Tensor:
    """A patch resized into `box` on an empty frame."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)
    resized = F.interpolate(patch[None, None], size=(y1 - y0, x1 - x0), mode="bilinear",
                            align_corners=False)[0, 0]
    canvas = patch.new_zeros((height, width))
    canvas[y0:y1, x0:x1] = resized[: height - y0, : width - x0]
    return canvas


def _signed_distance(binary):
    """Positive inside the shape, negative outside, in pixels from its edge."""
    from scipy import ndimage

    return ndimage.distance_transform_edt(binary) - ndimage.distance_transform_edt(~binary)


def _fill_gap_frame(mode, before, after, box, weight):
    """A mask for an empty frame between two masked ones, `weight` of the way to `after`.

    Both neighbours are first moved and scaled into this frame's interpolated box. blend then
    cross-fades them: shared pixels stay full, the rest fade in proportion. morph blends their
    signed distance fields instead, so one solid shape turns into the other with no ghosting.
    """
    if mode == "blend":
        return before * (1.0 - weight) + after * weight

    import numpy as np

    x0, y0, x1, y1 = (int(round(v)) for v in box)
    # A one-pixel border so a shape filling its box still has an outside to measure from.
    top, left = max(0, y0 - 1), max(0, x0 - 1)
    bottom, right = min(before.shape[0], y1 + 1), min(before.shape[1], x1 + 1)
    a = before[top:bottom, left:right].cpu().numpy() > 0.5
    b = after[top:bottom, left:right].cpu().numpy() > 0.5
    if not a.any() or not b.any():
        return before * (1.0 - weight) + after * weight
    blended = _signed_distance(a) * (1.0 - weight) + _signed_distance(b) * weight
    out = before.new_zeros(before.shape)
    out[top:bottom, left:right] = torch.from_numpy((blended > 0).astype(np.float32))
    return out


#: Rounds of smooth-then-constrain. The path settles well before this on any real sequence.
SMOOTHING_ROUNDS = 50


def _smooth_path(start, low, high, sigma: float):
    """A smoothed path near `start` that stays within [low, high] on every frame.

    A centered Gaussian: each frame looks both ways, so the path doesn't lag. Clamping it
    afterwards would kink the path wherever a clamp bites, so instead each clamp is fed back as a
    correction to the *input* and the original is smoothed again: the correction spreads along
    the path at the same strength. Re-smoothing the smoothed path instead would compound, and
    `sigma` would stop meaning what it says.
    """
    import numpy as np

    target = np.asarray(start, dtype=np.float64)
    if sigma <= 0 or len(target) < 2:
        return np.clip(target, low, high)
    from scipy import ndimage

    correction = np.zeros_like(target)
    for _ in range(SMOOTHING_ROUNDS):
        path = ndimage.gaussian_filter1d(target + correction, sigma, mode="nearest")
        clamped = np.clip(path, low, high)
        if np.array_equal(clamped, path):
            return path
        correction += clamped - path
    # Whatever is still out of range after the corrections is clamped: the mask comes first.
    return clamped


def _window_path(starts, edges, size, extent, sigma):
    """Top-left coordinates of the window along one axis, for each frame of the run.

    `edges` holds each frame's box as (begin, end). Where the box fits the window, the window
    must contain it; the window always stays inside the image, which wins if the two disagree.
    """
    import numpy as np

    low, high = [], []
    for begin, end in edges:
        lo, hi = 0, extent - size
        if end - begin <= size:
            lo, hi = max(lo, end - size), min(hi, begin)
            if lo > hi:  # can't satisfy both: the image edge wins
                lo, hi = (hi, hi) if begin > extent - size else (lo, lo)
        low.append(lo)
        high.append(hi)
    path = _smooth_path(starts, np.array(low, float), np.array(high, float), sigma)
    return [int(round(v)) for v in path]


def crop_size(max_w: int, max_h: int, multiplier: float, aspect_w: int, aspect_h: int,
              multiple_of: int) -> tuple[int, int]:
    """Window size from the largest box: scaled, then shaped to the aspect, then rounded up."""
    width, height = max_w * multiplier, max_h * multiplier
    if aspect_w > 0 and aspect_h > 0:
        # The longest side becomes the ratio's short side, so the mask fits either way round.
        ratio, longest = aspect_w / aspect_h, max(width, height)
        width, height = (longest * ratio, longest) if ratio >= 1 else (longest, longest / ratio)
    step = max(1, multiple_of)
    return math.ceil(width / step - 1e-9) * step, math.ceil(height / step - 1e-9) * step


class MaskTrackCrop(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_MaskTrackCrop",
            display_name="Mask Track Crop",
            category="MHNodes/mask",
            description=(
                "Cuts a fixed-size window that follows an animated mask: sized from the mask's "
                "largest box, moved along its smoothed path, kept inside the image. Gaps in the "
                "mask are filled; frames before and after it can be kept or dropped. Mask Track "
                "Stitch puts the result back."
            ),
            inputs=[
                io.Image.Input("images"),
                io.Mask.Input("mask", tooltip="Must match the images in frame count and size."),
                io.Float.Input("multiplier", default=1.0, min=0.05, max=16.0, step=0.05,
                               tooltip="Scales the window around the largest box. Below 1 the "
                                       "mask can fall outside it."),
                io.Int.Input("multiple_of", default=8, min=1, max=512,
                             tooltip="Window width and height are rounded up to a multiple of "
                                     "this."),
                io.Int.Input("aspect_width", default=0, min=0, max=16384,
                             tooltip="With aspect_height, forces the window's shape: 16 and 9, "
                                     "or 1920 and 1080. 0 leaves it free."),
                io.Int.Input("aspect_height", default=0, min=0, max=16384),
                io.Float.Input("smoothing", default=2.0, min=0.0, max=100.0, step=0.5,
                               tooltip="How much the window's path is smoothed, in frames. 0 "
                                       "follows the mask exactly."),
                io.Combo.Input("gap_fill", options=list(GAP_FILLS), default="morph",
                               tooltip="Empty frames inside the mask's run: none leaves them "
                                       "empty, blend cross-fades the masks either side, morph "
                                       "turns one shape into the other."),
                io.Boolean.Input("drop_empty_ends", default=False,
                                 tooltip="Leave out the empty frames before and after the mask. "
                                         "Kept, they hold the first/last position, mask empty."),
            ],
            outputs=[
                io.Image.Output(id="images", display_name="images"),
                io.Mask.Output(id="mask", display_name="mask"),
                CropData.Output(id="crop_data", display_name="crop_data",
                                tooltip="Window size and positions, for Mask Track Stitch."),
            ],
        )

    @classmethod
    def execute(cls, images, mask, multiplier, multiple_of, aspect_width, aspect_height,
                smoothing, gap_fill, drop_empty_ends) -> io.NodeOutput:
        frames, height, width = images.shape[0], images.shape[1], images.shape[2]
        if mask.ndim == 2:
            mask = mask[None]
        # Precise by design: a mismatch here means something upstream went wrong.
        if mask.shape[0] != frames:
            raise ValueError(f"{frames} images but {mask.shape[0]} masks.")
        if tuple(mask.shape[1:]) != (height, width):
            raise ValueError(f"Images are {width}x{height} but the mask is "
                             f"{mask.shape[2]}x{mask.shape[1]}.")

        mask = mask.to(images.device, torch.float32)
        boxes = _boxes(mask > THRESHOLD)
        filled = [i for i, box in enumerate(boxes) if box is not None]
        if not filled:
            raise ValueError("The mask is empty on every frame, so there is nothing to follow.")
        first, last = filled[0], filled[-1]

        # Gaps inside the run: the box is interpolated from the masked frames either side.
        out_mask = mask.clone()
        for a, b in zip(filled, filled[1:]):
            for t in range(a + 1, b):
                weight = (t - a) / (b - a)
                boxes[t] = tuple(p + (q - p) * weight for p, q in zip(boxes[a], boxes[b]))
                if gap_fill == "none":
                    continue
                ax0, ay0, ax1, ay1 = boxes[a]
                bx0, by0, bx1, by1 = boxes[b]
                before = _place(mask[a, ay0:ay1, ax0:ax1], boxes[t], height, width)
                after = _place(mask[b, by0:by1, bx0:bx1], boxes[t], height, width)
                out_mask[t] = _fill_gap_frame(gap_fill, before, after, boxes[t], weight)

        run = boxes[first:last + 1]
        max_w = max(box[2] - box[0] for box in run)
        max_h = max(box[3] - box[1] for box in run)
        crop_w, crop_h = crop_size(max_w, max_h, multiplier, aspect_width, aspect_height,
                                   multiple_of)
        if crop_w > width or crop_h > height:
            raise ValueError(
                f"The window would be {crop_w}x{crop_h}, bigger than the {width}x{height} "
                f"image. Lower the multiplier or multiple_of, or relax the aspect ratio."
            )

        # The window centred on each box, then smoothed -- but never so far that the mask would
        # leave it, where the box fits, and never past the image.
        xs = _window_path([(b[0] + b[2]) / 2 - crop_w / 2 for b in run],
                          [(round(b[0]), round(b[2])) for b in run], crop_w, width, smoothing)
        ys = _window_path([(b[1] + b[3]) / 2 - crop_h / 2 for b in run],
                          [(round(b[1]), round(b[3])) for b in run], crop_h, height, smoothing)
        positions = [[x, y] for x, y in zip(xs, ys)]
        positions = [positions[0]] * first + positions + [positions[-1]] * (frames - 1 - last)

        start, end = (first, last + 1) if drop_empty_ends else (0, frames)
        crops, crop_masks = [], []
        for i in range(start, end):
            x, y = positions[i]
            crops.append(images[i, y:y + crop_h, x:x + crop_w])
            if first <= i <= last:
                crop_masks.append(out_mask[i, y:y + crop_h, x:x + crop_w])
            else:
                crop_masks.append(out_mask.new_zeros((crop_h, crop_w)))

        crop_data = {
            "version": 1,
            "source_size": [height, width],
            "crop_size": [crop_h, crop_w],
            "positions": positions,   # [x, y] for every source frame
            "start": start,           # first source frame the cropped batch holds
            "count": end - start,
            "frames": frames,
        }
        return io.NodeOutput(torch.stack(crops), torch.stack(crop_masks), crop_data)


# ---------------------------------------------------------------- stitch

def _resize_images(images: torch.Tensor, height: int, width: int) -> torch.Tensor:
    if tuple(images.shape[1:3]) == (height, width):
        return images
    moved = images.movedim(-1, 1)
    moved = F.interpolate(moved, size=(height, width), mode="bicubic", align_corners=False,
                          antialias=True)
    return moved.clamp(0.0, 1.0).movedim(1, -1)


def _fade_mask(alpha: torch.Tensor, distance: int) -> torch.Tensor:
    """Feather outward: masked pixels keep their values, the falloff runs into unmasked ones."""
    if distance <= 0:
        return alpha
    from scipy import ndimage

    inside = (alpha > THRESHOLD).cpu().numpy()
    if not inside.any():
        return alpha
    away = torch.from_numpy(ndimage.distance_transform_edt(~inside)).to(alpha)
    falloff = (1.0 - away / (distance + 1)).clamp(min=0.0)
    return torch.maximum(alpha, falloff)


def _margin_ramp(height, width, distance, open_sides, like: torch.Tensor) -> torch.Tensor:
    """1 inside, fading to the crop's edges over `distance` pixels. Sides on the image edge are
    left hard: there is nothing beyond them to blend into."""
    ramp_y = torch.ones(height, dtype=like.dtype, device=like.device)
    ramp_x = torch.ones(width, dtype=like.dtype, device=like.device)
    steps_y = torch.arange(height, dtype=like.dtype, device=like.device)
    steps_x = torch.arange(width, dtype=like.dtype, device=like.device)
    edge = lambda steps: ((steps + 0.5) / distance).clamp(max=1.0)
    if open_sides["top"]:
        ramp_y = torch.minimum(ramp_y, edge(steps_y))
    if open_sides["bottom"]:
        ramp_y = torch.minimum(ramp_y, edge(steps_y.flip(0)))
    if open_sides["left"]:
        ramp_x = torch.minimum(ramp_x, edge(steps_x))
    if open_sides["right"]:
        ramp_x = torch.minimum(ramp_x, edge(steps_x.flip(0)))
    return torch.minimum(ramp_y[:, None], ramp_x[None, :])


class MaskTrackStitch(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_MaskTrackStitch",
            display_name="Mask Track Stitch",
            category="MHNodes/mask",
            description=(
                "Pastes frames cropped by Mask Track Crop back into the originals, through a "
                "mask if one is given. Frames the crop left out are passed through untouched.\n\n"
                "resolution picks what wins when sizes disagree: the crop data, the original "
                "frames (say, upscaled), or the pasted frames (keeping their detail, and scaling "
                "everything else to match)."
            ),
            inputs=[
                io.Image.Input("original_frames", tooltip="The frames to paste into."),
                io.Image.Input("images", tooltip="The cropped frames, after processing."),
                CropData.Input("crop_data"),
                io.Mask.Input("mask", optional=True,
                              tooltip="Pastes through this. Without it the whole crop is pasted."),
                io.Combo.Input("resolution", options=list(RESOLUTION_MODES),
                               default=RESOLUTION_MODES[0],
                               tooltip="match crop data: originals resized to the size cropped "
                                       "from. match original frames: the crop scales to them. "
                                       "match pasted frames: everything scales so the pasted "
                                       "frames go in at their own size."),
                io.Int.Input("fade_mask", default=0, min=0, max=4096,
                             tooltip="Pixels the mask feathers outward. Masked pixels stay as "
                                     "they are. Needs a mask."),
                io.Int.Input("fade_margin", default=0, min=0, max=4096,
                             tooltip="Pixels the paste fades in from the crop's edges. Applied "
                                     "after fade_mask, so the borders always blend."),
            ],
            outputs=[
                io.Image.Output(id="images", display_name="images"),
                io.Mask.Output(id="mask", display_name="mask",
                               tooltip="Where pasting happened, as blended: the mask in place, "
                                       "or the crop box without one."),
            ],
        )

    @classmethod
    def execute(cls, original_frames, images, crop_data, resolution, fade_mask, fade_margin,
                mask=None) -> io.NodeOutput:
        frames, start, count = crop_data["frames"], crop_data["start"], crop_data["count"]
        source_h, source_w = crop_data["source_size"]
        crop_h, crop_w = crop_data["crop_size"]
        if original_frames.shape[0] != frames:
            raise ValueError(f"The crop came from {frames} frames but {original_frames.shape[0]} "
                             f"original frames are connected.")
        if images.shape[0] != count:
            raise ValueError(f"The crop holds {count} frames but {images.shape[0]} images are "
                             f"connected.")
        if mask is not None:
            if mask.ndim == 2:
                mask = mask[None]
            if mask.shape[0] != count:
                raise ValueError(f"{count} images to paste but {mask.shape[0]} masks.")

        # Scale from crop-data space to the canvas, and the size each paste goes in at.
        if resolution == "match original frames":
            canvas_h, canvas_w = original_frames.shape[1], original_frames.shape[2]
            scale_x, scale_y = canvas_w / source_w, canvas_h / source_h
            paste_w, paste_h = round(crop_w * scale_x), round(crop_h * scale_y)
        elif resolution == "match pasted frames":
            paste_h, paste_w = images.shape[1], images.shape[2]
            scale_x, scale_y = paste_w / crop_w, paste_h / crop_h
            canvas_w, canvas_h = round(source_w * scale_x), round(source_h * scale_y)
        else:
            canvas_h, canvas_w, scale_x, scale_y = source_h, source_w, 1.0, 1.0
            paste_h, paste_w = crop_h, crop_w

        output = _resize_images(original_frames, canvas_h, canvas_w).clone()
        pasted = match_channels(_resize_images(images, paste_h, paste_w).to(output), output.shape[-1])
        if mask is not None:
            mask = resize_mask(mask.to(output.device, output.dtype), paste_h, paste_w)
        out_mask = output.new_zeros((frames, canvas_h, canvas_w))

        for k in range(count):
            i = start + k
            source_x, source_y = crop_data["positions"][i]
            x = min(max(round(source_x * scale_x), 0), canvas_w - paste_w)
            y = min(max(round(source_y * scale_y), 0), canvas_h - paste_h)

            alpha = mask[k] if mask is not None else output.new_ones((paste_h, paste_w))
            if mask is not None:
                alpha = _fade_mask(alpha, fade_mask)
            if fade_margin > 0:
                open_sides = {"left": x > 0, "top": y > 0,
                              "right": x + paste_w < canvas_w, "bottom": y + paste_h < canvas_h}
                alpha = alpha * _margin_ramp(paste_h, paste_w, fade_margin, open_sides, alpha)

            region = output[i, y:y + paste_h, x:x + paste_w]
            # lerp lands exactly on the pasted value at full alpha; a + (b - a) * 1 may not.
            output[i, y:y + paste_h, x:x + paste_w] = torch.lerp(region, pasted[k], alpha[..., None])
            out_mask[i, y:y + paste_h, x:x + paste_w] = alpha

        return io.NodeOutput(output, out_mask)
