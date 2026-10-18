# Load Video - Input

Loads frames and audio from a video in the input folder, straight to an image batch. No *Create Video* or *Get Video Components* step.

## Inputs
- **video**: a video in the input folder. Upload with **choose video to upload**, or drop a file on the node.
- **start**: first frame to load, counting from 0.
- **frame_cap**: most frames to load. **0** loads to the end.
- **select_every_nth**: keep one frame in every n.

## Outputs
- **images**: the frames.
- **audio**: the audio under those frames, cut to the same span. Nothing if the file has no audio.
- **fps**: the frame rate of what was loaded: the file's, divided by n. Feed it to *Video Preview*.
- **frame_count**: how many frames came out.

## Preview

Plays **only the frames that will load**, looping, with the range in the corner. Changing start, frame_cap or select_every_nth updates it instantly and costs nothing: the browser plays the file itself and only the loop points move. Nothing is re-encoded.

- **select_every_nth** plays the range n times faster. It shows the effect on motion; the exact frames dropped can't be shown without re-encoding.
- Files a browser can't play (ProRes, 10-bit or 4:2:2 H.264, HEVC, AVI...) get a small H.264 **preview copy**, made once per file and kept in temp until the next restart. Its frames line up one-to-one with the file's.
- The preview is muted, and doesn't take the mouse: dragging and zooming over it move the canvas.

## Uploads

Uploads go through core's own upload, into the input folder. The server's upload limit applies (100 MB unless ComfyUI was started with `--max-upload-size`). For anything bigger, use **Load Video - Path**, which reads the file where it is.

## Notes
- Only the frames asked for are decoded: it seeks to the start and stops at the cap rather than reading the whole file.
- Frames are 8-bit RGB. Memory is the usual for an image batch: about 25 MB per 1080p frame, 100 MB per 4K frame.
