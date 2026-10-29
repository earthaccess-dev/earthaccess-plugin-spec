import pytest

from earthaccess_plugin_spec import Capability, PluginBase
from earthaccess_plugin_spec.testing import Fixtures, run_conformance

from .dummy import (
    DummyAssetPlugin,
    DummyPlugin,
    MisclaimedPlugin,
    VariablePlugin,
)


def test_dummy_plugin_conforms():
    run_conformance(
        DummyPlugin,
        fixtures=Fixtures(options={"value": 7}, failing_options={"fail": True}),
    )


def test_dummy_asset_plugin_conforms():
    run_conformance(DummyAssetPlugin, fixtures=Fixtures(options={"count": 2}))


class BrokenPlugin(PluginBase):
    name = "broken"
    auth = "none"
    output = "dataframe"
    Options = DummyPlugin.Options

    def _request(self, results, options):
        return "not a job"


def test_conformance_detects_broken_plugin():
    with pytest.raises(AssertionError, match="conformance failed"):
        run_conformance(BrokenPlugin, fixtures=Fixtures())


def test_capability_contract_passes_with_a_case():
    run_conformance(
        VariablePlugin,
        fixtures=Fixtures(
            capability_cases={Capability.SUBSET_VARIABLE: {"variables": ["x"]}}
        ),
    )


def test_advertised_capability_needs_a_behavioural_case():
    with pytest.raises(AssertionError, match="capability_cases"):
        run_conformance(VariablePlugin, fixtures=Fixtures())


def test_advertised_capability_must_be_expressible():
    with pytest.raises(AssertionError, match="subset_variable"):
        run_conformance(
            MisclaimedPlugin,
            fixtures=Fixtures(
                capability_cases={Capability.SUBSET_VARIABLE: {"value": 1}}
            ),
        )
