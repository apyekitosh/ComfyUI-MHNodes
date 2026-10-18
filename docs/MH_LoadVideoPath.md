# Load Video - Path

Loads frames and audio from a video anywhere on disk, straight to an image batch. For files too big to upload, or that should stay where they are.

## Inputs
- **path**: full path to the video. A path pasted with quotes around it, as Windows' *Copy as path* gives, works as is.
- **start**: first frame to load, counting from 0.
- **frame_cap**: most frames to load. **0** loads to the end.
- **select_every_nth**: keep one frame in every n.

## Outputs
- **images**: the frames.
- **audio**: the audio under those frames, cut to the same span. Nothing if the file has no audio.
- **fps**: the frame rate of what was loaded: the file's, divided by n.
- **frame_count**: how many frames came out.

## Preview

The same as *Load Video - Input*: only the frames that will load, looping, updated instantly with no re-encoding.

ProRes and other formats a browser can't play get a small H.264 **preview copy**, made once per file version and kept in temp until the next restart. Making it means decoding the whole file once, so a long ProRes can take a little while the first time; *preparing preview…* shows meanwhile. Loading frames never waits for it.

## Serving the file

A file the browser *can* play is streamed to the preview straight from where it is. The route that does this only serves video files, so it can't be used to read anything else off the disk.

## Notes
- Only the frames asked for are decoded: it seeks to the start and stops at the cap.
- The file is re-read when it changes on disk, even at the same path.
