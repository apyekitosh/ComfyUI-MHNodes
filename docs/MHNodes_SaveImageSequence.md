# Save Image Sequence

Saves an image batch to an arbitrary filesystem path, outside of ComfyUI's `output` directory.

## Inputs
- **image**: image or image batch to save.
- **path**: output file path. Relative paths resolve against the ComfyUI working directory. Missing parent directories are created.
- **overwrite**: when off, files that already exist are skipped instead of being replaced.

## Outputs
- **paths**: newline-separated list of the files actually written (empty if everything was skipped).

## Notes
- A batch of one is written to `path` as given. A larger batch is written as `<stem>-0.png`, `<stem>-1.png`, ... with the index inserted before the extension.
- `.png` output embeds the prompt and workflow metadata. Other extensions are saved through PIL without metadata; RGBA is flattened to RGB for JPEG.
