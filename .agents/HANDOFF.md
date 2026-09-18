# py-seas-sip-power handoff

Updated 2026-09-18, America/Chicago.

## Start here

Read AGENTS.md, DECISIONS.md, VALIDATION.md and PROTOCOL.md. Run Git commands
inside this repository, not the parent. Begin with offline inspection; this
handoff does not authorize live control or further code changes by itself.

## Current architecture

Extracted from SinclairQuantumLab/seas-sip-power-to-influxdb commit b18c3a3.
Original saes_sip_power_client.py is now seas_sip_client.py; implementation and
public classes are unchanged. This repo owns source tests and the SIP POWER
Rev.4 manual. The relay keeps script/schema tests and uses an editable package
plus a pinned Git submodule.

- SAESSIPPowerClient(SAESSIPPowerSettings(host, port=2527, timeout_s=3)).
- connect, read_sample, reconnect, close manage synchronous reads.
- start/stop explicitly control HV, with no ACK or automatic retries.
- No implicit Stop, keepalive change or background heartbeat.
- Demo uses ignored local settings.toml and this library's .venv.

## Evidence and remaining work

The user's notebook has a successful Read All dated 2026-09-18 UTC, keepalive
10000 ms, enabled output and no alarm. Start/Stop cells were unexecuted. This
is operator read evidence, not a verified control transition. The exact dirty
notebook is backed up in the parent's ignored
.agents/local/demo-before-library-split.ipynb, not published.

Actual HV transitions, Stop voltage decay, keepalive ownership across competing
clients and behavior on disconnect are not hardware-qualified. Mocks cannot
establish those guarantees. Live control qualification needs explicit user
operation authorization.

Next notebook task: migrate to Jupytext tracked text sources and ignore all
ipynb files/outputs, preserving local runs. The user asked to record this now
and explicitly allowed implementation to wait.

## Development workflow

uv sync; uv run pytest -q; uv run ruff check . For demo: uv sync --group notebook
and select this repo's .venv. Do not execute hardware notebook cells unattended.
Push library commits first, then separately update/test the relay gitlink.
Use a separate clone for experiments if the consumer checkout runs continuously.
