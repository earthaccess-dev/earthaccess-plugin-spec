"""One concrete ``Job`` with a local mode and a remote mode.

Given a function, ``Job`` runs it in a background thread and derives its status
from the future: that is local work. A remote backend subclasses ``Job`` and
overrides ``_poll``, ``_fetch`` and (if it can cancel) ``_cancel``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, ClassVar, Literal, get_args

from .errors import JobCanceledError, JobFailedError, JobPausedError, NotSupportedError

__all__ = ["FORMATS", "Asset", "Format", "Job", "JobStatus", "TERMINAL_STATUSES"]


class JobStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    SUCCEEDED = auto()
    PARTIAL = auto()
    FAILED = auto()
    CANCELED = auto()


TERMINAL_STATUSES = frozenset(
    {
        JobStatus.PAUSED,
        JobStatus.SUCCEEDED,
        JobStatus.PARTIAL,
        JobStatus.FAILED,
        JobStatus.CANCELED,
    }
)
"""States where :meth:`Job.wait` stops polling. Shared with the conformance suite."""

_POOL = ThreadPoolExecutor(max_workers=4)
_UNSET = object()

Format = Literal["netcdf4", "zarr", "geoparquet", "csv", "geotiff"]

FORMATS = frozenset(get_args(Format))
"""The canonical result formats.

``Asset.format`` and ``Capabilities.formats`` both use this vocabulary, so a
plugin cannot report a format it could never hand back.
"""


@dataclass(frozen=True)
class Asset:
    """A result file produced by a job."""

    href: str
    access: Literal["https", "s3", "opendap"]
    auth: Literal["edl", "presigned", "none"] = "edl"
    format: Format | None = None


class Job:
    """A unit of work. Local by default; subclass only for a remote backend."""

    resumable: ClassVar[bool] = False
    """True means the plugin's ``get_job(job_id)`` can rebuild this job."""

    capabilities: ClassVar[frozenset[str]] = frozenset()
    """Subset of ``{'cancel', 'pause', 'resume'}``; a string means the method exists.

    Derived from which hooks a subclass overrides, so it cannot drift. Declare
    it explicitly only to report a subset of what the job can actually do.
    """

    poll_every: ClassVar[float] = 0.1
    """Seconds between polls; remote jobs raise it to a polite interval."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "capabilities" in cls.__dict__:
            return
        cls.capabilities = frozenset(
            name
            for name, hook in (
                ("cancel", "_cancel"),
                ("pause", "pause"),
                ("resume", "resume"),
            )
            if getattr(cls, hook) is not getattr(Job, hook)
        )

    def __init__(
        self,
        fn: Callable[[], Any] | None = None,
        *,
        plugin: str,
        output: str,
        id: str | None = None,
    ) -> None:
        self.id = id or uuid.uuid4().hex
        self.plugin = plugin
        self.output = output
        self._last = JobStatus.PENDING
        self._info: dict[str, Any] = {}
        self._exc: BaseException | None = None
        self._result: Any = _UNSET
        self._future = _POOL.submit(fn) if fn is not None else None

    # --- default implementation = local work; remote backends override these. ---
    def _poll(self) -> tuple[JobStatus, dict[str, Any]]:
        future = self._future
        if future is None:
            raise RuntimeError("a Job without a future must override _poll()")
        if not future.done():
            status = JobStatus.RUNNING if future.running() else JobStatus.PENDING
            return status, {"status": status.name.lower()}
        self._exc = future.exception()
        if self._exc is not None:
            return JobStatus.FAILED, {"status": "failed", "error": repr(self._exc)}
        return JobStatus.SUCCEEDED, {"status": "complete"}

    def _fetch(self) -> Any:
        future = self._future
        if future is None:
            raise RuntimeError("a Job without a future must override _fetch()")
        return future.result()

    def _cancel(self) -> bool:
        # Only reached when the 'cancel' capability is advertised; a capable
        # job subclass overrides this.
        raise NotImplementedError(f"{self.plugin} jobs cannot be canceled")

    # Symmetric with cancel(): a subclass that overrides pause()/resume() gets
    # the matching capability derived automatically.
    def pause(self) -> bool:
        raise NotSupportedError(f"{self.plugin} jobs cannot be paused")

    def resume(self) -> bool:
        raise NotSupportedError(f"{self.plugin} jobs cannot be resumed")

    # --- provided by the core contract ---
    def status(self) -> JobStatus:
        self._last, self._info = self._poll()
        return self._last

    def info(self) -> dict[str, Any]:
        self.status()
        return dict(self._info)

    def wait(self, timeout: float | None = None) -> JobStatus:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.status() not in TERMINAL_STATUSES:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"{self!r} is still {self._last.name}")
            time.sleep(self.poll_every)
        return self._last

    def results(self) -> Any:
        # Fetch at most once: repeated results()/ea.open(job) reuse the output.
        if self._result is not _UNSET:
            return self._result
        status = self.wait()
        if status is JobStatus.FAILED:
            raise JobFailedError(self.id, self._info) from self._exc
        if status is JobStatus.CANCELED:
            raise JobCanceledError(self.id)
        if status is JobStatus.PAUSED:
            raise JobPausedError(self.id)
        self._result = self._fetch()
        return self._result

    def cancel(self) -> bool:
        if "cancel" not in self.capabilities:
            raise NotSupportedError(f"{self.plugin} jobs cannot be canceled")
        return self._cancel()

    def __repr__(self) -> str:
        # Local work is a future: polling it is free, so show the real state
        # instead of the PENDING it was born with. Remote jobs are not polled
        # here (that would be a network call).
        if self._future is not None:
            self.status()
        return f"<{type(self).__name__} {self.plugin}:{self.id} {self._last.name}>"

    async def astatus(self) -> JobStatus:
        return await asyncio.to_thread(self.status)

    async def await_done(self, timeout: float | None = None) -> JobStatus:
        return await asyncio.to_thread(self.wait, timeout)

    async def aresults(self) -> Any:
        return await asyncio.to_thread(self.results)

    async def acancel(self) -> bool:
        return await asyncio.to_thread(self.cancel)
