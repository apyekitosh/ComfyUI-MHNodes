"""Injected aiohttp route registration for Comfy's existing server.

Only the local app/controller can call these routes. The authenticated worker
API exposes its own scoped forwarding contract; these are not a public file API.
"""
import asyncio
from functools import wraps
from uuid import UUID

from .core import CacheError

PREFIX = '/mhnodes/model_cache'


def register(routes, host, web):
    def local(handler):
        @wraps(handler)
        async def wrapped(request):
            if request.remote not in ('127.0.0.1', '::1'):
                raise web.HTTPForbidden(text='Model cache control requires the local app or controller')
            try:
                return web.json_response(await handler(request))
            except FileNotFoundError as exc:
                raise web.HTTPNotFound(text='Unknown model preparation') from exc
            except (CacheError, ValueError, KeyError, TypeError) as exc:
                raise web.HTTPConflict(text=str(exc)) from exc
        return wrapped

    @routes.get(PREFIX + '/catalogue')
    @local
    async def catalogue(request):
        return await asyncio.to_thread(host.bridge.inventory)

    @routes.post(PREFIX + '/startup')
    @local
    async def startup(request):
        return await asyncio.to_thread(host.startup)

    @routes.post(PREFIX + '/preparations')
    @local
    async def prepare(request):
        body = await request.json()
        owner, prompt_id, prompt = body['owner'], str(UUID(body['prompt_id'])), body['prompt']
        if not isinstance(prompt, dict) or len(prompt) > 4096:
            raise ValueError('Invalid preparation prompt')
        return await asyncio.to_thread(host.start, owner, prompt_id, prompt)

    @routes.get(PREFIX + '/preparations/{owner}')
    @local
    async def status(request):
        return await asyncio.to_thread(host.status, request.match_info['owner'])

    @routes.post(PREFIX + '/preparations/{owner}/cancel')
    @local
    async def cancel(request):
        return await asyncio.to_thread(host.cancel, request.match_info['owner'])

    @routes.post(PREFIX + '/preparations/{owner}/handoff')
    @local
    async def handoff(request):
        return await asyncio.to_thread(host.handoff, request.match_info['owner'])
