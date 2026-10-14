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

## Tiny VAE files

Any of these in `models/vae_approx` works:

- **Video TAEs** (`taehv`, `taew2_1`, `lighttaew2_*`, `taeltx2_*`, `taeh3`...): single files, used as they are.
- **Image TAEs as core ships them**: the `<name>_decoder` / `<name>_encoder` pair.
- **Image TAEs as one file**, e.g. a single `taef2.safetensors`: the diffusers layout of the same network, converted on load.

A file in some other layout, such as `FLUX2TinyAutoEncoder.safetensors` (a different architecture that ComfyUI itself can't load), gets the placeholder card saying so.

## Audio-video latents

MiniMax H3 and LTX 2 latents carry video and audio together. The preview shows the video and the card notes `+audio`. **Both parts are saved**, and Load Latent + Preview puts them back together, so the latent comes out as it went in.

The video part is stored under core's usual key, so core's `LoadLatent` can still read a moved file. It gets the video only, though.

## Notes
- Previews are animated WebP at a fixed 24 fps; a single frame is written as a still, in the same format.
- Previews carry the workflow, embedded the same way core's own WebP saves do it: drop one onto the canvas to load the workflow that made it. Off under `--disable-metadata`, as for core.
- An audio latent (rank 3, one-dimensional in time) gets a placeholder card rather than a nonsense decode.
- If a decode fails the node falls through to the next source rather than erroring — you still get the latent.
- The latent is written in ComfyUI's own format, so core's `LoadLatent` can read it if you move the file. For an audio-video latent it only gets the video.
