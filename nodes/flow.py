"""Controlling the order nodes run in."""

from __future__ import annotations

from comfy_api.latest import io


class ExecutionFlowController(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        # Each output takes the type of what is plugged into its input, as core's Switch does,
        # so a value passes through without losing its type to a wildcard.
        signal = io.MatchType.Template("signal")
        value = io.MatchType.Template("value")
        return io.Schema(
            node_id="MH_ExecutionFlowController",
            display_name="Execution Flow Controller",
            category="MHNodes/utils",
            description=(
                "Passes both inputs straight through, unchanged. It exists to order execution: "
                "a node only runs once all its inputs are ready, so anything fed by value here "
                "waits for whatever produced signal."
            ),
            inputs=[
                io.MatchType.Input("signal", template=signal,
                                   tooltip="Anything. Its producer runs before this node does."),
                io.MatchType.Input("value", template=value,
                                   tooltip="Anything. Passed on once signal is ready."),
            ],
            outputs=[
                io.MatchType.Output(template=signal, id="signal", display_name="signal"),
                io.MatchType.Output(template=value, id="value", display_name="value"),
            ],
        )

    @classmethod
    def execute(cls, signal, value) -> io.NodeOutput:
        return io.NodeOutput(signal, value)
