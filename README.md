# nexalware

Typed client for the [Nexalware](https://nexalware.com) API, control physical devices and read their telemetry from any Python agent or app. Zero third-party dependencies, built on `urllib` from the standard library, so dropping it into any existing agent environment can never trigger a version conflict.

Writing in TypeScript instead? See [`@nexalware/sdk`](https://www.npmjs.com/package/@nexalware/sdk) on npm. Want an MCP-aware host to discover these as tools automatically instead of calling them from code? See [`@nexalware/mcp`](https://www.npmjs.com/package/@nexalware/mcp).

## Install

```bash
pip install nexalware
```

## Quickstart

```python
from nexalware import NexalwareClient

client = NexalwareClient(api_key="nxw_live_sk_your_key_here")

client.turn_on("dev_a1b2c3")

latest = client.get_latest_telemetry("dev_a1b2c3")
print(latest["state"], latest["telemetry"])
```

Get an API key from the [dashboard](https://nexalware.com) (API Keys), and make sure it has a DeviceGrant covering the device(s) and command(s) you call, an ungranted key authenticates fine but every call is rejected with a 403.

> **Field names match the API's own JSON, not snake_case.** Return values are plain `dict`s (typed as `TypedDict` for editor/type-checker support), with the same field names the REST API itself uses, e.g. `latest["subDeviceId"]`, not `latest["sub_device_id"]`. Method and argument names are proper Python `snake_case`, only the data payloads keep the wire format.

## `NexalwareClient(api_key, base_url=...)`

| Param | Type | Required | Meaning |
|---|---|---|---|
| `api_key` | str | yes | A secret key from the dashboard. |
| `base_url` | str | no | Override for a self-hosted or staging deployment. Defaults to `https://api.nexalware.com`. |
| `timeout` | float | no | Abort a request after this many seconds. Defaults to `30.0`. |

## Errors

Every method raises `NexalwareApiError` on a non-2xx response, it never returns a "silent" error value.

| Attribute | Type | Meaning |
|---|---|---|
| `status` | int | HTTP status code. |
| `error` | str | Short machine-readable code, e.g. `"FORBIDDEN"`, `"NOT_FOUND"`. |
| `message` | str \| None | Human-readable reason, same text a dashboard user would see. |
| `details` | list \| None | Only present on a 400 validation failure. |

```python
from nexalware import NexalwareApiError

try:
    client.send_command("dev_a1b2c3", "SET_BRIGHTNESS", params={"level": 60})
except NexalwareApiError as err:
    print(err.status, err.error, err.message)
```

## Methods

Every method below is documented the same way: what each parameter actually means and how to fill it in, then a real example, then the return shape. If you've never touched this platform before, read `list_devices` and `send_command` first, almost everything else is a variation on those two.

### `list_devices(project_id=None)`

The devices this key can actually act on, only what its own [DeviceGrant](https://docs.nexalware.com/docs/concepts/authentication-and-access)(s) cover, never the rest of the account. This is the right first call when you don't already know a `device_id`, don't guess one or ask the user to dig it out of the dashboard, just ask the API.

**Parameters**

- **`project_id`** (str, optional) — Pass this only if you want to narrow the list to one project (Nexalware's grouping mechanism for devices, e.g. "Warehouse A" vs "Warehouse B"). Get a valid value by first calling `list_devices()` with no argument and reading the `"project"]["projectId"]` field off whatever comes back, there's no separate "list projects" call, projects only ever show up as a field on a device. Leave it as `None` (the default) to list every device the key can reach.

**Example**

```python
# Every device this key can see
devices = client.list_devices()
for d in devices:
    print(d["deviceId"], d["name"], "online" if d["isOnline"] else "offline")

# Only devices in one project
warehouse_devices = client.list_devices(project_id="proj_a1b2c3")
```

**Returns** `List[Device]`

| Field | Type | Meaning |
|---|---|---|
| `deviceId` | str | Use this everywhere else a method asks for `device_id`. |
| `name` | str | Whatever the human named it on the dashboard, e.g. `"Garage Light"`. |
| `boardType` | str | Free text set at registration, e.g. `"esp32"`. |
| `appType` | str | Free text set at registration, e.g. `"Industrial Automation"`. |
| `deviceStatus` | `"PENDING"` \| `"ACTIVE"` \| `"DISABLED"` \| `"REVOKED"` | `PENDING` means credentials were never generated, it will never come online. `DISABLED` means someone turned it off from the dashboard. |
| `enabled` | bool | `True` only when `deviceStatus` is `ACTIVE`. |
| `isOnline` | bool | Live connection state, not the same as `enabled`, a disabled device is never online but an enabled one can still be offline. |
| `lastSeen` | str \| None | ISO timestamp of its last MQTT activity, `None` if it's never connected. |
| `project` | `{"name", "projectId"} \| None` | `None` if it was never assigned to a project. |

### `get_commands(device_id)`

The command catalog this device accepts, name/label/params-schema per command. Call this before `send_command` so you know what `cmd` values are actually valid, sending an unrecognized `cmd` gets rejected.

**Parameters**

- **`device_id`** (str, required) — A device's public id, always shaped like `dev_` followed by a short alphanumeric string, e.g. `"dev_a1b2c3"`. Get one from `list_devices()`, never make one up.

**Example**

```python
commands = client.get_commands("dev_a1b2c3")
# [{"name": "ON", "label": "Turn on", "kind": "ACTION", "paramsSchema": None, "requiresApproval": False}, ...]
```

**Returns** `List[CommandDefinition]`

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Command name, use this exact string as `cmd` in `send_command`. |
| `label` | str | Human-readable label, e.g. show this in a UI instead of the raw `name`. |
| `kind` | `"ACTION"` \| `"QUERY"` | Whether it changes device state or just reads it. |
| `paramsSchema` | dict \| None | JSON Schema describing what `params` this command expects. `None` means it takes no params at all, don't pass any. |
| `requiresApproval` | bool | If `True`, calling `send_command` with this `cmd` still succeeds (HTTP-wise) but queues for manual approval instead of executing immediately, see `send_command`'s return shape below. |

A device with no custom catalog (nothing configured beyond the basics) returns the legacy set: `ON`, `OFF`, `TOGGLE`, `STATUS`, none of which take params.

### `send_command(device_id, cmd, params=None, target=None)`

The general-purpose way to actually make a device do something.

**Parameters**

- **`device_id`** (str, required) — The device to command, from `list_devices()`.
- **`cmd`** (str, required) — Must exactly match a `name` from `get_commands(device_id)`. Case-sensitive, `"on"` is not the same as `"ON"`.
- **`params`** (dict, optional) — Only include this if the command's catalog entry has a non-`None` `paramsSchema`. For a plain `ON`/`OFF`-style command, leave this as `None` (the default) rather than passing `{}`. Shape depends entirely on that specific command, e.g. `SET_BRIGHTNESS` might expect `{"level": 60}`, read the device's own `paramsSchema` to know what keys it wants.
- **`target`** (str, optional) — Only set this if `device_id` is a "master" orchestrating sub-devices and you want to aim the command at one specific sub-device instead of the master itself. If you're doing that, prefer `send_sub_device_command` below instead, it's the exact same call with clearer argument names, this `target` parameter exists mainly so `send_sub_device_command` has something to delegate to.

**Example**

```python
# No params
client.send_command("dev_a1b2c3", "ON")

# With params
client.send_command("dev_a1b2c3", "SET_BRIGHTNESS", params={"level": 60})

# Aimed at a sub-device behind a master (prefer send_sub_device_command for this)
client.send_command("dev_master1", "OPEN", target="sub_x1y2z3")
```

**Returns** `{"ok": True, "approvalRequired": bool | None, "approvalId": str | None}` — if `approvalRequired` is `True`, the command has *not* run yet, it's sitting in a queue waiting for an Owner/Admin to approve it from the dashboard; `approvalId` identifies that pending request.

### `turn_on(device_id)` / `turn_off(device_id)`

Shorthand for `send_command(device_id, "ON")` / `send_command(device_id, "OFF")`, for the common case of a plain relay-style device.

**Parameters**

- **`device_id`** (str, required) — The device to turn on/off.

**Example**

```python
client.turn_on("dev_a1b2c3")
client.turn_off("dev_a1b2c3")
```

**Returns** `{"ok": True}`

### `get_telemetry(device_id, metric=None, limit=None, since=None)`

Historical sensor/telemetry readings a device has reported, newest first.

**Parameters**

- **`device_id`** (str, required) — The device whose history you want.
- **`metric`** (str, optional) — Only return readings for this one metric name, e.g. `"power_draw"`. Metric names are whatever the device itself reports, there's no fixed list, if you don't know one, call this once without `metric` and look at what comes back.
- **`limit`** (int, optional) — How many rows to return, from 1 to 1000. Defaults to 100 if omitted.
- **`since`** (int, optional) — Unix **milliseconds**. Only readings recorded at or after this instant. To get "the last hour," pass `int(time.time() * 1000) - 60 * 60 * 1000`.

**Example**

```python
import time

# Last 100 readings, any metric
recent = client.get_telemetry("dev_a1b2c3")

# Last hour of just power_draw
power = client.get_telemetry(
    "dev_a1b2c3",
    metric="power_draw",
    since=int(time.time() * 1000) - 60 * 60 * 1000,
)
```

**Returns** `List[TelemetryReading]`

| Field | Type | Meaning |
|---|---|---|
| `metric` | str | Which metric this reading is for. |
| `value` | float \| None | Numeric reading, e.g. `4.2`. |
| `valueText` | str \| None | Non-numeric reading instead, e.g. a status string. Exactly one of `value`/`valueText` is set. |
| `unit` | str \| None | Whatever unit the device declared, e.g. `"watts"`. |
| `recordedAt` | str | ISO timestamp of when the device reported it. |

### `get_latest_telemetry(device_id)`

The device's current state snapshot plus the most recent reading for every metric it reports, in one call, instead of calling `get_telemetry` per metric and picking off the newest row yourself.

**Parameters**

- **`device_id`** (str, required) — The device to snapshot.

**Example**

```python
latest = client.get_latest_telemetry("dev_a1b2c3")
print(latest["relayState"])   # "ON" | "OFF" | None
print(latest["state"])        # whatever free-form state this device reports
print(latest["telemetry"])    # List[TelemetryReading], one per metric, all "latest"
```

**Returns** `{"state": ..., "relayState": ..., "telemetry": List[TelemetryReading]}` — `state` is free-form JSON the device itself reports (shape varies per device), `relayState` is `"ON"`/`"OFF"`/`None` for a plain relay-style device specifically.

### `list_sub_devices(device_id)`

Physical devices connected locally (not directly to Nexalware) behind this one, if it's acting as a master orchestrating them. Returns an empty list until the master's own firmware actually reports one, this is never populated automatically and never includes software agents, only physical sub-devices the master itself describes.

**Parameters**

- **`device_id`** (str, required) — The **master** device's id, not a sub-device id.

**Example**

```python
subs = client.list_sub_devices("dev_master1")
# [] until the master's firmware calls its own "report sub-device" step
```

**Returns** `List[SubDevice]`, each with `subDeviceId`, `externalId` (whatever id the master itself uses for it), `name`, `state`, `capabilities` (its own command catalog, if it declared one), `isOnline`, `lastSeen`.

### `get_sub_device(device_id, sub_device_id)`

One sub-device's current state and capabilities, a single-item version of `list_sub_devices`.

**Parameters**

- **`device_id`** (str, required) — The master device's id.
- **`sub_device_id`** (str, required) — One entry's `subDeviceId` from a prior `list_sub_devices(device_id)` call, shaped like `"sub_x1y2z3"`.

**Example**

```python
sub = client.get_sub_device("dev_master1", "sub_x1y2z3")
```

**Returns** `SubDevice` — same shape as one entry from `list_sub_devices`.

### `get_sub_device_telemetry(device_id, sub_device_id, metric=None, limit=None, since=None)`

Same idea as `get_telemetry`, scoped to one sub-device instead of the master itself.

**Parameters**

- **`device_id`** (str, required) — The master device's id.
- **`sub_device_id`** (str, required) — Which sub-device's history to read.
- **`metric` / `limit` / `since`** (optional) — Identical meaning to `get_telemetry`'s same-named arguments.

**Example**

```python
readings = client.get_sub_device_telemetry("dev_master1", "sub_x1y2z3", limit=50)
```

**Returns** `List[TelemetryReading]` — same shape as `get_telemetry`'s return.

### `send_sub_device_command(device_id, sub_device_id, cmd, params=None)`

The clear-named way to command one sub-device behind a master (equivalent to calling `send_command(device_id, cmd, params, target=sub_device_id)`, use this instead, the argument order reads better). Not validated against a catalog server-side the way `send_command` is for a top-level device, Nexalware relays it to the master opaquely, and the master and sub-device interpret the command between themselves.

**Parameters**

- **`device_id`** (str, required) — The master device's id.
- **`sub_device_id`** (str, required) — Which sub-device to target, from `list_sub_devices`.
- **`cmd`** (str, required) — Whatever command name the sub-device's own declared `capabilities.commands` says it accepts (check `get_sub_device`'s result), this is the master/sub-device's own vocabulary, not a Nexalware-defined catalog.
- **`params`** (dict, optional) — Arguments for that command, if it needs any, shape is whatever the sub-device itself expects.

**Example**

```python
client.send_sub_device_command("dev_master1", "sub_x1y2z3", "OPEN")
client.send_sub_device_command("dev_master1", "sub_x1y2z3", "SET_POSITION", params={"angle": 45})
```

**Returns** `{"ok": True}`

### `list_schedules(device_id)`

A device's active schedules, meaning `PENDING` (not fired yet) or `ACTIVE` (currently running between its on/off times).

**Parameters**

- **`device_id`** (str, required) — The device whose schedules to list.

**Example**

```python
schedules = client.list_schedules("dev_a1b2c3")
```

**Returns** `List[Schedule]`, each with `scheduleId`, `slot`, `onTs`, `offTs`, `label`, `enabled`, `status`, `onCommand`, `offCommand`.

### `get_schedule_context(device_id)`

The commands available to schedule for this device, exactly the same catalog `get_commands` returns, this exists so schedule-building UI code doesn't need to call two different endpoints for the same information.

**Parameters**

- **`device_id`** (str, required) — The device to check.

**Example**

```python
context = client.get_schedule_context("dev_a1b2c3")
commands = context["commands"]
```

**Returns** `{"commands": List[CommandDefinition]}` — same `CommandDefinition` shape documented under `get_commands`.

### `create_schedule(device_id, slot, on_ts, off_ts, label=None, enabled=None, on_command=None, off_command=None)`

Create or replace one of a device's 5 schedule slots, firing `on_command` at `on_ts` and `off_command` at `off_ts`. "Replace" means calling this again with the same `slot` overwrites whatever was there before, it isn't additive.

**Parameters**

- **`device_id`** (str, required) — The device to schedule.
- **`slot`** (int, required) — Which of the device's 5 schedule slots to use, an integer from **0 to 4**. Think of these as 5 fixed "rows" a device has for schedules, not an auto-incrementing list, you pick which row.
- **`on_ts`** (int, required) — Unix **seconds** (not milliseconds, unlike telemetry's `since`) for when to fire `on_command`. To schedule something starting in one hour: `int(time.time()) + 3600`.
- **`off_ts`** (int, required) — Unix seconds for when to fire `off_command`. Must make sense relative to `on_ts` for your use case, the API doesn't force `off_ts > on_ts` (an overnight schedule legitimately has `off_ts` "before" `on_ts` in clock time).
- **`label`** (str, optional) — A short label shown on the dashboard next to this schedule. **Max 7 characters** - this is a hard limit, e.g. `"Evening"` doesn't fit but `"Eve"` does.
- **`enabled`** (bool, optional) — Whether the schedule is active. Omit (`None`) to default to enabled; pass `False` to create it disabled (useful for staging a schedule you're not ready to turn on yet).
- **`on_command`** (dict, optional) — Shape: `{"command": str, "params": dict}` (an `Action`). Which command fires at `on_ts`. Omit to default to `{"command": "ON"}`. `command` must be a valid `cmd` from `get_commands`, exactly like `send_command`.
- **`off_command`** (dict, optional) — Same shape as `on_command`, fires at `off_ts`. Defaults to `{"command": "OFF"}` if omitted.

**Example**

```python
import time

# Simplest case: plain ON at 7am, OFF at 10pm, using the defaults
client.create_schedule(
    "dev_a1b2c3",
    slot=0,
    on_ts=int(time.mktime(time.strptime("2026-01-01 07:00:00", "%Y-%m-%d %H:%M:%S"))),
    off_ts=int(time.mktime(time.strptime("2026-01-01 22:00:00", "%Y-%m-%d %H:%M:%S"))),
    label="Day",
)

# Custom commands instead of plain ON/OFF
client.create_schedule(
    "dev_a1b2c3",
    slot=1,
    on_ts=int(time.time()) + 3600,
    off_ts=int(time.time()) + 7200,
    on_command={"command": "SET_BRIGHTNESS", "params": {"level": 80}},
    off_command={"command": "OFF"},
)
```

**Returns** `Schedule`. Raises `NexalwareApiError` (status 403) if the calling key lacks permission for either command, this is the exact same DeviceGrant check `send_command` applies, a schedule is just that same action, deferred to a later time.

### `update_schedule(device_id, slot, on_ts=None, off_ts=None, label=None, enabled=None, on_command=None, off_command=None)`

Update an existing schedule slot, only the arguments you actually pass are changed, everything else stays as it was.

**Parameters**

- **`device_id`** (str, required) — The device whose schedule to update.
- **`slot`** (int, required) — Which slot (0-4) to update, must already exist (created via `create_schedule`).
- **`on_ts` / `off_ts` / `label` / `enabled` / `on_command` / `off_command`** (all optional) — Same meaning as in `create_schedule`, include only what you're changing.

**Example**

```python
import time

# Only change the off-time, leave everything else as-is
client.update_schedule("dev_a1b2c3", 0, off_ts=int(time.time()) + 3600)

# Disable it without deleting it
client.update_schedule("dev_a1b2c3", 0, enabled=False)
```

**Returns** `Schedule`

### `delete_schedule(device_id, slot)`

Cancel a schedule slot, freeing it up for a future `create_schedule` call.

**Parameters**

- **`device_id`** (str, required) — The device whose schedule to cancel.
- **`slot`** (int, required) — Which slot (0-4) to cancel.

**Example**

```python
client.delete_schedule("dev_a1b2c3", 0)
```

**Returns** `{"ok": True}`

### `get_schedule_history(device_id)`

A device's completed or cancelled schedules, most recent first, for auditing what actually ran.

**Parameters**

- **`device_id`** (str, required) — The device to check.

**Example**

```python
history = client.get_schedule_history("dev_a1b2c3")
```

**Returns** `List[Schedule]` — same `Schedule` shape as `list_schedules`, but for slots that are `COMPLETED` or `CANCELLED` rather than still pending/active.

Full reference with every return type spelled out: **[SDK Reference](https://docs.nexalware.com/docs/sdk/sdk-python)**.

## Links

- [Docs](https://docs.nexalware.com)
- [Device Orchestration](https://docs.nexalware.com/docs/device-orchestration) - sub-devices, and the contract a master implements to report them.
- [Authentication & Access](https://docs.nexalware.com/docs/concepts/authentication-and-access) - API keys and DeviceGrants.

## License

MIT
