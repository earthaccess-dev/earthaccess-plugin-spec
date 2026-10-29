"""Cheap, non-materializing accessors for raw granule records.

A :class:`~earthaccess_plugin_spec.results.ResultSet` may be lazy, so plugins
iterate it and project only the few fields they need instead of materializing
the whole set. These helpers centralise that projection: every plugin used to
re-derive ``meta['concept-id']`` / ``umm['GranuleUR']`` by hand.

The functions never raise on a sparse or malformed record; a missing value is
``None`` (or ``""`` for the string accessors).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "NEEDS",
    "collection_concept_id",
    "collection_label",
    "concept_id",
    "granule_field",
    "native_id",
    "peek",
    "related_urls",
    "short_name",
    "version",
]

NEEDS = frozenset({"concept_id", "native_id", "umm"})
"""The values a plugin may declare in its ``needs``."""

_PATHS: dict[str, tuple[str, ...]] = {
    "concept_id": ("meta", "concept-id"),
    "native_id": ("umm", "GranuleUR"),
    "umm": ("umm",),
    "collection_concept_id": ("meta", "collection-concept-id"),
}


def _get(record: Any, *path: str) -> Any:
    """Walk ``path`` through nested mappings, returning ``None`` on a miss."""

    value = record
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def granule_field(record: Any, need: str) -> Any:
    """Return the value a declared ``needs`` name refers to, or ``None``."""

    try:
        path = _PATHS[need]
    except KeyError:
        raise KeyError(f"unknown plugin need {need!r}") from None
    return _get(record, *path)


def concept_id(granule: Any) -> str:
    """``meta.concept-id``: the granule's CMR concept id."""

    return _text(_get(granule, "meta", "concept-id"))


def native_id(granule: Any) -> str:
    """``umm.GranuleUR``: the granule's native id / name."""

    return _text(_get(granule, "umm", "GranuleUR"))


def collection_concept_id(granule: Any) -> str:
    """``meta.collection-concept-id``: the parent collection's concept id."""

    return _text(_get(granule, "meta", "collection-concept-id"))


def short_name(granule: Any) -> str:
    """The collection short name carried by the granule's UMM reference."""

    return _text(_get(granule, "umm", "CollectionReference", "ShortName"))


def version(granule: Any) -> str:
    """The collection version carried by the granule's UMM reference."""

    return _text(_get(granule, "umm", "CollectionReference", "Version"))


def related_urls(granule: Any) -> list[Mapping[str, Any]]:
    """The granule's ``umm.RelatedUrls`` entries (empty if there are none)."""

    urls = _get(granule, "umm", "RelatedUrls")
    if not isinstance(urls, list):
        return []
    return [url for url in urls if isinstance(url, Mapping)]


def peek(results: Any) -> Any:
    """The first record of a resultset, without materializing it.

    Returns ``None`` for an empty set or an object that is not iterable.
    """

    try:
        return next(iter(results), None)
    except TypeError:
        return None


def collection_label(results: Any) -> str:
    """A human label for a resultset's collection, without materializing it.

    Prefers an explicit ``short_name``; otherwise peeks the first record for
    ``meta.collection-concept-id``.
    """

    short = _text(getattr(results, "short_name", ""))
    if short:
        return short
    return collection_concept_id(peek(results))
