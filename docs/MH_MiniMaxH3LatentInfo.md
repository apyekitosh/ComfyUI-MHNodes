# MiniMax H3 Latent Info

Reads a MiniMax H3 latent and reports its dimensions in pixel space. Accepts video-only and joint audio-video latents.

## Input

- **latent**: the H3 latent to inspect.

## Outputs

- **latent**: the input, unchanged, so this node can sit inline in a workflow.
- **width** / **height** (INT): decoded pixel dimensions, using H3's 16x spatial compression.
- **frames** (INT): decoded frame count, using H3's repeating `1, 4, 4, 4, 4` frames per latent timestep.
- **seconds** (FLOAT): frame count divided by H3's native **24 fps**. This describes the native duration, regardless of any playback fps selected later.

After execution, the four numeric values appear beside their output sockets, without display nodes. Seconds are rounded to three decimal places for display; the FLOAT output retains full precision. For list-driven execution the labels show the last item's values.

This is also an output node: connect just its input and queue the workflow to inspect a latent even when none of its outputs are connected. Reconnecting the input clears the old labels until execution updates them.
