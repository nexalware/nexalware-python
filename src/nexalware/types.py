from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

# Field names deliberately match the API's own JSON wire format (camelCase)
# rather than being renamed to snake_case, so an example or error message
# from the docs, the REST API, or this SDK all refer to the same field by
# the same name, nothing to mentally translate between them.


class DeviceProject(TypedDict):
    name: str
    projectId: str


class Device(TypedDict):
    deviceId: str
    name: str
    boardType: str
    appType: str
    deviceStatus: Literal["PENDING", "ACTIVE", "DISABLED", "REVOKED"]
    enabled: bool
    deviceTypeId: Optional[str]
    relayState: Optional[bool]
    isOnline: bool
    lastSeen: Optional[str]
    createdAt: str
    project: Optional[DeviceProject]


class CommandDefinition(TypedDict, total=False):
    commandId: str
    name: str
    label: str
    description: str
    kind: Literal["ACTION", "QUERY"]
    paramsSchema: Optional[Dict[str, Any]]
    shape: Optional[Dict[str, Any]]
    requiresApproval: bool


class SendCommandResult(TypedDict, total=False):
    ok: Literal[True]
    approvalRequired: bool
    approvalId: str


class TelemetryReading(TypedDict):
    id: str
    deviceId: str
    accountId: str
    subDeviceId: Optional[str]
    metric: str
    value: Optional[float]
    valueText: Optional[str]
    unit: Optional[str]
    raw: Any
    recordedAt: str


class LatestTelemetry(TypedDict):
    state: Optional[Dict[str, Any]]
    relayState: Optional[Literal["ON", "OFF"]]
    telemetry: List[TelemetryReading]


class SubDeviceCapabilities(TypedDict, total=False):
    commands: List[Dict[str, Any]]
    telemetry_metrics: List[str]
    verifiable: bool


class SubDevice(TypedDict):
    subDeviceId: str
    externalId: str
    name: str
    state: Optional[Dict[str, Any]]
    capabilities: Optional[SubDeviceCapabilities]
    verifiable: bool
    enabled: bool
    isOnline: bool
    lastSeen: Optional[str]
    createdAt: str


class Action(TypedDict, total=False):
    command: str
    params: Dict[str, Any]


class Schedule(TypedDict):
    scheduleId: str
    deviceId: str
    slot: int
    onTs: int
    offTs: int
    label: str
    enabled: bool
    status: Literal["PENDING", "ACTIVE", "COMPLETED", "CANCELLED"]
    onCommand: Action
    offCommand: Action
