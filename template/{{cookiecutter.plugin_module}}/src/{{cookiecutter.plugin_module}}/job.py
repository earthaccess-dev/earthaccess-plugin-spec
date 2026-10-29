"""Remote job for {{ cookiecutter.plugin_class }}."""

from __future__ import annotations

from typing import Any

from earthaccess_plugin_spec import Job, JobStatus


class {{ cookiecutter.plugin_class }}Job(Job):
    resumable = True
    # 'cancel'/'pause'/'resume' are derived from overriding _cancel()/pause()/
    # resume(); declare capabilities explicitly only to advertise a subset.
    poll_every = 2.0

    def __init__(self, job_id: str, client: Any) -> None:
        super().__init__(
            plugin="{{ cookiecutter.plugin_name }}",
            output="{{ cookiecutter.output }}",
            id=job_id,
        )
        self._client = client

    def _poll(self) -> tuple[JobStatus, dict[str, Any]]:
        # One backend call -> (status, info). Never include the request payload.
        raise NotImplementedError

    def _fetch(self) -> Any:
        # Return the output of a SUCCEEDED or PARTIAL job.
        raise NotImplementedError
