# Join MiniMax H3 Latents

Joins a take and its continuation into one latent, to be decoded as a unit.

## Inputs
- **first**: the earlier take.
- **second**: the continuation, guided by the end of the first at frame 0.
- **overlap**: the frames the two share. Connect the **overlap** output of *Add Latent Guide for MiniMax H3*.

## Outputs
- **samples**: the joined latent.
- **frames**: its length in pixel frames.

## How it joins

The first take is cut where the guide started, and the second is appended whole:

```
first:   [reel][reel][reel][1+4]
                      ╰─ guide ─╯
second:               [reel …………]
joined:  [reel][reel] + [second …]
```

A 17n + 5 take minus a 17k + 5 guide leaves whole reels, so the seam always lands on a reel boundary, and the result is still a valid 17n + 5 length. That means it can be continued again, and joined again.

The H3 decoder works in windows that overlap by 5 frames and line up with reel boundaries, so it blends across the seam the same way it blends between any two reels of a single take.

## Audio

The second take keeps all of its audio. The first take's audio is cut so the total is exactly the length H3 pairs with the joined frame count, which keeps picture and sound in step within one audio latent frame (25 ms).

Join the latents and decode once rather than decoding each take and gluing the results: decoding audio pieces separately smears about half a second around the seam, because the decoder needs context on both sides of every sample.

## Memory
- Latents are small (about 1 MB for a 22-frame take at 864x480), so joining costs nothing.
- Core's H3 video decoder works window by window and moves finished frames off the GPU, so VRAM does not grow with length. The decoded video does sit in RAM, as for any image batch.
- The audio decoder handles the whole track in one pass. Untested beyond a few takes.
