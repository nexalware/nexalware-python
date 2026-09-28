from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, cast

from .errors import NexalwareApiError
from .types import (
    Action,
    CommandDefinition,
    Device,
    LatestTelemetry,
    Schedule,
    SendCommandResult,
    SubDevice,
    TelemetryReading,
)

DEFAULT_BASE_URL = "https://api.nexalware.com"
DEFAULT_TIMEOUT_SECONDS = 30.0


class NexalwareClient:
    """Thin typed wrapper over the Nexalware "Device Control" API tier, the
    same endpoints an API key can already call today. Built on ``urllib``
    from the standard library only, no third-party dependency, so dropping
    this into any existing agent environment can never trigger a version
    conflict.

    A key's actual reach is decided entirely by its DeviceGrant(s) on the
    dashboard, this client never expands or assumes permissions beyond that.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key:
            raise ValueError("NexalwareClient requires an api_key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self._base_url}/api/v1{path}"
        if query:
            filtered = {k: v for k, v in query.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)

        data = json.dumps(body).encode("utf-8") if body is not None else None
        # Content-Type describes the body, so it's only sent when there is
        # one - a bodyless POST (turn_on/turn_off) that still claims
        # application/json trips the API's own empty-JSON-body rejection.
        headers = {
            "X-Api-Key": self._api_key,
            "User-Agent": "nexalware-sdk-python",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                text = response.read().decode("utf-8")
                if not text:
                    return None
                try:
                    return json.loads(text)
                except ValueError:
                    raise NexalwareApiError(
                        status=response.status,
                        error="INVALID_RESPONSE",
                        message=f"Nexalware API returned a non-JSON response from {path}",
                    ) from None
        except urllib.error.HTTPError as err:
            text = err.read().decode("utf-8")
            # The API always returns JSON, but a proxy/CDN error page in
            # front of it (502, WAF block) won't - fail with a clear
            # NexalwareApiError either way, not an unhandled ValueError.
            try:
                payload = json.loads(text) if text else {}
            except ValueError:
                payload = {"message": text[:200]} if text else {}
            raise NexalwareApiError(
                status=err.code,
                error=payload.get("error", "UNKNOWN_ERROR"),
                message=payload.get("message"),
                details=payload.get("details"),
            ) from None
        except socket.timeout:
            # socket.timeout is TimeoutError itself on 3.10+, but stays a
            # distinct class pre-3.10 (this package supports 3.9+), so
            # catch it by its always-correct name rather than TimeoutError.
            raise TimeoutError(f"Nexalware API request to {path} timed out after {self._timeout}s") from None

    def list_devices(self, project_id: Optional[str] = None) -> List[Device]:
        """The devices this key can actually act on - only what its own
        DeviceGrant(s) cover, never the rest of the account. This is the
        right first call when you don't already know a ``device_id``,
        don't guess one or ask the user to dig it out of the dashboard,
        just ask the API.

        Args:
            project_id: Narrow the list to one project (Nexalware's
                grouping mechanism for devices, e.g. "Warehouse A" vs
                "Warehouse B"). Get a valid value from the
                ``"project"]["projectId"]`` field on a device returned by
                a prior unfiltered call, there's no separate "list
                projects" call. Leave as ``None`` (the default) to list
                every device this key can reach.

        Returns:
            Each device's ``deviceId``, ``name``, ``boardType``,
            ``appType``, ``deviceStatus``, ``enabled``, ``isOnline``,
            ``lastSeen``, and ``project``.
        """
        return cast(List[Device], self._request("GET", "/devices", query={"projectId": project_id}))

    def get_commands(self, device_id: str) -> List[CommandDefinition]:
        """The command catalog this device accepts. Call this before
        ``send_command`` so you know what ``cmd`` values are valid,
        sending an unrecognized ``cmd`` gets rejected.

        Args:
            device_id: A device's public id, always shaped like ``dev_``
                followed by a short alphanumeric string, e.g.
                ``"dev_a1b2c3"``. Get one from ``list_devices()``, never
                make one up.

        Returns:
            Each command's ``name`` (use as ``cmd``), ``label``, ``kind``
            (``"ACTION"`` | ``"QUERY"``), ``paramsSchema`` (JSON Schema,
            or ``None`` if it takes no params), and ``requiresApproval``.
        """
        return cast(List[CommandDefinition], self._request("GET", f"/devices/{device_id}/commands"))

    def send_command(
        self,
        device_id: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        target: Optional[str] = None,
    ) -> SendCommandResult:
        """Send a command to a device, or, with ``target`` set, to one
        specific sub-device behind it (see ``send_sub_device_command`` for
        the convenience form). Raises ``NexalwareApiError`` (status 403) if
        the calling key has no DeviceGrant covering this command.

        Args:
            device_id: The device to command, from ``list_devices()``.
            cmd: Must exactly match a ``name`` from
                ``get_commands(device_id)``. Case-sensitive, ``"on"`` is
                not the same as ``"ON"``.
            params: Only include this if the command's catalog entry has
                a non-``None`` ``paramsSchema``. For a plain ``ON``/``OFF``
                -style command, leave this as ``None`` rather than passing
                ``{}``. Shape depends entirely on the specific command,
                e.g. ``SET_BRIGHTNESS`` might expect ``{"level": 60}``.
            target: Only set this if ``device_id`` is a "master"
                orchestrating sub-devices and you want to aim the command
                at one specific sub-device instead. Prefer
                ``send_sub_device_command`` for that case, same call,
                clearer argument names.

        Returns:
            ``{"ok": True}``, plus ``approvalRequired``/``approvalId`` if
            this command required manual approval instead of executing
            immediately.
        """
        body: Dict[str, Any] = {"cmd": cmd}
        if params is not None:
            body["params"] = params
        if target is not None:
            body["target"] = target
        return cast(SendCommandResult, self._request("POST", f"/devices/{device_id}/command", body=body))

    def turn_on(self, device_id: str) -> SendCommandResult:
        """Shorthand for ``send_command(device_id, "ON")``.

        Args:
            device_id: The device to turn on.
        """
        return cast(SendCommandResult, self._request("POST", f"/devices/{device_id}/command/on"))

    def turn_off(self, device_id: str) -> SendCommandResult:
        """Shorthand for ``send_command(device_id, "OFF")``.

        Args:
            device_id: The device to turn off.
        """
        return cast(SendCommandResult, self._request("POST", f"/devices/{device_id}/command/off"))

    def get_telemetry(
        self,
        device_id: str,
        metric: Optional[str] = None,
        limit: Optional[int] = None,
        since: Optional[int] = None,
    ) -> List[TelemetryReading]:
        """Historical telemetry readings, newest first.

        Args:
            device_id: The device whose history to read.
            metric: Only return readings for this one metric name, e.g.
                ``"power_draw"``. Metric names are whatever the device
                itself reports, there's no fixed list - if you don't know
                one, call without ``metric`` first and see what comes back.
            limit: Max rows to return, 1-1000. Defaults to 100 if omitted.
            since: Unix **milliseconds**. Only readings recorded at or
                after this instant. For "the last hour":
                ``int(time.time() * 1000) - 60 * 60 * 1000``.

        Returns:
            Each reading's ``metric``, ``value``/``valueText`` (exactly
            one is set), ``unit``, and ``recordedAt``.
        """
        return cast(
            List[TelemetryReading],
            self._request(
                "GET",
                f"/devices/{device_id}/telemetry",
                query={"metric": metric, "limit": limit, "since": since},
            ),
        )

    def get_latest_telemetry(self, device_id: str) -> LatestTelemetry:
        """The device's current state plus the most recent reading per
        metric, in one call instead of calling ``get_telemetry`` per
        metric and picking off the newest row yourself.

        Args:
            device_id: The device to snapshot.

        Returns:
            ``state`` (free-form JSON, shape varies per device),
            ``relayState`` (``"ON"`` | ``"OFF"`` | ``None``), and
            ``telemetry`` (latest reading per metric).
        """
        return cast(LatestTelemetry, self._request("GET", f"/devices/{device_id}/telemetry/latest"))

    def list_sub_devices(self, device_id: str) -> List[SubDevice]:
        """Physical devices connected locally (not directly to Nexalware)
        behind this one, if it's acting as an orchestrator ("master").
        Returns an empty list until the master's own firmware actually
        reports one.

        Args:
            device_id: The **master** device's id, not a sub-device id.

        Returns:
            Each sub-device's ``subDeviceId``, ``externalId``, ``name``,
            ``state``, ``capabilities``, ``isOnline``, ``lastSeen``.
        """
        return cast(List[SubDevice], self._request("GET", f"/devices/{device_id}/sub-devices"))

    def get_sub_device(self, device_id: str, sub_device_id: str) -> SubDevice:
        """One sub-device's current state and capabilities, a single-item
        version of ``list_sub_devices``.

        Args:
            device_id: The master device's id.
            sub_device_id: One entry's ``subDeviceId`` from a prior
                ``list_sub_devices(device_id)`` call, shaped like
                ``"sub_x1y2z3"``.
        """
        return cast(SubDevice, self._request("GET", f"/devices/{device_id}/sub-devices/{sub_device_id}"))

    def get_sub_device_telemetry(
        self,
        device_id: str,
        sub_device_id: str,
        metric: Optional[str] = None,
        limit: Optional[int] = None,
        since: Optional[int] = None,
    ) -> List[TelemetryReading]:
        """Same idea as ``get_telemetry``, scoped to one sub-device instead
        of the master itself.

        Args:
            device_id: The master device's id.
            sub_device_id: Which sub-device's history to read.
            metric: Same meaning as ``get_telemetry``'s ``metric``.
            limit: Same meaning as ``get_telemetry``'s ``limit``.
            since: Same meaning as ``get_telemetry``'s ``since``.
        """
        return cast(
            List[TelemetryReading],
            self._request(
                "GET",
                f"/devices/{device_id}/sub-devices/{sub_device_id}/telemetry",
                query={"metric": metric, "limit": limit, "since": since},
            ),
        )

    def send_sub_device_command(
        self,
        device_id: str,
        sub_device_id: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> SendCommandResult:
        """The clear-named way to command one sub-device behind a master
        (equivalent to ``send_command(device_id, cmd, params,
        target=sub_device_id)``, prefer this, the argument order reads
        better). Not validated against a catalog server-side, Nexalware
        relays it to the master opaquely.

        Args:
            device_id: The master device's id.
            sub_device_id: Which sub-device to target, from ``list_sub_devices``.
            cmd: Whatever command name the sub-device's own declared
                ``capabilities.commands`` says it accepts (check
                ``get_sub_device``'s result), this is the sub-device's own
                vocabulary, not a Nexalware-defined catalog.
            params: Arguments for that command, if it needs any.
        """
        return self.send_command(device_id, cmd, params, target=sub_device_id)

    def list_schedules(self, device_id: str) -> List[Schedule]:
        """A device's active schedules, meaning ``PENDING`` (not fired
        yet) or ``ACTIVE`` (currently running between its on/off times).

        Args:
            device_id: The device whose schedules to list.
        """
        return cast(List[Schedule], self._request("GET", f"/devices/{device_id}/schedules"))

    def get_schedule_context(self, device_id: str) -> Dict[str, List[CommandDefinition]]:
        """The commands available to schedule for this device, exactly
        the same catalog ``get_commands`` returns.

        Args:
            device_id: The device to check.
        """
        return cast(
            Dict[str, List[CommandDefinition]],
            self._request("GET", f"/devices/{device_id}/schedules/context"),
        )

    def create_schedule(
        self,
        device_id: str,
        slot: int,
        on_ts: int,
        off_ts: int,
        label: Optional[str] = None,
        enabled: Optional[bool] = None,
        on_command: Optional[Action] = None,
        off_command: Optional[Action] = None,
    ) -> Schedule:
        """Create or replace one of a device's 5 schedule slots, firing
        ``on_command`` at ``on_ts`` and ``off_command`` at ``off_ts``.
        "Replace" means calling this again with the same ``slot``
        overwrites whatever was there before, it isn't additive.

        Args:
            device_id: The device to schedule.
            slot: Which of the device's 5 schedule slots to use, an
                integer from **0 to 4**. Think of these as 5 fixed "rows"
                a device has for schedules, not an auto-incrementing list,
                you pick which row.
            on_ts: Unix **seconds** (not milliseconds, unlike telemetry's
                ``since``) to fire ``on_command``. To start in one hour:
                ``int(time.time()) + 3600``.
            off_ts: Unix seconds to fire ``off_command``. Must make sense
                relative to ``on_ts`` for your use case, the API doesn't
                force ``off_ts > on_ts`` (an overnight schedule
                legitimately has ``off_ts`` "before" ``on_ts`` in clock time).
            label: A short label shown on the dashboard next to this
                schedule. **Max 7 characters** - a hard limit, e.g.
                ``"Evening"`` doesn't fit but ``"Eve"`` does.
            enabled: Whether the schedule is active. Omit (``None``) to
                default to enabled; pass ``False`` to create it disabled
                (useful for staging a schedule you're not ready to turn on).
            on_command: Shape ``{"command": str, "params": dict}`` (an
                ``Action``). Which command fires at ``on_ts``. Omit to
                default to ``{"command": "ON"}``. ``command`` must be a
                valid ``cmd`` from ``get_commands``, exactly like ``send_command``.
            off_command: Same shape as ``on_command``, fires at
                ``off_ts``. Defaults to ``{"command": "OFF"}`` if omitted.

        Raises:
            NexalwareApiError: Status 403 if the calling key lacks
                permission for either command, the same gate
                ``send_command`` applies, a schedule is just that same
                action, deferred to a later time.
        """
        body: Dict[str, Any] = {"slot": slot, "onTs": on_ts, "offTs": off_ts}
        if label is not None:
            body["label"] = label
        if enabled is not None:
            body["enabled"] = enabled
        if on_command is not None:
            body["onCommand"] = on_command
        if off_command is not None:
            body["offCommand"] = off_command
        return cast(Schedule, self._request("POST", f"/devices/{device_id}/schedules", body=body))

    def update_schedule(
        self,
        device_id: str,
        slot: int,
        on_ts: Optional[int] = None,
        off_ts: Optional[int] = None,
        label: Optional[str] = None,
        enabled: Optional[bool] = None,
        on_command: Optional[Action] = None,
        off_command: Optional[Action] = None,
    ) -> Schedule:
        """Update an existing schedule slot, only the arguments you
        actually pass are changed, everything else stays as it was.

        Args:
            device_id: The device whose schedule to update.
            slot: Which slot (0-4) to update, must already exist (created
                via ``create_schedule``).
            on_ts: New fire time for ``on_command``, in Unix seconds. Omit to leave unchanged.
            off_ts: New fire time for ``off_command``, in Unix seconds. Omit to leave unchanged.
            label: New label, max 7 characters. Omit to leave unchanged.
            enabled: Enable or disable the schedule. Omit to leave unchanged.
            on_command: New on-trigger command. Omit to leave unchanged.
            off_command: New off-trigger command. Omit to leave unchanged.
        """
        body: Dict[str, Any] = {}
        if on_ts is not None:
            body["onTs"] = on_ts
        if off_ts is not None:
            body["offTs"] = off_ts
        if label is not None:
            body["label"] = label
        if enabled is not None:
            body["enabled"] = enabled
        if on_command is not None:
            body["onCommand"] = on_command
        if off_command is not None:
            body["offCommand"] = off_command
        return cast(Schedule, self._request("PUT", f"/devices/{device_id}/schedules/{slot}", body=body))

    def delete_schedule(self, device_id: str, slot: int) -> Dict[str, bool]:
        """Cancel a schedule slot, freeing it up for a future ``create_schedule`` call.

        Args:
            device_id: The device whose schedule to cancel.
            slot: Which slot (0-4) to cancel.
        """
        return cast(Dict[str, bool], self._request("DELETE", f"/devices/{device_id}/schedules/{slot}"))

    def get_schedule_history(self, device_id: str) -> List[Schedule]:
        """A device's completed or cancelled schedules, most recent
        first, for auditing what actually ran.

        Args:
            device_id: The device to check.
        """
        return cast(List[Schedule], self._request("GET", f"/devices/{device_id}/schedules/history"))
