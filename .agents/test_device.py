"""Verify one semantic device API over all three offline protocol transports."""

from __future__ import annotations

import struct
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from demo_fakes import NotebookLab

import seas_sip_client as sip
from demo_helpers import format_changes, format_status
from seas_sip_client import ModbusRegisterEnum as R

TYPES = list(sip.ConnectionTypeEnum)


def connect_device(
    lab: NotebookLab,
    connection_type: sip.ConnectionTypeEnum,
    mode: sip.AccessModeEnum = sip.AccessModeEnum.READ_WRITE,
) -> sip.SAESSIPPower:
    """Connect the real common facade to the lab's intercepted adapters."""
    device = sip.SAESSIPPower(
        sip.ConnectionSettings("fake", connection_type=connection_type),
        access_mode=mode,
    )
    device.connect()
    return device


@pytest.mark.parametrize("connection_type", TYPES)
def test_all_connections_return_identical_normalized_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Check every shared value, units and decoded flag against one UDP fixture."""
    lab = NotebookLab(monkeypatch, tmp_path)
    lab.words[R.STATUS] = struct.unpack_from(">H", lab.payload, 32)[0]
    lab.words[R.VOUT] = 5000
    expected = asdict(sip.parse_read_all_response(b"\x01\x80" + lab.payload))
    device = connect_device(lab, connection_type, sip.AccessModeEnum.READ_ONLY)
    sample = device.read_sample()
    assert type(sample) is sip.DeviceStatus
    actual = asdict(sample)
    assert actual.pop("is_single_response") is (
        connection_type is sip.ConnectionTypeEnum.UDP
    )
    actual.pop("observed_at")
    expected.pop("observed_at")
    if connection_type is not sip.ConnectionTypeEnum.UDP:
        expected["modbus_id"] = None
    assert actual == expected
    assert sample.observed_at.utcoffset().total_seconds() == 0
    assert sample.device_id == "123456"
    before = len(lab.events)
    assert (
        device.status == device.status or len(lab.events) > before
    )  # Each access reads.
    assert len(lab.events) > before
    assert "26.9 °C" in format_status(sample)
    device.close()


@pytest.mark.parametrize("connection_type", TYPES[1:])
def test_unobservable_fields_are_none_not_configuration_or_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Keep write-only ID and absent Ethernet observations explicitly unknown."""
    lab = NotebookLab(monkeypatch, tmp_path, ethernet=False)
    device = connect_device(lab, connection_type)
    status = device.read_all()
    assert status.modbus_id is None
    assert device.settings.modbus_id == 11
    for key in ("keepalive_interval_ms", "ip_address", "ip_netmask", "mac_address"):
        assert getattr(status, key) is None
    assert "| Keepalive interval | Unavailable |" in format_status(status)
    assert (
        "| modbus_id | Unavailable | 12 | Unavailable | Unavailable |"
        in format_changes({"modbus_id": None}, {"modbus_id": None}, {"modbus_id": 12})
    )
    for operation in (
        lambda: device.set_ip_address("192.168.1.20", "255.255.255.0"),
        lambda: device.set_working_parameters(keepalive_interval_ms=1000),
    ):
        before = len(lab.events)
        with pytest.raises(sip.SAESSIPPowerUnsupportedOperationError):
            operation()
        assert all(event[1] == 3 for event in lab.events[before:])
    device.close()


WRITES = [
    ("start", (), {}),
    ("stop", (), {}),
    ("reset", (), {}),
    ("restart", (), {}),
    ("clear_alarm", (), {}),
    ("enable", (sip.EnableCommandEnum.START,), {}),
    ("set_ip_address", ("192.168.1.20", "255.255.255.0"), {}),
    ("set_modbus_id", (12,), {}),
    (
        "set_switch_modes",
        (sip.SwitchModeEnum.OFF, sip.SwitchModeEnum.SIMPLE, sip.SwitchModeEnum.WINDOW),
        {},
    ),
    ("set_working_parameters", (), {"output_voltage_setpoint_v": 4000}),
]


@pytest.mark.parametrize("connection_type", TYPES)
@pytest.mark.parametrize(("method", "args", "kwargs"), WRITES)
def test_common_read_only_guard_precedes_even_preservation_reads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
    method: str,
    args: tuple,
    kwargs: dict,
) -> None:
    """Every high-level write rejects before any I/O, connected or disconnected."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, connection_type, sip.AccessModeEnum.READ_ONLY)
    for _ in range(2):
        with pytest.raises(sip.SAESSIPPowerPermissionError):
            getattr(device, method)(*args, **kwargs)
        assert not lab.events
        device.close()


@pytest.mark.parametrize("connection_type", TYPES)
def test_lifecycle_never_controls_and_permissions_stay_fixed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Changing connection ownership cannot upgrade access or send HV commands."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, connection_type, sip.AccessModeEnum.READ_ONLY)
    with pytest.raises(AttributeError):
        device.access_mode = sip.AccessModeEnum.READ_WRITE
    with pytest.raises(AttributeError):
        device.settings = sip.ConnectionSettings("other")
    device.reconnect()
    assert device.access_mode is sip.AccessModeEnum.READ_ONLY
    device.close()
    assert not lab.events


@pytest.mark.parametrize("connection_type", TYPES)
def test_named_parameter_changes_preserve_unrelated_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Let callers use volts/milliseconds/enums without raw register knowledge."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, connection_type)
    before = device.read_sample()
    start = len(lab.events)
    device.set_working_parameters(
        output_voltage_setpoint_v=4200, output_voltage_ramp_interval_ms=3000
    )
    events = lab.events[start:]
    assert [e[1] for e in events] == ([5, 64] if connection_type is TYPES[0] else [16])
    after = device.read_sample()
    assert after.output_voltage_setpoint_v == 4200
    assert after.output_voltage_ramp_interval_ms == 3000
    assert after.switch_2_mode == before.switch_2_mode
    device.set_working_parameters(switch_3_mode=sip.SwitchModeEnum.WINDOW)
    after = device.read_sample()
    assert after.switch_1_mode == before.switch_1_mode
    assert after.switch_2_mode == before.switch_2_mode
    assert after.switch_3_mode == "WINDOW"
    device.close()


@pytest.mark.parametrize("connection_type", TYPES)
@pytest.mark.parametrize(
    "kwargs",
    [
        {"switch_1_mode": sip.SwitchModeEnum.WINDOW},
        {"switch_2_mode": "OFF"},
        {"output_voltage_setpoint_v": 999},
        {"keepalive_interval_ms": 50},
        {"modbus_id": True},
        {"output_voltage_ramp_interval_ms": 0},
        {"switch_1_threshold_na": -1},
        {"conversion_rate_a_per_torr": 65536},
    ],
)
def test_invalid_common_parameters_never_reach_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
    kwargs: dict,
) -> None:
    """Validate requested fields before any read, unlock or write occurs."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, connection_type)
    with pytest.raises((ValueError, TypeError)):
        device.set_working_parameters(**kwargs)
    assert not lab.events
    device.close()


@pytest.mark.parametrize("connection_type", TYPES)
def test_same_id_method_encodes_required_protocol_sequence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Expose one explicit ID operation while retaining the old connection target."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, connection_type)
    device.set_modbus_id(12)
    assert device.settings.modbus_id == 11
    if connection_type is TYPES[0]:
        assert [e[1] for e in lab.events] == [5, 64]
        assert lab.payload[133] == 12
    else:
        assert [struct.unpack_from(">H", e[2], 1)[0] for e in lab.events] == [
            0x7000,
            0x7001,
            0x8000,
        ]
        assert all(e[1] == 16 for e in lab.events)
    updated = device.settings.with_modbus_id(12)
    assert updated.modbus_id == 12
    device.close()


@pytest.mark.parametrize("step", ["critical_step1", "critical_step2", "set_modbus_id"])
def test_failed_id_step_stops_without_retry_or_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, step: str
) -> None:
    """A partially applied protocol sequence never progresses after an error."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, sip.ConnectionTypeEnum.MODBUS_TCP)
    methods = ("critical_step1", "critical_step2", "set_modbus_id")
    mocks = {}
    for name in methods:
        mocks[name] = Mock(
            side_effect=sip.SAESSIPPowerCommunicationError("synthetic failure")
            if name == step
            else None
        )
        monkeypatch.setattr(device._modbus, name, mocks[name])
    with pytest.raises(sip.SAESSIPPowerCommunicationError):
        device.set_modbus_id(12)
    index = methods.index(step)
    assert [mocks[n].call_count for n in methods] == [int(i <= index) for i in range(3)]
    device.close()


@pytest.mark.parametrize("connection_type", [TYPES[0], TYPES[2]])
def test_common_broadcast_rejects_reads_and_unresolvable_partial_updates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Broadcast cannot invent settings to fill a required parameter/mode block."""
    lab = NotebookLab(monkeypatch, tmp_path)
    settings = sip.ConnectionSettings(
        "fake", connection_type=connection_type
    ).for_broadcast(udp_address="192.168.50.255")
    device = sip.SAESSIPPower(settings, access_mode=sip.AccessModeEnum.READ_WRITE)
    device.connect()
    with pytest.raises(sip.SAESSIPPowerUnsupportedOperationError):
        device.read_sample()
    with pytest.raises(sip.SAESSIPPowerUnsupportedOperationError):
        device.set_working_parameters(switch_1_mode=sip.SwitchModeEnum.OFF)
    assert not lab.events
    device.stop()
    assert len(lab.events) == 1
    device.close()


@pytest.mark.parametrize("bad", [True, "udp", 1, sip.AccessModeEnum.READ_ONLY])
def test_connection_choice_requires_its_enum(bad: object) -> None:
    """Do not infer a protocol from strings, integers or unrelated enums."""
    with pytest.raises(TypeError):
        sip.ConnectionSettings("fake", connection_type=bad)


def test_connection_settings_retarget_only_the_relevant_endpoint() -> None:
    """IP changes affect Ethernet destinations while serial ports remain stable."""
    for kind in TYPES:
        settings = sip.ConnectionSettings("fake", connection_type=kind)
        new = settings.with_ip_address("192.168.50.35")
        assert new.address == ("fake" if kind is TYPES[2] else "192.168.50.35")
        assert settings.address == "fake"
    with pytest.raises(sip.SAESSIPPowerUnsupportedOperationError):
        sip.ConnectionSettings("fake", connection_type=TYPES[1]).for_broadcast()
    with pytest.raises(ValueError):
        sip.ConnectionSettings("fake").for_broadcast()


@pytest.mark.parametrize("connection_type", TYPES)
def test_complete_parameter_object_is_supported_without_inventing_observations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    connection_type: sip.ConnectionTypeEnum,
) -> None:
    """Accept fully specified targets, including explicit ID and keepalive values."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, connection_type)
    source = sip.parse_read_all_response(b"\x01\x80" + lab.payload)
    requested = replace(
        sip.WorkingParameters.from_sample(source),
        output_voltage_setpoint_v=4321,
        output_voltage_ramp_interval_ms=60000,
        switch_3_mode=sip.SwitchModeEnum.WINDOW,
        keepalive_interval_ms=1000,
        modbus_id=12,
    )
    device.set_working_parameters(requested)
    observed = device.read_sample()
    for name, target in asdict(requested).items():
        if name == "modbus_id" and connection_type is not TYPES[0]:
            assert observed.modbus_id is None
        else:
            assert getattr(observed, name) == (
                target.name if isinstance(target, sip.SwitchModeEnum) else target
            )
    device.close()


def test_multi_request_parameter_failure_does_not_continue_or_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An explicit multi-setting update can partially apply and is never retried."""
    lab = NotebookLab(monkeypatch, tmp_path)
    device = connect_device(lab, sip.ConnectionTypeEnum.MODBUS_TCP)
    failing_write = Mock(
        side_effect=[None, sip.SAESSIPPowerCommunicationError("failed")]
    )
    monkeypatch.setattr(device._modbus, "write_multiple_registers", failing_write)
    id_write = Mock()
    monkeypatch.setattr(device._modbus, "critical_step1", id_write)
    with pytest.raises(sip.SAESSIPPowerCommunicationError):
        device.set_working_parameters(
            output_voltage_setpoint_v=4000, keepalive_interval_ms=1000, modbus_id=12
        )
    assert failing_write.call_count == 2
    id_write.assert_not_called()
    device.close()
