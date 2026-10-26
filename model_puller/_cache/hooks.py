"""Comfy PromptQueue adapters against the inspected put/task_done/queue contract."""
from functools import wraps

from .core import CacheError


def install_queue_hooks(queue, bridge):
    """Register holds before enqueue, and release only after known completion/cancel.

    A missing API prevents installation; callers must leave collection disabled.
    Startup reconciles positive history, retaining unresolved persisted holds.
    """
    names = ('put', 'task_done', 'get_current_queue', 'get_history', 'wipe_queue', 'delete_queue_item')
    if not all(callable(getattr(queue, name, None)) for name in names):
        raise CacheError('Comfy queue API is incompatible; collection must stay disabled')
    if getattr(queue, '_shared_model_cache_identity', None):
        if queue._shared_model_cache_identity != bridge.prefix:
            raise CacheError('Queue already belongs to another cache adapter')
        return
    original = {name: getattr(queue, name) for name in names}

    def snapshot():
        running, pending = original['get_current_queue']()
        return running, pending

    def prompt(item):
        if not isinstance(item, (tuple, list)) or len(item) < 3 or not isinstance(item[2], dict):
            raise CacheError('Unknown Comfy queue item; collection must stay disabled')
        return str(item[1]), item[2]

    running, pending = snapshot()
    bridge.reconcile(dict(prompt(item) for item in [*running, *pending]), original['get_history']().keys())

    @wraps(original['put'])
    def put(item, *args, **kwargs):
        identifier, body = prompt(item)
        bridge.submitted(identifier, body)
        # If enqueue raises with uncertain acceptance, retain the hold.
        return original['put'](item, *args, **kwargs)

    @wraps(original['task_done'])
    def task_done(*args, **kwargs):
        result = original['task_done'](*args, **kwargs)
        # get_history contains positive receipts, including known execution errors.
        running, pending = snapshot()
        bridge.reconcile(dict(prompt(item) for item in [*running, *pending]), original['get_history']().keys())
        return result

    def cancellation(name):
        @wraps(original[name])
        def wrapped(*args, **kwargs):
            _, before = snapshot()
            result = original[name](*args, **kwargs)
            running, pending = snapshot()
            active = {prompt(item)[0] for item in [*running, *pending]}
            for item in before:
                identifier, _ = prompt(item)
                if identifier not in active:
                    bridge.finished(identifier)
            return result
        return wrapped

    queue.put = put
    queue.task_done = task_done
    queue.wipe_queue = cancellation('wipe_queue')
    queue.delete_queue_item = cancellation('delete_queue_item')
    queue._shared_model_cache_identity = bridge.prefix


def install_path_hook(folder_paths, bridge):
    original = folder_paths.get_full_path
    if getattr(original, '_shared_model_cache_identity', None):
        if original._shared_model_cache_identity != bridge.prefix:
            raise CacheError('Model path hook already belongs to another cache adapter')
        return

    @wraps(original)
    def resolve(category, name, *args, **kwargs):
        result = original(category, name, *args, **kwargs)
        if result is not None:
            bridge.resolved(category, name, result)
        return result

    resolve._shared_model_cache_identity = bridge.prefix
    folder_paths.get_full_path = resolve
