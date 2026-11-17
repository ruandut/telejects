"""One Hatchet client per process, created on first use.

Lazy so `manage.py migrate` etc. work before a HATCHET_CLIENT_TOKEN exists. The SDK reads its
config from env vars (HATCHET_CLIENT_TOKEN, HATCHET_CLIENT_TLS_STRATEGY, HATCHET_CLIENT_HOST_PORT),
which settings.py loads from the root .env.
"""

from functools import cache

from hatchet_sdk import Hatchet


@cache
def get_hatchet() -> Hatchet:
    return Hatchet()
