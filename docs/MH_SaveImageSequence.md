# Save Image Sequence

Saves an image batch to an arbitrary filesystem path, outside of ComfyUI's `output` directory.

## Inputs
- **image**: image or image batch to save.
- **path**: output file path stem, *without* extension or index. Relative paths resolve against the ComfyUI working directory. Missing parent directories are created. If you do type a known extension here it is stripped and replaced by the **filetype** widget.
- **filetype**: output format — `png`, `jpg`, `jpeg`, `webp`, `tiff` or `bmp`.
- **start_index**: index given to the first image of the batch. Raise it between runs to append to an existing sequence instead of overwriting it.
- **index_padding**: zero-padding width for the index suffix. `5` gives `image-00000.png`; `0` gives `image-0.png`.
- **overwrite**: when off, files that already exist are skipped instead of being replaced.

## Outputs
- **paths**: newline-separated list of the files actually written (empty if everything was skipped).

## Notes
- Every image gets a `-<index>` suffix inserted before the extension, including a batch of one — so a 1-frame render and a 30-frame render produce consistently named files.
- The index is `start_index` plus the position within the batch. With `start_index` left at 0 every run overwrites the same files; raise it by the previous batch size to continue a sequence across runs.
- Only `png` embeds the prompt and workflow metadata. The other formats are saved through PIL without it.
- RGBA input is flattened to RGB for `jpg`, `jpeg` and `bmp`, which cannot carry an alpha channel.
