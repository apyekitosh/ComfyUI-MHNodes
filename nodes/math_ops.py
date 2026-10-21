"""Small arithmetic, for the many one-step sums a graph needs without a full expression node."""

from __future__ import annotations

import math

from comfy_api.latest import io


def _round(x):
    # Halves away from zero (2.5 -> 3, -2.5 -> -3), as people expect. Python's round() sends
    # halves to the even neighbour (2.5 -> 2), which is right for statistics and surprising here.
    return math.copysign(math.floor(abs(x) + 0.5), x)


def _divisor(b, operation):
    if b == 0:
        raise ValueError(f"{operation} by zero.")
    return b


#: name -> (operands, function). Kept in the order the dropdown shows them.
OPERATIONS = {
    "add": (2, lambda a, b: a + b),
    "subtract": (2, lambda a, b: a - b),
    "multiply": (2, lambda a, b: a * b),
    "divide": (2, lambda a, b: a / _divisor(b, "divide")),
    "increment": (1, lambda a: a + 1),
    "decrement": (1, lambda a: a - 1),
    # Both remainders: they differ only for negatives. modulo follows b's sign (Python's %,
    # -7 mod 3 = 2), residual follows a's (fmod, -7 residual 3 = -1).
    "modulo": (2, lambda a, b: a % _divisor(b, "modulo")),
    "residual": (2, lambda a, b: math.fmod(a, _divisor(b, "residual"))),
    "floor": (1, math.floor),
    "ceil": (1, math.ceil),
    "round": (1, _round),
    "absolute": (1, abs),
    "negate": (1, lambda a: -a),
}


class QuickMath(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        # Sockets only, no widgets: the node stays three rows tall.
        number = [io.Int, io.Float]
        return io.Schema(
            node_id="MH_QuickMath",
            display_name="Quick Math",
            category="MHNodes/utils",
            description=(
                "One small operation on one or two numbers, ints or floats. Operations that take "
                "one number ignore b."
            ),
            inputs=[
                io.Combo.Input("operation", options=list(OPERATIONS), default="add"),
                io.MultiType.Input("a", number, tooltip="An int or a float."),
                io.MultiType.Input("b", number, optional=True,
                                   tooltip="An int or a float. Ignored by one-number operations."),
            ],
            outputs=[
                io.Int.Output(id="int", display_name="int",
                              tooltip="The result as an int, cut toward zero, as core's math "
                                      "node does."),
                io.Float.Output(id="float", display_name="float"),
            ],
        )

    @classmethod
    def execute(cls, operation, a, b=None) -> io.NodeOutput:
        operands, function = OPERATIONS[operation]
        if operands == 1:
            result = function(a)
        else:
            if b is None:
                raise ValueError(f"{operation} needs b connected.")
            result = function(a, b)
        return io.NodeOutput(int(result), float(result))
