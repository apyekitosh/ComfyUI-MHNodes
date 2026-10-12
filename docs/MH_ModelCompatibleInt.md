# Model Compatible Int

Rounds a number onto the grid a video model accepts, and tells you how many latents that is.

## Inputs
- **number**: the value to round. At least 1.
- **model**: Wan, LTXV or Minimax.
- **type**: Resolution or Frame Count.
- **rounding**: Floor (off, the default) or Ceil (on).

## Outputs
- **pixel int**: the rounded value, in pixels or frames.
- **latent int**: the same, in latents.

## Resolution

| Model | Multiple of | Latent int |
| --- | --- | --- |
| Wan | 16 | pixel / 16 |
| LTXV | 32 | pixel / 32 |
| Minimax | 32 | pixel / 32 |

`1000` on Wan floors to **992** (62 latents) and ceils to **1008** (63).

## Frame count

| Model | Valid counts | Latent int |
| --- | --- | --- |
| Wan | 4n + 1 | (pixel − 1) / 4 + 1 |
| LTXV | 8n + 1 | (pixel − 1) / 8 + 1 |
| Minimax | 17n + 5 | (pixel − 5) / 17 |

The latent formulas differ on purpose:

- **Wan and LTXV** give the first frame a latent of its own, then one latent per 4 (or 8) frames.
  5 Wan frames are **2** latents (1 + 4); 9 LTXV frames are **2** (1 + 8).
- **Minimax** folds its 5 extra frames into the first latent. 22 frames are **1** latent, not 17 + 5.

## Never below the minimum

Floor never goes under the smallest value the model accepts, since 0 or a negative count is
never useful:

- **Resolution**: at least one multiple. `10` on Wan gives 16 / 1, even on Floor.
- **Wan / LTXV frames**: at least 1 frame, 1 latent.
- **Minimax frames**: anything from 1 to 5 gives **5 frames, 1 latent**. The formula alone would
  give 0 latents for 5 frames, so this one is set explicitly.

A number below 1 is an error. The widget won't go there, but a linked value can.
