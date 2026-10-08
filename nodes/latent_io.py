"""Save a latent with a cheap visual preview, and load it back.

Full VAE decoding is often slower than the sampling that produced the latent, which makes
"generate a dozen options and pick the good ones" painful. A tiny VAE decodes the same latent
in a fraction of the time -- good enough to judge a take, not good enough to keep. So: save the
latent exactly, save a quick preview beside it, pick later, decode the winner properly.

Preview source, in order:

1. a VAE on the ``source`` socket -- full quality, because connecting one means you want the
   real decode as well as the latent (useful when continuing a video: a proper render to
   composite with, and the latent so the next generation does not inherit VAE round-trip loss),
2. a tiny VAE chosen from ``vae_approx`` -- the fast everyday path,
3. a MODEL on the ``source`` socket -- latent2RGB, free and instant, using that model's own
   factors. Quality depends entirely on the model's compression: at 8x (Wan, SD) it is clearly
   readable, at 32x (LTX) it is coloured mush,
4. nothing -- a placeholder card, so every latent still has a partner and the loader stays simple.
"""

from __future__ import annotations

import logging
import os

import torch
from comfy_api.latest import io

from .. import latent_store

log = logging.getLogger("MHNodes.LatentIO")

FPS = 24
NO_TAE = "none"


# ---------------------------------------------------------------- preview rendering

def _frames_from_decoded(decoded: torch.Tensor) -> torch.Tensor:
    """Normalise a VAE decode to [frames, H, W, C].

    Video VAEs return [B,T,H,W,C]; image VAEs return [B,H,W,C], where the batch is the frames.
    """
    if decoded.ndim == 5:
        return decoded[0]
    return decoded


def _latent2rgb(samples: torch.Tensor, latent_format) -> torch.Tensor | None:
    """Rough preview straight from the latent, using the model's own RGB factors.

    Emits one frame per *latent* step, so a video comes out temporally compressed -- 21 latent
    steps where the real decode would give 81.
    """
    factors = getattr(latent_format, "latent_rgb_factors", None)
    if not factors:
        return None

    weight = torch.tensor(factors, device="cpu").transpose(0, 1)
    bias = getattr(latent_format, "latent_rgb_factors_bias", None)
    bias = torch.tensor(bias, device="cpu") if bias else None
    reshape = getattr(latent_format, "latent_rgb_factors_reshape", None)

    x = samples.float().cpu()
    if reshape is not None:
        x = reshape(x)

    if x.ndim == 5:        # [B,C,T,H,W] -> [T,H,W,C]
        x = x[0].permute(1, 2, 3, 0)
    elif x.ndim == 4:      # [B,C,H,W]   -> [B,H,W,C]
        x = x.permute(0, 2, 3, 1)
    else:
        return None

    rgb = torch.nn.functional.linear(x, weight, bias=bias)
    return ((rgb + 1.0) / 2.0).clamp(0.0, 1.0)


def _placeholder(samples: torch.Tensor, reason: str):
    """A small card standing in for a preview, so every latent still has a partner."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (384, 216), (26, 26, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 383, 215), outline=(70, 70, 80))
    draw.text((16, 20), "no preview", fill=(210, 180, 120))
    draw.text((16, 48), reason[:46], fill=(150, 150, 160))
    draw.text((16, 84), f"shape {tuple(samples.shape)}", fill=(150, 150, 160))
    draw.text((16, 108), f"{samples.shape[1]} channels", fill=(150, 150, 160))
    if samples.ndim == 5:
        draw.text((16, 132), f"{samples.shape[2]} latent frames", fill=(150, 150, 160))
    draw.text((16, 176), "the latent is saved and loadable", fill=(120, 170, 130))
    return [image]


def _to_pil(frames: torch.Tensor, scale: float):
    from PIL import Image

    if scale and scale != 1.0:
        moved = frames.permute(0, 3, 1, 2)
        height = max(1, int(round(moved.shape[2] * scale)))
        width = max(1, int(round(moved.shape[3] * scale)))
        moved = torch.nn.functional.interpolate(
            moved, size=(height, width), mode="bilinear", align_corners=False
        )
        frames = moved.permute(0, 2, 3, 1)

    array = frames[..., :3].clamp(0.0, 1.0).mul(255.0).round().to(torch.uint8).cpu().numpy()
    return [Image.fromarray(f) for f in array]


def _write_webp(images, path: str) -> None:
    """One format for both cases: a single frame is a still, several are animated."""
    images[0].save(
        path,
        save_all=len(images) > 1,
        append_images=images[1:],
        duration=round(1000 / FPS),
        loop=0,
        quality=80,
        method=4,
    )


# ---------------------------------------------------------------- nodes

class SaveLatentPreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        import folder_paths

        approx = [NO_TAE] + folder_paths.get_filename_list("vae_approx")
        return io.Schema(
            node_id="MH_SaveLatentPreview",
            display_name="Save Latent + Preview",
            category="MHNodes/latent",
            description=(
                "Saves a latent together with a quick visual preview under the same name, so a "
                "batch of options can be judged by eye and only the keeper decoded properly.\n\n"
                "Preview source, in order: a VAE on the source socket (full quality), then the "
                "tiny VAE picked below, then latent2RGB from a MODEL on that same socket, then "
                "a placeholder card. The latent is saved either way."
            ),
            inputs=[
                io.Latent.Input("samples", tooltip="The latent to store."),
                io.String.Input(
                    "filename_prefix", default="take",
                    tooltip="Written under input/latents. A counter is appended.",
                ),
                io.Combo.Input(
                    "tae", options=approx, default=NO_TAE,
                    tooltip="Tiny VAE from models/vae_approx. The fast everyday preview.",
                ),
                io.MultiType.Input(
                    "source", [io.Vae, io.Model], optional=True,
                    tooltip="A VAE for a full-quality preview, or a MODEL for a free "
                            "latent2RGB one. A VAE wins over the tiny VAE above.",
                ),
                io.Float.Input(
                    "scale", default=0.5, min=0.05, max=1.0, step=0.05,
                    tooltip="Resizes the decoded preview. Ignored for latent2RGB, which is "
                            "already at latent resolution.",
                ),
            ],
            outputs=[io.Latent.Output(id="samples", display_name="samples")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            is_output_node=True,
        )

    @classmethod
    def execute(cls, samples, filename_prefix, tae, scale, source=None) -> io.NodeOutput:
        import comfy.utils
        import folder_paths

        tensor = samples["samples"]
        images, note = cls._render(tensor, tae, source, scale)

        base = latent_store.root()
        full_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, base
        )
        stem = os.path.join(full_folder, f"{filename}_{counter:05}_")

        payload = {
            "latent_tensor": tensor.contiguous(),
            "latent_format_version_0": torch.tensor([]),
        }
        metadata = cls._metadata()
        comfy.utils.save_torch_file(payload, stem + latent_store.LATENT_EXT, metadata=metadata)
        _write_webp(images, stem + latent_store.PREVIEW_EXT)

        log.info("saved %s (%s)", os.path.basename(stem), note)

        preview_name = os.path.basename(stem) + latent_store.PREVIEW_EXT
        relative = os.path.join(latent_store.SUBFOLDER, subfolder).replace("\\", "/").strip("/")
        return io.NodeOutput(
            samples,
            ui={"images": [{"filename": preview_name, "subfolder": relative, "type": "input"}]},
        )

    @classmethod
    def _metadata(cls) -> dict | None:
        import json

        from comfy.cli_args import args

        if args.disable_metadata:
            return None
        meta = {}
        if cls.hidden.prompt is not None:
            meta["prompt"] = json.dumps(cls.hidden.prompt)
        if cls.hidden.extra_pnginfo is not None:
            for key, value in cls.hidden.extra_pnginfo.items():
                meta[key] = json.dumps(value)
        return meta or None

    @classmethod
    def _render(cls, tensor, tae, source, scale):
        """Produce preview frames by the first route that works, never raising."""
        import comfy.sd

        # An audio latent is one-dimensional in time; there is nothing to look at.
        if tensor.ndim == 3:
            return _placeholder(tensor, "audio latent (1D)"), "placeholder"

        if source is not None and isinstance(source, comfy.sd.VAE):
            try:
                return _to_pil(_frames_from_decoded(source.decode(tensor)), scale), "vae"
            except Exception as exc:
                log.warning("VAE decode failed (%s); trying the next source", exc)

        if tae and tae != NO_TAE:
            try:
                import comfy.utils
                import folder_paths

                path = folder_paths.get_full_path_or_raise("vae_approx", tae)
                approx = comfy.sd.VAE(sd=comfy.utils.load_torch_file(path))
                return _to_pil(_frames_from_decoded(approx.decode(tensor)), scale), f"tae {tae}"
            except Exception as exc:
                log.warning("tiny VAE %s failed (%s); trying the next source", tae, exc)

        if source is not None and not isinstance(source, comfy.sd.VAE):
            latent_format = getattr(getattr(source, "model", None), "latent_format", None)
            if latent_format is not None:
                rgb = _latent2rgb(tensor, latent_format)
                if rgb is not None:
                    # Already at latent resolution, so scale is deliberately not applied.
                    return _to_pil(rgb, 1.0), "latent2rgb"
                return _placeholder(tensor, "model has no latent2RGB factors"), "placeholder"

        return _placeholder(tensor, "no VAE, tiny VAE or model given"), "placeholder"


class LoadLatentPreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_LoadLatentPreview",
            display_name="Load Latent + Preview",
            category="MHNodes/latent",
            description=(
                "Loads a latent saved by Save Latent + Preview. The dropdown lists the previews, "
                "so the node shows you what you are picking, and the latent beside it is what "
                "comes out. Right-click the node to discard a pair you are done with."
            ),
            inputs=[
                io.Combo.Input(
                    "preview",
                    options=latent_store.list_previews(),
                    upload=io.UploadType.image,
                    tooltip="A saved preview. The latent of the same name is what is loaded.",
                ),
            ],
            outputs=[io.Latent.Output(id="samples", display_name="samples")],
        )

    @classmethod
    def execute(cls, preview) -> io.NodeOutput:
        import safetensors.torch

        path = latent_store.latent_for(preview)
        if path is None:
            raise FileNotFoundError(
                f"No latent beside '{preview}'. The pair may have been partly deleted."
            )

        stored = safetensors.torch.load_file(path, device="cpu")
        # Latents written before the version marker existed were scaled differently.
        multiplier = 1.0 if "latent_format_version_0" in stored else 1.0 / 0.18215
        return io.NodeOutput({"samples": stored["latent_tensor"].float() * multiplier})

    @classmethod
    def fingerprint_inputs(cls, preview):
        import hashlib

        path = latent_store.latent_for(preview)
        if path is None:
            return float("nan")
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def validate_inputs(cls, preview):
        if latent_store.latent_for(preview) is None:
            return f"No latent paired with '{preview}'"
        return True
