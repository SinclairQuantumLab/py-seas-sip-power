# Validation evidence

## Extraction baseline, 2026-09-18

Parent b18c3a3 recorded 32 passing offline tests (16 relay, 16 client/notebook)
and Ruff. The two notebook cwd variants become one library-local variant.
Library source is copied byte-for-byte under seas_sip_client.py.

The dirty notebook contained an operator-run Read All; no Start/Stop execution
was recorded. Original preserved locally in parent .agents/local; distributed
demo outputs are empty. No device connection, upload or service restart is part
of extraction. See HANDOFF.md for hardware qualification gaps.

## Completed extraction checks

- Library: uv sync --group notebook, 15 offline tests and Ruff passed.
- Consumer: uv sync, 16 relay tests and CLI help passed; imports now resolve
  through the installed editable package. Ruff passed after import grouping.
- uv build produced an sdist and a py3-none-any wheel with seas_sip_client.py.
- Source bytes match b18c3a3 exactly; only the module path changed.
- Settings and original notebook output remain local/ignored. The public demo
  remains output-free. Jupytext migration is recorded, explicitly deferred.

## Jupytext migration and readable status, 2026-09-18

- The user authorized the deferred migration. demo.py now holds the percent-format
  notebook source, paired through jupytext.toml. All ipynb files and checkpoints
  are ignored, and demo.ipynb was removed from the Git index while kept locally.
- Before conversion, the operator-run notebook was copied to ignored
  .agents/local/demo-before-jupytext-20260918-015435.ipynb. Its SHA256 is
  F5D4443929B4E7EF7CD60EA92DBC8EFFF0E6B957DF919B8971D26CED6A1AFC56,
  verified before and after migration. This preserves the original execution
  counts and raw Read All result. The same saved Read All output/count also remain
  in the updated local demo; they were compared with the backup. Conversion did
  not execute cells, so the saved output still shows the old raw representation
  until the user renders the new summary.
- uv sync --group notebook completed; uv run pytest -q passed all 18 offline
  tests; uv run ruff check . and uv build passed. After extending the round-trip
  test to cover notebook-to-text sync, that test and Ruff passed again.
- Offline demo execution uses synthetic settings and fake sockets; real socket
  construction is blocked in the demo test. The original Read All/Start/Stop
  datagram sequence is unchanged. Status formatting covers active/absent alarms,
  an individual alarm without the global flag, unavailable pressure, disabled
  keepalive, units and UTC labels. Disabled HV is displayed separately from the
  remaining measured voltage in the synthetic Stop readback.
- A temporary directory test generates ipynb from text alone, updates text-to-
  notebook inputs while retaining a synthetic output/execution count, then syncs
  a notebook edit back to text while retaining that output. No notebook cells
  are executed by these conversion commands.
- The generated local notebook's cell types and sources match demo.py.
  Git ignore rules cover both root and nested notebooks and checkpoints.
- seas_sip_client.py is unchanged from HEAD; runtime dependencies remain empty.
  Existing locked third-party packages are unchanged; additions support Jupytext.
- These are offline agent checks, not live hardware evidence. No device access,
  HV operation, parent relay changes, commit or push was performed.

## Separate control and sample cells, 2026-09-18

- Enable HV and Read 10 samples are separate cells. Disable HV and readback are
  also separate; the user's local commented-out client.stop() and 0.1-second
  delay before readback were preserved in the text source and regenerated demo.
- The latest local notebook, including operator outputs and edits, was backed up
  byte-for-byte to .agents/local/demo-before-cell-split-20260918-022424.ipynb
  before regeneration. Its code cells had execution counts 4, 3, 5, None, 9,
  None; the count-9 cell had Stop commented out, so it is not control evidence.
- uv run pytest -q passed all 18 offline tests; uv run ruff check . passed.
  The demo test executes the sampling cell twice and confirms that it sends
  only 20 Read All requests, with no repeated Start or Stop. Start is checked
  separately as a single send. The commented-out Stop cell sends nothing.
- The official Rev. 4 manual page 46 was text-extracted and visually inspected:
  Start (0x01) and Stop (0x02) are manufacturer UDP command names. The library's
  Python method names mirror those terms; no public API change was made.
- The local notebook was regenerated without executing device cells. No live
  connection, HV operation, parent repository change, commit or push occurred.

## Full remote interface and access modes, 2026-09-18

- User authorized all Rev. 4 remote commands/functions and enum-typed read-only
  versus read/write instances. Implemented all seven UDP request commands and
  Read All Answer parsing, explicit UDP broadcast mode, Modbus TCP and RS485 RTU,
  both supported Modbus functions, and all 31 documented register entries.
- AccessModeEnum.READ_ONLY is the default. All six UDP write commands, Modbus
  helpers/direct register writes and the shared transport write boundary reject
  read-only access before I/O, including disconnected clients. Enum type checks,
  absence of a public mode setter and mode preservation on reconnect are tested.
- UDP tests use independent byte literals for all write packets. Tests cover
  parameter ranges/widths, switch mode enums, netmasks (including inverted host
  mask rejection), broadcast read rejection, exact one-send behavior and failures.
- Modbus tests cover every writable register, low-word-first encoding, all read
  groups with/without Ethernet, reserved/misaligned/inaccessible registers, typed
  helpers, no implicit critical steps, IP/mask encoding and no endpoint retargeting.
  Protocol tests cover fragmented reads, MBAP matching, device exceptions, RTU
  CRC with an independent known vector, broadcast 255, read deadlines, 4-ms gaps,
  malformed/short replies and write timeouts without replay. Production TCP and
  serial adapters are exercised through mocks, including short serial writes.
- The notebook is tested in both access modes: control cells fail without
  sending in READ_ONLY and send only their explicit commands in READ_WRITE.
  Repeating the sampling cell sends only reads. No notebook validation,
  exception handler, confirmation prompt or background worker was added.
- Latest local notebook inputs/outputs were backed up before changes to
  .agents/local/demo-before-full-api-20260918-024435.ipynb. The user's re-enabled
  Stop call, 0.1-second readback delay and extra empty cell were preserved. Both
  saved output cells also remain unchanged in the regenerated notebook.
- uv sync --group notebook --extra serial completed, and pySerial 3.5 imported
  without opening a port. uv run pytest -q: 214 passed. uv run ruff check .:
  passed. uv build: sdist and wheel succeeded. Git whitespace checks passed.
- SourceSample and parse_read_all_response ASTs match HEAD exactly, preserving
  the existing consumer's UDP schema, units and normalization behavior. The
  deliberate API change is READ_ONLY by default for existing control callers.
- The manual's command/parameter/register maps were text-extracted and the
  relevant packet/register tables visually inspected. Protocol/pySerial primary
  sources and manual ambiguities are recorded in PROTOCOL.md.
- These are software and mock checks only. New UDP writes, configuration changes,
  broadcasts, Modbus transports and physical HV transitions remain unqualified
  on real hardware. No device connection/control, parent relay/credential access,
  commit or push was performed.

## Library documentation rewrite, 2026-09-18

- Reordered README around installation into a consuming project, imports and
  basic use, connection choices, access modes and official command mappings.
  Clone/uv sync and the Jupytext workflow now belong to development/demo setup.
  Persisted the documentation convention in AGENTS, decisions and handoff.
- Parsed all four Python examples without executing them; checked referenced
  public module names, local links and the section anchor. All three Git
  dependency strings parse as PEP 508 requirements, including the serial extra.
  Confirmed uv add accepts PEP 508 requirements using the installed CLI help.
- Staged and unstaged Git whitespace checks passed. This update changes only
  documentation; the earlier code checks were not repeated. No notebook cells,
  installation examples, device connections or controls were executed.

## Local notebook synchronization, 2026-09-18

- The user requested that the ignored runnable notebook remain available and
  synchronized. Before this update demo.ipynb already existed, with all 18 cell
  inputs matching demo.py; Git's staged D represented removal from tracking.
- Backed up the current notebook byte-for-byte to ignored .agents/local using
  a demo-before-local-sync timestamped filename and verified its SHA256. Ran
  uv run jupytext --to ipynb --update demo.py without executing any cells.
- Validated the resulting nbformat document and all 18 cell inputs against the
  text source. Both saved output cells and every execution count were preserved.
  Git still ignores the local notebook. AGENTS and handoff now require this
  local generation/sync step whenever demo source changes.

## One notebook with read-only and write sections, 2026-09-18

- The user clarified the final layout: keep one demo.ipynb, with all read-only
  tests first, an explicit end boundary, then optional READ_WRITE tests below.
  demo.py now covers UDP reads/all sample fields, all 26 readable Modbus entries
  (22 without Ethernet), TCP/RTU, raw reads, connection lifecycle and offline
  parsing. Part 2 has 28 explicit command cells covering all six UDP writes,
  all 17 writable Modbus entries/helpers and UDP/RTU broadcast Stop examples.
- Every write test has fresh before/after observations; the critical-step/ID
  sequence has them around the complete sequence because its registers are
  write-only. Readback cells acquire three snapshots and show state, alarms,
  measurements and target comparisons. They can repeat without resending writes.
  demo_helpers.py contains checkout-only pure formatting, with no device I/O.
- New notebook tests use actual library clients with fake UDP/TCP/RTU transports
  and forbid real adapters. They cover both Modbus transports, Ethernet/no-Ethernet
  read sections, every written register, address/ID retargeting, serial-port
  exclusivity and repeating every After cell. Part 1 sends only read requests.
- uv run pytest -q: 217 passed. uv run ruff check .: passed. uv build: source
  distribution and wheel succeeded; the wheel still installs only seas_sip_client
  plus package metadata. No notebook/runtime dependency was added to the library.
- The previous local notebook was backed up byte-for-byte before editing to
  .agents/local/demo-before-demo-split-20260918-031140-683091.ipynb. The expanded
  notebook is generated locally, with all 249 cell inputs matching demo.py and
  the original two saved output cells retained with their execution counts.
  Saved Start/Stop execution counts (9/10) are pre-existing local metadata,
  retained as history; they do not demonstrate accepted control or new testing.
- No live notebook execution, device connection, HV/configuration command,
  parent repository change, commit or push occurred during this work.

## Unified device API and common demo, 2026-09-18

- User requested one semantic interface after selecting UDP/Modbus at instance
  construction. Added SAESSIPPower, ConnectionSettings/ConnectionTypeEnum and
  DeviceStatus. All links expose the same state names/units and common controls,
  named parameter changes, switch modes, address/ID setters and lifecycle.
  Unknown observations remain None; is_single_response describes acquisition
  framing without claiming simultaneous physical measurements.
- Common setting updates hide UDP block preservation and Modbus register/word
  details. All targets and permissions are checked before I/O. The explicit
  common ID setter performs critical steps and ID without retry; legacy raw
  behavior remains unchanged. Failure tests cover immediate abort and partial
  application without continuation or automatic restoration.
- uv run pytest -q: 299 passed. uv run ruff check .: passed. uv build: sdist and
  wheel succeeded. Tests run identical notebook business cells across all three
  fake transports by changing only connection setup. Every After cell is repeated
  and checked for reads only. Status normalization tests compare every shared
  field/unit/flag, including unknown Ethernet and write-only observations.
- One-off AST comparison against .agents/local/before-unified-seas_sip_client.py
  confirms SourceSample, parse_read_all_response and both original transport
  client classes are unchanged. No parent consumer changes are needed or made.
- Latest local notebook inputs/outputs were preserved byte-for-byte in
  .agents/local/demo-before-unified-20260918-085711-911076.ipynb, then again just
  before generation in demo-before-unified-sync-20260918-091114-003416.ipynb.
  Its new operator edit (0.1-second pause after Start Before read) was merged.
- The single local demo.ipynb is synchronized with all 193 text-source cells.
  All five historical output cells and their counts are retained. The writable
  connection output needed explicit transfer to the corresponding renamed
  connection cell; it remains clearly historical, not evidence of a new API run.
  The notebook instructs restarting an old kernel after the library update.
- No notebook cells, live device connection, HV/configuration commands, parent
  repository changes, commit or push were performed by this implementation run.

## Inline demo connection setup, 2026-09-18

- Removed settings-file loading from the demo. Connection setup now uses inline
  connection_type and identifier, with IP/hostname versus serial-device examples
  and comments explaining default ports and optional overrides. Broadcast also
  uses a direct inline target; no protocol-selection branches are needed.
- Removed the fake lab's settings.toml fixture: all common notebook sections now
  pass against fake UDP/TCP/RTU adapters without a configuration file.
  uv run pytest -q: 299 passed; uv run ruff check .: passed.
- Backed up the local notebook to ignored .agents/local/
  demo-before-inline-setup-20260918-190312-670049.ipynb before editing. Preserved
  the operator's newly commented status display in the text source. Generated
  the notebook without execution; all 193 inputs match, and every execution count
  and all five historical output cells match the backup. Git whitespace checks
  passed and demo.ipynb remains ignored. No live device connection or control ran.

## Editable consumer installation documentation, 2026-09-18

- Installation now leads with cloning inside the consuming project and running
  uv add --editable from that project's root. Direct Git uv/pip examples follow;
  the editable serial-extra example and source-change behavior are documented.
- Checked --editable and --extra against the installed uv add --help. This is a
  documentation-only change; installation commands and notebook cells were not
  executed, and the earlier offline tests were not repeated.

## Developer/consumer handoff for another computer, 2026-09-18

- Expanded root AGENTS.md with separate developer and consumer integration
  contexts, fresh-clone commands, runtime/API expectations, publication order
  and ignored-file boundaries. HANDOFF records the still-uncommitted working
  tree and required untracked helper/test files; parent files were not edited.
- Found one newer notebook input: the operator changed identifier from the
  example IP to 192.168.50.34. Backed up its latest bytes to .agents/local/
  demo-before-portable-handoff-20260918-191656-742211.ipynb, merged that one input
  into demo.py, and ran Jupytext update without executing cells. All 193 inputs
  now match; all eight current output cells and every execution count are intact.
- uv run --locked pytest -q: 299 passed; uv run ruff check .: passed. Checked
  local links in the agent entry documents. No runtime/protocol/package behavior
  changed; no live connections, controls, commit or push occurred. Operator-run
  notebook outputs remain historical evidence, not an agent-run live test.

## Commit preparation and staged-tree verification, 2026-09-18

- User authorized local commits. Kept the common API, interdependent demo and
  offline suites in one implementation commit (95bc12b); agent instructions and
  development/consumer handoff records are the following documentation commit.
- Exported the first commit's exact staged files with git checkout-index to an
  ignored isolated directory. Confirmed imports resolve to that exported module,
  not the editable working copy. No local notebook, settings.toml or .agents/local
  data was exported. Using the existing developer Python/tool environment, that
  source snapshot passed 299 offline tests and Ruff. uv build produced its source
  distribution and wheel; no additional runtime module was packaged.
- Before committing, backed up demo.ipynb byte-for-byte to .agents/local/
  demo-before-commit-20260918-192052-529219.ipynb. Its 193 cell inputs match demo.py;
  eight output cells and all execution counts remain local and intact. No ipynb
  is tracked. Git whitespace checks passed. No live device I/O, parent repository
  edits or push were performed.
