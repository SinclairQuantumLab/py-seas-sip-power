# py-seas-sip-power Agent Instructions

## Scope and start

Maintain the synchronous SAES SIP POWER library and minimal demo. This directory
is its own Git repository and a submodule of seas-sip-power-to-influxdb. Confirm
the Git root before editing or committing. Do not change the parent relay or
its credential submodule unless consumer changes are explicitly requested.

1. Inspect git status and every staged/unstaged diff; preserve user edits.
2. Read .agents/HANDOFF.md, DECISIONS.md, VALIDATION.md, then PROTOCOL.md before
   protocol/control work. Inspect source, tests, notebook and recent history.

## Ownership

- seas_sip_client.py: sockets, framing, parsing, samples, explicit Start/Stop.
- demo.ipynb: direct demo/test calls. The user wants no input validation,
  exception handling, confirmation prompts, or background workers here.
- .agents/test_seas_sip_client.py: offline protocol and notebook tests.
- settings.toml.template: portable configuration. Actual settings are ignored.
- .agents/: protocol sources, decisions, evidence and current handoff.
- Never read parent imaq-secret credentials; the library has no InfluxDB needs.

## Control contract

- Read All is the only read_sample command. Connecting, reconnecting and closing
  never issue Start, Stop, Reset or Clear Alarm.
- start/stop send one explicit unicast datagram; no automatic retries, alarm
  clearing, interlock bypass, implicit Stop on close or parameter changes.
- No ACK exists. Send success is not proof of accepted control. Read back enabled
  status, actual voltage and alarms to understand the observed state.
- Keepalive is unchanged: after remote Start, poll with the same client within
  its configured interval. No background heartbeat exists.
- The API separation does not enforce authorization or network security.
- Development/demo requests do not authorize live HV switching. Use offline
  tests first; send live controls only with explicit user direction for the
  identified device. Respect already-granted authorization without reasking.
- Never run all notebook cells against hardware as an unattended check.

## Implementation and verification

Keep the single-module design, typed functions and useful docstrings. Preserve
public classes, sample fields/types/units, UTC timestamps and error behavior.
Coordinate sample changes with consumers; do not introduce relay policy here.
Use uv sync, or uv sync --group notebook for the demo. Run uv run pytest -q and
uv run ruff check . after code changes; uv build for packaging changes.
Distinguish mocks, operator evidence and agent-run live checks. Update README
and .agents records when behavior or evidence changes. Preserve user notebook
runs locally before clearing outputs for commits.

Make focused commits; publish library commits before consumer gitlinks. Editable
source affects consumers before commit, so use an isolated clone for experiments
when needed. Use to-influxdb-development for parent relay changes; ordinary
standalone library maintenance does not require the relay skill.

## Deferred notebook migration requested by the user

Use Jupytext text sources as the Git-tracked notebook representation. Ignore all
actual `*.ipynb` files and notebook checkpoints so execution outputs never enter
Git. Preserve local notebooks/outputs when removing already-tracked notebooks
from the index. Update notebook generation/sync instructions and offline tests
as part of that migration. The user explicitly deferred implementation during
the repository extraction; record this as the next notebook-maintenance task.
