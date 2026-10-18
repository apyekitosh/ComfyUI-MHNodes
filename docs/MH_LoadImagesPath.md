# Load Images - Path

Loads an image sequence from a folder, straight to an image batch.

## Inputs
- **path**: the folder. A path pasted with quotes around it works as is.
- **start**: first image to load, counting from 0.
- **frame_cap**: most images to load. **0** loads to the end.
- **select_every_nth**: keep one image in every n.
- **fps**: the rate the sequence plays at. Images carry none of their own, so this drives the preview and the **fps** output. 24 by default.

## Outputs
- **images**: the frames.
- **fps**: the fps above, divided by n.
- **frame_count**: how many frames came out.

## Order

By name, in **natural** order: `frame2` comes before `frame10`, as a person would sort them. Zero-padded names sort the same either way. Only `png`, `jpg`/`jpeg`, `webp`, `bmp` and `tif`/`tiff` files directly in the folder are read; anything else in it is ignored.

## Preview

Plays only the frames that will load, looping, like the video loaders. The folder is turned into a small H.264 preview copy **once**, at a fixed rate, and kept in temp until the next restart:

- **fps** and **select_every_nth** only change how fast that copy plays, so neither rebuilds it.
- Adding, removing or rewriting an image does make a new copy, so the preview always shows what's in the folder.
- A big folder takes a moment the first time; *preparing preview…* shows meanwhile.

## Sizes that don't match

A sequence folder shouldn't mix sizes, so this is a safeguard rather than a feature: any image that doesn't match the **first one loaded** is fitted to it, filling the frame and cropping the overflow so it is never stretched. A warning in the console names the images that were changed.

## Notes
- Images are picked before anything is opened, so skipped frames are never read.
- 16-bit images are scaled to 8-bit, not clipped. Alpha is dropped. EXIF rotation is applied.
- The node re-reads the folder when its contents change.
