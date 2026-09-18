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
