# Durable decisions

- 2026-09-18: before moving work to another computer, keep developer and consumer
  agent entry points in the library's root AGENTS.md. Include fresh checkout setup,
  runtime/import expectations, common API semantics, local notebook preservation,
  publication dependencies and the boundary between offline tests and hardware
  evidence. Parent relay instructions remain separately owned. HANDOFF records
  transient Git/publication status so future agents must recheck it.

- 2026-09-18: installation instructions lead with cloning this repository inside
  the consuming project and running uv add --editable ./py-seas-sip-power from
  the consumer root. Direct Git uv/pip installs follow as alternatives. This
  consumer workflow belongs in Installation; the library's own uv sync and demo
  setup remain in Development. Include the serial extra for the editable path.

- 2026-09-18: demo setup is direct test code, not a configuration-file loader.
  Set connection_type and one identifier inline (IP/hostname for UDP/TCP, serial
  device for RTU). Use library defaults for ports/baudrate, with explanatory
  comments for overrides. Broadcast also has an inline target. This supersedes
  earlier notebook settings.toml instructions; retain optional legacy templates.

- 2026-09-18: user clarified the abstraction: select UDP/Modbus at construction,
  then keep the same device methods/properties and test flow. SAESSIPPower is
  the common device API; ConnectionSettings uses ConnectionTypeEnum. DeviceStatus
  normalizes field names, units, bits and network strings across all transports.
  Unobservable values (notably Modbus ID) are None, never a configured/cached guess.
  Existing UDP/raw Modbus classes and SourceSample remain unchanged for consumers.
- Common named working-parameter updates hide UDP full-block preservation and
  Modbus registers/word order. An explicit common set_modbus_id includes its
  required Modbus critical-step sequence; this supersedes the earlier rule that
  callers must perform these protocol details themselves. The legacy raw setter
  keeps its old one-register behavior. No implicit HV/alarm operations, retries
  or rollback are introduced. Partial failure of multi-write updates is exposed.
- Demo remains one notebook, read-only first then writable. Only setup selects
  protocol; all subsequent tests use the same device API. Raw-register tests stay
  in the offline protocol suite. Preserve the operator's added 0.1-second delay
  after the Start Before read and keep the local notebook synchronized.

- 2026-09-18: user requested comprehensive notebook tests with read-only and
  write examples, then clarified that both belong in one demo.ipynb. Put all
  read-only tests first with an explicit stopping boundary; optional write
  tests follow and construct new READ_WRITE instances. Use separate fresh
  Before/Write/After cells for each operation. Cover all UDP commands, readable
  and writable Modbus registers, TCP/RTU, endpoint changes and broadcasts.
  Readback repeats reads only. Critical-step/ID writes remain an explicit
  consecutive sequence with before/after observations; write-only values are
  never fabricated. Keep reusable display-only functions in demo_helpers.py.

- 2026-09-18: user clarified that Git-ignored notebooks must still be maintained
  locally. Every demo source update must include generation/synchronization of
  demo.ipynb and verification of matching cell inputs before task completion.
  Preserve local edits, outputs and execution counts; synchronization executes
  no cells. Ignoring ipynb is not permission to omit the runnable local file.

- 2026-09-18: user requested a README and repository concept centered on an
  importable library. Consumer installation uses pip/uv add in the consumer's
  environment; clone/uv sync is only the local development/demo workflow.
  Keep basic imports, connection choices and official-command API mapping in
  README; detailed evidence and handoff history stay in .agents. This changes
  documentation, not the single-module design or parent relay ownership.

- 2026-09-18: user requested separate library ownership after adding explicit
  HV control, with Git submodule plus uv editable consumption by the relay.
- Repository/distribution py-seas-sip-power, import seas_sip_client. Preserve
  SAESSIPPowerClient, SAESSIPPowerSettings, SourceSample and their behavior.
- One root module, setuptools backend, uv project, no runtime dependencies.
  Notebook group provides ipykernel and Jupytext; the development group includes
  it to exercise notebook sources offline without a pre-existing ipynb.
- Use Git submodule, not subtree or the separate git-subrepo extension.
  Editable local changes can affect the consumer before its gitlink changes.
- Original scope was Start/Stop only. The full-interface decision below supersedes
  that limitation; no implicit control, retries or background heartbeat is allowed.
- Notebook remains simple, without validation or exception handling, and uses
  library-local settings and environment rather than a parent checkout.
- Deferred by the user: adopt Jupytext tracked sources and ignore every ipynb
  and its outputs. Preserve local runs during migration; see AGENTS.md.
- 2026-09-18: user authorized the deferred migration and readable notebook status.
  Track demo.py in Jupytext percent format; ignore all ipynb/checkpoint files.
  Preserve the operator-run original in ignored library-local backup storage.
  Format snapshots in the demo only, keeping SourceSample and the installed
  library unchanged. A separate display setup cell permits reformatting an
  existing sample without opening a socket or requesting another sample.
- 2026-09-18: user requested separating Start from sampling. Give HV commands
  and reads separate cells with explicit Enable/Disable HV headings; repeated
  sampling must never resend a control command. Preserve local edits commenting
  out client.stop() and delaying readback by 0.1 seconds. Start/Stop are official
  manufacturer UDP names (Rev. 4, section 9.2, p. 46); public API names remain.
- 2026-09-18: user explicitly authorized all manual remote commands/functions
  and a mandatory enum-typed access choice at instance creation. Both client
  classes default to AccessModeEnum.READ_ONLY; READ_WRITE must be explicit.
  Mode is fixed through the public API and survives reconnect. No device writes
  are permitted through read-only helpers, raw register methods or broadcasts.
  All public enum class names end in Enum. This is an accident-prevention API
  guard, not hardware authentication or a hostile-code sandbox.
- All official UDP commands and Modbus TCP/RTU functions/registers are supported.
  Keep the single-module design and unchanged UDP SourceSample contract. Modbus
  uses a separate ModbusSample because its acquisition spans multiple requests
  and some values are unavailable or write-only. Only RTU needs optional pySerial.
- Defaults now deliberately deny legacy start/stop callers unless they opt into
  READ_WRITE. Read-only consumers require no constructor changes. No parent relay
  or credential files were accessed or changed for this implementation.
- The user's later notebook edit re-enabled client.stop(); it is preserved, with
  the new READ_ONLY default protecting command cells. Original local inputs and
  outputs were backed up again before migration. There are no notebook prompts,
  validation handlers or background workers.
