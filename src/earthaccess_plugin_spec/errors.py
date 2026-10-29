"""Typed errors raised by the earthaccess plugin contract."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "EarthaccessPluginError",
    "JobCanceledError",
    "JobError",
    "JobFailedError",
    "JobPausedError",
    "MissingResultsError",
    "NotSupportedError",
    "PluginLoadError",
    "PluginNotFoundError",
    "UnsupportedCollectionError",
    "UnsupportedOutputError",
]


class EarthaccessPluginError(Exception):
    """Base class for every error raised by the plugin contract."""


class PluginNotFoundError(EarthaccessPluginError, AttributeError):
    """Raised when a plugin is not installed.

    It also derives from :class:`AttributeError` so the ``earthaccess.plugins``
    namespace can translate it into a failed attribute lookup.
    """


class PluginLoadError(EarthaccessPluginError):
    """Raised when an installed plugin fails to import or targets another contract."""


class MissingResultsError(EarthaccessPluginError):
    """Raised when the supplied results do not satisfy a plugin's requirements."""


class NotSupportedError(EarthaccessPluginError):
    """Raised when a plugin or job does not support an operation."""


class UnsupportedOutputError(EarthaccessPluginError):
    """Raised when a job's output kind cannot feed a requested operation."""


class UnsupportedCollectionError(EarthaccessPluginError):
    """Raised when a plugin definitely does not handle a collection.

    Points the user at the plugins that do accept the results.
    """

    def __init__(
        self,
        plugin: str,
        collection_id: str,
        *,
        short_name: str = "",
        reason: str = "",
        accepting: list[str] | None = None,
    ) -> None:
        self.plugin = plugin
        self.collection_id = collection_id
        self.short_name = short_name
        self.reason = reason
        self.accepting = list(accepting or [])
        super().__init__(self._message())

    def _message(self) -> str:
        label = self.short_name or self.collection_id or "these results"
        accepting = ", ".join(self.accepting) if self.accepting else "none"
        return (
            f"{self.plugin} does not support {label} ({self.collection_id}): "
            f"{self.reason}. Plugins that accept these results: {accepting}. "
            "See results.list_services()."
        )


class JobError(EarthaccessPluginError):
    """Base class for job state errors. Carries the job id and a detail payload."""

    def __init__(self, job_id: str, detail: Any = None) -> None:
        self.job_id = job_id
        self.detail = detail
        super().__init__(self._message())

    def _message(self) -> str:
        return f"job {self.job_id} is in an error state"


class JobFailedError(JobError):
    """Raised by ``Job.results()`` when the job failed."""

    def __init__(self, job_id: str, info: Mapping[str, Any] | None = None) -> None:
        self.info = dict(info or {})
        super().__init__(job_id, detail=self.info)

    def _message(self) -> str:
        error = self.info.get("error")
        return f"job {self.job_id} failed" + (f": {error}" if error else "")


class JobCanceledError(JobError):
    """Raised by ``Job.results()`` when the job was canceled."""

    def __init__(self, job_id: str) -> None:
        super().__init__(job_id)

    def _message(self) -> str:
        return f"job {self.job_id} was canceled"


class JobPausedError(JobError):
    """Raised by ``Job.results()`` when the job is paused (for example a preview gate).

    The message tells the caller how to move forward.
    """

    def __init__(self, job_id: str) -> None:
        super().__init__(job_id)

    def _message(self) -> str:
        return (
            f"job {self.job_id} is paused; call resume() to continue "
            "(or the plugin's preview-skip method, if it has one)"
        )
