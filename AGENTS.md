# py-seas-sip-power Agent Instructions

## Scope and start

Maintain the synchronous SAES SIP POWER library and direct-call demo. This directory
is its own Git repository and a submodule of seas-sip-power-to-influxdb. Confirm
the Git root before editing or committing. Do not change the parent relay or
its credential submodule unless consumer changes are explicitly requested.

1. Inspect git status and every staged/unstaged diff; preserve user edits.
2. Read .agents/HANDOFF.md, .agents/DECISIONS.md, .agents/VALIDATION.md, then
   .agents/PROTOCOL.md before
   protocol/control work. Inspect source, tests, notebook and recent history.

## For agents using this library

This section is the integration context for an agent working in a consuming
project. Read [README.md](README.md) for examples and the Control contract below
before device I/O. Application scheduling, storage and reconnect policy belong
to the consumer; this repository owns device communication only.

- Python >=3.11. Distribution: py-seas-sip-power; import: seas_sip_client
  (repository/module spelling uses seas; public classes use manufacturer SAES).
- From an existing uv consumer project's root, clone this repository into
  ./py-seas-sip-power and run `uv add --editable ./py-seas-sip-power`.
  For RTU add `--extra serial`. Run the application with the consumer's environment;
  its runtime does not need this library's dev/notebook groups or settings.toml.
  Git dependency alternatives are in README. The installed package contains
  seas_sip_client only; demo_helpers is not an installed/public library module.
- Use SAESSIPPower(ConnectionSettings(identifier, connection_type=...),
  access_mode=AccessModeEnum.READ_ONLY). identifier is a caller variable passed
  to the address field, not an identifier keyword on ConnectionSettings.
  UDP/TCP take an IPv4 address or hostname; RTU takes a serial device such as
  COM3 or /dev/ttyUSB0. Defaults: UDP 2527, TCP 502; RTU 38400 baud/8N2; ID 11.
  Use ConnectionTypeEnum.UDP/MODBUS_TCP/MODBUS_RTU; no protocol branches after setup.
- Constructor performs no I/O. Explicitly connect, read and close. Calls are
  synchronous; serialize operations on one instance. is_connected describes local
  transport ownership, not device reachability. status performs a fresh read;
  retain a returned snapshot when inspecting several fields without more I/O.
- read_sample/read_all/status return DeviceStatus on every transport. Units are
  named in fields (V, nA, K, ms/s/h, Torr); observed_at is host aware UTC, not a
  device clock. Modbus ID is unobservable and None; network/keepalive fields may
  also be None. Do not replace unknowns with configured values, zero or last writes.
  is_single_response does not promise simultaneous physical measurements.
- Use named settings/control methods, not raw registers, in ordinary consumer
  code. AccessModeEnum.READ_WRITE must be selected at construction for writes.
  Preserve the distinction between observations and requested targets, including
  partial configuration failures. Never blindly replay a timed-out write.
  IP/ID setters do not retarget the client: use with_ip_address/with_modbus_id,
  close, create/connect a new client, and verify identity and state by reading.
- Handle SAESSIPPowerError in the consuming application as appropriate; errors
  include permission, communication, protocol, unsupported-operation and Modbus
  device exceptions. Do not turn a failed acquisition into a fabricated sample.
  Legacy UDP/raw Modbus APIs remain compatible; new integrations use SAESSIPPower.
- Editable source changes immediately affect new imports in the consumer; restart
  running processes/kernels after updates. A nested clone and editable path are
  not transferred by pushing the outer project alone. Follow that project's
  chosen clone/submodule workflow; do not silently restructure it. The existing
  parent relay uses a submodule whose Git pointer is managed in a separate thread.

## For agents developing this library

Read the ownership map and implementation rules below, then the linked
[handoff](.agents/HANDOFF.md), [decisions](.agents/DECISIONS.md),
[validation](.agents/VALIDATION.md) and [protocol](.agents/PROTOCOL.md).
The protocol source is device-docs/saes-sip_power-user_manual-rev_4.pdf.
Other bundled device manuals do not extend the implemented SIP POWER scope.

On another computer, clone this library and run from its repository root:

```bash
uv sync --locked
uv run jupytext --to ipynb --update demo.py
uv run pytest -q
uv run ruff check .
```

For RTU use `uv sync --locked --extra serial`. The default dev group includes
notebook dependencies. Select the recreated .venv as the notebook kernel; check
the inline identifier and transport for the intended device before running cells.
Neither .venv nor local notebook outputs/backups/settings transfer through Git.
The generated notebook starts without old execution evidence on a fresh clone.
Tests use synthetic adapters and generate notebooks without device execution;
they must not depend on an ignored local notebook, settings or .agents/local data.

Before publishing, inspect both the current tree and the staged snapshot: earlier
partial staging can contain an older demo than the tested source. Include all
required new modules/tests and uv.lock; never force-add ignored notebooks or
outputs. Removing demo.ipynb from the index is intentional, not a local deletion.
Publish this repository before a consuming repository updates its gitlink. Record
what was actually tested in VALIDATION; do not claim hardware qualification from
mock tests or historical notebook counts. Current remaining work/status belongs
in HANDOFF, not an assumption that all local changes have already been committed.

## Library identity and documentation

This repository provides an importable device library. Lead README with installing
it into a consuming project's environment: first clone inside that project and
uv add --editable, then direct Git dependencies with uv/pip. Follow with Python
imports, basic use, connections and the manual-to-API mapping. Keep this library's
own uv sync environment, notebook setup and offline checks in the development section.
Do not present the library as a standalone relay/application or require consumers
to adopt this checkout's environment, settings file or notebook dependencies.
Keep operational history and detailed protocol evidence in .agents; README should
explain the current public API and the control constraints a caller needs.

## Ownership

- seas_sip_client.py: UDP/Modbus transports, framing, parsing, samples, commands,
  register access, the common SAESSIPPower device API and AccessModeEnum guard.
  ConnectionSettings/ConnectionTypeEnum select transport once. DeviceStatus
  exposes the same names/units across transports; unobservable fields are None.
  Keep legacy UDP SourceSample/client and raw Modbus APIs compatible.
- demo.py: tracked Jupytext percent source for direct demo/test calls;
  demo.ipynb is generated locally and ignored. The user wants no input validation,
  exception handling, confirmation prompts, or background workers here.
  Specify connection_type and identifier directly in the setup cell; never load
  a settings file. Use identifier for either an IP/hostname or a serial device,
  with comments explaining formats and library defaults instead of protocol branches.
  Keep HV commands and sample reads in separate cells so repeating a read never
  resends Start/Stop. Preserve the operator's local edits and execution outputs.
- Keep one demo notebook: Part 1 contains only READ_ONLY clients and tests,
  followed by an explicit end-of-read-only boundary. Part 2 creates READ_WRITE
  clients and covers all remote write functions. Do not split these into files.
  Select transport only in connection setup. All subsequent device tests use
  SAESSIPPower and DeviceStatus, with no raw registers or duplicated protocol flows.
  Writes have separate Before/Write/After cells with rich fresh readback; repeating
  readback must never resend a write. The common set_modbus_id call owns the
  required protocol sequence; the notebook only observes before and after it.
- demo_helpers.py: checkout-only pure snapshot/table formatting, with no device I/O.
- .agents/test_seas_sip_client.py: offline protocol and notebook tests.
- .agents/test_commands_and_modbus.py: permissions, all commands/registers,
  transport framing and failure-path tests; no hardware access.
- .agents/test_demo.py: all notebook sections against fake UDP/TCP/RTU transports,
  read-only isolation, write coverage, repeatable readback and formatted displays.
- .agents/test_device.py and demo_fakes.py: common API/unit equivalence, unknown
  observations, guards, setting preservation and failure sequences on fake adapters.
- settings.toml.template: optional legacy configuration reference, not loaded by
  the demo or library. Actual settings are ignored.
- .agents/: protocol sources, decisions, evidence and current handoff.
- Never read parent imaq-secret credentials; the library has no InfluxDB needs.

## Control contract

- UDP read_sample sends only Read All; Modbus acquisition uses read functions.
  Connecting, reconnecting and closing
  never issue Start, Stop, Reset or Clear Alarm.
- Default access is AccessModeEnum.READ_ONLY. Every write/control path must fail
  before device I/O unless constructed with AccessModeEnum.READ_WRITE. Require
  enum members, not strings/bools/ints; all public enum names end in Enum.
  No public mode setter or reconnect-based mode upgrade is allowed.
- The user authorized the complete Rev. 4 remote interface on 2026-09-18: UDP
  commands and Modbus TCP/RTU functions/registers, including explicit configuration,
  Reset/Restart, Clear Alarm and broadcast writes. Preserve official names.
- Every write is explicit, with no automatic retry, alarm clearing, interlock
  bypass, implicit Stop on close or configuration changes. Broadcast is explicit;
  broadcast reads are prohibited. The common set_modbus_id operation explicitly
  authorizes its protocol-specific prerequisite sequence (critical steps then ID).
  Stop at the first failure without retry or rollback. The legacy raw Modbus
  setter still writes only ID, preserving its original low-level contract.
- UDP has no ACK. Send success is not proof of accepted control. Read back enabled
  status, actual voltage and alarms to understand the observed state.
- Modbus writes check the response/echo but still require physical-state readback.
- Keepalive changes only through an explicit writable configuration call. After
  remote Start/Reset/Restart, poll with the same client within the configured
  interval. No background heartbeat exists.
- Access mode prevents accidental application writes, not arbitrary Python
  manipulation or network access by other programs.
- Development/demo requests do not authorize live HV switching. Use offline
  tests first; send live controls only with explicit user direction for the
  identified device. Respect already-granted authorization without reasking.
- Never run all notebook cells against hardware as an unattended check.

## Implementation and verification

Keep the single-module design, typed functions and useful docstrings. Preserve
public classes, sample fields/types/units, UTC timestamps and error behavior.
Existing control callers must opt into READ_WRITE. The main device-facing API
is SAESSIPPower with DeviceStatus on every transport; scale and decode internally.
The old ModbusSample/SourceSample types remain for legacy transport clients.
Never fill an unavailable observation from configured values or the last write.
Named setting changes preserve other settings internally (UDP read-modify-write,
Modbus affected registers/packed modes); guard and validate before any I/O.
Coordinate sample changes with consumers; do not introduce relay policy here.
Use uv sync, or uv sync --group notebook for the demo. Run uv run pytest -q and
uv run ruff check . after code changes; uv build for packaging changes.
RTU uses the optional serial extra (uv sync --extra serial); UDP/TCP have no
runtime dependencies. No implicit live serial/network checks are authorized.
Distinguish mocks, operator evidence and agent-run live checks. Update README
and .agents records when behavior or evidence changes. Preserve user notebook
runs locally before clearing outputs for commits.

Make focused commits; publish library commits before consumer gitlinks. Editable
source affects consumers before commit, so use an isolated clone for experiments
when needed. Use to-influxdb-development for parent relay changes; ordinary
standalone library maintenance does not require the relay skill.

## Notebook source and outputs

Use Jupytext text sources as the Git-tracked notebook representation. Ignore all
actual `*.ipynb` files and notebook checkpoints so execution outputs never enter
Git. Preserve local notebooks/outputs when removing already-tracked notebooks
from the index. Update notebook generation/sync instructions and offline tests
as part of that migration. The user explicitly deferred implementation during
the repository extraction, then authorized it on 2026-09-18. Migration is now
implemented: edit demo.py, generate/update with
`uv run jupytext --to ipynb --update demo.py`, or save notebook edits and run
`uv run jupytext --sync demo.ipynb`. Conversion/sync must never execute cells.
Preserve local runs before changing executed cells; `--update` retains outputs
for matching cells. Only the text source belongs in Git.

Git ignore governs version control only. Always maintain a usable local
demo.ipynb alongside demo.py. After changing the demo source, generate/update
the notebook before finishing the task and verify their cell inputs match.
If it is missing, generate it. Inspect and preserve local notebook edits and
outputs before choosing the sync direction; never overwrite newer local inputs
blindly. Back up existing runs before conversion, retain matching outputs and
execution counts, and never execute cells as part of synchronization. Do not
leave regeneration to the user merely because the notebook is ignored by Git.
