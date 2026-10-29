"""Collection-support reporting: ``Capabilities`` and the ``list_services`` table."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "Capability",
    "Capabilities",
    "ServiceRow",
    "ServiceTable",
]


class Capability(str, Enum):
    """An operation a plugin/service can perform on a collection.

    The union of what the reference plugins expose; each plugin reports the
    subset it supports.
    """

    LAZY_READ = "lazy_read"  # read slices without downloading (OPeNDAP)
    SUBSET_BBOX = "subset_bbox"
    SUBSET_TEMPORAL = "subset_temporal"
    SUBSET_VARIABLE = "subset_variable"
    SUBSET_DIMENSION = "subset_dimension"
    SUBSET_SHAPE = "subset_shape"
    REPROJECT = "reproject"
    AVERAGE_TIME = "average_time"
    AVERAGE_AREA = "average_area"
    CONCATENATE = "concatenate"
    PROCESS = "process"  # run an on-demand processor (SlideRule)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Capabilities:
    """The result of a plugin's cheap, collection-level capability check.

    ``ok`` is tri-state on purpose: service associations and capabilities can
    lag reality, so ``None`` ("could not tell") must never hard-block a request
    the service might accept. Only a definite ``False`` raises.
    """

    ok: bool | None
    plugin: str = ""
    collection: str = ""
    operations: frozenset[Capability] = frozenset()
    formats: frozenset[str] = frozenset()
    apis: frozenset[str] = frozenset()
    reason: str = ""

    def _label(self) -> str:
        return {True: "supported", False: "unsupported", None: "unknown"}[self.ok]

    def _title(self) -> str:
        who = self.plugin or "plugin"
        what = self.collection or "these results"
        return f"{who} {self._label()} {what}"

    def __str__(self) -> str:
        lines = [self._title()]
        if self.reason:
            lines.append(f"  {self.reason}")
        if self.operations:
            lines.append(
                "  operations: " + ", ".join(sorted(str(o) for o in self.operations))
            )
        if self.apis:
            lines.append("  apis: " + ", ".join(sorted(self.apis)))
        if self.formats:
            lines.append("  formats: " + ", ".join(sorted(self.formats)))
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"Capabilities({self._title()!r}, operations={len(self.operations)})"

    def _repr_html_(self) -> str:
        colour = {True: "#2e7d32", False: "#c62828", None: "#ef6c00"}[self.ok]
        icon = {True: "\u2713", False: "\u2717", None: "?"}[self.ok]
        parts = [
            f"<div><b>{self.plugin or 'plugin'}</b> "
            f'<span style="color:{colour}">{icon} {self._label()}</span> '
            f"<code>{self.collection}</code>"
        ]
        if self.reason:
            parts.append(f"<div><i>{self.reason}</i></div>")
        for label, values in (
            ("operations", sorted(str(o) for o in self.operations)),
            ("apis", sorted(self.apis)),
            ("formats", sorted(self.formats)),
        ):
            if values:
                items = "".join(f"<li>{value}</li>" for value in values)
                parts.append(f"<div>{label}:<ul>{items}</ul></div>")
        parts.append("</div>")
        return "".join(parts)


@dataclass(frozen=True)
class ServiceRow:
    """One plugin's answer in the ``list_services`` table."""

    plugin: str
    ok: bool | None
    detail: str = ""

    @property
    def _label(self) -> str:
        return {True: "yes", False: "no", None: "?"}[self.ok]


@dataclass
class ServiceTable:
    """A printable table of which installed plugins accept some results."""

    rows: list[ServiceRow] = field(default_factory=list)

    def __iter__(self) -> Any:
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def accepting(self) -> list[str]:
        return [row.plugin for row in self.rows if row.ok is True]

    def _render(self) -> str:
        header = ("plugin", "supported", "detail")
        body = [(row.plugin, row._label, row.detail) for row in self.rows]
        widths = [len(col) for col in header]
        for row in body:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))
        lines = [
            "  ".join(
                str(cell).ljust(widths[i]) for i, cell in enumerate(header)
            ).rstrip(),
            "  ".join("-" * widths[i] for i in range(len(header))),
        ]
        for row in body:
            lines.append(
                "  ".join(
                    str(cell).ljust(widths[i]) for i, cell in enumerate(row)
                ).rstrip()
            )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self._render()

    def __str__(self) -> str:
        return self._render()

    def _repr_html_(self) -> str:
        head = "<tr><th>plugin</th><th>supported</th><th>detail</th></tr>"
        body = "".join(
            f"<tr><td>{row.plugin}</td><td>{row._label}</td><td>{row.detail}</td></tr>"
            for row in self.rows
        )
        return f"<table>{head}{body}</table>"
