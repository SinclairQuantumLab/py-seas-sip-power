# py-seas-sip-power handoff

Updated 2026-09-18, America/Chicago.

## Start here

Read AGENTS.md, DECISIONS.md, VALIDATION.md and PROTOCOL.md. Run Git commands
inside this repository, not the parent. Begin with offline inspection; this
handoff does not authorize live control or further code changes by itself.

AGENTS.md now has separate entry points for agents developing the library and
agents integrating it into a consumer, including fresh-computer setup. The root
AGENTS.md is the shared context; the parent relay's files remain separately owned.

## Transfer status, 2026-09-18

- Requested software scope is implemented: complete Rev. 4 UDP/Modbus interface,
  enum access guards, common device/status API and the single Jupytext demo.
  Hardware qualification remains outstanding as described below; there is no
  remaining feature request from this session to infer or implement automatically.
- Implementation, README/protocol documentation and the final demo/test sources
  are committed in 95bc12b (Add unified UDP and Modbus device API with guarded
  controls). All previously untracked helpers/tests are included. This handoff
  and agent context form the following documentation commit. The user authorized
  local commits; no push has been performed by this thread. Check Git status/log
  and remote state before transferring work; publish the library before any
  separate consumer gitlink update.
- demo.ipynb is intentionally removed from tracking and remains present locally.
  A fresh clone reconstructs it from demo.py; saved outputs and .agents/local
  backups do not transfer through Git. The user corrected the local identifier
  to 192.168.50.34; it is a saved connection target, not authorization to connect.
  Recheck the intended endpoint on another computer.
- The last reported notebook error was identified by the user as an address
  issue; they explicitly withdrew the debugging request. Do not reopen it as an
  unresolved library/merge defect. Current local outputs remain operator evidence.
- See AGENTS for uv sync --locked, notebook generation and offline checks.
  The parent relay's credential submodule, code and gitlink are outside this work.
- Commit verification exported only the staged files to an isolated folder,
  excluding ignored notebooks/settings/backups. That snapshot passed 299 offline
  tests, Ruff and uv build (sdist and wheel). The developer environment supplied
  the test tools; no new-machine dependency installation or hardware check was
  claimed. Local demo.ipynb retains all eight saved output cells and counts.

## Current architecture

The user corrected the abstraction after the complete protocol implementation.
The primary API is now SAESSIPPower with ConnectionSettings/ConnectionTypeEnum.
DeviceStatus has identical names/units across UDP, TCP and RTU; unobservable
fields are None. Named setting methods hide register addresses, packed bits,
scaling, UDP block preservation and Modbus ID prerequisite sequences. The old
clients described below remain compatibility/protocol APIs with unchanged ASTs.
Use the common API in README/demo and new consumer code; do not reintroduce
separate UDP and Modbus usage/test flows after connection setup.

Extracted from SinclairQuantumLab/seas-sip-power-to-influxdb commit b18c3a3.
Original saes_sip_power_client.py became seas_sip_client.py without behavioral
changes at extraction. The library has since gained the full remote interface
and read/write permissions at the user's request. This repo owns source tests and the SIP POWER
Rev.4 manual. The relay keeps script/schema tests and uses an editable package
plus a pinned Git submodule.

- SAESSIPPowerClient(SAESSIPPowerSettings(host, port=2527, timeout_s=3),
  access_mode=AccessModeEnum.READ_ONLY). Omitting mode also defaults to READ_ONLY.
- connect, read_sample, reconnect, close manage synchronous reads.
- read_all is the manual-name alias of read_sample; SourceSample is unchanged.
- All UDP commands are implemented: start, stop, reset, clear_alarm,
  set_working_parameters and set_ip_address. They require READ_WRITE and have
  no ACK or automatic retry. WorkingParameters validates the whole 34-byte block.
- SAESSIPPowerModbusClient takes ModbusTCPSettings or ModbusRTUSettings and the
  same AccessModeEnum. Functions 0x03/0x10 and all 31 official register entries
  are supported, including explicit critical steps for Modbus ID changes.
- All public enum class names end in Enum; callers must supply real enum members.
  The public mode is immutable and cannot be upgraded through reconnect.
- Broadcast writes are explicit (UDPAddressModeEnum.BROADCAST or RTU unit 255).
  Broadcast reads are rejected. No implicit Stop, settings change or heartbeat.
- UDP/TCP need no runtime dependency; RTU optionally imports pySerial on connect.
- Demo uses this library's .venv and inline connection values, without reading
  settings.toml. Set connection_type and identifier (IP/hostname or serial device)
  in setup; library defaults supply network ports and serial parameters. Optional
  broadcast uses an inline broadcast_identifier in its own test section.
- demo.py is the tracked Jupytext percent source; demo.ipynb and all notebook
  outputs/checkpoints are local and ignored. The setup cell imports pure
  formatting from checkout-only demo_helpers.py; it never opens a connection.
- One notebook has Part 1 read-only tests, an explicit stopping boundary, then
  optional Part 2 read/write tests. ConnectionTypeEnum is chosen only in setup;
  every later test uses SAESSIPPower/DeviceStatus without raw registers. The same
  cells cover all controls, parameters, endpoint changes and broadcast capability.
  Part 1 never constructs a writable client; Part 2 creates READ_WRITE instances.
- Every write has separate Before/Write/After cells; three fresh readbacks show
  observed status and comparisons. Re-running After sends reads only. Modbus
  critical steps and ID write are handled inside the common set_modbus_id method;
  the notebook observes around that explicit operation. Existing Stop and
  the 0.1-second readback interval remain. No notebook handlers/prompts or workers
  were added. Complete checks use fake transports, not a live notebook kernel.
- The operator's additional time.sleep(0.1) following the Start Before read was
  found in the local notebook and preserved during the common-API rewrite.

## Evidence and remaining work

The original extraction notebook has a successful Read All dated 2026-09-18 UTC,
keepalive 10000 ms, enabled output and no alarm. Start/Stop were unexecuted in
that extraction record. This
is operator read evidence, not a verified control transition. The exact dirty
notebook is backed up in the parent's ignored
.agents/local/demo-before-library-split.ipynb, not published.

The later local notebook preserved before expanding the demo reports execution
counts 9 and 10 on Start and Stop, with no outputs on those cells. This is local
notebook metadata, not an agent-run hardware check or proof of accepted HV
transitions. Its exact bytes are preserved in the library's ignored
.agents/local/demo-before-demo-split-20260918-031140-683091.ipynb. Existing saved
outputs and execution counts remain historical records in the updated notebook.

Actual HV transitions, Stop voltage decay, keepalive ownership across competing
clients and behavior on disconnect are not hardware-qualified. Mocks cannot
establish those guarantees. Live control qualification needs explicit user
operation authorization.
New configuration commands, Modbus TCP/RTU, broadcasts and critical-step sequences
are offline-tested only. No library development request authorizes live controls.

The previously deferred Jupytext migration was authorized and implemented on
2026-09-18, together with readable status tables and named active alarms.
Before migration, this library's operator-run notebook was copied byte-for-byte
to ignored .agents/local/demo-before-jupytext-20260918-015435.ipynb and its SHA256
was verified. It contains the 2026-09-18 06:52:48 UTC Read All result; no control
cell was executed. The updated local demo was generated without execution.

The user then requested the complete manual remote interface and enum access
modes; these are implemented. Before updating the notebook again, its latest
inputs/outputs were preserved in .agents/local/demo-before-full-api-20260918-024435.ipynb.
See README for the deliberate migration requirement on existing control callers.
All parent relay files and credentials remain outside this thread's work.

No further software implementation item remains from the extraction handoff.
The hardware qualification gaps above remain separate, explicitly authorized
operator work. No live device access was performed for the notebook changes.

## Documentation convention

README is written for users importing the library into another program:
first clone inside the consuming project and uv add --editable from its root,
then direct Git uv/pip alternatives, basic API use, connections and commands.
The library's own uv sync environment and notebook instructions belong to Development.
Preserve this distinction in future edits; see AGENTS.md. Detailed protocol
evidence and implementation history remain here and in the other .agents records.

## Development workflow

uv sync; uv run pytest -q; uv run ruff check . For demo: uv sync --group notebook
and select this repo's .venv. Do not execute hardware notebook cells unattended.
Optional serial installation: uv sync --extra serial. Run uv build for packaging.
Generate/update locally: uv run jupytext --to ipynb --update demo.py.
Maintaining local demo.ipynb is mandatory after demo source edits, even though
Git ignores it. Inspect local edits, back up outputs, sync without execution,
and verify matching cell inputs before finishing; generate it if missing.
After saving notebook edits: uv run jupytext --sync demo.ipynb; review demo.py.
See README for output preservation and editor synchronization details.
Push library commits first, then separately update/test the relay gitlink.
Use a separate clone for experiments if the consumer checkout runs continuously.
