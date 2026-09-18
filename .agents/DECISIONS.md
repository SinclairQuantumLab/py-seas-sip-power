# Durable decisions

- 2026-09-18: user requested separate library ownership after adding explicit
  HV control, with Git submodule plus uv editable consumption by the relay.
- Repository/distribution py-seas-sip-power, import seas_sip_client. Preserve
  SAESSIPPowerClient, SAESSIPPowerSettings, SourceSample and their behavior.
- One root module, setuptools backend, uv project, no runtime dependencies.
  Optional notebook group provides ipykernel.
- Use Git submodule, not subtree or the separate git-subrepo extension.
  Editable local changes can affect the consumer before its gitlink changes.
- Explicit Start/Stop only, no ACK/retry, implicit Stop, heartbeat, resets,
  alarm clearing or keepalive edits. API scope is not an authorization system.
- Notebook remains simple, without validation or exception handling, and uses
  library-local settings and environment rather than a parent checkout.
- Deferred by the user: adopt Jupytext tracked sources and ignore every ipynb
  and its outputs. Preserve local runs during migration; see AGENTS.md.
