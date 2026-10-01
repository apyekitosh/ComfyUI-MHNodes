"""Mask batch operations."""

from __future__ import annotations

import torch
from comfy_api.latest import io


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
