# {{ cookiecutter.distribution_name }}

{{ cookiecutter.description }}

An [`earthaccess`](https://github.com/earthaccess-dev/earthaccess) plugin built
on [`earthaccess-plugin-spec`](https://github.com/earthaccess-dev/earthaccess-plugin-spec).

## Install

```bash
pip install "{{ cookiecutter.distribution_name }}"
```

## What to fill in

1. `src/{{ cookiecutter.plugin_module }}/plugin.py` — declare your `Options` and
   implement `_request()`.
{% if cookiecutter.remote == 'yes' -%}
2. `src/{{ cookiecutter.plugin_module }}/job.py` — implement the remote `_poll`,
   `_fetch` and `_cancel` hooks.
{%- endif %}
3. `tests/test_conformance.py` — point `Fixtures` at your backend fake and pass
   real options.

```bash
pip install -e ".[test]"
pytest
```

## Contract

- `name = "{{ cookiecutter.plugin_name }}"`, `output = "{{ cookiecutter.output }}"`,
  `auth = "{{ cookiecutter.auth }}"`, `needs = { {{ cookiecutter.needs }} }`.
- Import `{{ cookiecutter.backend_package }}` inside methods, never at module level.
- `request()` returns a `Job`; `results()` blocks and returns the output.

## License

MIT.
