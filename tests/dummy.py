"""A minimal plugin used to exercise the contract and the conformance suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from earthaccess_plugin_spec import Asset, Capabilities, PluginBase


@dataclass
class Options:
    value: int = 1
    fail: bool = False


class DummyPlugin(PluginBase):
    name = "dummy"
    needs = frozenset({"concept_id"})
    auth = "none"
    output = "dataframe"
    Options = Options

    def _request(self, results: Any, options: Any) -> Any:
        def work() -> dict[str, int]:
            if options.fail:
                raise RuntimeError("boom")
            return {"value": options.value}

        return self.job(work)


@dataclass
class AssetOptions:
    count: int = 1


class DummyAssetPlugin(PluginBase):
    name = "dummy-assets"
    needs = frozenset({"concept_id"})
    auth = "none"
    output = "assets"
    Options = AssetOptions

    def _request(self, results: Any, options: AssetOptions) -> Any:
        def work() -> list[Asset]:
            return [
                Asset(href=f"https://example.org/{i}.nc4", access="https")
                for i in range(options.count)
            ]

        return self.job(work)


@dataclass
class VirtualOptions:
    concat_dim: str | None = None
    store: str | None = None


class _FakeVirtualDataset:
    """Duck-typed stand-in for a ManifestArray-backed ``xarray.Dataset``.

    The contract only requires ``.variables`` (Dataset) or ``.children``
    (DataTree), so the conformance suite stays dependency-free.
    """

    variables = {"sst": object()}


class DummyVirtualPlugin(PluginBase):
    """Virtual-dataset output, the way the ``vds`` plugin uses it.

    Without ``store`` the job's result is the virtual dataset itself
    (``output="virtual"``); with ``store`` the plugin virtualizes *and*
    persists, returning a one-asset store result (``output="assets"``).
    """

    name = "dummy-virtual"
    needs = frozenset({"concept_id"})
    auth = "none"
    output = "virtual"
    Options = VirtualOptions

    def _supports(self, results: Any) -> Capabilities:
        from earthaccess_plugin_spec import Capability

        return Capabilities(
            True,
            operations=frozenset({Capability.VIRTUALIZE, Capability.APPEND}),
            formats=frozenset({"icechunk", "kerchunk"}),
        )

    def _request(self, results: Any, options: VirtualOptions) -> Any:
        if options.store is None:
            return self.job(lambda: _FakeVirtualDataset())
        return self.job(
            lambda: [
                Asset(
                    href=options.store,
                    access="file",
                    auth="none",
                    format="icechunk",
                )
            ],
            output="assets",
        )


class GatedPlugin(PluginBase):
    name = "gated"
    needs = frozenset({"concept_id"})
    auth = "none"
    output = "dataframe"
    Options = Options
    allowed = frozenset({"C1"})

    def __init__(self, ctx: Any) -> None:
        super().__init__(ctx)
        self.checks = 0

    def _supports(self, results: Any) -> Capabilities:
        self.checks += 1
        key = getattr(results, "collection_id", "") or getattr(
            results, "short_name", ""
        )
        if key in self.allowed:
            return Capabilities(True)
        return Capabilities(False, reason=f"{key} is not supported")

    def _request(self, results: Any, options: Any) -> Any:
        return self.job(lambda: "ok")


@dataclass
class VariableOptions:
    variables: list[str] = field(default_factory=list)


class VariablePlugin(PluginBase):
    """Advertises SUBSET_VARIABLE through the canonical ``variables`` option."""

    name = "variable"
    auth = "none"
    output = "dataframe"
    Options = VariableOptions

    def _supports(self, results: Any) -> Capabilities:
        from earthaccess_plugin_spec import Capability

        return Capabilities(True, operations=frozenset({Capability.SUBSET_VARIABLE}))

    def _request(self, results: Any, options: VariableOptions) -> Any:
        return self.job(lambda: {"variables": list(options.variables)})


class MisclaimedPlugin(PluginBase):
    """Advertises SUBSET_VARIABLE without a ``variables`` option."""

    name = "misclaimed"
    auth = "none"
    output = "dataframe"
    Options = Options

    def _supports(self, results: Any) -> Capabilities:
        from earthaccess_plugin_spec import Capability

        return Capabilities(True, operations=frozenset({Capability.SUBSET_VARIABLE}))

    def _request(self, results: Any, options: Any) -> Any:
        return self.job(lambda: "ok")
