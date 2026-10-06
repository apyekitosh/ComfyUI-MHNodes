# Model Puller

Pull models from a shared server on demand, and delete them again once nobody has used them for a while.

The problem it solves is the last step: people copy a model from the server, use it, and forget to delete it. This makes the cleanup automatic, and makes it impossible to lose anything that wasn't pulled by this tool.

## Settings

Under **Settings → MHNodes → Model Puller**:

| Setting | Meaning |
| --- | --- |
| **Server model path** | Root of the shared store, laid out like ComfyUI's `models/` folder. A UNC path such as `\server\models` works. |
| **Preferred destination root** | Optional. Set it to send every model type to one drive. Blank means per-type defaults. |
| **Delete after this many days unused** | Default 7. Checked at startup only. |
| **Enable automatic cleanup** | Off keeps pulling but never deletes. |
| **Track model usage** | Records when each pulled model was last used. Takes effect after a restart. |

## Pulling

Right-click the canvas → **Pull models from server…**, or the **MHNodes** menu. The browser walks the server tree; the first path segment is the model type, mirroring `models/`.

Each file shows one of three states:

- **no tag** — not present locally, tick it to pull
- **✓ _n_ d left** — pulled by this tool, counting down to deletion (amber at ≤ 2 days)
- **✓ kept** / **✓ installed** — exempt from cleanup, or installed by hand

**Keep** exempts a model from cleanup, after a confirmation. It sets a flag rather than dropping the registry row, so it is reversible and the record of where the model came from survives.

## Where pulled models land

You never type a destination. The target is read from `folder_paths`, i.e. whatever
`extra_model_paths.yaml` registers, so a pulled model is findable by ComfyUI **by construction** —
there is no way to write it somewhere invisible, and an unknown model type is refused rather than
guessed at.

### Pinning everything to one drive

Set **Preferred destination root** to e.g. `E:\models` and every model type goes
there. A type still lands in its own subfolder (`loras/`, `vae/`, …), picked from the folders
ComfyUI already searches under that root.

The one limit: a type that has **no** registered folder under the preferred root falls back to
the per-type default, rather than writing somewhere ComfyUI would not look for it. Check the
startup log or `/mhnodes/model_puller/targets` to see where each type resolves.

### How a destination is chosen

When a model type has several registered folders, the choice is:

1. the **Preferred destination root**, if one is set and the type is registered under it,
2. otherwise whichever folder already holds the most models of that type — that is where this
   install actually keeps them,
3. on a tie, never a folder inside ComfyUI's own source directory. On the Desktop build that is
   the app install, which an update replaces wholesale. Note this keys on where ComfyUI's *code*
   lives, not `folder_paths.base_path` — Desktop launches with `--base-directory` pointing at the
   user's data root, so `base_path` is where the real models are,
4. and finally the folder actually named after the type. Several types register legacy aliases
   — `diffusion_models` also searches `unet`, `text_encoders` also searches `clip`, `controlnet`
   also searches `t2i_adapter` — and those can come first in the list. This applies to the
   preferred root too, so pinning a drive still puts loras in `loras/`.

Nothing is read from any yaml. Desktop in particular has moved its model config around — it now
generates a per-instance file under `Comfy Desktop/instance-model-paths/` — so reading
`folder_paths` at runtime is what keeps this correct across those changes.

Junctions are handled: a model root reached through one resolves correctly, and the free-space
check reports the volume actually written to, not the one the path appears to be on.

## Pulling missing models in bulk

**Pull missing models for this workflow** (canvas right-click or the MHNodes menu) collects every
model widget in the open graph whose value is not in its own option list, resolves each to a model
folder, and checks the server for it. You get one list with sizes, everything available
pre-ticked, and a single button.

Nothing is automatic: you see what will be fetched and confirm it. Models that cannot be resolved
or are not on the server are listed with the reason, unticked.

Re-run the workflow once the copies finish — ComfyUI re-checks the folder on each request, so the
error clears without a restart.

## Cleanup

Runs once at startup, when nothing is loaded and nobody has a session open. A model is deleted when all of the following hold:

1. the registry recorded it as pulled by this tool,
2. it is not marked kept,
3. nothing has used it for longer than the configured number of days,
4. its size and modification time still match what was written at pull time.

Rule 1 is the safety property: **a model installed by hand can never be deleted**, because nothing but this tool's own registry is ever consulted. Rule 4 covers the case where someone replaced a pulled file by hand — the file is no longer the one we wrote, so it is left alone and logged.

Losing the registry strands pulled models on disk forever. That is the intended failure direction: wasted disk, never lost work.

## Usage tracking

"Used" means a workflow referenced the model, not when it was downloaded — otherwise the models you use most would be the ones deleted most often.

Two hooks, because neither alone is correct:

- `folder_paths.get_full_path` sees every model a loader resolves. But ComfyUI caches node outputs, so re-running a workflow does not re-execute the loader.
- Walking the prompt at submission catches those cached runs. Measured at ~30 µs for a 67-node workflow.

ComfyUI exposes no execution hook, so both are patches. If a ComfyUI update breaks either, that hook logs a warning and disables itself — tracking degrades, model loading does not.

## Which folder a model belongs to

A loader's combo is filled from `folder_paths.get_filename_list(folder)`, but the folder name never reaches the client. It is recovered by scoring each combo's options against each folder's listing. On a heavily modded install this resolves ~94% of model combos, custom packs included, with no cooperation from node authors. Unresolved ones are mostly self-downloading nodes that aren't `folder_paths`-backed at all.

## Safety

- Every client-supplied path is confined to the configured root; `..` traversal is rejected.
- Copies are written to a `.part` file and renamed only after the full byte count is verified, so an interrupted copy can never leave a truncated model that looks loadable.
- Free space is checked before a copy starts, keeping 512 MB of headroom.
- Copies run on a worker thread so the server stays responsive, reporting progress over the websocket.

## Dependencies

None. Standard library plus what ComfyUI already ships.
