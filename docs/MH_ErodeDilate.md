# Erode / Dilate (RGB)

Greyscale morphology applied per channel.

## Inputs
- **image**: image or image batch to process.
- **operation**: `dilate`, `erode`, `open` or `close`.
- **radius**: kernel radius in pixels; the structuring element is `2 * radius + 1` across. `0` passes the image through unchanged.
- **iterations**: how many times to repeat the operation.
- **shape**: structuring element — `ellipse`, `rect` or `cross`.

## Outputs
- **image**: the processed image, same shape as the input.

## What the operations do

- **dilate** takes the local maximum, so bright areas grow.
- **erode** takes the local minimum, so dark areas grow.
- **open** (erode then dilate) drops isolated specks without moving the big edges.
- **close** (dilate then erode) seals pinholes without growing the outline.

Against a black background, dilate bleeds surrounding content into holes and erode eats content away from their edges.

## Notes
- Per-channel maxima can tint a boundary between two saturated colours — red beside blue reads magenta for a pixel or two. Against black it is harmless, since any real colour already beats 0.
- Works in full float precision. Values are only ever selected, never averaged, so nothing is quantized.
- Pure torch, no OpenCV. Output is bit-identical to `cv2.dilate` / `cv2.erode` / `cv2.morphologyEx` with the matching `getStructuringElement`, for all three shapes.
- Cost grows with the radius. On a 1024x1024 image: radius 3 is ~0.04s, radius 32 ~0.4s, radius 256 ~2-3s.
