# ComfyUI-MHNodes

Simple, general-purpose custom nodes for ComfyUI, built on the V3 node API
(`comfy_api.latest`).

## Nodes

| Node | Category | What it does |
| --- | --- | --- |
| **Save Image Sequence** | `MHNodes/image` | Saves an image batch to an arbitrary filesystem path, with optional skip-if-exists. |
| **Linear Gradient from Coords** | `MHNodes/generate` | Generates a black-to-white linear gradient defined by two points. |

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
    gradient.py      # generators
    image_io.py      # file I/O
    utils.py         # shared tensor/PIL helpers
  docs/              # per-node help pages (filename == node_id)
```

To add a node: define it in a module under `nodes/`, export it from
`nodes/__init__.py`, and add it to `get_node_list()` in `__init__.py`.

## License

MIT
