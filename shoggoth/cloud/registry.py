"""
Registry of known CloudProvider instances, keyed by `provider.key`. Populated
at import time below -- no dynamic/plugin discovery yet, see provider.py's
docstring.
"""

_PROVIDERS = {}


def register(provider):
    _PROVIDERS[provider.key] = provider


def get_provider(key):
    return _PROVIDERS.get(key)


def available_providers(config):
    """Providers that should be offered right now (e.g. logged in with
    access), in registration order."""
    return [p for p in _PROVIDERS.values() if p.is_available(config)]


from shoggoth.cloud.celaeno import CelaenoProvider  # noqa: E402

register(CelaenoProvider())
