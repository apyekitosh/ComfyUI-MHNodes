# Extend MiniMax H3 Latent

Continues a take by **masking** rather than guiding: the end of the source becomes the start of a longer latent, held fixed by a noise mask, and only the frames after it are generated. Picture and sound both.

## Inputs
- **latent**: the take to continue.
- **length**: total frames of the new latent, the kept overlap **included**: 5, 22, 39... (17n + 5).
- **overlap**: frames kept from the end of the source: 5, 22, 39... (17n + 5). Limited to what the source has.

## Outputs
- **latent**: the kept tail, masked, followed by new frames to generate. Sample it like any latent.
- **length** / **overlap**: the values actually used. Wired values are snapped **down** onto the grid, so these may differ from what came in. Feed **overlap** to *Join MiniMax H3 Latents*.

## Layout

```
new latent:  [ source's last <overlap> frames ][ new frames ]  = <length> frames
noise mask:    0  kept                           1  generated
```

The kept tail starts on a reel boundary of the source, exactly as in *Add Latent Guide for MiniMax H3*, and a 17n + 5 length minus a 17k + 5 overlap is always whole reels, so the new latent is a valid H3 length whatever the numbers.

The audio is kept from the same instant as the picture, to the nearest audio latent frame (at most 12.5 ms off), and the rest of the track is generated.

## Joining back

*Join MiniMax H3 Latents* with the source as **source_latent**, the sampled result as **new_latent**, and this node's **overlap** gives the whole sequence: the source up to where the overlap began, then the extension.

## Guide or extend?

- **Add Latent Guide** hands the tail to the model as *conditioning*: the new take is steered towards it, but generated freely.
- **Extend** puts the tail *in the latent* and masks it: those frames are held to the source at every step, so they come out unchanged, and the model generates only what follows them.

Which one continues more smoothly depends on the model and the shot. They're two approaches to compare.

## Errors
- **length** must leave room for new frames: with a 22-frame overlap, the smallest useful length is 39.
- Both values must be at least 5.
