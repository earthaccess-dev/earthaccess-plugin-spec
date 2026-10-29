import asyncio

import pytest

from earthaccess_plugin_spec import (
    TERMINAL_STATUSES,
    Capabilities,
    Capability,
    MissingResultsError,
    NotSupportedError,
    PluginBase,
    ResultSet,
    UnsupportedCollectionError,
    as_result_set,
    list_services,
    validate_inputs,
)
from earthaccess_plugin_spec.context import (
    LazyEDLAuthHandle,
    PluginContext,
    default_context,
)
from earthaccess_plugin_spec.errors import JobFailedError
from earthaccess_plugin_spec.job import Asset, Job, JobStatus
from earthaccess_plugin_spec.results import GranuleResultSet
from earthaccess_plugin_spec.support import ServiceRow, ServiceTable
from earthaccess_plugin_spec.testing import fake_context, sample_result_set

from .dummy import DummyAssetPlugin, DummyPlugin, GatedPlugin


def granule(concept_id="G1", collection_id="C1", ur="G1.EXAMPLE", umm=None):
    return {
        "meta": {"concept-id": concept_id, "collection-concept-id": collection_id},
        "umm": umm if umm is not None else {"GranuleUR": ur},
    }


class TestGranuleResultSet:
    def test_fields(self):
        rs = GranuleResultSet([granule()])
        assert rs.collection_id == "C1"
        assert rs.ids == ["G1"]
        assert rs.native_ids == ["G1.EXAMPLE"]
        assert rs.umm() == [{"GranuleUR": "G1.EXAMPLE"}]

    def test_empty(self):
        rs = GranuleResultSet([])
        assert rs.collection_id == ""
        assert rs.ids == []

    def test_multiple_collections_rejected(self):
        with pytest.raises(ValueError, match="one collection"):
            GranuleResultSet([granule(collection_id="C1"), granule(collection_id="C2")])


class TestAsResultSet:
    def test_none_passthrough(self):
        assert as_result_set(None) is None

    def test_result_set_passthrough(self):
        rs = sample_result_set()
        assert as_result_set(rs) is rs

    def test_list_wrapped(self):
        wrapped = as_result_set([granule()])
        assert isinstance(wrapped, GranuleResultSet)
        assert isinstance(wrapped, ResultSet)

    def test_as_result_set_does_not_read_collection_id(self):
        # A lazy resultset computes collection_id by scanning; as_result_set
        # must detect it cheaply and never trigger that.
        class Lazy:
            @property
            def collection_id(self):
                raise AssertionError("collection_id must not be read")

            def umm(self):
                return []

        lazy = Lazy()
        assert as_result_set(lazy) is lazy

    def test_validate_inputs_peeks_a_single_record(self):
        class Counting:
            def __init__(self) -> None:
                self.consumed = 0

            def __iter__(self):
                for i in range(10):
                    self.consumed += 1
                    yield {
                        "meta": {"concept-id": f"G{i}"},
                        "umm": {"GranuleUR": f"G{i}"},
                    }

        class Plugin:
            name = "p"
            needs = frozenset({"concept_id"})
            requires_results = True

        results = Counting()
        validate_inputs(Plugin, results)
        assert results.consumed == 1


class TestLocalJob:
    def test_success(self):
        plugin = DummyPlugin(fake_context())
        job = plugin.request(sample_result_set(), value=5)
        assert isinstance(job, Job)
        assert job.status() in (
            JobStatus.PENDING,
            JobStatus.RUNNING,
            JobStatus.SUCCEEDED,
        )
        assert job.wait(timeout=30) is JobStatus.SUCCEEDED
        assert job.status() is JobStatus.SUCCEEDED
        assert job.results() == {"value": 5}
        assert "request" not in job.info()

    def test_failure_raises_typed_error(self):
        plugin = DummyPlugin(fake_context())
        job = plugin.request(sample_result_set(), fail=True)
        assert job.wait(timeout=30) is JobStatus.FAILED
        with pytest.raises(JobFailedError):
            job.results()

    def test_wait_timeout_does_not_raise_for_failure(self):
        plugin = DummyPlugin(fake_context())
        job = plugin.request(sample_result_set(), fail=True)
        assert job.wait(timeout=30) is JobStatus.FAILED

    def test_repr_is_identity(self):
        plugin = DummyPlugin(fake_context())
        job = plugin.request(sample_result_set())
        assert plugin.name in repr(job)
        assert job.id in repr(job)

    def test_cancel_without_capability(self):
        plugin = DummyPlugin(fake_context())
        job = plugin.request(sample_result_set())
        with pytest.raises(NotSupportedError):
            job.cancel()

    def test_run_blocks(self):
        plugin = DummyPlugin(fake_context())
        assert plugin.request(sample_result_set(), value=3).results() == {"value": 3}

    def test_async(self):
        plugin = DummyPlugin(fake_context())
        job = asyncio.run(plugin.arequest(sample_result_set(), value=9))
        assert asyncio.run(job.await_done(timeout=30)) is JobStatus.SUCCEEDED
        assert asyncio.run(job.aresults()) == {"value": 9}


class TestValidation:
    def test_missing_results(self):
        plugin = DummyPlugin(fake_context())
        with pytest.raises(MissingResultsError):
            plugin.request(None)

    def test_missing_need(self):
        plugin = DummyPlugin(fake_context())
        stub = sample_result_set(ids=())
        with pytest.raises(MissingResultsError, match="concept_id"):
            plugin.request(stub)

    def test_unknown_option(self):
        plugin = DummyPlugin(fake_context())
        with pytest.raises(TypeError):
            plugin.request(sample_result_set(), nope=1)

    def test_get_job_not_supported(self):
        plugin = DummyPlugin(fake_context())
        with pytest.raises(NotSupportedError):
            plugin.get_job("abc")

    def test_umm_need_is_called_not_truthy_method(self):
        from earthaccess_plugin_spec import validate_inputs

        class UMMPlugin:
            name = "umm"
            needs = frozenset({"umm"})
            requires_results = True

        stub = sample_result_set(umms=[{}])
        with pytest.raises(MissingResultsError, match="umm"):
            validate_inputs(UMMPlugin(), stub)


class TestJobResultCaching:
    def test_results_fetched_once(self):
        class CountingJob(Job):
            resumable = True

            def __init__(self):
                super().__init__(plugin="counting", output="dataframe")
                self.fetches = 0

            def _poll(self):
                return JobStatus.SUCCEEDED, {"status": "successful"}

            def _fetch(self):
                self.fetches += 1
                return ["asset"]

        job = CountingJob()
        first = job.results()
        second = job.results()
        assert first is second
        assert job.fetches == 1


class TestAssetPlugin:
    def test_assets_output(self):
        plugin = DummyAssetPlugin(fake_context())
        assets = plugin.request(sample_result_set(), count=3).results()
        assert len(assets) == 3
        assert all(isinstance(a, Asset) for a in assets)
        assert assets[0].access == "https"


def test_plugin_is_subclass():
    assert issubclass(DummyPlugin, PluginBase)


def test_default_context_uses_lazy_edl_handle():
    ctx = default_context()
    assert isinstance(ctx, PluginContext)
    assert isinstance(ctx.auth, LazyEDLAuthHandle)
    assert ctx.label == "earthaccess"


class TestSupport:
    def test_default_is_supported(self):
        assert DummyPlugin(fake_context()).capabilities(sample_result_set()).ok is True

    def test_unsupported_raises_before_request(self):
        plugin = GatedPlugin(fake_context())
        results = sample_result_set(collection_id="C-OTHER")
        with pytest.raises(UnsupportedCollectionError) as excinfo:
            plugin.request(results)
        assert "does not support" in str(excinfo.value)
        assert excinfo.value.collection_id == "C-OTHER"

    def test_check_false_bypasses(self):
        plugin = GatedPlugin(fake_context())
        results = sample_result_set(collection_id="C-OTHER")
        job = plugin.request(results, check=False)
        assert job.results() == "ok"

    def test_supports_is_cached_per_collection(self):
        plugin = GatedPlugin(fake_context())
        results = sample_result_set(collection_id="C1")
        assert plugin.capabilities(results).ok is True
        assert plugin.capabilities(results).ok is True
        assert plugin.checks == 1

    def test_check_is_reserved(self):
        from dataclasses import dataclass

        with pytest.raises(TypeError, match="reserved"):

            @dataclass
            class BadOptions:
                check: bool = False

            class BadPlugin(PluginBase):
                name = "bad"
                auth = "none"
                output = "dataframe"
                Options = BadOptions

                def _request(self, results, options):  # noqa: ANN001, ANN201
                    return self.job(lambda: None)

    def test_capabilities_accepts_short_name(self):
        plugin = GatedPlugin(fake_context())
        assert plugin.capabilities("C1").ok is True
        assert plugin.capabilities("C-OTHER").ok is False

    def test_capabilities_repr_is_informative(self):
        caps = Capabilities(
            True,
            plugin="harmony",
            collection="ATL06",
            operations=frozenset({Capability.SUBSET_BBOX, Capability.SUBSET_VARIABLE}),
            formats=frozenset({"application/netcdf4"}),
        )
        text = str(caps)
        assert "harmony" in text and "ATL06" in text and "subset_bbox" in text
        assert "harmony" in repr(caps)
        assert "ATL06" in caps._repr_html_()

    def test_capability_enum_values(self):
        assert Capability.LAZY_READ == "lazy_read"
        assert str(Capability.SUBSET_BBOX) == "subset_bbox"


class TestGranuleResultSetExtras:
    def test_short_name_and_version(self):
        g = granule(
            umm={
                "GranuleUR": "G1",
                "CollectionReference": {"ShortName": "ATL06", "Version": "006"},
            }
        )
        rs = GranuleResultSet([g])
        assert rs.short_name == "ATL06"
        assert rs.version == "006"

    def test_is_a_list(self):
        rs = GranuleResultSet([granule()])
        assert isinstance(rs, list)
        assert len(rs) == 1

    def test_slice_preserves_type_and_services(self):
        rs = GranuleResultSet(
            [granule(concept_id="g1"), granule(concept_id="g2")],
            services=[{"Type": "Harmony", "Name": "svc"}],
        )
        sliced = rs[:1]
        assert isinstance(sliced, GranuleResultSet)
        assert len(sliced) == 1
        assert sliced.services() == [{"Type": "Harmony", "Name": "svc"}]


class TestListServices:
    def test_table_renders(self):
        table = ServiceTable(
            [ServiceRow("harmony", False, "no service"), ServiceRow("sliderule", True)]
        )
        text = repr(table)
        assert "plugin" in text and "harmony" in text and "sliderule" in text
        assert table.accepting() == ["sliderule"]

    def test_list_services_queries_installed(self, monkeypatch):
        from earthaccess_plugin_spec import discovery

        monkeypatch.setattr(
            discovery, "installed_plugins", lambda group=None: {"gated": GatedPlugin}
        )
        table = list_services(sample_result_set(collection_id="C1"))
        assert [row.plugin for row in table] == ["gated"]
        assert table.rows[0].ok is True

    def test_result_set_list_services(self, monkeypatch):
        from earthaccess_plugin_spec import discovery

        monkeypatch.setattr(
            discovery, "installed_plugins", lambda group=None: {"gated": GatedPlugin}
        )
        rs = GranuleResultSet([granule(collection_id="C1")])
        table = rs.list_services()
        assert [row.plugin for row in table] == ["gated"]
        assert table.rows[0].ok is True


class TestGranules:
    def test_accessors_read_sparse_records_without_raising(self):
        from earthaccess_plugin_spec.granules import (
            collection_concept_id,
            concept_id,
            native_id,
            related_urls,
            short_name,
            version,
        )

        assert concept_id({}) == ""
        assert native_id({"umm": {}}) == ""
        assert collection_concept_id({"meta": None}) == ""
        assert related_urls({"umm": {"RelatedUrls": [{"URL": "u"}]}}) == [{"URL": "u"}]
        assert related_urls({}) == []
        assert short_name({}) == "" and version({}) == ""

    def test_accessors_read_values(self):
        from earthaccess_plugin_spec.granules import (
            collection_concept_id,
            concept_id,
            native_id,
            short_name,
            version,
        )

        record = granule(
            umm={
                "GranuleUR": "G1",
                "CollectionReference": {"ShortName": "ATL06", "Version": "006"},
            }
        )
        assert concept_id(record) == "G1"
        assert native_id(record) == "G1"
        assert collection_concept_id(record) == "C1"
        assert short_name(record) == "ATL06"
        assert version(record) == "006"

    def test_granule_field_matches_declared_needs(self):
        from earthaccess_plugin_spec.granules import NEEDS, granule_field

        record = granule()
        assert granule_field(record, "concept_id") == "G1"
        assert granule_field(record, "native_id") == "G1.EXAMPLE"
        assert granule_field(record, "umm") == {"GranuleUR": "G1.EXAMPLE"}
        assert {"concept_id", "native_id", "umm"} == NEEDS
        with pytest.raises(KeyError):
            granule_field(record, "nope")

    def test_peek_and_collection_label_do_not_materialize(self):
        from earthaccess_plugin_spec import collection_label, peek

        class Lazy:
            def __init__(self) -> None:
                self.consumed = 0

            @property
            def short_name(self) -> str:
                return ""

            def __iter__(self):
                for _ in range(10):
                    self.consumed += 1
                    yield {"meta": {"collection-concept-id": "C1"}}

        lazy = Lazy()
        assert peek(lazy) == {"meta": {"collection-concept-id": "C1"}}
        assert lazy.consumed == 1
        assert peek(iter(())) is None
        assert peek(object()) is None
        assert collection_label(lazy) == "C1"

    def test_collection_label_prefers_short_name(self):
        from earthaccess_plugin_spec import collection_label

        assert collection_label(sample_result_set(short_name="ATL06")) == "ATL06"
        assert collection_label(sample_result_set(short_name="")) == "C1234-EXAMPLE"


class TestJobCapabilities:
    def test_base_job_advertises_nothing(self):
        job = Job(plugin="p", output="dataframe")
        assert job.capabilities == frozenset()
        with pytest.raises(NotSupportedError):
            job.pause()
        with pytest.raises(NotSupportedError):
            job.resume()

    def test_capabilities_are_derived_from_overridden_hooks(self):
        class Cancellable(Job):
            def _cancel(self):
                return True

        class Pausable(Job):
            def pause(self):
                return True

            def resume(self):
                return True

        assert Cancellable(plugin="p", output="assets").capabilities == {"cancel"}
        assert Pausable(plugin="p", output="assets").capabilities == {"pause", "resume"}

    def test_explicit_capabilities_win(self):
        class NoPause(Job):
            capabilities = frozenset({"cancel"})

            def pause(self):
                return True

            def _cancel(self):
                return True

        assert NoPause(plugin="p", output="assets").capabilities == {"cancel"}

    def test_terminal_statuses_match_wait(self):
        assert {
            JobStatus.PAUSED,
            JobStatus.SUCCEEDED,
            JobStatus.PARTIAL,
            JobStatus.FAILED,
            JobStatus.CANCELED,
        } == TERMINAL_STATUSES


class TestGranuleResultSetOverrides:
    def test_short_name_and_version_override(self):
        rs = GranuleResultSet([granule()], short_name="ATL06", version="006")
        assert rs.short_name == "ATL06"
        assert rs.version == "006"

    def test_slice_preserves_short_name(self):
        rs = GranuleResultSet(
            [granule(concept_id="g1"), granule(concept_id="g2")],
            short_name="ATL06",
        )
        assert rs[:1].short_name == "ATL06"

    def test_sparse_record_does_not_raise(self):
        rs = GranuleResultSet([{}, {"meta": {"concept-id": "G1"}}])
        assert rs.collection_id == ""
        assert rs.ids == ["", "G1"]
        assert rs.version == ""

    def test_blank_labels_do_not_look_like_two_collections(self):
        rs = GranuleResultSet([granule(collection_id="C1"), {}])
        assert rs.collection_id == "C1"


class TestVocabulary:
    def test_outputs_and_auths_are_shared(self):
        from earthaccess_plugin_spec import AUTHS, OUTPUTS

        assert {"assets", "xarray", "dataframe", "opendap"} == set(OUTPUTS)
        assert {"edl", "own", "none"} == set(AUTHS)

    def test_unknown_need_is_rejected_at_class_creation(self):
        with pytest.raises(TypeError, match="unknown value"):

            class BadNeed(PluginBase):
                name = "bad-need"
                needs = frozenset({"nope"})
                auth = "none"
                output = "dataframe"
                Options = GatedPlugin.Options


class TestFormats:
    def test_format_name_normalises_backend_spellings(self):
        from earthaccess_plugin_spec import format_name

        assert format_name("application/netcdf4") == "netcdf4"
        assert format_name("application/x-netcdf4") == "netcdf4"
        assert format_name("image/tiff") == "geotiff"
        assert format_name("application/vnd.apache.parquet") == "geoparquet"
        assert format_name("GEOPARQUET") == "geoparquet"
        assert format_name("application/octet-stream") is None

    def test_formats_are_the_asset_format_vocabulary(self):
        from typing import get_args

        from earthaccess_plugin_spec import FORMATS, Format

        assert set(get_args(Format)) == FORMATS


class TestCapabilitySpecs:
    def test_every_capability_has_a_spec(self):
        from earthaccess_plugin_spec import CAPABILITY_SPECS, Capability

        assert set(CAPABILITY_SPECS) == set(Capability)

    def test_specs_are_bounded_by_the_contract_vocabulary(self):
        from earthaccess_plugin_spec import CAPABILITY_SPECS, OUTPUTS

        for spec in CAPABILITY_SPECS.values():
            assert spec.summary, f"{spec.capability} needs a normative summary"
            assert spec.outputs <= set(OUTPUTS), (
                f"{spec.capability} uses an unknown output kind"
            )
            if spec.case:
                assert spec.options, (
                    f"{spec.capability} is behavioural but names no option"
                )


class TestCapabilityRendering:
    @staticmethod
    def _caps():
        return Capabilities(
            True,
            plugin="harmony",
            collection="ATL06",
            operations=frozenset(
                {Capability.SUBSET_VARIABLE, Capability.REPROJECT}
            ),
            formats=frozenset({"netcdf4"}),
        )

    def test_str_shows_a_summary_per_operation(self):
        text = str(self._caps())
        assert "harmony supported ATL06" in text
        assert "select a subset of variables" in text
        assert "reproject the result" in text
        assert "hint: use .explain()" in text
        assert "formats: netcdf4" in text

    def test_explain_lists_options_return_types_and_examples(self):
        text = self._caps().explain()
        assert "subset_variable — select a subset of variables" in text
        assert "options: variables" in text
        assert "assets: list[Asset] (href/access/format)" in text
        assert "opendap: native backend objects" in text
        assert 'example: plugin.request(results, variables=["var1", "var2"])' in text
        assert "reproject — reproject the result" in text

    def test_explain_prefers_a_plugin_specific_example(self):
        caps = Capabilities(
            True,
            plugin="pydap",
            collection="MUR-JPL-L4-GLOB-v4.1",
            operations=frozenset({Capability.LAZY_READ}),
            examples={
                Capability.LAZY_READ: (
                    'pyds = ea.plugins.pydap.request(results, client="pydap").results()[0]'
                )
            },
        )
        text = caps.explain()
        assert 'client="pydap"' in text
        assert "ea.open(job)" not in text

    def test_capabilities_without_a_target_is_an_error(self):
        with pytest.raises(TypeError, match="needs search results"):
            DummyPlugin(fake_context()).capabilities()

    def test_output_types_cover_every_output_kind(self):
        from earthaccess_plugin_spec import OUTPUT_TYPES, OUTPUTS

        assert set(OUTPUT_TYPES) == set(OUTPUTS)

    def test_html_is_a_meaning_and_example_table(self):
        html = self._caps()._repr_html_()
        assert "<th>operation</th><th>description</th><th>example</th>" in html
        assert "select a subset of variables" in html
        assert "plugin.request(results, variables=" in html
        assert "netcdf4" in html

    def test_repr_stays_a_single_line(self):
        text = repr(self._caps())
        assert "\n" not in text
        assert "operations=2" in text

    def test_explain_capability_rejects_unknown_values(self):
        from earthaccess_plugin_spec import explain_capability

        with pytest.raises(KeyError, match="unknown capability"):
            explain_capability("nope")  # type: ignore[arg-type]

    def test_every_spec_has_an_example(self):
        from earthaccess_plugin_spec import CAPABILITY_SPECS

        for spec in CAPABILITY_SPECS.values():
            assert spec.example, f"{spec.capability} needs an example"


class TestExplanationDisplay:
    @staticmethod
    def _explain():
        caps = Capabilities(
            True,
            plugin="pydap",
            collection="MUR",
            operations=frozenset({Capability.SUBSET_VARIABLE}),
        )
        return caps.explain()

    def test_text_and_str_agree(self):
        explanation = self._explain()
        assert str(explanation) == explanation.text
        assert "options: variables" in explanation
        assert "native backend objects" in explanation

    def test_repr_is_the_text_not_a_quoted_string(self):
        text = repr(self._explain())
        assert not text.startswith("'")
        assert "subset_variable —" in text

    def test_jupyter_gets_html(self):
        html = self._explain()._repr_html_()
        assert "<code>subset_variable</code>" in html
        assert "list[Asset]" in html
        assert "plugin.request(results, variables=" in html

    def test_explain_capability_is_also_displayable(self):
        from earthaccess_plugin_spec import Explanation, explain_capability

        explanation = explain_capability(Capability.REPROJECT)
        assert isinstance(explanation, Explanation)
        assert "<code>crs</code>" in explanation._repr_html_()


class TestJobReprState:
    def test_repr_refreshes_a_local_job(self):
        import time

        job = Job(lambda: 1, plugin="p", output="dataframe")
        deadline = time.monotonic() + 5
        text = repr(job)
        while "SUCCEEDED" not in text and time.monotonic() < deadline:
            time.sleep(0.01)
            text = repr(job)
        assert "SUCCEEDED" in text

    def test_repr_does_not_poll_a_remote_job(self):
        class RemoteJob(Job):
            def _poll(self):
                raise AssertionError("repr must not poll a remote job")

        job = RemoteJob(plugin="p", output="assets")
        assert "PENDING" in repr(job)
