"""Settings for the model puller.

The UI writes these through ComfyUI's own settings panel, which persists them to
``user/<user>/comfy.settings.json``. The startup purge runs long before any browser connects,
so it reads that file directly rather than going through the frontend.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("MHNodes.ModelPuller")

PREFIX = "MHNodes.ModelPuller."

DEFAULTS = {
    "ServerPath": "",
    "LocalPath": "",
    "PurgeDays": 7,
    "Enabled": True,
    "TrackUsage": True,
}


def _settings_file() -> str | None:
    try:
        import folder_paths

        user_dir = folder_paths.get_user_directory()
    except Exception:
        return None

    # ComfyUI stores per-user settings; "default" is the single-user case.
    candidate = os.path.join(user_dir, "default", "comfy.settings.json")
    if os.path.isfile(candidate):
        return candidate

    # Multi-user install: fall back to the first user directory that has settings.
    try:
        for entry in sorted(os.listdir(user_dir)):
            candidate = os.path.join(user_dir, entry, "comfy.settings.json")
            if os.path.isfile(candidate):
                return candidate
    except OSError:
        pass
    return None


def load() -> dict:
    """Current settings, falling back to defaults for anything unset."""
    values = dict(DEFAULTS)

    path = _settings_file()
    if not path:
        return values

    try:
        with open(path, encoding="utf-8") as handle:
            stored = json.load(handle)
    except Exception as exc:
        log.warning("could not read settings (%s); using defaults", exc)
        return values

    for key in DEFAULTS:
        stored_value = stored.get(PREFIX + key)
        if stored_value not in (None, ""):
            values[key] = stored_value

    return values


def data_dir() -> str:
    """Directory holding the registry, alongside ComfyUI's other user data."""
    try:
        import folder_paths

        base = folder_paths.get_user_directory()
    except Exception:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data")

    path = os.path.join(base, "MHNodes")
    os.makedirs(path, exist_ok=True)
    return path
