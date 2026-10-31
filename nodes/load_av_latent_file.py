"""Owned H3 AV input for application refinement; no preview-pair requirement."""
from pathlib import Path
import hashlib
import json
import re
import struct

import folder_paths
from comfy_api.latest import io
from .latent_io import read_latent


def owned_path(latent):
    if not isinstance(latent, str) or not re.fullmatch(r'(?:refine-[0-9a-f]{24,64}|worker-[0-9a-f-]{36}-[0-9a-f-]{36})\.latent', latent):
        raise ValueError('Choose an owned refinement latent input')
    root = Path(folder_paths.get_input_directory()).resolve()
    path = (root/latent).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError('Refinement latent is missing or outside the input directory')
    return path


def validate_header(path):
    with path.open('rb') as stream:
        raw = stream.read(8)
        if len(raw) != 8:raise ValueError('Invalid AV latent header')
        count = struct.unpack('<Q', raw)[0]
        if not 2 <= count <= 8*1024*1024 or count+8 > path.stat().st_size:raise ValueError('Invalid AV latent header size')
        header = json.loads(stream.read(count))
    parts = {k for k in header if k == 'latent_tensor' or k.startswith('latent_tensor_part_')}
    if parts != {'latent_tensor', 'latent_tensor_part_1'}:
        raise ValueError('Refinement requires video and audio latent parts')


class LoadAVLatentFile(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id='MH_LoadAVLatentFile', display_name='Load owned AV latent',
            category='MHNodes/latent', description='Load a retained AV latent supplied by the application.',
            inputs=[io.String.Input('latent', default='', tooltip='Owned input filename for a validated H3 audio-video latent.')],
            outputs=[io.Latent.Output(id='samples', display_name='samples')])

    @classmethod
    def execute(cls, latent):
        path = owned_path(latent); validate_header(path)
        return io.NodeOutput({'samples': read_latent(str(path))})

    @classmethod
    def validate_inputs(cls, latent):
        try:validate_header(owned_path(latent))
        except (ValueError, OSError) as exc:return str(exc)
        return True

    @classmethod
    def fingerprint_inputs(cls, latent):
        path = owned_path(latent); validate_header(path)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):digest.update(block)
        return digest.hexdigest()
