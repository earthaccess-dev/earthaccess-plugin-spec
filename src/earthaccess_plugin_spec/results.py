"""The results a plugin consumes: a protocol, an adapter and support listing.

A ``ResultSet`` may be **lazy**: iterating it streams the results from CMR (one
bounded page at a time) and a plugin is responsible for paginating/projecting
the few fields it needs rather than materializing everything. `GranuleResultSet`
is a ``list`` subclass so existing list-based code keeps working, while slicing
preserves the type (and therefore the extra methods).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from . import granules
from .support import ServiceRow, ServiceTable
from .version import CONTRACT_VERSION

if TYPE_CHECKING:
    from .context import PluginContext

__all__ = ["GranuleResultSet", "ResultSet", "as_result_set"]


@runtime_checkable
class ResultSet(Protocol):
    """The minimal shape a plugin needs from search results.

    Iterate the resultset to consume it (it may be lazy and page in the results);
    the ``collection_id``/``ids``/``native_ids``/``umm()`` accessors are
    convenient shortcuts that may materialize the whole set, so plugins should
    prefer iterating and projecting.
    """

    collection_id: str
    """Concept id of the single collection the granules belong to."""

    short_name: str
    """Collection short name (from the granule's UMM CollectionReference)."""

    version: str
    """Collection version (from the granule's UMM CollectionReference)."""

    ids: Sequence[str]
    """Granule concept ids (``meta.concept-id``); may materialize the resultset."""

    native_ids: Sequence[str]
    """Granule URs / names (``umm.GranuleUR``); may materialize the resultset."""

    def __iter__(self) -> Iterator[Mapping[str, Any]]:
        """Yield the raw granule records, streaming them if the set is lazy."""
        ...

    def umm(self) -> Sequence[Mapping[str, Any]]:
        """Return the raw UMM-G records (may materialize the resultset)."""
        ...

    def services(self) -> Sequence[Mapping[str, Any]]:
        """Return the UMM-S records associated with the collection (may be empty)."""
        ...

    def list_services(self, context: PluginContext | None = None) -> ServiceTable:
        """Return which installed plugins accept these results."""
        ...


class GranuleResultSet(list):
    """Adapter over the plain ``list[dict]`` returned by ``search_data()``.

    ``short_name``/``version`` default to the value carried by the first
    granule's UMM reference and can be overridden (by search results that know
    them, or by test fixtures).
    """

    def __init__(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        services: Sequence[Mapping[str, Any]] | None = None,
        short_name: str | None = None,
        version: str | None = None,
    ) -> None:
        super().__init__(records)
        # Ignore blank labels so one sparse record does not look like a second
        # collection.
        collections = {
            label
            for label in (granules.collection_concept_id(g) for g in self)
            if label
        }
        if len(collections) > 1:
            raise ValueError("a ResultSet holds granules from one collection")
        self.collection_id = next(iter(collections), "")
        self.ids = [granules.concept_id(g) for g in self]
        self.native_ids = [granules.native_id(g) for g in self]
        first = self[0] if self else None
        self.short_name = (
            short_name
            if short_name is not None
            else (granules.short_name(first) if first else "")
        )
        self.version = (
            version
            if version is not None
            else (granules.version(first) if first else "")
        )
        self._services = list(services) if services else []

    def __getitem__(self, key: Any) -> Any:
        result = super().__getitem__(key)
        if isinstance(key, slice):
            # Slicing must preserve the type, or the extra methods are lost.
            return GranuleResultSet(
                result,
                services=self._services,
                short_name=self.short_name,
                version=self.version,
            )
        return result

    def umm(self) -> list[Mapping[str, Any]]:
        return [granules.granule_field(g, "umm") or {} for g in self]

    def services(self) -> list[Mapping[str, Any]]:
        return list(self._services)

    def list_services(self, context: PluginContext | None = None) -> ServiceTable:
        return list_services(self, context)


def as_result_set(results: Any) -> Any:
    """Wrap a plain list of granules, pass through a ResultSet or ``None``.

    Detection is deliberately cheap: it never reads ``collection_id``, which a
    lazy resultset computes by scanning the whole set.
    """

    if results is None or hasattr(results, "umm"):
        return results
    return GranuleResultSet(results)


def list_services(results: Any, context: PluginContext | None = None) -> ServiceTable:
    """Query every installed plugin for support of ``results``.

    Plugins that are not installed cannot be checked and are not listed, and a
    plugin whose check errors is shown as ``?`` rather than failing the table.
    """

    from .context import default_context
    from .discovery import installed_plugins

    if context is None:
        context = default_context()
    rows: list[ServiceRow] = []
    for name, plugin_cls in installed_plugins().items():
        if getattr(plugin_cls, "contract_version", None) != CONTRACT_VERSION:
            continue
        try:
            support = plugin_cls(context).capabilities(results)
        except Exception as exc:  # noqa: BLE001 - a broken plugin must not break the table
            rows.append(ServiceRow(name, None, f"error: {exc!r}"))
            continue
        rows.append(ServiceRow(name, support.ok, support.reason))
    return ServiceTable(rows)
