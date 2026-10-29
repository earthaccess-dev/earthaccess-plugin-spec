"""``PluginBase``: the class every earthaccess plugin subclasses."""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any, ClassVar, Literal

from . import granules
from .context import PluginContext
from .errors import (
    MissingResultsError,
    NotSupportedError,
    UnsupportedCollectionError,
)
from .job import Job
from .results import as_result_set, list_services
from .support import Capabilities
from .version import CONTRACT_VERSION

__all__ = [
    "AUTHS",
    "OUTPUTS",
    "PluginBase",
    "accepting_plugins",
    "validate_inputs",
]

OUTPUTS = frozenset({"assets", "xarray", "dataframe", "opendap"})
"""The conventional ``output`` kinds.

``assets`` is the only kind earthaccess itself knows how to open or download.
The rest are handed back to the caller as-is; ``opendap`` means "native backend
objects" (for example PyDAP datasets) rather than OPeNDAP URLs.
"""

AUTHS = frozenset({"edl", "own", "none"})
"""The allowed ``auth`` modes: login through earthaccess, self-managed, none."""

_RESERVED_OPTIONS = frozenset({"check"})
_warned_unknown_support: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class _ShortNameTarget:
    """A results-like target for ``capabilities("ATL06")`` calls."""

    short_name: str
    collection_id: str = ""

    def __iter__(self) -> Iterator[Any]:
        return iter(())


def _as_target(target: Any) -> Any:
    """Normalise a capability-check target: a short name, results, or ``None``."""

    if target is None:
        return None
    if isinstance(target, str):
        return _ShortNameTarget(target)
    return as_result_set(target)


def validate_inputs(plugin: PluginBase, results: Any) -> None:
    """Check the plugin's ``requires_results`` and ``needs`` against ``results``.

    ``needs`` is checked, not fetched. We peek the first record instead of
    materializing the resultset (which may be lazy).
    """

    if results is None:
        if plugin.requires_results:
            raise MissingResultsError(f"{plugin.name} needs search results")
        return
    if not plugin.needs:
        return
    record = granules.peek(results)
    for need in plugin.needs:
        if record is None or not granules.granule_field(record, need):
            raise MissingResultsError(
                f"{plugin.name} needs {need!r}; these results do not provide it"
            )


def accepting_plugins(results: Any, exclude: Any = ()) -> list[str]:
    """Names of installed plugins whose capabilities are definitely supported."""

    excluded = {exclude} if isinstance(exclude, str) else set(exclude)
    return sorted(
        name for name in list_services(results).accepting() if name not in excluded
    )


def warn_once(plugin: str, collection_id: str, reason: str) -> None:
    """Warn a single time per (plugin, collection) that support is unknown."""

    key = (plugin, collection_id or "")
    if key in _warned_unknown_support:
        return
    _warned_unknown_support.add(key)
    warnings.warn(
        f"{plugin}: could not confirm support for {collection_id or 'these results'}: "
        f"{reason}",
        stacklevel=3,
    )


class PluginBase:
    """Subclass this. Implement ``Options`` and ``_request``.

    Optionally override ``_supports`` to report the collection's capabilities.
    """

    name: ClassVar[str]
    contract_version: ClassVar[int] = CONTRACT_VERSION
    needs: ClassVar[frozenset[str]] = frozenset()
    requires_results: ClassVar[bool] = True
    auth: ClassVar[Literal["edl", "own", "none"]]
    output: ClassVar[str]  # one of OUTPUTS; 'assets' unless the plugin says otherwise
    Options: ClassVar[type]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        fields = getattr(getattr(cls, "Options", None), "__dataclass_fields__", {})
        clash = _RESERVED_OPTIONS & set(fields)
        if clash:
            raise TypeError(
                f"{cls.__name__}.Options defines reserved option name(s): "
                f"{sorted(clash)}; 'check' is reserved by request()"
            )
        unknown = set(cls.needs) - granules.NEEDS
        if unknown:
            raise TypeError(
                f"{cls.__name__}.needs has unknown value(s): {sorted(unknown)}; "
                f"expected a subset of {sorted(granules.NEEDS)}"
            )

    def __init__(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        self._capabilities_cache: dict[str, Capabilities] = {}

    # --- implemented by the plugin ---
    def _request(self, results: Any, options: Any) -> Job:
        raise NotImplementedError

    def _supports(self, results: Any) -> Capabilities:
        """Cheap, collection-level capability check.

        Default: the plugin handles everything, with no extra detail.
        """

        return Capabilities(True)

    # --- provided by the contract ---
    def capabilities(self, target: Any = None) -> Capabilities:
        """Return the collection's capabilities.

        ``target`` is search results or a collection short name.
        """

        results = _as_target(target)
        if results is None:
            return Capabilities(True, plugin=self.name)
        key = granules.collection_label(results)
        if key and key in self._capabilities_cache:
            return self._capabilities_cache[key]
        try:
            caps = self._supports(results)
        except Exception as exc:  # noqa: BLE001 - never let a check crash a request
            caps = Capabilities(None, reason=f"capability check failed: {exc!r}")
        if not isinstance(caps, Capabilities):
            caps = Capabilities(
                None, reason=f"_supports returned {type(caps).__name__}"
            )
        caps = replace(
            caps,
            plugin=caps.plugin or self.name,
            collection=caps.collection or key,
        )
        if key:
            self._capabilities_cache[key] = caps
        return caps

    def job(self, fn: Any, output: str | None = None) -> Job:
        """Run ``fn`` in the shared background pool and return a local :class:`Job`.

        ``output`` overrides the plugin's declared output for this job (for a
        plugin whose result kind depends on the request).
        """

        return Job(fn, plugin=self.name, output=output or self.output)

    def request(
        self, results: Any = None, *, check: bool = True, **options: Any
    ) -> Job:
        """Validate inputs, check support, and return a :class:`Job` immediately."""

        # a plain list from search_data() becomes a GranuleResultSet
        results = as_result_set(results)
        validate_inputs(self, results)
        if check and results is not None:
            caps = self.capabilities(results)
            if caps.ok is False:
                label = granules.collection_label(results)
                raise UnsupportedCollectionError(
                    self.name,
                    label,
                    short_name=getattr(results, "short_name", ""),
                    reason=caps.reason,
                    accepting=accepting_plugins(results, exclude=self.name),
                )
            if caps.ok is None:
                warn_once(self.name, granules.collection_label(results), caps.reason)
        # unknown kwargs raise TypeError here
        return self._request(results, self.Options(**options))

    def get_job(self, job_id: str) -> Job:
        """Rebuild a resumable remote job from its id. Overridden by remote plugins."""

        raise NotSupportedError(f"{self.name} jobs cannot be resumed")

    async def arequest(
        self, results: Any = None, *, check: bool = True, **options: Any
    ) -> Job:
        return await asyncio.to_thread(self.request, results, check=check, **options)
