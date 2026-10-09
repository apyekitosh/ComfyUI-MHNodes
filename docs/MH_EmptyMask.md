# Empty Mask

A mask filled with a single value — the same thing as Comfy's **Create Solid Mask**, plus a batch size.

## Inputs
- **value**: fill value, 0 (black) to 1 (white).
- **width** / **height**: resolution.
- **batch_size**: how many identical masks to return.

## Outputs
- **mask**: `[batch_size, height, width]`.

## Difference from Create Solid Mask

Only `batch_size`. At `batch_size = 1` the output is bit-identical to the core node — same shape, same dtype, same device. The core node is hardcoded to a batch of one, so matching a video meant adding a repeat node after it.
