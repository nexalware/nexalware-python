from importlib.metadata import PackageNotFoundError, version

from .client import DEFAULT_BASE_URL, NexalwareClient
from .errors import NexalwareApiError
from .tools import make_tools
from .types import (
    Action,
    CommandDefinition,
    Device,
    LatestTelemetry,
    Schedule,
    SendCommandResult,
    SubDevice,
    SubDeviceCapabilities,
    TelemetryReading,
)

__all__ = [
    "NexalwareClient",
    "NexalwareApiError",
    "DEFAULT_BASE_URL",
    "make_tools",
    "Action",
    "CommandDefinition",
    "Device",
    "LatestTelemetry",
    "Schedule",
    "SendCommandResult",
    "SubDevice",
    "SubDeviceCapabilities",
    "TelemetryReading",
]

try:
    # Single source of truth is pyproject.toml's version - read it back at
    # runtime instead of hand-duplicating it here, so the two can never
    # drift out of sync.
    __version__ = version("nexalware")
except PackageNotFoundError:
    # Editable/local checkout with no installed distribution metadata yet.
    __version__ = "0.0.0+unknown"
