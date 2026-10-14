# Video Preview

Plays an image batch as a video, with optional audio. No *Create Video* step needed.

## Inputs
- **images**: frames to preview.
- **audio** *(optional)*: soundtrack to play with them.
- **fps**: frames per second. 24 by default.

## Outputs
- **images** / **audio**: the inputs, passed straight through, so the node can sit in the middle of a graph.

## Notes
- Always H.264 in MP4, written to the **temp** folder, which ComfyUI clears on restart. Nothing accumulates in output.
- Encoding uses core's own video pipeline (the one *Save Video* uses), and the player is core's own video preview, so there is no custom widget code involved.
- H.264 can't encode odd dimensions, so an odd-sized batch gets one row or column repeated **in the preview only**. The images passed through are untouched.
- The workflow is embedded the way core's *Save Video* does it. Off under `--disable-metadata`.
