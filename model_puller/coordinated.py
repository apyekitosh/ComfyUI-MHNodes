"""Staged MHNodes startup adapter. Installed only after deployment review.

This file is copied into model_puller alongside a versioned copy of the canonical
stdlib cache core. Importing this module alone does not start or change anything.
"""
import json
from pathlib import Path

_bridge = None


def remove_model(key):
    from ._cache.legacy import split
    if _bridge is None:
        raise RuntimeError('Shared model cache is not initialized')
    _bridge.cache.remove_managed(*split(key))
    from . import folders
    import folder_paths
    folders.invalidate();folder_paths.filename_list_cache.clear()


def start():
    global _bridge
    from . import config
    path = Path(config.data_dir()) / 'coordinated-cache.json'
    if not path.exists():
        return False  # No activation/configuration change on an existing install.
    settings = json.loads(path.read_text(encoding='utf-8'))
    if not settings.get('enabled', False):
        return False
    # Any failure propagates to MHNodes' existing guarded setup. Never run its old
    # purge as a fallback once coordinated mode has been explicitly requested.
    from ._cache import Cache
    from ._cache.bridge import ComfyBridge
    from ._cache.hooks import install_path_hook, install_queue_hooks
    from ._cache.legacy import install_legacy
    from ._cache.host import TransferHost
    from ._cache.routes import register
    from . import folders, registry, transfer, purge, api
    import folder_paths
    from server import PromptServer
    server = PromptServer.instance
    resource_directory = Path(settings['resource_flag_directory'])
    flag = settings['resource_flag_family']
    if flag not in ('isgpufree', 'thatgpufree'):
        raise ValueError('Invalid model-transfer resource flag family')

    def resources():
        if not (resource_directory / (flag + '.true')).is_file() or (resource_directory / (flag + '.false')).exists():
            raise RuntimeError('Model transfer paused by resource availability flag')

    destinations = settings['destinations']
    for category, target in destinations.items():
        registered = {str(Path(p).resolve()).casefold() for p in folders.roots_for(category)}
        if str(Path(target).resolve()).casefold() not in registered:
            raise ValueError('Cache destination is not a registered Comfy model root: ' + category)
    cache = Cache(settings['state'], settings['source'], destinations, before_transfer=resources,
                  source_categories=settings.get('source_categories'))
    bridge = ComfyBridge(cache, folders.build_map(), identity=settings['comfy_identity'],
                         resolve=folders.find_local,opaque_nodes=settings.get('opaque_model_nodes',[]))
    install_queue_hooks(server.prompt_queue, bridge)
    install_path_hook(folder_paths, bridge)
    def invalidate():
        folders.invalidate()
        folder_paths.filename_list_cache.clear()
    integration_ready=lambda:bool(settings.get('usage_tracking_verified',False))
    install_legacy(registry, transfer, purge, bridge, integration_ready=integration_ready,config=config,invalidate=invalidate)
    _bridge = bridge
    api.register(server.routes)
    transfers = TransferHost(bridge, terminal=lambda prompt_id:bool(server.prompt_queue.get_history(prompt_id)),
                             invalidate=invalidate,
                             collect=lambda:cache.collect(dry_run=not settings.get('cleanup_enabled',False),
                                                          integration_ready=integration_ready()))
    from aiohttp import web
    register(server.routes, transfers, web)
    # Startup cleanup is a dry run until its separate live activation gate.
    summary = transfers.startup()
    print('[MHNodes] Shared model-cache startup:', summary)
    return True
