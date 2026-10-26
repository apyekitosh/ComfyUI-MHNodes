"""Opt-in maintainer verification instrumentation, never a product prerequisite.

Normal app/controller/Comfy launches do not inspect development availability
files. An explicitly resource-gated verification process may opt in; the agent
must still check the real repository flags immediately before its heavy actions.
"""
import os
from pathlib import Path


class ResourcesUnavailable(RuntimeError):
    pass


def require_resources(repository, flag='isgpufree'):
    if os.environ.get('PAAT_DEVELOPMENT_RESOURCE_FLAGS') != '1':
        return
    if flag not in ('isgpufree', 'thatgpufree'):
        raise ValueError('Unknown development resource flag')
    if repository is None:
        raise ResourcesUnavailable('Development verification needs its repository resource-flag directory')
    root=Path(repository)
    if not (root/f'{flag}.true').is_file() or (root/f'{flag}.false').exists():
        raise ResourcesUnavailable(f'Heavy processing paused: require {flag}.true present and {flag}.false absent')
