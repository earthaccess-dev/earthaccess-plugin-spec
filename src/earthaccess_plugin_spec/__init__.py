"""The earthaccess plugin contract.

Plugin authors subclass :class:`~earthaccess_plugin_spec.PluginBase`, declare an
``Options`` dataclass, and implement ``_request``. Remote backends also subclass
:class:`~earthaccess_plugin_spec.Job`. Override ``_supports`` to reject
collections the plugin cannot handle.

Run the conformance suite from ``earthaccess_plugin_spec.testing`` in CI.
"""

from __future__ import annotations

from .base import (
    AUTHS,
    OUTPUTS,
    PluginBase,
    accepting_plugins,
    validate_inputs,
)
from .context import AuthHandle, LazyEDLAuthHandle, PluginContext, default_context
from .errors import (
    EarthaccessPluginError,
    JobCanceledError,
    JobError,
    JobFailedError,
    JobPausedError,
    MissingResultsError,
    NotSupportedError,
    PluginLoadError,
    PluginNotFoundError,
    UnsupportedCollectionError,
    UnsupportedOutputError,
)
from .granules import NEEDS, collection_label, peek
from .job import FORMATS, TERMINAL_STATUSES, Asset, Format, Job, JobStatus
from .results import GranuleResultSet, ResultSet, as_result_set, list_services
from .support import (
    CAPABILITY_SPECS,
    OUTPUT_TYPES,
    Capabilities,
    Capability,
    CapabilitySpec,
    ServiceRow,
    ServiceTable,
    explain_capability,
    format_name,
)
from .version import CONTRACT_VERSION

__all__ = [
    "AUTHS",
    "CAPABILITY_SPECS",
    "CONTRACT_VERSION",
    "FORMATS",
    "NEEDS",
    "OUTPUT_TYPES",
    "OUTPUTS",
    "Asset",
    "AuthHandle",
    "Capabilities",
    "Capability",
    "CapabilitySpec",
    "EarthaccessPluginError",
    "Format",
    "GranuleResultSet",
    "Job",
    "JobCanceledError",
    "JobError",
    "JobFailedError",
    "JobPausedError",
    "JobStatus",
    "LazyEDLAuthHandle",
    "MissingResultsError",
    "NotSupportedError",
    "PluginBase",
    "PluginContext",
    "PluginLoadError",
    "PluginNotFoundError",
    "ResultSet",
    "ServiceRow",
    "ServiceTable",
    "TERMINAL_STATUSES",
    "UnsupportedCollectionError",
    "UnsupportedOutputError",
    "accepting_plugins",
    "as_result_set",
    "collection_label",
    "default_context",
    "explain_capability",
    "format_name",
    "list_services",
    "peek",
    "validate_inputs",
]
