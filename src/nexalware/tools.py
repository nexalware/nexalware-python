from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .client import NexalwareClient
from .types import Action

# One function per callable operation, each one's own signature/docstring
# is the schema an MCP host (or any other tool-calling framework) reads -
# this is the single source of truth for "what can an agent do to a
# device", any adapter is just a thin loop over make_tools(client)'s
# result, so the set of capabilities can't drift between adapters.


def make_tools(client: NexalwareClient) -> List[Callable[..., Any]]:
    """Build the tool functions, each one bound to this specific client."""

    def list_devices(project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List the devices this API key can actually act on - only what its own DeviceGrant(s) cover, never the rest of the account. Call this first to discover valid device_id values instead of guessing or asking the user to paste one in.

        Args:
            project_id: Only list devices in this project.
        """
        return client.list_devices(project_id)  # type: ignore[return-value]

    def get_device_commands(device_id: str) -> List[Dict[str, Any]]:
        """List the commands a device accepts: name, label, and the params each one expects.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.get_commands(device_id)  # type: ignore[return-value]

    def send_command(device_id: str, cmd: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command to a device. Check get_device_commands first for valid cmd names and expected params. Rejected if the calling key has no permission for this device/command.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
            cmd: Command name, matches one of get_device_commands' results.
            params: Arguments for this command, only if its command definition declares a paramsSchema.
        """
        return client.send_command(device_id, cmd, params)  # type: ignore[return-value]

    def turn_device_on(device_id: str) -> Dict[str, Any]:
        """Shorthand for sending the ON command to a device.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.turn_on(device_id)  # type: ignore[return-value]

    def turn_device_off(device_id: str) -> Dict[str, Any]:
        """Shorthand for sending the OFF command to a device.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.turn_off(device_id)  # type: ignore[return-value]

    def get_device_telemetry(
        device_id: str,
        metric: Optional[str] = None,
        limit: Optional[int] = None,
        since: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Read a device's telemetry history, newest first.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
            metric: Only return readings for this metric.
            limit: Max rows to return (1-1000), defaults to 100.
            since: Unix ms, only readings recorded at or after this time.
        """
        return client.get_telemetry(device_id, metric, limit, since)  # type: ignore[return-value]

    def get_latest_telemetry(device_id: str) -> Dict[str, Any]:
        """Read a device's current state plus the most recent reading per telemetry metric.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.get_latest_telemetry(device_id)  # type: ignore[return-value]

    def list_sub_devices(device_id: str) -> List[Dict[str, Any]]:
        """List the physical sub-devices connected locally behind this device, if it's acting as a master. Empty until the master actually reports one, this never includes software agents.

        Args:
            device_id: The master device's public id.
        """
        return client.list_sub_devices(device_id)  # type: ignore[return-value]

    def get_sub_device(device_id: str, sub_device_id: str) -> Dict[str, Any]:
        """Read one sub-device's current state and capabilities.

        Args:
            device_id: The master device's public id.
            sub_device_id: The sub-device's public id, e.g. sub_x1y2z3.
        """
        return client.get_sub_device(device_id, sub_device_id)  # type: ignore[return-value]

    def get_sub_device_telemetry(
        device_id: str,
        sub_device_id: str,
        metric: Optional[str] = None,
        limit: Optional[int] = None,
        since: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Read one sub-device's telemetry history, newest first.

        Args:
            device_id: The master device's public id.
            sub_device_id: The sub-device's public id, e.g. sub_x1y2z3.
            metric: Only return readings for this metric.
            limit: Max rows to return (1-1000), defaults to 100.
            since: Unix ms, only readings recorded at or after this time.
        """
        return client.get_sub_device_telemetry(device_id, sub_device_id, metric, limit, since)  # type: ignore[return-value]

    def send_sub_device_command(
        device_id: str, sub_device_id: str, cmd: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a command to one specific sub-device behind a master, instead of the master itself. Not validated against a catalog, Nexalware relays it opaquely, the master and sub-device interpret it.

        Args:
            device_id: The master device's public id.
            sub_device_id: The sub-device's public id, e.g. sub_x1y2z3.
            cmd: Command name, whatever the sub-device declared it accepts.
            params: Arguments for this command, if any.
        """
        return client.send_sub_device_command(device_id, sub_device_id, cmd, params)  # type: ignore[return-value]

    def list_schedules(device_id: str) -> List[Dict[str, Any]]:
        """List a device's active (pending or currently running) schedules.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.list_schedules(device_id)  # type: ignore[return-value]

    def get_schedule_context(device_id: str) -> Dict[str, Any]:
        """List the commands available to schedule for a device, same catalog as get_device_commands.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.get_schedule_context(device_id)  # type: ignore[return-value]

    def create_schedule(
        device_id: str,
        slot: int,
        on_ts: int,
        off_ts: int,
        label: Optional[str] = None,
        enabled: Optional[bool] = None,
        on_command: Optional[Action] = None,
        off_command: Optional[Action] = None,
    ) -> Dict[str, Any]:
        """Create or replace one of a device's schedule slots (0-4), firing on_command at on_ts and off_command at off_ts. Rejected if the calling key has no permission for either command.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
            slot: Which of the device's 5 schedule slots (0-4) to use.
            on_ts: Unix seconds to fire on_command.
            off_ts: Unix seconds to fire off_command.
            label: Short label shown on the dashboard, max 7 characters.
            enabled: Whether the schedule is active.
            on_command: Defaults to {"command": "ON"}.
            off_command: Defaults to {"command": "OFF"}.
        """
        return client.create_schedule(  # type: ignore[return-value]
            device_id, slot, on_ts, off_ts, label, enabled, on_command, off_command
        )

    def update_schedule(
        device_id: str,
        slot: int,
        on_ts: Optional[int] = None,
        off_ts: Optional[int] = None,
        label: Optional[str] = None,
        enabled: Optional[bool] = None,
        on_command: Optional[Action] = None,
        off_command: Optional[Action] = None,
    ) -> Dict[str, Any]:
        """Update an existing schedule slot, only the fields provided are changed.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
            slot: Which schedule slot (0-4) to update.
            on_ts: Unix seconds to fire on_command.
            off_ts: Unix seconds to fire off_command.
            label: Short label shown on the dashboard, max 7 characters.
            enabled: Whether the schedule is active.
            on_command: New on-trigger command, if changing it.
            off_command: New off-trigger command, if changing it.
        """
        return client.update_schedule(  # type: ignore[return-value]
            device_id, slot, on_ts, off_ts, label, enabled, on_command, off_command
        )

    def delete_schedule(device_id: str, slot: int) -> Dict[str, Any]:
        """Cancel a schedule slot.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
            slot: Which schedule slot (0-4) to cancel.
        """
        return client.delete_schedule(device_id, slot)  # type: ignore[return-value]

    def get_schedule_history(device_id: str) -> List[Dict[str, Any]]:
        """List a device's completed or cancelled schedules, most recent first.

        Args:
            device_id: The device's public id, e.g. dev_a1b2c3.
        """
        return client.get_schedule_history(device_id)  # type: ignore[return-value]

    return [
        list_devices,
        get_device_commands,
        send_command,
        turn_device_on,
        turn_device_off,
        get_device_telemetry,
        get_latest_telemetry,
        list_sub_devices,
        get_sub_device,
        get_sub_device_telemetry,
        send_sub_device_command,
        list_schedules,
        get_schedule_context,
        create_schedule,
        update_schedule,
        delete_schedule,
        get_schedule_history,
    ]
