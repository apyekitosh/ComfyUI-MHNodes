"""Image file I/O nodes."""

from __future__ import annotations

from pathlib import Path

from comfy_api.latest import io

from .utils import save_image_to_path


class SaveImageSequence(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MHNodes_SaveImageSequence",
            display_name="Save Image Sequence",
            category="MHNodes/image",
            description=(
                "Saves an image batch to an arbitrary filesystem path. A single image is written "
                "to the path as given; a batch is written as <stem>-0, <stem>-1, ... Missing "
                "parent directories are created. PNG output embeds the workflow metadata."
            ),
            inputs=[
                io.Image.Input("image", tooltip="Image or image batch to save."),
                io.String.Input(
                    "path",
                    default="./image.png",
                    tooltip=(
                        "Output file path. Relative paths resolve against the ComfyUI working "
                        "directory. Batches get a -<index> suffix before the extension."
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
    def execute(cls, image, path: str, overwrite: bool) -> io.NodeOutput:
        base_path = Path(path)
        batch_size = image.shape[0]

        if batch_size == 1:
            targets = [(image[0], base_path)]
        else:
            targets = [
                (frame, base_path.with_stem(f"{base_path.stem}-{i}"))
                for i, frame in enumerate(image)
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
