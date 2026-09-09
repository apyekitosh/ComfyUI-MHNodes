# ComfyUI-MHNodes

Simple, general-purpose custom nodes for ComfyUI, built on the V3 node API
(`comfy_api.latest`).

## Nodes

| Node | Category | What it does |
| --- | --- | --- |
| **Save Image Sequence** | `MHNodes/image` | Saves an image batch to an arbitrary filesystem path, with optional skip-if-exists. |
| **Linear Gradient from Coords** | `MHNodes/generate` | Generates a black-to-white linear gradient defined by two points. |
| **Crop Image and Mask** | `MHNodes/image` | Crops an image and/or a mask to a fixed size by alignment and offset, returning paste coordinates. |

Per-node documentation lives in [`docs/`](docs).

## Installation

Clone into your ComfyUI `custom_nodes` directory and restart ComfyUI:

```bash
git clone https://github.com/mh/ComfyUI-MHNodes
```

No extra dependencies — everything used ships with ComfyUI.

## Requirements

ComfyUI with the V3 node API (`comfy_api.latest`), i.e. reasonably recent.
Developed against ComfyUI 0.8.2.

## Layout

```
ComfyUI-MHNodes/
  __init__.py        # ComfyExtension + comfy_entrypoint()
  nodes/
    __init__.py      # re-exports every node class
    crop.py          # cropping
    gradient.py      # generators
    image_io.py      # file I/O
    utils.py         # shared tensor/PIL helpers
  docs/              # per-node help pages (filename == node_id)
```

To add a node: define it in a module under `nodes/`, export it from
`nodes/__init__.py`, and add it to `get_node_list()` in `__init__.py`.

## Conventions

- **`node_id`** is `MH_<NodeName>`, e.g. `MH_SaveImageSequence`. This is the
  globally unique key ComfyUI stores in saved workflows — never change it after
  a node ships; change `display_name` instead.
- **`display_name`** is the human-readable name, spaced and capitalized.
- **`category`** is `MHNodes/<group>`, e.g. `MHNodes/image`.
- Each node gets a help page at `docs/<node_id>.md` — the filename must match
  the `node_id` exactly for ComfyUI to find it.

## License

MIT
