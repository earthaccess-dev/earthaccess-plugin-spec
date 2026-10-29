# The plugin contract (reference)

Detailed reference for what a plugin implements. The [README](../README.md) is
the quick start; this is the full picture.

A plugin implements **two** classes from `earthaccess_plugin_spec`:

- `PluginBase` — subclass it **always**.
- `Job` — subclass it **only** for a remote backend you poll.

## How earthaccess discovers and imports plugins

Plugins register a class under the `earthaccess.plugins` entry-point group:

```toml
[project.entry-points."earthaccess.plugins"]
myplugin = "earthaccess_myplugin:MyPlugin"
```

Discovery reads **distribution metadata only**; it never imports a plugin module
(and hence never a backend). A module is imported the first time it is used:

| Call | Imports |
| --- | --- |
| `ea.list_plugins()` | `importlib.metadata` only |
| `ea.list_plugins(details=True)` | each installed plugin **module** (not its backend) |
| `ea.plugins.myplugin` | `earthaccess_myplugin`, then instantiates `MyPlugin` with a `PluginContext` |

A `contract_version` mismatch is rejected at load. Because of this, **import your
backend inside methods, never at module level**, so discovery stays cheap.

## `PluginBase`

```python
class MyPlugin(PluginBase):
    name: ClassVar[str]                       # the plugin name (matches the entry point)
    contract_version: ClassVar[int] = 1       # major; a mismatch is rejected at load
    needs: ClassVar[frozenset[str]] = frozenset()   # subset of {'concept_id','native_id','umm'}
    requires_results: ClassVar[bool] = True
    auth: ClassVar[Literal["edl", "own", "none"]]
    output: ClassVar[str]                     # one of OUTPUTS; 'assets' is special
    Options: ClassVar[type]                    # a dataclass, validated by the core

    def __init__(self, ctx: PluginContext): ...

    # implement this
    def _request(self, results, options) -> Job: ...

    # optional
    def _supports(self, results) -> Capabilities: ...   # default: Capabilities(True)
    def get_job(self, job_id) -> Job: ...               # only if resumable
```

The core provides `request()`, `arequest()`, `job()` and `capabilities()`:

```python
def request(self, results=None, *, check=True, **options) -> Job:
    results = as_result_set(results)      # plain list[dict] -> GranuleResultSet
    validate_inputs(self, results)        # requires_results + needs (peek, not materialize)
    if check and results is not None:     # _supports() must not be False
        ...
    return self._request(results, self.Options(**options))  # unknown kwargs -> TypeError
```

- `needs` is **checked, not fetched**: the core peeks one granule record; it
  never materializes the (possibly lazy) resultset. See [ResultSet](#resultset).
- `check=False` bypasses the support check for a dataset you know the service
  accepts.
- `self.job(fn)` returns a local `Job` (see below).

## The Job lifecycle

`request()` returns a `Job` immediately. Callers drive every job the same way:

```python
job.status()          # PENDING | RUNNING | PAUSED | SUCCEEDED | PARTIAL | FAILED | CANCELED
job.info()            # backend detail (a dict); never the request payload
job.results()         # blocks until settled, then returns the output (or raises)
job.wait(timeout=60)  # wait without fetching; returns the final status
job.cancel()          # only if 'cancel' is in capabilities
repr(job)             # never makes a network call
```

Async mirrors: `await job.astatus()`, `await job.await_done()`, `await job.aresults()`,
`await job.acancel()`.

`wait()` returns on PAUSED or any terminal state (`TERMINAL_STATUSES`) and never
raises because a job
failed (it raises `TimeoutError` on timeout). `results()` then:

- `FAILED` → raises `JobFailedError`
- `CANCELED` → raises `JobCanceledError`
- `PAUSED` → raises `JobPausedError` (resume or skip the preview)
- `PARTIAL` → returns what succeeded (`info()` carries the error detail)
- `SUCCEEDED` → returns the output

Results are fetched once; repeated `results()` reuses them.

## Three shapes

**A value in hand** (PyDAP builds OPeNDAP URLs) and **local compute**
(SlideRule) both use `self.job(fn)`:

```python
def _request(self, results, options):
    return self.job(lambda: do_the_work())   # core runs fn in a background thread
```

A value in hand is a function that returns at once; a local compute job is one
that takes a while. `status()` is `PENDING`/`RUNNING` until it settles. No
subclass is needed.

**Remote, polled** (Harmony) subclasses `Job`:

```python
from earthaccess_plugin_spec import Job, JobStatus

class MyJob(Job):
    resumable = True          # plugin.get_job(id) can rebuild it
    poll_every = 2.0          # seconds between polls
    # capabilities is derived: override _cancel() and it advertises 'cancel'.

    def __init__(self, job_id, client):
        super().__init__(plugin="myplugin", output="assets", id=job_id)
        self._client = client

    def _poll(self):                      # one call -> (status, info)
        info = self._client.status(self.id)
        info.pop("request", None)         # never expose the payload
        raw = info.get("status")
        return {
            "queued": JobStatus.PENDING,
            "running": JobStatus.RUNNING,
            "done": JobStatus.SUCCEEDED,
        }.get(raw, JobStatus.RUNNING), info

    def _fetch(self):                     # output of a settled job
        return [Asset(href=u, access="s3") for u in self._client.result_urls(self.id)]

    def _cancel(self):
        self._client.cancel(self.id)
        return True
```

`Job` class attributes: `resumable` (bool), `capabilities` (subset of
`{'cancel','pause','resume'}`), `poll_every` (seconds). `capabilities` is derived
from which of `_cancel()`, `pause()` and `resume()` the subclass overrides, so it
cannot drift; declaring it explicitly still wins. The plugin's `get_job(job_id)`
rebuilds the job when `resumable = True`.

## Output and `ea.open` / `ea.download`

`output` tells earthaccess how to treat `results()`:

| `output` | `results()` returns | `ea.open(job)` / `ea.download(job, path)` |
| --- | --- | --- |
| `assets` | `list[Asset]` (files) | opened / downloaded by earthaccess |
| `xarray`, `dataframe`, `opendap`, ... | whatever the plugin deems correct | `ea.open` returns it as-is; `download` is not supported |

An `Asset` is `Asset(href, access, auth="edl", format=None)` where `access` is
`'https'`, `'s3'` or `'opendap'`. For non-asset outputs, `results()` returns any
object — a lazy `xarray.Dataset`, a `GeoDataFrame`, native PyDAP datasets, OPeNDAP
URLs, ... — and earthaccess hands it straight back.

## Capabilities (`_supports`)

`_supports(results)` returns a `Capabilities`: a tri-state `ok`
(`True`/`False`/`None`) plus the `operations` (`Capability` enum), `formats` and
`apis` a collection supports.

- `False` → `request()` raises `UnsupportedCollectionError` listing the plugins
  that do accept the results.
- `None` ("could not tell") → warns once, then proceeds. Use it when the check
  depends on flaky evidence (CMR associations, capabilities endpoints).
- `True` → proceed.

Users ask with `plugin.capabilities(results)` /
`plugin.capabilities("ATL06")`, or list every installed plugin's answer with
`results.list_services()` / `ea.list_services(results)`.

### What each operation means

Every `Capability` has a normative `CapabilitySpec` (`CAPABILITY_SPECS`) and an
advertised operation must be requestable through its canonical `Options` field:

| Operation | Meaning | Canonical option(s) | Result kinds |
| --- | --- | --- | --- |
| `lazy_read` | read slices without downloading the granule | — (a read property) | any |
| `subset_bbox` | restrict to a spatial extent | `bbox` or `wkt` | assets, xarray, dataframe |
| `subset_temporal` | restrict to a time interval | `temporal` | assets, xarray, dataframe |
| `subset_variable` | select variables; unknown names raise | `variables` | assets, xarray, dataframe |
| `subset_dimension` | select along named dimensions | `dimensions` | assets, xarray |
| `subset_shape` | restrict to a shapefile/region | `shapefile` | assets, xarray, dataframe |
| `reproject` | reproject to a target CRS | `crs` | assets, xarray |
| `average_time` | average over time | `average` (`time`, `time,area`) | assets |
| `average_area` | average over area | `average` (`area`, `time,area`) | assets |
| `concatenate` | concatenate the matched granules | `concatenate` | assets |
| `process` | run an on-demand processor | `api` | assets, dataframe |

The summary says what the **result** guarantees, not how the backend implements
it; two plugins advertising `subset_variable` must both accept `variables=[...]`
and both fail on an unknown name. `apis` remains free-form for backend-specific
processor names.

### Formats

`Capabilities.formats` uses the same vocabulary as `Asset.format` — `netcdf4`,
`zarr`, `geoparquet`, `csv`, `geotiff` (`FORMATS`). Map backend spellings with
`format_name()`; unknown formats are omitted rather than leaked:

```python
>>> format_name("application/netcdf4")
'netcdf4'
>>> format_name("image/tiff")
'geotiff'
>>> format_name("application/octet-stream") is None
True
```

### Adding a capability

Only add to the `Capability` enum when all of these hold:

1. the name is lowercase `verb_noun` and there is no synonym in use;
2. the spec summary states the result guarantee **and** the failure behaviour;
3. there is a canonical `Options` field a caller can set (otherwise it belongs in
   `apis`, not `operations`);
4. at least two backends could plausibly implement it;
5. it is not a parameterisation of an existing capability.

Then add the enum member, its `CAPABILITY_SPECS` entry, a docs row, and a
`Fixtures.capability_cases` example. If the capability already exists, map your
backend vocabulary onto it and do not advertise it unless you can honour the
canonical option — a narrower implementation should stay out of `operations`.

## ResultSet

Plugins receive search results (`ea.search_data()` output) or a plain
`list[dict]` (wrapped into `GranuleResultSet`). A `ResultSet` may be **lazy**:
iterating it streams the results from CMR one bounded page at a time. **Plugins
should iterate and project the fields they need** (`for granule in results`) and
avoid the convenience accessors `collection_id` / `ids` / `native_ids` /
`umm()`, which may materialize the whole set.

A raw granule record is a mapping with `meta["concept-id"]`,
`meta["collection-concept-id"]` and `umm` (the UMM-G). `short_name` and `version`
come from the search query when known (the granule UMM does not always carry the
short name).

Do not walk those mappings by hand: `earthaccess_plugin_spec.granules` exposes
`peek(results)`, `collection_label(results)`, `concept_id(granule)`,
`native_id(granule)`, `collection_concept_id(granule)`, `short_name(granule)`,
`version(granule)` and `related_urls(granule)`. They tolerate sparse records and
never materialize a lazy resultset.

## Errors

All plugin errors derive from `EarthaccessPluginError`: `PluginNotFoundError`,
`PluginLoadError`, `MissingResultsError`, `NotSupportedError`,
`UnsupportedCollectionError`, `UnsupportedOutputError`, and the job errors
`JobError` → `JobFailedError` / `JobCanceledError` / `JobPausedError`.

## Conformance suite

```python
from earthaccess_plugin_spec.testing import Fixtures, run_conformance


class MyFixtures(Fixtures):
    def backend(self):
        return patch_my_backend()  # a context manager


def test_conformance():
    run_conformance(
        MyPlugin,
        fixtures=MyFixtures(
            options={"format": "zarr"},
            capability_cases={
                Capability.SUBSET_BBOX: {"bbox": (-110, 40, -109, 41)},
            },
        ),
    )
```

`run_conformance` checks option rejection, `requires_results`, `needs`,
`capabilities()`, the job contract (id/plugin/output/resumable/capabilities), settling, `info()`/`repr()`, `results()` typing, `check=False`,
and the error paths. It fails with a list of every check that did not pass.
