# Add Audio to H3 Latent

Adds an empty audio stream to a **video-only MiniMax H3 latent**, ready to generate sound by sampling at full denoise. This creates latent samples, not a silent waveform or an encoded audio guide.

## Input / output

- **latent** input: a video-only H3 latent.
- **latent** output: a joint audio-video latent with the same video samples and metadata.

Audio is zero-filled with native H3 shape `[batch, 32, 2, time]`. Its length matches the video's duration at 24 fps, rounded to the nearest audio latent frame at 40 Hz. It uses the video's device and dtype.

If the video has a noise mask, that mask is preserved exactly and paired with an all-ones audio mask so the audio is fully available to denoise. Without a video mask, no mask is added. The input is not modified.

An input that already contains audio is rejected to avoid replacing existing sound. Use the resulting latent with your normal H3 conditioning and sampler; choose full-denoise settings to generate the new audio. The video remains subject to its existing mask and your sampler settings.

No VAE, encoding pass or additional dependencies are needed.
