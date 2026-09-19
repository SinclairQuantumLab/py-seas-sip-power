# py-seas-sip-power

A synchronous Python library for reading and controlling SAES SIP POWER ion-pump
power supplies. Choose UDP, Modbus TCP or Modbus RTU when creating the connection;
use the same device methods, status fields and units afterward. The implementation
follows the [SIP POWER Rev. 4 manual](device-docs/saes-sip_power-user_manual-rev_4.pdf).

Clients are read-only by default. Control and configuration require an explicit
`AccessModeEnum.READ_WRITE` when creating the device instance.

## Installation

Python 3.11 or newer and Git are required to install from this repository.
In a project managed with uv, clone the library inside the consuming project's
repository and add the local checkout as an editable dependency. Run both commands
from the consuming project's root (the directory containing its `pyproject.toml`):

```bash
git clone https://github.com/SinclairQuantumLab/py-seas-sip-power.git
uv add --editable ./py-seas-sip-power
```

This installs the library into the consuming project's environment. Edits to the
local library source are used without reinstalling it. Keep the checkout at that
path; restart a running Python process or notebook kernel after source changes.

Alternatively, add the dependency directly from Git:

```bash
uv add "py-seas-sip-power @ git+https://github.com/SinclairQuantumLab/py-seas-sip-power.git"
```

For a project using pip, install into that project's environment:

```bash
python -m pip install "py-seas-sip-power @ git+https://github.com/SinclairQuantumLab/py-seas-sip-power.git"
```

The distribution is `py-seas-sip-power`; the import is `seas_sip_client`.
UDP and Modbus TCP use only the standard library. RTU needs the `serial` extra.
For the editable checkout, use:

```bash
uv add --editable ./py-seas-sip-power --extra serial
```

For a direct Git dependency, use `py-seas-sip-power[serial]` in the requirement:

```bash
python -m pip install "py-seas-sip-power[serial] @ git+https://github.com/SinclairQuantumLab/py-seas-sip-power.git"
```

Use the same `[serial]` requirement with `uv add` in a uv project.
Checkout setup for development and the demo is described below.

## Basic use

```python
import seas_sip_client as sip

connection = sip.ConnectionSettings(
    "192.168.1.20",
    connection_type=sip.ConnectionTypeEnum.UDP,
)
client = sip.SAESSIPPower(connection, access_mode=sip.AccessModeEnum.READ_ONLY)
client.connect()
try:
    status = client.read_sample()
    print(f"HV enabled: {status.enabled}")
    print(f"Output: {status.output_voltage_v} V, {status.output_current_na} nA")
    print(f"Input: {status.input_voltage_v} V")
    print(f"Alarm: {status.global_alarm}")
finally:
    client.close()
```

For Modbus TCP change the choice to `ConnectionTypeEnum.MODBUS_TCP`. For RTU use
`ConnectionTypeEnum.MODBUS_RTU` and the serial port as the address. The code after
constructing the connection stays the same.

## Connections and access

| Connection choice | Address | Defaults |
| --- | --- | --- |
| `ConnectionTypeEnum.UDP` | Controller IP or hostname | Port 2527 |
| `ConnectionTypeEnum.MODBUS_TCP` | Controller IP or hostname | Port 502, unit ID 11 |
| `ConnectionTypeEnum.MODBUS_RTU` | Serial port, such as `COM3` or `/dev/ttyUSB0` | 38400 baud, 8N2, no flow control, unit ID 11 |

`ConnectionSettings` also accepts `timeout_s` (default 3), an optional Ethernet
`port`, `modbus_id`, `baudrate` and `address_mode`. Connection and access choices
require actual enum members. Construction opens no connection. `connect()`,
`reconnect()` and `close()` manage the selected transport without controls or
settings changes. Calls are synchronous; use one execution flow per instance.

| Access mode | Allowed operations |
| --- | --- |
| `AccessModeEnum.READ_ONLY` (default) | Connection management and reads |
| `AccessModeEnum.READ_WRITE` | Reads, explicit control and configuration writes |

Access mode has no public setter and survives reconnect. A read-only write raises
`SAESSIPPowerPermissionError` before any I/O, including a read needed to preserve
other settings. Create another instance to choose a different mode. This prevents
accidental API writes; it is not device authentication. Reads can still refresh
an active keepalive watchdog.

## Reading state

`read_sample()`, `read_all()` and the `status` property each perform a fresh
acquisition and return **DeviceStatus** on every connection. Store a snapshot
once when examining several fields; accessing its fields performs no I/O.

```python
status = client.status
print(status.serial_number, status.hardware_revision, status.software_version)
print(status.enabled, status.need_restart, status.interlock_alarm)
print(status.output_voltage_setpoint_v, status.output_voltage_ramp_interval_ms)
print(status.switch_1_mode, status.switch_1_threshold_na)
print(status.ip_address, status.ip_netmask)
```

Status includes identification, measurements, individual alarms, switch states,
working parameters and network settings. Voltage is V, current/thresholds are nA,
temperature is K, pressure is Torr, and time fields end in `_ms`, `_s` or `_h`.
Addresses and masks are dotted IPv4 strings. Modbus scaling, word order and
status-bit decoding are internal. `observed_at` is an aware UTC host timestamp.

Unavailable observations are `None`. Modbus cannot read the write-only Modbus ID;
`client.settings.modbus_id` is the configured destination, not a measured value.
Ethernet settings are unavailable on non-Ethernet cards. `pressure_torr` is
unavailable when the conversion rate is zero. `is_single_response` is true for
UDP's one Read All response and false for a Modbus acquisition spanning several
requests; neither implies simultaneous physical sensor measurements.

## Control and configuration

Create a writable instance with the same connection, then connect it before
issuing a selected operation:

```python
client = sip.SAESSIPPower(connection, access_mode=sip.AccessModeEnum.READ_WRITE)
client.connect()
```

These methods have the same meaning on every supported connection:

| Operation | Device API |
| --- | --- |
| Enable / disable HV | `client.start()` / `client.stop()` |
| Recover from the restart-required condition | `client.reset()` or `client.restart()` |
| Select a control through an enum | `client.enable(sip.EnableCommandEnum.STOP)` |
| Clear alarm latches | `client.clear_alarm()` |
| Change working parameters | `client.set_working_parameters(...)` |
| Set three comparator modes | `client.set_switch_modes(sw1, sw2, sw3)` |
| Change device Modbus ID | `client.set_modbus_id(new_id)` |
| Change IPv4 address and dotted netmask | `client.set_ip_address(address, netmask)` |

Start and Stop are the manufacturer's HV commands; acquisition is separate.
`reset()` and `restart()` are aliases, sending UDP Reset or Modbus Restart. They
do not reset the connection or factory settings.

Use named fields to change only the settings you intend:

```python
client.set_working_parameters(
    output_voltage_setpoint_v=5000,
    output_voltage_ramp_interval_ms=2000,
)
client.set_working_parameters(switch_2_mode=sip.SwitchModeEnum.WINDOW)
```

Accepted fields are `output_voltage_setpoint_v`, `output_voltage_ramp_interval_ms`,
`switch_1_mode`, `switch_2_mode`, `switch_3_mode`, `switch_1_threshold_na`,
`switch_2_min_threshold_na`, `switch_2_max_threshold_na`, `switch_3_min_threshold_na`,
`switch_3_max_threshold_na`, `keepalive_interval_ms`, `conversion_rate_a_per_torr`
and `modbus_id`. Omitted fields remain unchanged. Modes require
`SwitchModeEnum.OFF`, `.SIMPLE` or `.WINDOW`; SW1 supports only OFF/SIMPLE.
A complete `WorkingParameters` target object is also accepted.

All supplied targets are validated before I/O. A partial UDP update reads the
current block, preserves other settings and sends Set Working Parameters once.
Modbus encodes affected registers and preserves unspecified packed switch modes.
Coordinate concurrent writers: UDP read-modify-write is not atomic. Multi-request
Modbus changes can partially succeed; there is no automatic rollback or retry.

An explicit `set_modbus_id()` includes the required Modbus critical step 1,
critical step 2 and ID write, stopping at the first error. UDP updates the ID in
the working-parameter block. No alarm clear, HV switching or unrelated setting
change is inserted into a configuration operation.

### Readback and endpoint changes

Reads remain separate from writes:

```python
before = client.read_sample()
client.set_working_parameters(output_voltage_setpoint_v=5000)
after = client.read_sample()
print(before.output_voltage_setpoint_v, after.output_voltage_setpoint_v)
print(after.enabled, after.output_voltage_v, after.global_alarm)
```

UDP writes have no ACK; successful transmission does not prove acceptance.
Modbus replies confirm protocol handling. Inspect actual voltage/current,
enabled state and alarms to assess the resulting state. A timed-out write does
not establish that nothing changed.

Address/ID setters leave the current connection unchanged. Prepare a new
connection explicitly for readback:

```python
client.set_ip_address("192.168.1.21", "255.255.255.0")
client.close()
connection = connection.with_ip_address("192.168.1.21")
client = sip.SAESSIPPower(connection, access_mode=sip.AccessModeEnum.READ_WRITE)
client.connect()
status = client.read_sample()
client.close()
```

`with_ip_address()` updates an Ethernet destination and retains an RTU serial
port. Use `connection.with_modbus_id(new_id)` after an ID change. These settings
methods perform no device I/O. Compare identity at the changed endpoint.

### Broadcast and unsupported operations

UDP and RTU support explicit broadcast connections. UDP needs a destination;
RTU retains its bus and internally selects SAES broadcast unit 255:

```python
broadcast_connection = connection.for_broadcast(udp_address="192.168.1.255")
broadcaster = sip.SAESSIPPower(
    broadcast_connection, access_mode=sip.AccessModeEnum.READ_WRITE,
)
```

Broadcasts require `READ_WRITE`, have no ACK, and cannot read. Use unicast
observers for the intended targets. TCP broadcast and unavailable Ethernet
settings raise `SAESSIPPowerUnsupportedOperationError`. UDP broadcast parameter
writes need a complete `WorkingParameters` object; Modbus broadcast mode changes
need all three switch modes because missing values cannot be read.

## Keepalive and errors

After remote Start or Reset/Restart, poll through the same instance within the
configured keepalive interval when enabled. Missing it stops HV with a
communication alarm. The library has no background heartbeat; the application
owns polling. Closing never sends Stop.

Failures derive from `SAESSIPPowerError`, including permission, communication,
protocol and unsupported-operation errors. Modbus device exceptions retain their
function and exception code. Invalid or incomplete Modbus replies close the
transport; reconnect explicitly when appropriate. No request is retried automatically.

## Development and notebook demo

Clone to edit the library or use the included notebook:

```bash
git clone https://github.com/SinclairQuantumLab/py-seas-sip-power.git
cd py-seas-sip-power
uv sync
uv run jupytext --to ipynb --update demo.py
```

This prepares the development environment and generates a notebook without
executing cells. For RTU use `uv sync --extra serial`. Open `demo.ipynb` with
this checkout's `.venv` kernel. Set `connection_type` and `identifier` directly
in its connection cell: an IP/hostname for UDP/TCP, or a serial device such as
`COM3` for RTU. The library supplies the default network port and serial settings;
the cell comments explain overrides. The demo does not read a settings file.
Restart an existing kernel after updating library code so imports use the new API.

The single notebook selects `ConnectionTypeEnum` once, then tests the common API.
**Part 1** contains only read-only tests and an explicit stopping boundary.
**Part 2** creates writable instances and covers controls, every working parameter,
mode groups, ID/address changes and optional broadcast. Writes have separate
Before/Write/After cells, three fresh readbacks and comparison tables. Repeating
After never resends a write. Run individual cells, accounting for keepalive;
do not Run All or execute `demo.py` as a script.

[`demo.py`](demo.py) is the tracked Jupytext source;
[`demo_helpers.py`](demo_helpers.py) provides checkout-only formatting without I/O.
Keep local `demo.ipynb` synchronized whenever the source changes. All ipynb files,
checkpoints, settings and outputs remain local and Git-ignored. After saving
notebook edits, run `uv run jupytext --sync demo.ipynb` and review the text diff.
After source edits use `--to ipynb --update` as above. Save and close the editor
before external updates; preserve local runs before changing executed cells.
Matching outputs are retained. Sync never executes cells.

```bash
uv run pytest -q
uv run ruff check .
uv build
```

Tests use synthetic transports. New configuration operations, Modbus transports,
broadcasts and physical HV transitions remain unqualified on hardware; see
[VALIDATION.md](.agents/VALIDATION.md) for software tests and operator evidence.

The implementation remains [`seas_sip_client.py`](seas_sip_client.py). Existing
`SAESSIPPowerClient`/`SourceSample` UDP and `SAESSIPPowerModbusClient` register
interfaces remain available for compatibility and advanced protocol work. Their
contracts are unchanged; ordinary device code uses `SAESSIPPower` and
`DeviceStatus`. Wire details are in [PROTOCOL.md](.agents/PROTOCOL.md).

The InfluxDB relay is a separate consumer. Applications own scheduling, storage
and deployment; this library owns device communication. Maintainer workflow is
in [AGENTS.md](AGENTS.md) and [HANDOFF.md](.agents/HANDOFF.md).
