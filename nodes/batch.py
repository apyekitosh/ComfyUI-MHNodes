"""Batch slicing."""

from __future__ import annotations

from comfy_api.latest import io

from .utils import match_batch_size


class ImageMaskFromBatch(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_ImageMaskFromBatch",
            display_name="Image/Mask from Batch",
            category="MHNodes/batch",
            description=(
                "Takes a run of frames out of an image and/or mask batch. Asking for more than "
                "is there returns what exists rather than padding or repeating, so the length "
                "output tells you how many frames you actually got.\n\n"
                "Only the batch dimension is touched, so the image and the mask keep their own "
                "resolutions."
            ),
            inputs=[
                io.Image.Input("image", optional=True, tooltip="Image batch to slice."),
                io.Mask.Input("mask", optional=True, tooltip="Mask batch to slice."),
                io.Int.Input("start", default=0, min=0, max=0xFFFFFFFF, step=1,
                             tooltip="First frame to take, counting from 0."),
                io.Int.Input(
                    "length", default=-1, min=-1, max=0xFFFFFFFF, step=1,
                    tooltip="How many frames to take. -1 runs to the end of the batch.",
                ),
            ],
            outputs=[
                io.Image.Output(id="image", display_name="image"),
                io.Mask.Output(id="mask", display_name="mask"),
                io.Int.Output(id="length", display_name="length",
                              tooltip="Frames actually returned, which can be fewer than asked."),
            ],
        )

    @classmethod
    def execute(cls, start, length, image=None, mask=None) -> io.NodeOutput:
        if image is None and mask is None:
            raise ValueError("Image/Mask from Batch needs an image, a mask, or both.")
        if length == 0:
            raise ValueError("A length of 0 returns nothing. Use -1 to run to the end.")

        # Counts are matched before slicing, not after: the mask is aligned with the image
        # frame for frame, so trimming a short mask to the slice first would leave the two
        # out of step. Resolution is deliberately untouched.
        if image is not None and mask is not None:
            mask = match_batch_size(mask, image.shape[0])

        total = image.shape[0] if image is not None else mask.shape[0]
        if start >= total:
            raise ValueError(
                f"start {start} is past the end of a {total}-frame batch, so there is nothing "
                f"to return."
            )

        stop = total if length < 0 else min(start + length, total)

        return io.NodeOutput(
            image[start:stop] if image is not None else None,
            mask[start:stop] if mask is not None else None,
            stop - start,
        )


class ImageMaskFromTail(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_ImageMaskFromTail",
            display_name="Image/Mask from Tail",
            category="MHNodes/batch",
            description=(
                "Takes a run of frames off the end of an image and/or mask batch. The window is "
                "counted backwards from the last frame, but comes back in the original order "
                "unless you reverse it.\n\n"
                "Asking for more than is there returns what exists rather than padding, so the "
                "length output tells you how many frames you actually got.\n\n"
                "Only the batch dimension is touched, so the image and the mask keep their own "
                "resolutions."
            ),
            inputs=[
                io.Image.Input("image", optional=True, tooltip="Image batch to slice."),
                io.Mask.Input("mask", optional=True, tooltip="Mask batch to slice."),
                io.Int.Input("skip", default=0, min=0, max=0xFFFFFFFF, step=1,
                             tooltip="Frames to drop off the end first. 0 ends on the last "
                                     "frame, 1 ends one before it."),
                io.Int.Input(
                    "length", default=-1, min=-1, max=0xFFFFFFFF, step=1,
                    tooltip="How many frames to take, counting backwards. -1 runs to the "
                            "start of the batch.",
                ),
                io.Boolean.Input(
                    "reverse", default=False,
                    tooltip="Return the frames back to front, so the last frame becomes the "
                            "first. Off, the original order is kept.",
                ),
            ],
            outputs=[
                io.Image.Output(id="image", display_name="image"),
                io.Mask.Output(id="mask", display_name="mask"),
                io.Int.Output(id="length", display_name="length",
                              tooltip="Frames actually returned, which can be fewer than asked."),
            ],
        )

    @classmethod
    def execute(cls, skip, length, reverse, image=None, mask=None) -> io.NodeOutput:
        if image is None and mask is None:
            raise ValueError("Image/Mask from Tail needs an image, a mask, or both.")
        if length == 0:
            raise ValueError("A length of 0 returns nothing. Use -1 to run to the start.")

        # Matched from the start, exactly as the forward node does, so that the two nodes
        # disagree about which end they count from but never about which mask belongs to
        # which image. Trimming a long mask from the end instead would pair image[i] with
        # a different mask[i].
        if image is not None and mask is not None:
            mask = match_batch_size(mask, image.shape[0])

        total = image.shape[0] if image is not None else mask.shape[0]
        if skip >= total:
            raise ValueError(
                f"skip {skip} is past the start of a {total}-frame batch, so there is nothing "
                f"to return."
            )

        stop = total - skip
        start = 0 if length < 0 else max(0, stop - length)

        image = image[start:stop] if image is not None else None
        mask = mask[start:stop] if mask is not None else None

        if reverse:
            # flip() rather than a negative stride, which torch does not accept.
            if image is not None:
                image = image.flip(0)
            if mask is not None:
                mask = mask.flip(0)

        return io.NodeOutput(image, mask, stop - start)
