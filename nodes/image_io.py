"""Image file I/O nodes."""

from __future__ import annotations

from pathlib import Path

from comfy_api.latest import io

from .utils import FILETYPES, save_image_to_path


class SaveImageSequence(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_SaveImageSequence",
            display_name="Save Image Sequence",
            category="MHNodes/image",
            description=(
                "Saves an image batch to an arbitrary filesystem path as <stem>-0, <stem>-1, ... "
                "counting up from start_index, zero-padded to index_padding digits. Every image "
                "gets an index, including a batch of one, so incremental renders keep a "
                "consistent sequence. The extension comes from the filetype widget, and missing "
                "parent directories are created. PNG output embeds the workflow metadata."
            ),
            inputs=[
                io.Image.Input("image", tooltip="Image or image batch to save."),
                io.String.Input(
                    "path",
                    default="./image",
                    tooltip=(
                        "Output file path, without extension. Relative paths resolve against the "
                        "ComfyUI working directory. Any extension typed here is replaced by the "
                        "filetype widget."
                    ),
                ),
                io.Combo.Input(
                    "filetype",
                    options=list(FILETYPES),
                    default="png",
                    tooltip="Output format. Only png embeds the prompt and workflow metadata.",
                ),
                io.Int.Input(
                    "start_index",
                    default=0,
                    min=0,
                    max=999999,
                    step=1,
                    tooltip=(
                        "Index given to the first image of the batch. Raise it between runs to "
                        "append to an existing sequence instead of overwriting it."
                    ),
                ),
                io.Int.Input(
                    "index_padding",
                    default=5,
                    min=0,
                    max=12,
                    step=1,
                    tooltip=(
                        "Zero-padding width for the index suffix every image gets, e.g. 5 gives "
                        "image-00000. Set to 0 for an unpadded index."
                    ),
                ),
                io.Boolean.Input(
                    "overwrite",
                    default=True,
                    tooltip="When off, existing files are left untouched and skipped.",
                ),
            ],
            outputs=[
                io.String.Output(
                    display_name="paths",
                    tooltip="Newline-separated list of the files actually written.",
                ),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, image, path: str, filetype: str, start_index: int, index_padding: int,
                overwrite: bool):
        base_path = Path(path)
        if not base_path.name:
            raise ValueError(f"path must include a filename, got {path!r}")

        # The filetype widget owns the extension; drop whatever was typed into the path.
        if base_path.suffix.lower().lstrip(".") in FILETYPES:
            base_path = base_path.with_suffix("")
        base_path = base_path.with_name(f"{base_path.name}.{filetype}")

        targets = [
            (frame, base_path.with_stem(f"{base_path.stem}-{i:0{index_padding}d}"))
            for i, frame in enumerate(image, start=start_index)
        ]

        written: list[str] = []
        for frame, target in targets:
            if not overwrite and target.exists():
                continue
            save_image_to_path(
                frame,
                target,
                prompt=cls.hidden.prompt,
                extra_pnginfo=cls.hidden.extra_pnginfo,
            )
            written.append(str(target))

        return io.NodeOutput("\n".join(written))
