"""Load a saved latent directly, without a companion preview."""
from pathlib import Path

from comfy_api.latest import io
from .latent_io import read_latent


def latent_path(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Enter the absolute path to a saved latent file")
    value = path.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", chr(34)):
        value = value[1:-1]
    result = Path(value)
    if not result.is_absolute():
        raise ValueError("Latent path must be absolute")
    if not result.is_file():
        raise ValueError("Latent file does not exist or is not a file")
    return result.resolve()


class LoadLatentPath(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MH_LoadLatentPath",
            display_name="Load Latent from Path",
            category="MHNodes/latent",
            description="Load a saved image, video or audio-video latent from an absolute path. No preview required.",
            inputs=[io.String.Input("path", default="", tooltip="Absolute path on the Comfy server to a saved latent file. Quoted paths are accepted.")],
            outputs=[io.Latent.Output(id="samples", display_name="samples")],
        )

    @classmethod
    def execute(cls, path):
        source = latent_path(path)
        try:
            samples = read_latent(str(source))
        except Exception as exc:
            raise ValueError(f"Could not load saved latent: {exc}") from exc
        return io.NodeOutput({"samples": samples})

    @classmethod
    def validate_inputs(cls, path):
        try:
            latent_path(path)
        except (ValueError, OSError) as exc:
            return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, path):
        source = latent_path(path)
        stat = source.stat()
        return (str(source), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
