"""{{ cookiecutter.plugin_class }}: {{ cookiecutter.description }}."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from earthaccess_plugin_spec import Capabilities, PluginBase


class {{ cookiecutter.plugin_class }}(PluginBase):
    name = "{{ cookiecutter.plugin_name }}"
    auth = "{{ cookiecutter.auth }}"
    output = "{{ cookiecutter.output }}"
{% if cookiecutter.needs.strip() %}    needs = frozenset({"{{ cookiecutter.needs.split(',') | map('trim') | join('", "') }}"})
{% endif %}
    @dataclass
    class Options:
        # TODO: declare the options this plugin accepts.
        pass

    def _supports(self, results: Any) -> Capabilities:
        # Optional. Report the collection's capabilities; callers ask with
        # plugin.capabilities(results) or plugin.capabilities("SHORT_NAME").
        # Return Capabilities(False, reason=...) to reject it early. This is
        # the default: accept everything, with no extra detail.
        return Capabilities(True)

    def _request(self, results: Any, options: Options) -> Any:
        # Import the backend inside the method so plugin discovery stays cheap.
{% if cookiecutter.backend_package %}        # import {{ cookiecutter.backend_package }}
{% endif %}
        def work() -> Any:
            # TODO: call the backend and return the {{ cookiecutter.output }} output.
            raise NotImplementedError("implement {{ cookiecutter.plugin_class }}._request")

        return self.job(work)
