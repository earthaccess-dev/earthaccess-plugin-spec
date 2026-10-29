# earthaccess-plugin-spec

The contract that every [`earthaccess`](https://github.com/earthaccess-dev/earthaccess)
plugin follows, plus a cookiecutter template and a conformance suite.

## How earthaccess finds and loads a plugin

Plugins register a class under the `earthaccess.plugins` **entry-point group**;
installing the package is all it takes:

```toml
[project.entry-points."earthaccess.plugins"]
myplugin = "earthaccess_myplugin:MyPlugin"
```

Discovery reads distribution metadata only — it never imports a backend. A
plugin module is imported the first time it is used:

- `ea.list_plugins()` — the installed plugins (metadata only).
- `ea.list_plugins(details=True)` — loads each plugin **module** (not its
  backend) to report contract version, auth, output and needs.
- `ea.plugins.myplugin` — loads `earthaccess_myplugin`, checks the
  `contract_version`, and instantiates `MyPlugin` with a `PluginContext`.

Because of this, **import your backend inside methods, never at module level**,
so discovery and `list_plugins()` stay cheap.

## Install

```bash
pip install earthaccess-plugin-spec
# or, to use the default Earthdata Login auth handle:
pip install "earthaccess-plugin-spec[edl]"
```

> **Not on PyPI yet.** For now install the contract and the plugins from GitHub,
> together with the `plugin-spec` earthaccess branch — see
> **[Installing the current drafts](docs/installing-drafts.md)**.

## Write a plugin

Subclass `PluginBase` (always), declare `Options`, and implement `_request()`:

```python
from dataclasses import dataclass
from earthaccess_plugin_spec import Asset, PluginBase


class MyPlugin(PluginBase):
    name = "myplugin"
    needs = frozenset({"concept_id"})
    auth = "edl"          # 'edl' | 'own' | 'none'
    output = "assets"     # 'assets' opens/downloads; anything else is passed through

    @dataclass
    class Options:
        format: str = "netcdf4"

    def _request(self, results, options):
        # import your backend inside the method, never at module level
        return self.job(lambda: [Asset(href="s3://...", access="s3")])
```

## The Job

`request(results, **options)` validates the inputs, runs `_supports()`, calls
`_request()`, and returns a `Job` immediately. Callers drive every job the same
way:

```python
job = ea.plugins.myplugin.request(results, ...)

job.status()          # PENDING | RUNNING | PAUSED | SUCCEEDED | PARTIAL | FAILED | CANCELED
job.info()            # backend detail (a dict); never the request payload
job.results()         # blocks until settled, then returns the output (or raises)
job.wait(timeout=60)  # wait without fetching; returns the final status
repr(job)             # never makes a network call
```

There are three shapes to choose from:

| Shape | How | Example |
| --- | --- | --- |
| **A value in hand** | `return self.job(fn)` where `fn` returns at once | PyDAP builds OPeNDAP URLs |
| **Local compute** | `return self.job(fn)` where `fn` does the work | SlideRule processing |
| **Remote, polled** | subclass `Job`, override `_poll` / `_fetch` / `_cancel` | Harmony |

`self.job(fn)` runs `fn` in a background thread, so a value in hand is just a
function that returns immediately and a local compute job is one that takes a
while. Only a remote backend needs a `Job` subclass.

### When the job is done

`output` tells earthaccess how to treat `results()`:

| `output` | `results()` returns | `ea.open(job)` / `ea.download(job, path)` |
| --- | --- | --- |
| `assets` | `list[Asset]` (files) | opened / downloaded by earthaccess |
| `xarray`, `dataframe`, ... | whatever the plugin deems correct | `ea.open` returns it as-is; `download` is not supported |

If your job yields assets, users can open or download it. For anything else,
`results()` returns whatever makes sense for your backend — a lazy
`xarray.Dataset`, a `GeoDataFrame`, native PyDAP datasets, OPeNDAP URLs, ... —
and earthaccess hands it straight back.

### The rules

- `needs` is **checked, not fetched**: `search_data()` already returns full UMM.
- Read granule fields through the `earthaccess_plugin_spec.granules` helpers
  (`peek`, `collection_label`, `concept_id`, `native_id`, `related_urls`, ...)
  instead of walking `meta`/`umm` by hand; they never materialize a lazy set.
- An advertised capability must be **requestable**: `subset_variable` means your
  `Options` accepts `variables`, and the conformance suite exercises it. Report
  formats through `format_name()` so they stay in the shared `FORMATS`
  vocabulary.
- `request()` returns a `Job`; `results()` blocks and returns the output.
- Import your backend **inside methods**, never at module level.
- Subclass `Job` **only** for a remote backend.
- Override `_supports()` (returns a `Capabilities`) to report what a collection
  supports; a definite `False` makes `request()` raise
  `UnsupportedCollectionError`. Users can bypass it with `check=False`, ask with
  `plugin.capabilities(results)` / `plugin.capabilities("ATL06")`, or list
  every plugin's answer with `results.list_services()`.

## Learn more

- **[Installing the current drafts](docs/installing-drafts.md)** — install the
  contract and plugins from GitHub (pre-release).
- **[The full contract reference](docs/contract.md)** — `PluginBase` fields,
  `Job` hooks, `JobStatus`, capabilities, the lazy `ResultSet`, errors, and the
  conformance checks.
- [Plugin system overview](docs/index.md)
- Per-plugin guides: [harmony](docs/plugins/harmony.md) ·
  [pydap](docs/plugins/pydap.md) · [sliderule](docs/plugins/sliderule.md)

## Conformance suite

```python
from earthaccess_plugin_spec.testing import Fixtures, run_conformance


class MyFixtures(Fixtures):
    def backend(self):
        return patch_my_backend()  # a context manager


def test_conformance():
    run_conformance(MyPlugin, fixtures=MyFixtures(options={"format": "zarr"}))
```

`run_conformance` fails with a list of every check that did not pass.

## Cookiecutter template

Scaffold a new plugin repository:

```bash
cookiecutter gh:betolink/earthaccess-plugin-spec --directory template
```

You will be asked for the plugin name, backend package, output kind and auth
mode. The generated project has a working `PluginBase` subclass, an optional
`Job` subclass (remote only), a conformance test, and CI.

## Import name

The distribution is `earthaccess-plugin-spec`; the import package is
`earthaccess_plugin_spec`.

## License

MIT.
