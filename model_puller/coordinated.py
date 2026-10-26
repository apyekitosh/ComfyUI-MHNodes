"""Staged MHNodes startup adapter. Installed only after deployment review.

This file is copied into model_puller alongside a versioned copy of the canonical
stdlib cache core. Importing this module alone does not start or change anything.
"""
import json
from pathlib import Path

_bridge = None


def preferred_root(config):
    # The legacy loader deliberately falls back on malformed settings. That is
    # unsuitable for choosing a write drive: a read error must stop preparation.
    from ._cache import CacheError
    path = config._settings_file() if hasattr(config,'_settings_file') else None
    if path is None:return (config.load().get('LocalPath') or '').strip()
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8')).get('MHNodes.ModelPuller.LocalPath','')
        if not isinstance(value,str):raise ValueError('Preference must be text')
        return value.strip()
    except (OSError,ValueError,TypeError,AttributeError) as exc:
        raise CacheError('Cannot read Preferred destination root; no drive fallback') from exc


def destination_info(category, roots, preferred):
    """A bad preference in one category must not hide all registered roots."""
    from ._cache.destinations import select_root
    from ._cache import CacheError
    try:return {'roots':roots, 'destination':str(select_root(category, roots, preferred))}
    except CacheError as exc:return {'roots':roots, 'destination':None, 'error':str(exc)}


def transfer_permission(settings):
    from ._cache.development import require_resources
    # Production admission is the explicit cache configuration plus durable
    # host/queue ownership. These optional fields serve developer tests only.
    return lambda: require_resources(settings.get('resource_flag_directory'),
                                    settings.get('resource_flag_family','isgpufree'))


def remove_model(key):
    from ._cache.legacy import RegistryView
    if _bridge is None:
        raise RuntimeError('Shared model cache is not initialized')
    cache, entry = RegistryView(_bridge.cache, _bridge.installed).location(key)
    cache.remove_managed(entry['category'],entry['name'])
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
    from ._cache.destinations import select_root
    from . import folders, registry, transfer, purge, api
    import folder_paths
    from server import PromptServer
    server = PromptServer.instance
    # Existing setting is the only preference authority. A request gets a fresh
    # immutable view; running requests keep the view they were accepted with.
    registered = {c: folders.roots_for(c) for c in settings['destinations']}
    destinations = {c: select_root(c, roots, preferred_root(config))
                    for c, roots in registered.items()}
    cache = Cache(settings['state'], settings['source'], destinations, before_transfer=transfer_permission(settings),
                  source_categories=settings.get('source_categories'), registered_roots=registered)
    def locations():
        preferred = preferred_root(config)
        roots = {c: folders.roots_for(c) for c in destinations}
        return cache.with_destinations({c:select_root(c, paths, preferred) for c,paths in roots.items()},
                                       registered_roots=roots)
    def destination_root(category, preferred=''):
        from aiohttp import web
        from ._cache import CacheError
        try:return str(select_root(category, folders.roots_for(category), preferred_root(config)))
        except CacheError as exc:raise web.HTTPBadRequest(reason=str(exc)) from exc
    folders.destination_root = destination_root
    bridge = ComfyBridge(cache, folders.build_map(), identity=settings['comfy_identity'],
                         resolve=folders.find_local,opaque_nodes=settings.get('opaque_model_nodes',[]),locations=locations)
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
