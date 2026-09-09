# Crop Image and Mask

Crops an image and/or a mask to a fixed size, positioned by alignment plus an offset. Behaves like **Image Crop** from `comfyui_essentials`, with the differences noted below.

## Inputs
- **image** *(optional)*: image or image batch to crop.
- **mask** *(optional)*: mask or mask batch to crop. At least one of image/mask must be connected.
- **width** / **height**: crop size, before rounding down to a multiple of **multiplier**.
- **alignment**: where the crop sits before the offset — `top-left`, `top-center`, `top-right`, `right-center`, `bottom-right`, `bottom-center`, `bottom-left`, `left-center`, `center`.
- **x_offset** / **y_offset**: nudge from the alignment, in pixels. Clamped so the crop stays in bounds.
- **multiplier**: crop size is rounded *down* to a multiple of this before any calculation. Default `2`; set to `1` to disable.

## Outputs
- **image**: the cropped image, or nothing when no image was connected.
- **mask**: the cropped mask, or nothing when no mask was connected.
- **x** / **y**: top-left corner of the crop in source pixels, i.e. where to paste the result back so it lands in the same place. `0,0` is the top-left of the source.

## Differences from `comfyui_essentials` Image Crop

- Takes a mask as well as an image, and both are optional.
- Width and height step by 1, not 8.
- **The output is always exactly the requested size.** Essentials shrinks the crop when the offset pushes it out of bounds; this node clamps the offset instead. Cropping a 256×256 image to 64×64 with `x_offset = 1000` returns a full 64×64 crop at `x = 192`, the furthest right it fits. (Essentials could also return a crop *larger* than requested on negative offsets, from negative-index slicing — that cannot happen here.)
- Crop size is rounded down to a multiple of **multiplier** first.
- A crop larger than the source in either dimension raises an error rather than silently shrinking.

## Image and mask mismatches

When both are connected, the mask is conformed to the image before cropping:

- **Resolution**: the mask is stretched to the image's width and height, ignoring aspect ratio.
- **More images than masks**: the last mask repeats to fill the batch.
- **More masks than images**: the mask batch is trimmed.

With only a mask connected, the crop is computed against the mask's own dimensions.
