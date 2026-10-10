# Pad Frame Count

Rounds a batch up to a frame count the chosen video model will accept, adding frames to get there.

## Inputs
- **image** *(optional)* / **mask** *(optional)*: at least one must be connected.
- **policy**: which model's rule to satisfy.
- **amount**: frame count to reach.
- **add_to**: `Start`, `End` or `Both`.

## Outputs
- **image** / **mask**: the padded batches.
- **amount**: the frame count after padding.

## Policies

| policy | valid counts | formula |
| --- | --- | --- |
| **Wan** | 4n + 1 | `ceil((n-1)/4)*4 + 1` |
| **LTXV** | 8n + 1 | `ceil((n-1)/8)*8 + 1` |
| **Minimax** | 17n + 5 | `ceil((n-5)/17)*17 + 5` |
| **Free** | any | no rounding |

A count that is already valid is left alone.

## How amount is used

`amount` is a target, never a limit — **the batch is never shortened**.

- `amount` **above** the batch: round `amount` up to a valid count and pad to it.
- `amount` **below** the batch (including the default `0`): the policy is applied to the batch you actually have, so you still end up with a count the model accepts. Under **Free** that means nothing changes.

So `policy = Wan, amount = 0` is a useful shorthand for "make this batch a valid Wan length".

## Order of operations

1. The mask is matched to the image — last mask repeated if short, excess trimmed if long.
2. Padding is added to both.

Matching first matters: 10 images and 20 masks at `amount 15` drops the last 10 masks, *then* repeats frame 10 of each to reach 15. Padding before matching would pad a mask batch that was about to be cut.

## Placement

`Both` splits the padding, and an odd split puts the extra frame at the **start** — padding 5 gives 3 before and 2 after.

## Notes
- Added frames repeat the first frame (at the start) or the last (at the end). To fill with a flat colour instead, see [Pad Frame Count (Advanced)](MH_PadFrameCountAdvanced.md).
- Only the batch dimension changes; resolution is untouched, and image and mask may differ in size.
