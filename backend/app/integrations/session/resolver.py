"""Dataset → session-context resolver (decoupling layer).

The collection workers previously imported a per-platform
``resolve_*_runtime_context`` function (alimama / sycm / cps / databank /
brandsearch / utry), which coupled every worker to the individual provider
modules.  This helper replaces that with a single, data-driven entry point::

    from app.integrations.session.resolver import resolve_dataset_context
    ctx = resolve_dataset_context(dataset, source=..., cookie_env=..., **extra)

A worker only needs a ``CollectionDataset`` whose ``platform_code`` names
the platform.  The resolver looks the platform up in the shared
``default_registry``, picks the matching per-platform ``resolve_*``
function, and forwards ``**extra`` to it.  Datasets with an empty
``platform_code`` raise a clear error because no platform session is
required.

High cohesion: one module, one concern (dataset → platform context).
Low coupling: workers depend on this module + the dataset record, not on
six separate resolve_* functions.
"""

from __future__ import annotations

from typing import Any

from app.integrations.session.alimama import resolve_alimama_runtime_context
from app.integrations.session.brandsearch import resolve_brandsearch_runtime_context
from app.integrations.session.cps import resolve_cps_runtime_context
from app.integrations.session.databank import resolve_databank_runtime_context
from app.integrations.session.sycm import resolve_sycm_runtime_context
from app.integrations.session.utry import resolve_utry_runtime_context

# platform_code → resolver.  Callers pass each resolver's keyword arguments
# through ``**extra``; see each resolver's docstring for its contract.
_RESOLVERS = {
    "sycm": resolve_sycm_runtime_context,
    "alimama": resolve_alimama_runtime_context,
    "databank": resolve_databank_runtime_context,
    "cps": resolve_cps_runtime_context,
    "brandsearch": resolve_brandsearch_runtime_context,
    "utry": resolve_utry_runtime_context,
}


def resolve_dataset_context(
    dataset: Any,
    *,
    source: str,
    cookie_env: str,
    **extra: Any,
) -> Any:
    """Resolve the platform runtime context for a collection dataset.

    Parameters
    ----------
    dataset:
        Any object exposing ``platform_code`` (``CollectionDataset``).
    source:
        Session source, "env" or "drissionpage".
    cookie_env:
        Named cookie environment (e.g. "RTB_COOKIE", "DATABANK_COOKIE").
    **extra:
        Platform-specific resolver keyword arguments, forwarded verbatim:

        * sycm: required ``home_url``, ``request_target``, ``platform_name``;
          optional ``token``, ``browser_port``, ``timeout``.
        * alimama: optional ``csrf_id``, ``login_point_id``,
          ``report_home_url``, ``browser_port``, ``timeout``.
        * cps: optional ``tb_token``, ``report_home_url``, ``browser_port``,
          ``timeout``.
        * databank: optional ``csrf_token``, ``csrf_env``, ``home_url``,
          ``browser_port``.
        * brandsearch: optional ``csrf_id``, ``report_home_url``,
          ``browser_port``, ``timeout``.
        * utry: optional ``report_home_url``, ``browser_port``, ``timeout``
          (drissionpage only).

    Returns
    -------
    The platform's runtime context object (``*.RuntimeContext``) that carries
    ``.session`` (a ``RuntimeSession``) plus the platform's transient values.
    """
    code = getattr(dataset, "platform_code", "") or ""
    if not code:
        raise ValueError(
            f"Dataset '{getattr(dataset, 'key', '?')}' has no platform_code; "
            "no platform session is required for this dataset."
        )
    if code not in _RESOLVERS:
        raise KeyError(f"Unknown dataset platform_code: {code!r}")

    return _RESOLVERS[code](source=source, cookie_env=cookie_env, **extra)


__all__ = ["resolve_dataset_context"]
