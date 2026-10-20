# Add Latent Guide for MiniMax H3

Core's *Add Guide for MiniMax H3*, fed from a latent instead of an image. Anchors the end of a previous take at a frame of the new one, without a decode and re-encode in between. Built for continuing a video.

## Inputs
- **positive**: conditioning to add the guide to. Chain several guide nodes to stack guides.
- **latent**: the new take's latent. Only its size is read.
- **guide**: the previous take. Its last frames become the guide.
- **frames**: frames to take from the end of the guide. Steps through the valid lengths only: 5, 22, 39... (17n + 5). Limited to what the guide has.
- **frame_idx**: frame of the new take the guide starts at. **0** for continuation. Negative counts from the end.
- **use_audio**: guide the audio too, if the guide has any.
- **audio_vae** *(optional)*: connected, the audio is decoded and its tail encoded fresh instead of sliced. See *Audio* below.

## Outputs
- **positive**: the conditioning with the guide added.
- **overlap**: the frames the guide actually covers. Feed it to *Join MiniMax H3 Latents*.

## Why only 5, 22, 39... frames

The H3 video VAE encodes in independent **reels of 17 frames**, each packed into 5 latent frames as 1 + 4 + 4 + 4 + 4. A slice that starts on a reel boundary is **bit-identical** to encoding those frames on their own; a slice from anywhere else is something no encode would ever produce.

A take is always 17n + 5 frames, so tails of 17k + 5 frames always start on a reel boundary. For the same reason, the last frame alone can't be a guide: it sits inside a 4-frame latent frame.

## Audio

The audio VAE has no reels. Each audio latent frame remembers everything before it, so a sliced audio latent differs from a fresh encode for roughly its first 100 ms, then converges. It still decodes to the right sound.

- **audio_vae unconnected (default)**: the audio latent is sliced. Audio runs at 40 latent frames a second against 24 video frames, so the cut is rounded to the nearest audio latent frame: at most **12.5 ms** off the picture.
- **audio_vae connected**: the whole audio track is decoded, cut at the exact instant, and the tail encoded fresh. This is what core's node does with real audio.

On a 5-frame guide (0.2 s of audio) the two differ across the whole guide; on longer guides only near the start. Worth an A/B if a continuation's first moments sound off.

## Requirements
- Both takes must be the **same size**. A latent can't be resized the way core resizes an image.
- The guide must fit in the new take at **frame_idx**.

## Notes
- Sampler output is in the same space as a fresh VAE encode, for video and audio alike, so a saved take can be used directly.
- The guide is conditioning: the new take is steered towards it, not forced to equal it.
