"""A minimal plugin used to exercise the contract and the conformance suite."""

from __future__ import annotations

from dataclasses import dataclass
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
