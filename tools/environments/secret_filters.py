"""Pure helpers for identifying Hermes-internal dynamic secret names.

These predicates are shared across multiple spawn surfaces (local, docker,
env_passthrough) so they can be imported without creating a dependency loop on
``tools.environments.local``.
"""

from __future__ import annotations


def is_hermes_internal_secret(key: str) -> bool:
    """Return True for Hermes-internal secrets injected under dynamic names.

    Matches the runtime-only secret names that are not covered by the static
    provider/tool blocklist:

    - ``AUXILIARY_<TASK>_API_KEY`` / ``AUXILIARY_<TASK>_BASE_URL``
    - ``GATEWAY_RELAY_*_SECRET`` / ``_KEY`` / ``_TOKEN``

    Non-secret routing hints like ``AUXILIARY_<TASK>_PROVIDER`` or
    ``GATEWAY_RELAY_URL`` intentionally do not match.
    """
    upper = key.upper()
    if upper.startswith("AUXILIARY_") and (
        upper.endswith("_API_KEY") or upper.endswith("_BASE_URL")
    ):
        return True
    if upper.startswith("GATEWAY_RELAY_") and (
        upper.endswith("_SECRET") or upper.endswith("_KEY") or upper.endswith("_TOKEN")
    ):
        return True
    return False
