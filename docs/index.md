# earthaccess plugins

earthaccess plugins let you reach services that are not part of `earthaccess`
itself without growing the core library. Each plugin is a small, independently
installable package that implements one remote or local backend and registers
itself with earthaccess.

```bash
pip install earthaccess-plugin-harmony   # or -pydap, -sliderule
```

> **Pre-release:** the packages are not on PyPI yet — see
> [Installing the current drafts](installing-drafts.md).

Once installed, a plugin appears under `ea.plugins`:

```python
import earthaccess as ea

ea.list_plugins()                 # table of installed plugins
results = ea.search_data(short_name="ATL06", ...)
job = ea.plugins.harmony.request(results, variables=["/gt1l/land_ice_segments/h_li"])
assets = ea.open(job)             # or ea.download(job, "./data")
```

## The plugins

| Plugin | Upstream service | Returns | Auth | Job |
| --- | --- | --- | --- | --- |
| [harmony](plugins/harmony.md) | NASA Harmony | `list[Asset]` | Earthdata Login | remote, resumable |
| [pydap](plugins/pydap.md) | OPeNDAP via PyDAP | lazy `xarray.Dataset` | Earthdata Login | local |
| [sliderule](plugins/sliderule.md) | SlideRule | `GeoDataFrame` | its own | local |

## The contract in one screen

Plugins are written against two classes from
[`earthaccess-plugin-spec`](https://github.com/betolink/earthaccess-plugin-spec):

- **`PluginBase`** — **always** subclass it, declare `Options` (a dataclass) and
  implement `_request()`. Optionally override `_supports()` to report the
  collection's capabilities.
- **`Job`** — one class for both modes. Local work is `self.job(fn)`. Subclass
  `Job` **only for a remote backend** that you poll, overriding `_poll` /
  `_fetch` / `_cancel` (and setting `resumable`/`capabilities`/`poll_every`).

See the [full contract reference](contract.md) for the class fields, job hooks
and errors.

Every request follows the same shape regardless of backend:

```python
job = ea.plugins.<name>.request(results, **options)   # returns immediately
job.status()       # PENDING / RUNNING / PAUSED / SUCCEEDED / PARTIAL / FAILED / CANCELED
job.info()         # backend detail; never the request payload
job.results()      # blocks, returns the plugin's output
```

## Collection capabilities

Passing results a plugin cannot handle fails early, before any backend call.
Each plugin implements a cheap, collection-level `_supports()` check and reports
a **`Capabilities`** object: a tri-state `ok` (`True`/`False`/`None`) plus the
operations, output formats and (where relevant) server APIs it can use. There is
a `Capability` enum (`subset_bbox`, `reproject`, `lazy_read`, `process`, ...).

| Plugin | Evidence it uses | Network | Reports |
| --- | --- | --- | --- |
| harmony | the capabilities endpoint | one cached call | subset/reproject/average/concatenate operations + formats |
| pydap | OPeNDAP links already in the granule UMM | none | lazy read + variable subsetting |
| sliderule | a hardcoded allowlist of dataset short names | none | processors (`apis`) + bbox/temporal subsetting |

```python
>>> ea.plugins.harmony.capabilities(results)
harmony supported ATL06
  subset_bbox      restrict the result to a spatial extent (bbox or wkt)
  subset_temporal  restrict the result to a time interval (temporal)
  subset_variable  select a subset of variables; an unknown name raises
  formats: netcdf4
  hint: use .explain() for options and examples

>>> ea.plugins.harmony.capabilities(results).explain()
harmony supported ATL06

subset_bbox — restrict the result to a spatial extent (bbox or wkt)
  options: bbox, wkt
  outputs: assets, dataframe, xarray
  example: plugin.request(results, bbox=(west, south, east, north))
...

>>> ea.plugins.sliderule.capabilities("ATL06")   # by short name
sliderule supported ATL06
  process          run an on-demand processor selected by api
  subset_bbox      restrict the result to a spatial extent (bbox or wkt)
  subset_temporal  restrict the result to a time interval (temporal)
  formats: geoparquet
  apis: atl03sp, atl03x, atl06p, ... gedil4a
  hint: use .explain() for options and examples

>>> results.list_services()
plugin     supported  detail
--------   ---------  ------
harmony    no         no Harmony service for C1234567890-NSIDC_CPRD
pydap      yes
sliderule  yes

>>> ea.plugins.harmony.request(results, variables=["h_li"])
UnsupportedCollectionError: harmony does not support ATL06 (C1234567890-NSIDC_CPRD):
no Harmony service for that collection.
Plugins that accept these results: sliderule, pydap. See results.list_services().
```

The answer is tri-state: `True` (yes), `False` (definitively no) and `None`
("could not tell"). Only a definite `False` raises, because service
associations and capabilities can lag reality. `request(results, check=False)`
skips the check for a dataset you know the service accepts.

## Walkthrough notebook

See [notebooks/plugins_overview.ipynb](notebooks/plugins_overview.ipynb) for a
runnable tour with an example per plugin.

## Writing your own plugin

```bash
cookiecutter gh:betolink/earthaccess-plugin-spec --directory template
```

The generated project has a working `PluginBase`, an optional `_supports`, a
conformance test and CI. See the [spec repository](https://github.com/betolink/earthaccess-plugin-spec)
for the full contract and the conformance suite.

> **Status:** the plugin registry (`ea.plugins`, `ea.list_plugins`,
> `ea.open`/`ea.download` dispatch) is the next core milestone. Until it lands,
> the examples above describe the intended API; the plugins and their
> conformance tests already implement it.
