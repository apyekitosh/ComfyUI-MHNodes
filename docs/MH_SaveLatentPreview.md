# Save Latent + Preview

Saves a latent together with a quick visual preview under the same name, so a batch of options can be judged by eye and only the keeper decoded properly.

Full VAE decoding is often slower than the sampling that produced the latent — for video at high resolution, much slower. A tiny VAE decodes the same latent in a fraction of the time: good enough to pick a take, not good enough to keep.

## Inputs
- **samples**: the latent to store.
- **filename_prefix**: written under `input/latents`. A counter is appended. Subfolders in the prefix work.
- **tae**: a tiny VAE from `models/vae_approx`. The fast everyday path.
- **source** *(optional)*: either a **VAE** or a **MODEL** — one socket, both accepted.
- **scale**: resizes the decoded preview. Default `0.5`.

## Outputs
- **samples**: the latent, passed through unchanged.

## Which preview you get

| | |
|---|---|
| a **VAE** on `source` | full-quality decode |
| otherwise **tae** | tiny VAE decode |
| otherwise a **MODEL** on `source` | latent2RGB |
| otherwise | a placeholder card |

A VAE beats the tiny VAE deliberately: connecting one means you want the real decode *as well as* the latent. That is the video-continuation case — a proper render to composite with, and the latent so the next generation doesn't inherit VAE round-trip loss.

The latent is always saved, whichever route the preview took.

## latent2RGB

Free and instant, using the model's own RGB factors. Two things to know:

- **It works at latent resolution.** Quality therefore depends entirely on the model's compression. At 8× (Wan, SD) it is clearly readable; at 32× (LTX) a 1920×1056 frame becomes 60×33 and is unusable for picking takes.
- **It does not expand time.** One frame per *latent* step — 21 where the real decode gives 81 — so a video preview runs temporally compressed.

`scale` is ignored in this mode, since the output is already tiny.

## Notes
- Previews are animated WebP at a fixed 24 fps; a single frame is written as a still, in the same format.
- An audio latent (rank 3, one-dimensional in time) gets a placeholder card rather than a nonsense decode.
- If a decode fails the node falls through to the next source rather than erroring — you still get the latent.
- The latent is written in ComfyUI's own format, so core's `LoadLatent` can read it if you move the file.
