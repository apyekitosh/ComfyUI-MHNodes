# Mask Track Stitch

Pastes frames cropped by *Mask Track Crop* back into the original frames, after whatever processing they went through.

## Inputs
- **original_frames**: the frames to paste into. Wired separately so you can paste onto a version that changed along the way: upscaled, graded, anything.
- **images**: the cropped frames, processed.
- **crop_data**: from *Mask Track Crop*.
- **mask** *(optional)*: pastes through this. Without it, the whole crop is pasted.
- **resolution**: what wins when sizes disagree. See below.
- **fade_mask**: pixels the mask feathers **outward**. Masked pixels stay exactly as they are; the falloff runs into the unmasked ones. Does nothing without a mask.
- **fade_margin**: pixels the paste fades in from the crop's edges. Applied **after** fade_mask, so the borders always blend, masked pixels included.

## Outputs
- **images**: the originals with the crops pasted in. Always the full original length: frames the crop dropped pass through untouched.
- **mask**: where pasting happened, exactly as blended. With a mask, it's that mask put back in place; without one, the crop box itself, an animated rectangle. Fades are included.

## Resolution

| Mode | Output size | What's resized |
| --- | --- | --- |
| **match crop data** | the size cropped from | original frames, if they differ; pasted frames to the crop's size |
| **match original frames** | the original frames' | the crop's position and size scale to them; pasted frames follow |
| **match pasted frames** | scaled so the pasted frames fit at their own size | original frames and the crop's position scale up or down; pasted frames are untouched |

**match pasted frames** is for keeping processed detail: crop at 304×640, upscale the crop 2×, and the whole output comes out 2× with the crop pasted pixel for pixel.

Whatever doesn't match is stretched to fit, so a crop that was resized to suit a model's grid still lands exactly where it came from.

## Fades

```
fade_mask:    mask ████▓▒░            (masked pixels untouched, falloff outward)
fade_margin:  crop edge ░▒▓████       (fades in from the border, over everything)
```

**fade_margin** leaves a side hard where the crop sits on the image's edge: there's nothing beyond it to blend into.

## Errors
Frame counts must match: the original frames against what the crop came from, the pasted frames against what it holds, and a mask against the pasted frames.
