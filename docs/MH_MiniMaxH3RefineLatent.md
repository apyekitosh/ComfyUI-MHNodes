# Refine MiniMax H3 Latent

Prepares an existing continuation for a second pass (hi-res fix) without decoding or re-encoding. Use it when **current** was generated from the original previous segment, and **previous** has now been refined.

## Inputs

- **previous**: the already refined previous segment.
- **current**: the existing continuation, including its original overlap with the previous segment. Both inputs must already have matching batch size and resolution; upscale current first if needed.
- **overlap**: shared pixel frames, starting at 5 in increments of 17: **5, 22, 39...**. Wired values snap **down** to this grid and are capped to fit both segments. Values below 5 are rejected, as in Extend.

## Outputs

- **latent**: current with its first overlap frames replaced by the previous segment's last overlap frames. Its length stays the same. The replacement has noise mask **0** (held fixed); the remaining samples stay intact with noise mask **1** (available to refine). Existing noise masks are replaced.
- **overlap**: the corrected overlap in pixel frames. Connect this to **overlap** on *Join MiniMax H3 Latents*.

```text
previous: [ already refined segment ][ refined tail ]
current:                            [ old overlap  ][ existing continuation ]
output:                             [ refined tail ][ existing continuation ]
noise mask:                               0                    1
```

Sample the output with your second-pass settings. Then join **previous** as **source_latent** and the sampled output as **new_latent**, using the returned **overlap**. Repeat for each later segment, using the newly refined segment as the next previous input.

Both segments must have valid H3 lengths of 17n + 5 pixel frames. This ensures the previous tail starts on a reel boundary. This node assumes the overlap already matches in time; it does not find or align segments.

## Audio

Video-only and joint audio-video latents are supported. Both inputs must have the same streams. With audio, the previous tail replaces the beginning of current's audio and is masked in the same way, using Extend's nearest audio-frame boundary (40 audio latent frames per second against 24 pixel frames per second). The remaining current audio samples and total audio length are preserved.

Uses only the existing ComfyUI and torch APIs; no additional dependencies.
