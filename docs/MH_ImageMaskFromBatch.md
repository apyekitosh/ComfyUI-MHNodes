# Image/Mask from Batch

Takes a run of frames out of an image and/or mask batch.

## Inputs
- **image** *(optional)*: image batch to slice.
- **mask** *(optional)*: mask batch to slice. At least one of image/mask must be connected.
- **start**: first frame to take, counting from 0.
- **length**: how many frames to take. **-1** (the default) runs to the end of the batch.

## Outputs
- **image** / **mask**: the slice, or nothing for an input that wasn't connected.
- **length**: how many frames actually came back.

## Asking for more than exists

You get what's there. Nothing is padded, repeated or looped — a 10-frame batch with `start 5, length 10` returns **5** frames. That's what the **length** output is for: it reports the real count, so whatever comes next can adapt.

`start` at or past the end of the batch is an error rather than an empty batch, since zero frames breaks everything downstream and would be a confusing way to find out you'd overrun.

## Image and mask together

- **More images than masks**: the last mask repeats to fill.
- **More masks than images**: the excess is dropped.

Counts are matched **before** the slice, not after, because the mask is aligned with the image frame for frame. Slicing first would pull the two out of step — a 10-image / 3-mask pair sliced at `start 5` would ask for `mask[5:3]`, which is empty.

## Resolution

Untouched. Only the batch dimension is sliced, so the image and the mask keep their own sizes — a 128×64 image and a 32×200 mask come back at those sizes. Nothing is resized.

## Notes
- The outputs are views onto the input tensors, so slicing copies no pixel data.
- A `length` of 0 is an error; use -1 for "to the end".
