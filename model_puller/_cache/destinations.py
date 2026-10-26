"""Strict selection among registered Comfy roots; no directory scans or fallback."""
from pathlib import Path

from .core import CacheError, canonical

ALIASES = {'unet': 'diffusion_models', 'clip': 'text_encoders', 't2i_adapter': 'controlnet'}


def select_root(category, registered, preferred=''):
    category = category.lower()
    roots = {canonical(p): Path(p).resolve() for p in registered}
    if preferred:
        prefix = Path(preferred).resolve()
        roots = {k: p for k, p in roots.items() if p == prefix or p.is_relative_to(prefix)}
    if not roots:
        raise CacheError(f'{category}: no registered destination matches the preferred root')
    # Canonical/legacy siblings are one family, but two different drives are not.
    families = {}
    for path in roots.values():
        name = ALIASES.get(path.name.lower(), path.name.lower())
        family = canonical(path.parent) if name == ALIASES.get(category, category) else canonical(path)
        families.setdefault(family, []).append(path)
    if len(families) != 1:
        raise CacheError(f'{category}: multiple registered destinations; set Preferred destination root')
    candidates = next(iter(families.values()))
    named = [p for p in candidates if p.name.lower() == ALIASES.get(category, category)]
    if len(named) == 1:
        return named[0]
    if len(candidates) == 1:
        return candidates[0]
    raise CacheError(f'{category}: ambiguous destination aliases')
