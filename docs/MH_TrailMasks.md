# Trail Masks

Leaves a motion trail across a mask batch. Each output frame is the **maximum** of its own mask and the frames just before it, so a moving shape smears backwards through time.

## Inputs
- **masks**: the mask batch to trail.
- **trail_count**: how many frames each output covers, *including the current one*. `1` leaves the batch unchanged.
- **fade**: scale older frames down so the trail falls off instead of being uniformly solid.

## Outputs
- **masks**: the trailed batch, same length, resolution and dtype as the input.

## How the window works

`trail_count` is the window size. At `trail_count = 3`:

| output frame | merges |
| --- | --- |
| 1 | 1 |
| 2 | 1, 2 |
| 3 | 1, 2, 3 |
| 4 | 2, 3, 4 |
| 5 | 3, 4, 5 |

The first frames simply have fewer frames available, so the window is shorter there.

## Fading

With **fade** on, a frame `n` steps back is multiplied by `(trail_count - n) / trail_count` before the maximum. At `trail_count = 3`, output frame 4 is:

- `3/3` of mask 4 (the current frame, always full strength)
- `2/3` of mask 3
- `1/3` of mask 2

The weight depends only on a frame's **age**, not on how much of the window is available — which is why frame 1 comes out unchanged rather than dimmed.

## Notes
- Frames are combined with a per-pixel maximum, not a sum, so overlapping masks never exceed the brightest contributor. Values are left as they are, with no clamping.
- `trail_count` larger than the batch is fine: every frame just reaches back as far as it can.
