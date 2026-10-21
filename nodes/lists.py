"""Lists, for running part of a graph once per item.

A node fed by a list output runs once per item; that is how ComfyUI iterates.
"""

from __future__ import annotations

from comfy_api.latest import io

#: Autogrow's own ceiling in core.
MAX_ITEMS = 100


def _ordered(items: dict | None) -> list:
    """Autogrow values in socket order, skipping sockets left unconnected."""
    names = sorted(items or {}, key=lambda name: int(name.removeprefix("item")))
    return [items[name] for name in names if items[name] is not None]


class AnyList(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        # One type for every socket and the output, as core's Switch does it. A new socket
        # appears as the last one is connected, up to Autogrow's limit.
        item = io.MatchType.Template("item")
        return io.Schema(
            node_id="MH_AnyList",
            display_name="Any List",
            category="MHNodes/utils",
            description=(
                "Collects its inputs into a list. Whatever the list feeds runs once per item, in "
                f"socket order. A new socket appears as the last is connected, up to {MAX_ITEMS}."
            ),
            inputs=[
                io.Autogrow.Input("items", template=io.Autogrow.TemplatePrefix(
                    io.MatchType.Input("item", template=item, optional=True),
                    prefix="item", min=1, max=MAX_ITEMS,
                )),
            ],
            outputs=[
                io.MatchType.Output(template=item, id="list", display_name="list",
                                    is_output_list=True,
                                    tooltip="The inputs, one item each, in socket order."),
            ],
        )

    @classmethod
    def execute(cls, items: io.Autogrow.Type = None) -> io.NodeOutput:
        values = _ordered(items)
        if not values:
            raise ValueError("Any List has nothing connected.")
        return io.NodeOutput(values)


class AnyPlot(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        first = io.MatchType.Template("first")
        second = io.MatchType.Template("second")
        return io.Schema(
            node_id="MH_AnyPlot",
            display_name="Any Plot",
            category="MHNodes/utils",
            description=(
                "Expands two lists into every combination, as the cells of a grid. list_1 runs "
                "along each row and list_2 down the rows:\n\n"
                "A B C  and  X Y Z  give\n"
                "list_1: A B C A B C A B C\n"
                "list_2: X X X Y Y Y Z Z Z"
            ),
            # Whole lists in, rather than being run once per item.
            is_input_list=True,
            inputs=[
                io.MatchType.Input("list_1", template=first,
                                   tooltip="Repeats as a whole: A B C A B C..."),
                io.MatchType.Input("list_2", template=second,
                                   tooltip="Repeats item by item: X X X Y Y Y..."),
            ],
            outputs=[
                io.MatchType.Output(template=first, id="list_1", display_name="list_1",
                                    is_output_list=True),
                io.MatchType.Output(template=second, id="list_2", display_name="list_2",
                                    is_output_list=True),
                # Plain values, not lists, so they reach the next node once rather than per cell:
                # what an image grid needs to know its shape.
                io.Int.Output(id="columns", display_name="columns",
                              tooltip="Length of list_1: the width of the grid."),
                io.Int.Output(id="rows", display_name="rows",
                              tooltip="Length of list_2: the height of the grid."),
            ],
        )

    @classmethod
    def execute(cls, list_1, list_2) -> io.NodeOutput:
        if not list_1 or not list_2:
            raise ValueError("Any Plot needs both lists to have at least one item.")
        expanded_1 = [a for _ in list_2 for a in list_1]
        expanded_2 = [b for b in list_2 for _ in list_1]
        return io.NodeOutput(expanded_1, expanded_2, len(list_1), len(list_2))
