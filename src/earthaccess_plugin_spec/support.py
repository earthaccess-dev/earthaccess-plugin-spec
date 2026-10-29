"""Collection-support reporting: ``Capabilities`` and the ``list_services`` table."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from typing import Any

from .job import FORMATS

__all__ = [
    "CAPABILITY_SPECS",
    "FORMATS",
    "Capability",
    "CapabilitySpec",
    "Capabilities",
    "OUTPUT_TYPES",
    "Explanation",
    "ServiceRow",
    "ServiceTable",
    "explain_capability",
    "format_name",
]

OUTPUT_TYPES: dict[str, str] = {
    "assets": "list[Asset] (href/access/format)",
    "xarray": "xarray.Dataset",
    "dataframe": "pandas.DataFrame or GeoDataFrame",
    "opendap": "native backend objects (e.g. pydap Dataset, not downloaded)",
}
"""What a job's ``output`` kind means as a Python return type."""

_FORMAT_ALIASES = {
    "application/x-netcdf": "netcdf4",
    "application/x-netcdf4": "netcdf4",
    "application/netcdf": "netcdf4",
    "application/netcdf4": "netcdf4",
    "application/x-zarr": "zarr",
    "application/zip": "zarr",
    "image/tiff": "geotiff",
    "image/geotiff": "geotiff",
    "application/geoparquet": "geoparquet",
    "application/vnd.apache.parquet": "geoparquet",
    "text/csv": "csv",
}


def format_name(value: str) -> str | None:
    """Normalize a backend format string to the canonical :data:`FORMATS`.

    Returns ``None`` for a format the contract does not model, so callers can
    omit it instead of leaking a backend-specific name.
    """

    key = value.strip().lower()
    if key in FORMATS:
        return key
    return _FORMAT_ALIASES.get(key)


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
class CapabilitySpec:
    """The normative meaning of a :class:`Capability`.

    ``summary`` is what the *result* guarantees (not how the backend does it).
    ``options`` are the canonical ``Options`` fields through which a caller can
    ask for the capability; at least one must exist on a plugin that advertises
    it. ``values`` constrain the requested value (for example
    ``average="time"``). ``outputs`` are the result kinds where it applies.
    ``case`` means the conformance suite must exercise it with a real request.
    """

    capability: Capability
    summary: str
    options: tuple[str, ...] = ()
    values: frozenset[str] = frozenset()
    outputs: frozenset[str] = frozenset()
    case: bool = True
    example: str = ""


CAPABILITY_SPECS: dict[Capability, CapabilitySpec] = {
    Capability.LAZY_READ: CapabilitySpec(
        Capability.LAZY_READ,
        "read slices without downloading the whole granule",
        case=False,
        example='ea.open(job)  # slices are read on access',
    ),
    Capability.SUBSET_BBOX: CapabilitySpec(
        Capability.SUBSET_BBOX,
        "restrict the result to a spatial extent (bbox or wkt)",
        options=("bbox", "wkt"),
        outputs=frozenset({"assets", "xarray", "dataframe"}),
        example='plugin.request(results, bbox=(west, south, east, north))',
    ),
    Capability.SUBSET_TEMPORAL: CapabilitySpec(
        Capability.SUBSET_TEMPORAL,
        "restrict the result to a time interval (temporal)",
        options=("temporal",),
        outputs=frozenset({"assets", "xarray", "dataframe"}),
        example='plugin.request(results, temporal={"start": ..., "stop": ...})',
    ),
    Capability.SUBSET_VARIABLE: CapabilitySpec(
        Capability.SUBSET_VARIABLE,
        "select a subset of variables; an unknown name raises",
        options=("variables",),
        outputs=frozenset({"assets", "xarray", "dataframe", "opendap"}),
        example='plugin.request(results, variables=["var1", "var2"])',
    ),
    Capability.SUBSET_DIMENSION: CapabilitySpec(
        Capability.SUBSET_DIMENSION,
        "select a subset along named dimensions (dimensions)",
        options=("dimensions",),
        outputs=frozenset({"assets", "xarray"}),
        example='plugin.request(results, dimensions=[...])',
    ),
    Capability.SUBSET_SHAPE: CapabilitySpec(
        Capability.SUBSET_SHAPE,
        "restrict the result to a shapefile/region geometry (shapefile)",
        options=("shapefile",),
        outputs=frozenset({"assets", "xarray", "dataframe"}),
        example='plugin.request(results, shapefile="aoi.geojson")',
    ),
    Capability.REPROJECT: CapabilitySpec(
        Capability.REPROJECT,
        "reproject the result to a target CRS (crs)",
        options=("crs",),
        outputs=frozenset({"assets", "xarray"}),
        example='plugin.request(results, crs="EPSG:3995")',
    ),
    Capability.AVERAGE_TIME: CapabilitySpec(
        Capability.AVERAGE_TIME,
        "average the result over time (average contains 'time')",
        options=("average",),
        values=frozenset({"time", "time,area"}),
        outputs=frozenset({"assets"}),
        example='plugin.request(results, average="time")',
    ),
    Capability.AVERAGE_AREA: CapabilitySpec(
        Capability.AVERAGE_AREA,
        "average the result over area (average contains 'area')",
        options=("average",),
        values=frozenset({"area", "time,area"}),
        outputs=frozenset({"assets"}),
        example='plugin.request(results, average="area")',
    ),
    Capability.CONCATENATE: CapabilitySpec(
        Capability.CONCATENATE,
        "concatenate the matched granules into one output (concatenate)",
        options=("concatenate",),
        outputs=frozenset({"assets"}),
        example='plugin.request(results, concatenate=True)',
    ),
    Capability.PROCESS: CapabilitySpec(
        Capability.PROCESS,
        "run an on-demand processor selected by api",
        options=("api",),
        outputs=frozenset({"assets", "dataframe"}),
        example='plugin.request(results, api="atl06p")',
    ),
}


class Explanation:
    """A rendered explanation: text in a terminal, HTML in Jupyter.

    Jupyter displays the ``_repr_html_()`` form automatically; everywhere else
    ``str()``/``repr()`` give the plain layout. No environment detection.
    """

    __slots__ = ("html", "text")

    def __init__(self, text: str, html: str = "") -> None:
        self.text = text
        self.html = html

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.text

    def __contains__(self, item: str) -> bool:
        return item in self.text

    def _repr_html_(self) -> str:
        return self.html or f"<pre>{escape(self.text)}</pre>"


def explain_capability(
    capability: Capability, example: str | None = None
) -> Explanation:
    """Describe one capability: meaning, options, return types and an example."""

    try:
        spec = CAPABILITY_SPECS[capability]
    except KeyError:
        raise KeyError(f"unknown capability {capability!r}") from None
    lines = [f"{capability} — {spec.summary}"]
    html = [
        f"<div><h4><code>{escape(str(capability))}</code></h4>"
        f"<div>{escape(spec.summary)}</div>"
    ]
    if spec.options:
        detail = ", ".join(spec.options)
        if spec.values:
            detail += f" ({' | '.join(sorted(spec.values))})"
        lines.append(f"  options: {detail}")
        html.append(f"<div>options: <code>{escape(detail)}</code></div>")
    if spec.outputs:
        lines.append("  returns:")
        rows = []
        for kind in sorted(spec.outputs):
            meaning = OUTPUT_TYPES.get(kind, "plugin-defined")
            lines.append(f"    {kind}: {meaning}")
            rows.append(
                f"<li><code>{escape(kind)}</code>: {escape(meaning)}</li>"
            )
        html.append("<div>returns:<ul>" + "".join(rows) + "</ul></div>")
    snippet = example or spec.example
    if snippet:
        lines.append(f"  example: {snippet}")
        html.append(f"<div>example: <code>{escape(snippet)}</code></div>")
    return Explanation("\n".join(lines), "".join(html) + "</div>")


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
    examples: Mapping[Capability, str] = field(default_factory=dict)
    """Per-plugin usage snippets; they override the generic spec example."""

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
            width = max(len(str(op)) for op in self.operations)
            for operation in sorted(self.operations, key=str):
                spec = CAPABILITY_SPECS[operation]
                lines.append(f"  {str(operation):<{width}}  {spec.summary}")
        if self.formats:
            lines.append("  formats: " + ", ".join(sorted(self.formats)))
        if self.apis:
            lines.append("  apis: " + ", ".join(sorted(self.apis)))
        if self.operations:
            lines.append("  hint: use .explain() for options and examples")
        return "\n".join(lines)

    def explain(self) -> Explanation:
        """A detailed, copy-pasteable explanation of what this plugin can do."""

        sections = [self._title()]
        html = [f"<div><b>{escape(self._title())}</b></div>"]
        if self.reason:
            sections.append(f"  {self.reason}")
            html.append(f"<div><i>{escape(self.reason)}</i></div>")
        for operation in sorted(self.operations, key=str):
            detail = explain_capability(operation, self.examples.get(operation))
            sections.extend(("", detail.text))
            html.append(detail.html)
        for label, values in (
            ("formats", sorted(self.formats)),
            ("apis", sorted(self.apis)),
        ):
            if values:
                text = f"{label}: " + ", ".join(values)
                sections.extend(("", text))
                html.append(f"<div>{escape(text)}</div>")
        return Explanation("\n".join(sections), "".join(html))

    def __repr__(self) -> str:
        return f"Capabilities({self._title()!r}, operations={len(self.operations)})"

    def _repr_html_(self) -> str:
        colour = {True: "#2e7d32", False: "#c62828", None: "#ef6c00"}[self.ok]
        icon = {True: "\u2713", False: "\u2717", None: "?"}[self.ok]
        parts = [
            f"<div><b>{escape(self.plugin or 'plugin')}</b> "
            f'<span style="color:{colour}">{icon} {self._label()}</span> '
            f"<code>{escape(self.collection)}</code></div>"
        ]
        if self.reason:
            parts.append(f"<div><i>{escape(self.reason)}</i></div>")
        if self.operations:
            rows = "".join(
                "<tr>"
                f"<td><code>{escape(str(operation))}</code></td>"
                f"<td>{escape(CAPABILITY_SPECS[operation].summary)}</td>"
                f"<td><code>{escape(CAPABILITY_SPECS[operation].example)}</code></td>"
                "</tr>"
                for operation in sorted(self.operations, key=str)
            )
            parts.append(
                "<table><tr><th>operation</th><th>description</th>"
                f"<th>example</th></tr>{rows}</table>"
            )
        for label, values in (
            ("formats", sorted(self.formats)),
            ("apis", sorted(self.apis)),
        ):
            if values:
                parts.append(
                    f"<div>{label}: "
                    + ", ".join(f"<code>{escape(value)}</code>" for value in values)
                    + "</div>"
                )
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
