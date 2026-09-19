"""Run identical notebook business cells through each fake connection protocol."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import jupytext
import pytest
from demo_fakes import NotebookLab, is_read

import seas_sip_client as sip
from demo_helpers import format_changes, format_status

SOURCE = Path(__file__).resolve().parents[1] / "demo.py"


@pytest.mark.parametrize("connection_type", list(sip.ConnectionTypeEnum))
@pytest.mark.parametrize("writable", [False, True])
def test_same_notebook_cells_on_every_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
    writable: bool,
) -> None:
    """Change only connection construction and exercise all common operations."""
    lab = NotebookLab(monkeypatch, tmp_path)
    namespace: dict[str, object] = {}
    commands = 0
    for cell in jupytext.read(SOURCE).cells:
        if cell.cell_type != "code":
            continue
        tags = cell.metadata.tags
        tag = tags[0]
        setup = tag in ("display-setup", "connection-settings")
        if not setup and ("read-write" in tags) != writable:
            continue
        if (
            tag.startswith("broadcast-")
            and connection_type is sip.ConnectionTypeEnum.MODBUS_TCP
        ):
            continue  # Hardware capability, not a different business API.
        start = len(lab.events)
        exec(compile(cell.source, str(SOURCE), "exec"), namespace)
        if tag == "connection-settings":
            namespace["connection"] = replace(
                namespace["connection"],
                connection_type=connection_type,
                address="fake",
                port=None,
            )
        events = lab.events[start:]
        writes = [event for event in events if not is_read(event)]
        if tag.endswith("-write"):
            expected = (
                3
                if tag == "modbus-id-write"
                and connection_type is not sip.ConnectionTypeEnum.UDP
                else 1
            )
            assert len(writes) == expected, tag
            commands += 1
        else:
            assert not writes, tag
        if tag.endswith("-after") or tag == "read-samples":
            assert events, tag
            start = len(lab.events)
            exec(compile(cell.source, str(SOURCE), "exec"), namespace)
            assert lab.events[start:] and all(map(is_read, lab.events[start:])), tag
        if "target_value =" in cell.source:
            value = namespace["target_value"]
            namespace["target_value"] = (
                (
                    sip.SwitchModeEnum.OFF
                    if value is not sip.SwitchModeEnum.OFF
                    else sip.SwitchModeEnum.SIMPLE
                )
                if isinstance(value, sip.SwitchModeEnum)
                else value + 1
            )
        if tag == "modbus-id-before":
            namespace["target_modbus_id"] = 12
        if tag == "ip-address-before":
            namespace["target_ip"] = "192.168.50.35"
    assert all(not client.is_connected for client in lab.clients)
    if writable:
        assert commands == (
            22 if connection_type is sip.ConnectionTypeEnum.MODBUS_TCP else 23
        )
        text = "\n".join(call.args[0].data for call in lab.display.call_args_list)
        assert "Target observed" in text
        assert "| HV enabled | **ENABLED** |" in text
        assert "| HV enabled | **DISABLED** |" in text
        assert namespace["connection"].modbus_id == 12
        assert namespace["connection"].address == (
            "fake"
            if connection_type is sip.ConnectionTypeEnum.MODBUS_RTU
            else "192.168.50.35"
        )
    else:
        assert lab.events and all(map(is_read, lab.events))
        assert all(
            client.access_mode is sip.AccessModeEnum.READ_ONLY for client in lab.clients
        )
        assert type(namespace["status"]) is sip.DeviceStatus


def test_notebook_layout_and_api_are_protocol_independent() -> None:
    """Only the initial connection cell selects protocol; user tests stay semantic."""
    notebook = jupytext.read(SOURCE)
    boundary = next(
        i for i, c in enumerate(notebook.cells) if c.source.startswith("# Part 2")
    )
    assert any(
        "# End of read-only tests" in c.source for c in notebook.cells[:boundary]
    )
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type != "code":
            continue
        assert not cell.outputs and cell.execution_count is None
        tags = cell.metadata.tags
        assert ("read-only" if index < boundary else "read-write") in tags
        tree = ast.parse(cell.source)
        assert not any(isinstance(n, (ast.Try, ast.Assert)) for n in ast.walk(tree))
        assert not any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "input"
            for n in ast.walk(tree)
        )
        for token in (
            "ModbusRegisterEnum",
            "read_register(",
            "write_register(",
            ".registers",
            "SAESSIPPowerModbusClient",
            "SAESSIPPowerClient",
        ):
            assert token not in cell.source
        if tags[0] not in ("display-setup", "connection-settings"):
            assert "ConnectionTypeEnum." not in cell.source
        if index < boundary:
            assert "AccessModeEnum.READ_WRITE" not in cell.source
    before_start = next(
        c.source for c in notebook.cells if "start-before" in c.metadata.get("tags", [])
    )
    assert "time.sleep(0.1)" in before_start  # Preserve the user's local edit.


@pytest.mark.parametrize("conversion", [0, 20])
def test_common_display_distinguishes_missing_and_zero(conversion: int) -> None:
    """Retain readable units and represent unobservable fields honestly."""
    from test_seas_sip_client import read_all_response

    sample = sip.parse_read_all_response(read_all_response(conversion_rate=conversion))
    text = format_status(sample)
    assert "1,000 nA (1.000 µA)" in text and "26.9 °C (300 K)" in text
    assert "Global, Safe, Interlock" in text
    assert ("5.000e-08 Torr" if conversion else "Unavailable") in text
    assert "| x | 0 | 2 | 1 | No |" in format_changes({"x": 0}, {"x": 1}, {"x": 2})
