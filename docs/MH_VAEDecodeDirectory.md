# VAE Decode Full Directory

Decodes every saved latent in a folder in one run, for when a batch of takes has been generated and saved, and they all need rendering.

## Inputs
- **directory**: the folder holding the `.latent` files. Absolute, or relative to ComfyUI's input folder, so the default `latents` is where *Save Latent + Preview* writes. Pasted quotes are fine.
- **vae**: decodes the picture.
- **audio_vae** *(optional)*: decodes the sound of audio-video latents (MiniMax H3, LTX 2). Without it, only the picture is written.
- **fps**: the frame rate written.
- **output**: **mp4** or **image sequence**.

## Outputs
- **folder**: the `decoded` folder that was written to, for chaining into anything that reads a folder.

## What it writes

A `decoded` folder inside the directory:

```
latents/
  take_00001_.latent
  take_00002_.latent
  decoded/
    take_00001_.mp4                 ← mp4: one per latent, audio inside
    take_00002_/                    ← image sequence: one folder per latent
      take_00002_00000.png
      take_00002_00001.png
      ...
      take_00002_.mp3
```

Names follow the source latent. Running it again overwrites what's there.

## Skipping

Every latent in the folder is expected to be the same kind, made by the same model. One that isn't (a different model, a corrupt file) is **skipped with a warning**, and the run carries on. The node's result lists what was skipped and why.

A latent that fails partway leaves **nothing** behind: each file is written under a temporary name and only moved into place once complete.

One thing it can't catch: a latent from a *compatible* but wrong model (same channel count) decodes without error, just as nonsense.

## Progress

The node shows **3/47**, then **4/47**, and so on as each latent finishes, plus how many were skipped. Cancelling stops between latents.

## Notes
- Only the folder's own `.latent` files are read, not subfolders.
- The node re-runs when the folder's latents change, even if no input did.
- Audio is decoded the same way core's *VAE Decode Audio* does it.
- MP3 rounds up to its own frame size, so a sequence's mp3 can run a few milliseconds past the last picture.
