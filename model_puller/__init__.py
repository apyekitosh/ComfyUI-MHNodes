"""Pull models from a shared server and clean them up when nobody has used them.

Wiring happens in :func:`setup`, called from the extension's on_load. Every step is guarded:
a failure here must never stop the nodes in this pack from registering.
"""

from __future__ import annotations

import logging

log = logging.getLogger("MHNodes.ModelPuller")

__all__ = ["setup"]


def setup() -> None:
    from . import api, config, purge, registry, tracking

    settings = config.load()

    try:
        registry.instance()
    except Exception as exc:
        log.error("registry unavailable, model puller disabled: %s", exc)
        return

    try:
        from server import PromptServer

        api.register(PromptServer.instance.routes)
        log.info("routes registered at %s", api.PREFIX)
    except Exception as exc:
        log.error("could not register routes: %s", exc)

    if settings.get("TrackUsage", True):
        tracking.install()

    # The purge runs now, while nothing is loaded and nobody has a session open.
    try:
        purge.run()
    except Exception as exc:
        log.error("purge failed: %s", exc)
