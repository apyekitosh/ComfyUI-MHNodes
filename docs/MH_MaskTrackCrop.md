# Mask Track Crop

Cuts a fixed-size window that follows an animated mask, so a model gets the same resolution on every frame and only ever sees the region that matters. *Mask Track Stitch* puts the result back.

## Inputs
- **images** / **mask**: must match exactly, in frame count and in size. A mismatch is an error, since it means something upstream went wrong.
- **multiplier**: scales the window around the largest box. Below 1 the mask can fall outside the window.
- **multiple_of**: the window's width and height are rounded **up** to a multiple of this.
- **aspect_width** / **aspect_height**: force the window's shape. Only the ratio matters: 16 and 9 is the same as 1920 and 1080. **0** in either leaves it free.
- **smoothing**: how much the window's path is smoothed, in frames. **0** follows the mask exactly.
- **gap_fill**: what empty frames *inside* the mask's run get. See below.
- **drop_empty_ends**: leave out the empty frames before the mask starts and after it ends.

## Outputs
- **images** / **mask**: the cropped frames, all the same size.
- **crop_data**: the window's size and position on every frame, for *Mask Track Stitch*.

## How it works

1. **Find the run.** A mask pixel counts if it's above 0.1. Frames before the first non-empty mask are the *head*, frames after the last are the *tail*.
2. **Box every frame** of the run. Empty frames inside it get a box interpolated from the masked frames either side, as if the mask had animated through the gap.
3. **Size the window** from the largest box: the largest width and the largest height, taken separately (a 2×100 box on one frame and a 120×3 box on another give 120×100). Then × **multiplier**, then shaped to the aspect, then rounded up to **multiple_of**.
4. **Move it.** The window follows the centre of each box, smoothed over time, and stays inside the image.
5. **Cut** every frame.

### Aspect ratio

The box's longest side becomes the ratio's **short** side, so the mask fits whichever way round it is. A 90×160 box at 4:3 with multiple_of 2 gives **214×160**; use 3:4 for portrait.

### Gap fill

- **none**: the box still interpolates, the mask stays empty.
- **blend**: both neighbouring masks are moved and scaled into the frame's box and cross-faded by distance. Pixels they share stay full; the rest fade. Keeps soft edges, and shows both shapes at once.
- **morph**: the neighbours' *signed distance fields* (how far each pixel is inside or outside the shape) are blended instead, then thresholded. One solid shape turns into the other, with no ghosting. The result is a hard-edged mask.

### Smoothing

A Gaussian over time, **centred**: each frame looks both ways, so the window doesn't lag behind fast movement the way a live tracker's would. It can't cost you the subject: wherever the mask's box fits in the window, the path is held so the box stays inside, and the correction is spread along the path rather than snapping a single frame.

A **multiplier** a little above 1 gives the window room to move, so smoothing has more freedom. At exactly 1 the widest frame pins the window in place.

### Edges

The window is always **clamped inside the image**. Near an edge it shifts, so the subject is off-centre there, but every pixel is real. A window bigger than the image is an error.

### Empty ends

Kept (the default), head frames sit at the **first** position and tail frames at the **last**, with an empty mask. Dropped, the batch starts at the first masked frame; *crop_data* records where, so stitching still lines up.

## Notes
- A mask that's empty on every frame is an error.
- Non-gap frames keep the mask's own values; only gap frames are generated.
