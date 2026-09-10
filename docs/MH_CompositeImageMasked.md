# Composite Image Masked

Pastes a foreground image onto a background at an x/y offset, with two independent masks controlling the blend. A cleaner alternative to Comfy's **ImageCompositeMasked**.

## Inputs
- **background**: the canvas. Sets the output resolution and batch size.
- **foreground**: the image pasted onto the canvas.
- **x** / **y**: offset of the foreground's top-left corner, in canvas pixels. **May be negative.**
- **background_mask** *(optional)*: stretched to the background's resolution and **fixed in canvas space**. Marks where on the canvas the foreground is allowed to show. Does not move with the offset.
- **foreground_mask** *(optional)*: stretched to the foreground's resolution and pasted at the same offset as the foreground — as if its alpha had been applied before compositing. **Moves with the offset.**

## Outputs
- **image**: the composited result, at the background's resolution.
- **mask**: the blend actually applied, in canvas space — the two masks multiplied together, with the foreground mask already moved into position. Zero everywhere the foreground does not land.

## The two masks

This is the whole point of the node. Both masks end up multiplied together, but they are positioned differently:

| | Resized to | Position |
| --- | --- | --- |
| `background_mask` | background resolution | fixed on the canvas — moving the foreground changes which part of it applies |
| `foreground_mask` | foreground resolution | travels with the foreground |

So `background_mask` answers *"where on the canvas may anything be drawn?"* and `foreground_mask` answers *"which parts of this image are opaque?"*

## Differences from ImageCompositeMasked

- **Two masks instead of one**, with the distinct positioning above. The original stretches its single mask to the *source* size — so it matches the foreground — but then samples it from the canvas top-left, so it does not follow the offset. That is the behaviour this node replaces.
- **Negative offsets work.** The original clamps `x` and `y` to `min=0` at the widget.
- **No `resize_source`.** The foreground is never rescaled; it is pasted at its own size and anything past the canvas edge is cropped.
- Outputs the resulting mask as well as the image.

## Overflow and batching

- The foreground may be larger than the canvas, and may be placed partly or fully outside it. Off-canvas pixels are cropped. If nothing lands on the canvas, the background is returned unchanged with an empty mask.
- The background sets the batch size. A shorter foreground batch repeats its last frame; a longer one is trimmed. Each mask is matched to its own image the same way.
- If the two images have different channel counts, the output keeps the background's. A foreground short of channels is padded with opaque alpha.
- Masks are clamped to 0–1 before blending.
