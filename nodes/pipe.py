"""Bundle several connections into one link, and unpack them again.

Useful for carrying a group of unrelated values through a switch or a reroute as a single unit,
rather than running five parallel wires alongside each other.

The two nodes are deliberately symmetric at SLOTS wide. Inputs could grow on demand -- ComfyUI
has Autogrow for that -- but outputs cannot, and a pipe that packs more than it can unpack would
be worse than a fixed width. Nest instead: a pipe is an ordinary value, so putting one in a slot
costs nothing and the width stops mattering.
"""

from __future__ import annotations

from comfy_api.latest import io

#: How many values one pipe carries. Both nodes read this, so they can never disagree.
SLOTS = 5

#: A dedicated type, so a pipe only fits a pipe input and a mis-drag is caught at the socket.
Pipe = io.Custom("MH_PIPE")


class AnyToPipe(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_AnyToPipe",
            display_name="Any to Pipe",
            category="MHNodes/pipe",
            description=(
                f"Bundles up to {SLOTS} connections of any type into a single pipe, to carry "
                "them through a workflow as one link. Empty slots stay empty. Pipes nest: feed "
                "a pipe into one of the slots and unpack it in stages later."
            ),
            inputs=[
                io.AnyType.Input(
                    f"value_{i}",
                    display_name=str(i),
                    optional=True,
                    tooltip=f"Anything at all, including another pipe. Comes back out of slot {i}.",
                )
                for i in range(1, SLOTS + 1)
            ],
            outputs=[Pipe.Output(id="pipe", display_name="pipe")],
        )

    @classmethod
    def execute(cls, **kwargs) -> io.NodeOutput:
        # A tuple of fixed width, so an unconnected slot round-trips as None rather than
        # shifting everything after it along.
        return io.NodeOutput(tuple(kwargs.get(f"value_{i}") for i in range(1, SLOTS + 1)))


class PipeToAny(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_PipeToAny",
            display_name="Pipe to Any",
            category="MHNodes/pipe",
            description=(
                f"Unpacks a pipe back into its {SLOTS} values, in the order they went in. "
                "Outputs are untyped, so they connect anywhere -- ComfyUI cannot know what a "
                "pipe holds until it runs. A slot that was left empty comes out as nothing."
            ),
            inputs=[Pipe.Input("pipe", tooltip="The pipe to unpack.")],
            outputs=[
                io.AnyType.Output(id=f"value_{i}", display_name=str(i))
                for i in range(1, SLOTS + 1)
            ],
        )

    @classmethod
    def execute(cls, pipe) -> io.NodeOutput:
        values = list(pipe) if isinstance(pipe, (tuple, list)) else [pipe]
        # Tolerate a pipe of a different width, in case these nodes are ever resized.
        values = (values + [None] * SLOTS)[:SLOTS]
        return io.NodeOutput(*values)
