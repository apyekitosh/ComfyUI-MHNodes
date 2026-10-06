# Model Puller

Pull models from a shared server on demand, and delete them again once nobody has used them for a while.

The problem it solves is the last step: people copy a model from the server, use it, and forget to delete it. This makes the cleanup automatic, and makes it impossible to lose anything that wasn't pulled by this tool.

## Settings

Under **Settings → MHNodes → Model Puller**:

| Setting | Meaning |
| --- | --- |
| **Server model path** | Root of the shared store, laid out like ComfyUI's `models/` folder. A UNC path such as `\server\models` works. |
| **Local destination** | Where pulled models are written. Must already be a path ComfyUI searches — set that in `extra_model_paths.yaml`; this tool does not validate it. |
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
