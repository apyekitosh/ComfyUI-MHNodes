# Load Latent + Preview

Loads a latent saved by [Save Latent + Preview](MH_SaveLatentPreview.md).

## Inputs
- **preview**: the dropdown lists saved previews, and the node renders the one you pick — so you choose by looking, not by filename. The latent of the same name is what gets loaded.

## Outputs
- **samples**: the latent, bit-identical to what was saved.

## Why it shows a picture

The combo lists the `.webp` previews rather than the `.latent` files. The frontend already knows how to render an image from a dropdown — it is the same mechanism `LoadImage` uses — so the preview appears with no custom frontend code at all, and the latent is found from the matching stem.

Subfolders are listed recursively, unlike core's loaders, whose flat `os.listdir` is why a pasted image never shows up in `LoadImage`'s dropdown even though the value works.

## Discarding

Right-click the node → **Discard this latent and its preview**. Both files are deleted after a confirmation, and the dropdown refreshes.

This is a menu action rather than a node on purpose: deleting files should never be a side effect of running a workflow. The route it calls refuses any path outside `input/latents`.

**Refresh list** re-reads the folder without reloading the page.
