# Blockify Mask to H3 Grid

Snaps a mask onto MiniMax H3's latent grid, in space and in time. Meant for moving masks that "bleed", leaving a visible trace of where the mask was: lining every masked region up with what the model actually sees is what stops it.

## Inputs
- **mask**: the mask to snap.
- **binarize_threshold**: pixels at or above this become white, below it black. 0.5 by default.
- **cell_threshold**: white pixels a 32×32 cell needs to fill; fewer and the whole cell empties. 4 by default. Only used with spatial blocking.
- **spatial_blocking**: fill or empty whole 32×32 cells. On by default.
- **temporal_blocking**: merge each group of 4 frames in H3's reels. On by default.

## Outputs
- **mask**: the snapped mask.

## What it does

Always:

1. **Trim** to the largest 17n + 5 frame count: 23–38 frames become 22, 40–55 become 39, and so on. Fewer than 5 is an error.
2. **Resize** each side down to a multiple of 32: 1000×563 becomes 992×544. Scaled, not cropped.
3. **Binarise** at **binarize_threshold**.

Then, each switchable:

4. **Spatial blocking.** H3 sees the picture in 32×32 cells (16× VAE compression, then 2×2 patches). Every cell becomes all white or all black, by **cell_threshold**.
5. **Temporal blocking.** H3 packs each 17-frame reel as **[1][4][4][4][4]**. The single frame opening each reel (frames 1, 18, 35... counting from 1) is left as it is; in each group of 4 (2–5, 6–9, 10–13, 14–17, 19–22...) a cell that's white on any frame becomes white on all four.

With spatial blocking off and temporal on, the merge happens **per pixel** rather than per cell, so the time rule can be tested on its own.

## Finding what you need

Everything on is the strictest version. To find which part a case actually needs, switch one off at a time:

| spatial | temporal | Result |
| --- | --- | --- |
| on | on | blocky cells, merged over each group of 4 |
| on | off | blocky cells, every frame its own |
| off | on | pixel-accurate edges, merged over each group of 4 |
| off | off | just trimmed, resized and binarised |

## Notes
- The video has to get the **same** resize and trim, or mask and frames won't line up: scaled to the same multiple-of-32 size, and trimmed to the same 17n + 5 length.
- If you used the standalone `blockify_mask_to_grid.py` while testing, delete it from `custom_nodes`: both register the same node.
