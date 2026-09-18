# py-seas-sip-power

Synchronous Python client for one SAES SIP POWER controller over Ethernet UDP.
Read snapshots and explicitly start or stop pump HV output. Stop leaves the
controller powered. No InfluxDB dependency or credentials.

## Installation

```bash
git clone https://github.com/SinclairQuantumLab/py-seas-sip-power.git
cd py-seas-sip-power
uv sync
```

## Usage

```python
from seas_sip_client import SAESSIPPowerClient, SAESSIPPowerSettings

client = SAESSIPPowerClient(SAESSIPPowerSettings("192.168.1.20"))
client.connect()
status = client.read_sample()
print(status.enabled, status.output_voltage_v, status.pressure_torr)
client.close()
```

`connect()`, `read_sample()`, `reconnect()`, and `close()` do not issue HV control
commands. `start()` sends Start; `stop()` sends Stop. Read back enabled state,
voltage/current and alarms with `read_sample()`. Control commands have no ACK
or automatic retry. Send success does not prove the device accepted a command.
Closing the socket does not send Stop.

After remote Start, poll through the same client within the reported
`keepalive_interval_ms` when enabled; otherwise HV stops with a communication
alarm. There is no automatic heartbeat, keepalive change, alarm clearing, or
interlock override. The API does not implement network authorization.

## Notebook demo

```bash
uv sync --group notebook
cp settings.toml.template settings.toml
```

Set `host`, open `demo.ipynb` in VS Code and select this library's `.venv`
kernel. Run from the library directory. Execute individual cells: connect,
read, Start + ten polls, Stop + read, close. The notebook intentionally has no
input validation or exception handling. Pausing can exceed device keepalive.

## Protocol and scope

- Ethernet IPv4 UDP port 2527, version 1.
- Read All `01 05`, exactly 302-byte response.
- Start `01 01`, Stop `01 02`, no payload or ACK.
- No Reset, Clear Alarm, parameter/IP writes or NEG controller support.
- SourceSample preserves snake_case fields and aware UTC host timestamps.
- One client owns one socket; synchronous calls, no concurrent use.

Source: `device-docs/saes-sip_power-user_manual-rev_4.pdf`, section 9.2.

## Validation status

Offline tests cover framing, control sends and notebook execution. The
operator's saved notebook records a successful read on 2026-09-18 UTC;
Start/Stop cells were unexecuted. Actual HV transitions remain unverified.
No device access was performed during extraction.

## Developer's note

Implementation: the installable root module `seas_sip_client.py`. Public class
names retain SAES manufacturer spelling; repository/module names use `seas`
as requested. Start with AGENTS.md and .agents/HANDOFF.md.

```bash
uv run pytest -q
uv run ruff check .
uv build
```

The relay consumes this repository as a pinned Git submodule and uv editable
path dependency. Push library commits first, then update/test/commit the
consumer pointer. Editable changes immediately affect the consumer environment;
the gitlink does not isolate uncommitted edits. Use a separate library clone
for experiments if the relay checkout runs continuously.
