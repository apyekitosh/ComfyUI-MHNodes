# Image/Mask from Tail

Takes a run of frames off the **end** of an image and/or mask batch.

## Inputs
- **image** *(optional)*: image batch to slice.
- **mask** *(optional)*: mask batch to slice. At least one of image/mask must be connected.
- **skip**: frames to drop off the end first. **0** ends on the last frame, **1** ends one before it.
- **length**: how many frames to take, counting backwards. **-1** (the default) runs to the start of the batch.
- **reverse**: return the frames back to front. Off by default.

## Outputs
- **image** / **mask**: the slice, or nothing for an input that wasn't connected.
- **length**: how many frames actually came back.

## How the window is worked out

The window runs from `total - skip - length` up to `total - skip - 1`, inclusive — so with a
20-frame batch, `skip 1, length 5` gives indices **14 to 18**. Index 19 is the last frame, `skip 1`
drops it, and the five frames before it are what you get.

`skip` is just `start` renamed, because counting from the end makes "start" read like the wrong
end of the batch. **0 is the last frame**, not the first.

## Order

Off by default, **reverse** leaves the order alone: counting from the end picks *which* frames,
not what order they arrive in, so the end frame is still the end frame. Turn it on and both the
image and the mask are flipped together, so what was the last frame becomes the first.

## Asking for more than exists

You get what's there. Nothing is padded, repeated or looped — a 10-frame batch with
`skip 2, length 20` returns **8** frames, from index 0 to 7. The **length** output reports the
real count so whatever comes next can adapt.

`skip` at or past the batch size is an error rather than an empty batch, for the same reason
overrunning `start` is in *Image/Mask from Batch*: zero frames breaks everything downstream.

## Image and mask together

- **More images than masks**: the last mask repeats to fill.
- **More masks than images**: the excess is dropped.

Counts are matched **from the start**, not from the end — the same as *Image/Mask from Batch*.
With 10 images and 15 masks, masks 0–9 are kept, and then both are sliced identically. Matching
from the end instead would keep masks 5–14 and pair image 0 with mask 5, so the two nodes would
disagree about which mask belongs to which image.

## Resolution

Untouched. Only the batch dimension is sliced, so the image and the mask keep their own sizes.

## Notes
- Unreversed, the outputs are views onto the input tensors and no pixel data is copied.
  `reverse` has to materialise a copy.
- A `length` of 0 is an error; use -1 for "to the start".
