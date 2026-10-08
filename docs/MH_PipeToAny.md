# Pipe to Any

Unpacks a pipe back into its 5 values, in the order they went in.

## Inputs
- **pipe**: the pipe to unpack.

## Outputs
- **1** – **5**: the values, untyped.

## Why the outputs are untyped

ComfyUI fixes a node's outputs when the node is defined, and a pipe's contents are not known until the workflow runs — so the outputs cannot take on the types of whatever was packed. They are wildcards instead, which ComfyUI accepts into any input (`comfy_execution/validation.py`: a connection where either side is `*` is always valid).

The practical consequence: **nothing checks that slot 3 really holds a MODEL before you wire it into a model input.** Keep track of the order you packed things in. Wiring the wrong slot somewhere fails at run time, not when you connect it.

A slot that was left empty when packing comes out as nothing, which will usually error in whatever it is connected to — so leave those outputs unwired.

## Notes
- A pipe of a different width than this node expects is padded or trimmed rather than erroring, so the two nodes can be resized without invalidating saved workflows.
- Values pass through by reference; nothing is copied.

See [MH_AnyToPipe.md](MH_AnyToPipe.md) for packing, including how to nest beyond 5 values.
