"""Mask batch operations."""

from __future__ import annotations

import torch
from comfy_api.latest import io

from .utils import MAX_RESOLUTION


class TrailMasks(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_TrailMasks",
            display_name="Trail Masks",
            category="MHNodes/mask",
            description=(
                "Leaves a motion trail across a mask batch. Each output frame is the maximum of "
                "its own mask and the trail_count-1 frames before it, so a moving shape smears "
                "backwards through time. With fade on, older frames contribute progressively "
                "less: at trail_count 3 a frame is its own mask, 2/3 of the previous one and 1/3 "
                "of the one before that."
            ),
            inputs=[
                io.Mask.Input("masks", tooltip="The mask batch to trail."),
                io.Int.Input(
                    "trail_count",
                    default=3,
                    min=1,
                    max=1000,
                    step=1,
                    tooltip=(
                        "How many frames each output covers, including the current one. 1 leaves "
                        "the batch unchanged; 3 merges each frame with the two before it."
                    ),
                ),
                io.Boolean.Input(
                    "fade",
                    default=False,
                    tooltip=(
                        "Scale older frames down so the trail falls off. A frame n steps back is "
                        "multiplied by (trail_count - n) / trail_count."
                    ),
                ),
            ],
            outputs=[io.Mask.Output(id="masks", display_name="masks")],
        )

    @classmethod
    def execute(cls, masks, trail_count: int, fade: bool) -> io.NodeOutput:
        # The current frame always contributes at full strength, so start from a copy.
        trailed = masks.clone()

        # Each step back in time is one shifted maximum against the whole batch at once.
        for age in range(1, min(trail_count, masks.shape[0])):
            weight = (trail_count - age) / trail_count if fade else 1.0
            previous = masks[:-age] * weight
            trailed[age:] = torch.maximum(trailed[age:], previous)

        return io.NodeOutput(trailed)


class EmptyMask(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_EmptyMask",
            display_name="Empty Mask",
            category="MHNodes/mask",
            description=(
                "Creates a mask filled with one value, like Create Solid Mask, but with a "
                "batch size so it can match a video without a separate repeat node."
            ),
            search_aliases=["solid mask", "create solid mask", "blank mask"],
            inputs=[
                io.Float.Input("value", default=1.0, min=0.0, max=1.0, step=0.01,
                               tooltip="Fill value. 0 is fully black, 1 fully white."),
                io.Int.Input("width", default=512, min=1, max=MAX_RESOLUTION, step=1),
                io.Int.Input("height", default=512, min=1, max=MAX_RESOLUTION, step=1),
                io.Int.Input("batch_size", default=1, min=1, max=4096, step=1,
                             tooltip="How many identical masks to return."),
            ],
            outputs=[io.Mask.Output(id="mask", display_name="mask")],
        )

    @classmethod
    def execute(cls, value, width, height, batch_size) -> io.NodeOutput:
        import comfy.model_management

        return io.NodeOutput(torch.full(
            (batch_size, height, width), value,
            dtype=torch.float32, device=comfy.model_management.intermediate_device(),
        ))
