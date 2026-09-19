"""Verify permissions and official UDP/Modbus wire contracts without hardware."""

from __future__ import annotations

import struct
import sys
from collections.abc import Callable
from dataclasses import replace
from enum import Enum
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_seas_sip_client import FakeSocket, read_all_response

import seas_sip_client as sip
from seas_sip_client import (
    AccessModeEnum,
    EnableCommandEnum,
    ModbusFunctionEnum,
    ModbusRTUSettings,
    ModbusTCPSettings,
    SAESSIPPowerClient,
    SAESSIPPowerCommunicationError,
    SAESSIPPowerModbusClient,
    SAESSIPPowerModbusError,
    SAESSIPPowerPermissionError,
    SAESSIPPowerProtocolError,
    SAESSIPPowerSettings,
    SwitchModeEnum,
    UDPAddressModeEnum,
    WorkingParameters,
)
from seas_sip_client import (
    ModbusRegisterEnum as R,
)


def parameters() -> WorkingParameters:
    """Copy the offline reference frame's valid working parameters."""
    return WorkingParameters.from_sample(
        sip.parse_read_all_response(read_all_response())
    )


UDP_WRITES = [
    ("start", (), b"\x01\x01"),
    ("stop", (), b"\x01\x02"),
    ("reset", (), b"\x01\x03"),
    ("clear_alarm", (), b"\x01\x04"),
    (
        "set_working_parameters",
        (parameters(),),
        bytes.fromhex(
            "0140 1388 000007d0 09 0000000b 0000000c 0000000d 0000000e "
            "0000000f 00007530 0014 0b"
        ),
    ),
    (
        "set_ip_address",
        ("192.168.1.34", "255.255.255.0"),
        bytes.fromhex("0141 c0a80122 ffffff00"),
    ),
]


@pytest.mark.parametrize(("method", "args", "expected"), UDP_WRITES)
@pytest.mark.parametrize("connected", [False, True])
def test_udp_read_only_blocks_every_write_before_io(
    method: str, args: tuple, expected: bytes, connected: bool
) -> None:
    """Default clients reject every control/configuration command without sending."""
    fake = FakeSocket([])
    client = SAESSIPPowerClient(
        SAESSIPPowerSettings("controller"), socket_factory=lambda: fake
    )
    if connected:
        client.connect()
    with pytest.raises(SAESSIPPowerPermissionError):
        getattr(client, method)(*args)
    assert client.access_mode is AccessModeEnum.READ_ONLY
    assert not fake.sent


@pytest.mark.parametrize(("method", "args", "expected"), UDP_WRITES)
def test_udp_write_frames_are_exact_and_sent_once(
    method: str, args: tuple, expected: bytes
) -> None:
    """Compare all six writes to independent wire literals from the manual layout."""
    fake = FakeSocket([read_all_response()])
    client = SAESSIPPowerClient(
        SAESSIPPowerSettings("controller"),
        access_mode=AccessModeEnum.READ_WRITE,
        socket_factory=lambda: fake,
    )
    client.connect()
    getattr(client, method)(*args)
    assert fake.sent == [expected]
    assert len(fake.responses) == 1  # No ACK or hidden readback.
    assert client.settings.host == "controller"
    client.close()
    assert fake.sent == [expected]


@pytest.mark.parametrize(("method", "args", "expected"), UDP_WRITES)
def test_udp_failed_writes_are_not_retried(
    method: str, args: tuple, expected: bytes
) -> None:
    """Failed sends across every command propagate after exactly one attempt."""
    fake = FakeSocket([])
    fake.send = Mock(side_effect=OSError("synthetic failure"))
    client = SAESSIPPowerClient(
        SAESSIPPowerSettings("controller"),
        access_mode=AccessModeEnum.READ_WRITE,
        socket_factory=lambda: fake,
    )
    client.connect()
    with pytest.raises(SAESSIPPowerCommunicationError):
        getattr(client, method)(*args)
    fake.send.assert_called_once_with(expected)


@pytest.mark.parametrize(
    "mode", ["read_write", "READ_WRITE", True, 1, None, SwitchModeEnum.SIMPLE]
)
@pytest.mark.parametrize("kind", ["udp", "tcp", "rtu"])
def test_access_mode_requires_its_exact_enum(kind: str, mode: object) -> None:
    """Reject permissive-looking strings, integers and unrelated enums."""
    with pytest.raises(TypeError, match="AccessModeEnum"):
        if kind == "udp":
            SAESSIPPowerClient(SAESSIPPowerSettings("controller"), access_mode=mode)
        else:
            settings = (
                ModbusTCPSettings("controller")
                if kind == "tcp"
                else ModbusRTUSettings("fake")
            )
            SAESSIPPowerModbusClient(settings, access_mode=mode)


def test_access_mode_survives_reconnect_and_has_no_public_setter() -> None:
    """Replacing the transport never upgrades permissions or sends commands."""
    sockets = [FakeSocket([]), FakeSocket([read_all_response()])]
    factory = Mock(side_effect=sockets)
    client = SAESSIPPowerClient(
        SAESSIPPowerSettings("controller"), socket_factory=factory
    )
    with pytest.raises(AttributeError):
        client.access_mode = AccessModeEnum.READ_WRITE
    client.connect()
    client.reconnect()
    assert sockets[0].closed and not sockets[0].sent
    assert client.read_all().serial_number == 123456
    with pytest.raises(SAESSIPPowerPermissionError):
        client.stop()
    assert sockets[1].sent == [b"\x01\x05"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("output_voltage_setpoint_v", 999),
        ("output_voltage_setpoint_v", 6001),
        ("output_voltage_ramp_interval_ms", 999),
        ("output_voltage_ramp_interval_ms", 60001),
        ("switch_1_mode", SwitchModeEnum.WINDOW),
        ("switch_2_mode", 1),
        ("switch_3_mode", "SIMPLE"),
        ("switch_1_threshold_na", -1),
        ("switch_2_max_threshold_na", 2**32),
        ("keepalive_interval_ms", 999),
        ("keepalive_interval_ms", True),
        ("conversion_rate_a_per_torr", 65536),
        ("modbus_id", 0),
        ("modbus_id", 248),
        ("output_voltage_setpoint_v", 5000.5),
    ],
)
def test_working_parameters_reject_invalid_values(field: str, value: object) -> None:
    """Reject invalid wire widths, device ranges and non-enum mode selectors."""
    with pytest.raises((ValueError, TypeError)):
        replace(parameters(), **{field: value})


def test_udp_broadcast_is_explicit_write_only_and_permission_checked() -> None:
    """Enable SO_BROADCAST only on explicit instances and never broadcast Read All."""
    fake = FakeSocket([])
    fake.setsockopt = Mock()
    settings = SAESSIPPowerSettings(
        "192.168.1.255", address_mode=UDPAddressModeEnum.BROADCAST
    )
    client = SAESSIPPowerClient(
        settings, access_mode=AccessModeEnum.READ_WRITE, socket_factory=lambda: fake
    )
    client.connect()
    fake.setsockopt.assert_called_once_with(
        sip.socket.SOL_SOCKET, sip.socket.SO_BROADCAST, 1
    )
    with pytest.raises(ValueError, match="broadcast"):
        client.read_sample()
    assert not fake.sent
    client.clear_alarm()
    assert fake.sent == [b"\x01\x04"]


@pytest.mark.parametrize("mask", ["255.0.255.0", "0.0.0.255", "invalid", "ffff::"])
def test_invalid_network_configuration_never_sends(mask: str) -> None:
    """Reject malformed/non-contiguous IPv4 masks before touching the socket."""
    fake = FakeSocket([])
    client = SAESSIPPowerClient(
        SAESSIPPowerSettings("controller"),
        access_mode=AccessModeEnum.READ_WRITE,
        socket_factory=lambda: fake,
    )
    client.connect()
    with pytest.raises(ValueError):
        client.set_ip_address("192.168.1.34", mask)
    assert not fake.sent


class FakeStream:
    """Return framed synthetic Modbus replies, including fragmented byte streams."""

    def __init__(
        self, tcp: bool, response_pdu: bytes | None = None, fragment: int = 1000
    ) -> None:
        """Configure fixed responses or auto-echoed writes and synthetic reads."""
        self.tcp = tcp
        self.response_pdu = response_pdu
        self.fragment = fragment
        self.sent: list[bytes] = []
        self.pending = b""
        self.closed = False
        self.timeouts: list[float] = []
        self.mutate: Callable[[bytes], bytes] = lambda data: data
        self.words: dict[int, int] = {}

    def write(self, data: bytes) -> None:
        """Record one ADU and synthesize a response without network access."""
        self.sent.append(data)
        unit = data[6] if self.tcp else data[0]
        pdu = data[7:] if self.tcp else data[1:-2]
        response = self.response_pdu
        if response is None:
            start, count = struct.unpack(">HH", pdu[1:5])
            if pdu[0] == 3:
                response = bytes((3, count * 2)) + struct.pack(
                    f">{count}H",
                    *(
                        self.words.get(start + i, (start + i) & 65535)
                        for i in range(count)
                    ),
                )
            else:
                response = pdu[:5]
        if self.tcp:
            frame = data[:4] + struct.pack(">HB", len(response) + 1, unit) + response
        else:
            frame = bytes((unit,)) + response
            frame += sip._modbus_crc(frame)
        self.pending = self.mutate(frame)

    def read(self, count: int) -> bytes:
        """Simulate arbitrarily fragmented reads and EOF."""
        count = min(count, self.fragment)
        result, self.pending = self.pending[:count], self.pending[count:]
        return result

    def settimeout(self, seconds: float) -> None:
        """Record the bounded receive budget."""
        self.timeouts.append(seconds)

    def close(self) -> None:
        """Record transport cleanup."""
        self.closed = True


def modbus_client(
    tcp: bool,
    mode: AccessModeEnum = AccessModeEnum.READ_ONLY,
    response: bytes | None = None,
    fragment: int = 1000,
) -> tuple[SAESSIPPowerModbusClient, FakeStream]:
    """Build and connect an entirely synthetic Modbus client."""
    fake = FakeStream(tcp, response, fragment)
    settings = ModbusTCPSettings("controller") if tcp else ModbusRTUSettings("fake")
    client = SAESSIPPowerModbusClient(
        settings, access_mode=mode, connection_factory=lambda _: fake
    )
    client.connect()
    return client, fake


MODBUS_WRITES = [
    ("start", ()),
    ("stop", ()),
    ("restart", ()),
    ("clear_alarm", ()),
    ("enable", (EnableCommandEnum.START,)),
    ("critical_step1", ()),
    ("critical_step2", ()),
    ("set_modbus_id", (12,)),
    ("set_ip_address", ("192.168.1.34", "255.255.255.0")),
    (
        "set_switch_modes",
        (SwitchModeEnum.SIMPLE, SwitchModeEnum.WINDOW, SwitchModeEnum.OFF),
    ),
    ("write_register", (R.VOUT_SETPOINT, 5000)),
    ("write_multiple_registers", (R.VOUT_SETPOINT, [5000])),
    ("_exchange", (ModbusFunctionEnum.WRITE_MULTIPLE_REGISTERS, b"")),
]


@pytest.mark.parametrize("tcp", [False, True])
@pytest.mark.parametrize(("method", "args"), MODBUS_WRITES)
def test_modbus_read_only_blocks_all_write_paths(
    tcp: bool, method: str, args: tuple
) -> None:
    """Protect helpers, register APIs and the common transport boundary alike."""
    client, fake = modbus_client(tcp)
    with pytest.raises(SAESSIPPowerPermissionError):
        getattr(client, method)(*args)
    assert not fake.sent
    client.close()
    with pytest.raises(SAESSIPPowerPermissionError):
        getattr(client, method)(*args)
    assert not fake.sent


@pytest.mark.parametrize("tcp", [False, True])
def test_modbus_read_decodes_fragmented_low_word_first_values(tcp: bool) -> None:
    """Use the manual's 0x33221100 example and read-only access over both transports."""
    client, fake = modbus_client(
        tcp, response=bytes.fromhex("0304 1100 3322"), fragment=1
    )
    assert client.read_register(R.SERIAL_NUMBER) == 0x33221100
    pdu = fake.sent[0][7:] if tcp else fake.sent[0][1:-2]
    assert pdu == bytes.fromhex("03 1003 0002")
    assert client.access_mode is AccessModeEnum.READ_ONLY
    assert all(0 < timeout <= 3 for timeout in fake.timeouts)


@pytest.mark.parametrize("tcp", [False, True])
@pytest.mark.parametrize(
    ("register", "value", "words"),
    [
        (R.VOUT_SETPOINT, 5000, "1388"),
        (R.VOUT_RAMP_INTV, 10000, "2710 0000"),
        (R.SW_MODE, 0x29, "0029"),
        (R.SW1_THR, 0x33221100, "1100 3322"),
        (R.SW2_THR_MIN, 1, "0001 0000"),
        (R.SW2_THR_MAX, 2, "0002 0000"),
        (R.SW3_THR_MIN, 3, "0003 0000"),
        (R.SW3_THR_MAX, 4, "0004 0000"),
        (R.CONV_RATE, 65, "0041"),
        (R.IP_ADDR, 0xC0A80122, "0122 c0a8"),
        (R.IP_NETMASK, 24, "0018"),
        (R.KEEPALIVE, 10000, "2710 0000"),
        (R.ENABLE_CMD, 2, "0002"),
        (R.ALARM_CLEAR, 0, "0000"),
        (R.CRITICAL_STEP1, 0x5A5A, "5a5a"),
        (R.CRITICAL_STEP2, 0xA5A5, "a5a5"),
        (R.MODBUS_ID, 12, "000c"),
    ],
)
def test_every_writable_register_encodes_its_full_value(
    tcp: bool, register: R, value: int, words: str
) -> None:
    """Exercise every official writable register with explicit expected word order."""
    client, fake = modbus_client(tcp, AccessModeEnum.READ_WRITE)
    client.write_register(register, value)
    expected_words = bytes.fromhex(words)
    pdu = fake.sent[0][7:] if tcp else fake.sent[0][1:-2]
    assert (
        pdu
        == struct.pack(
            ">BHHB", 0x10, register, len(expected_words) // 2, len(expected_words)
        )
        + expected_words
    )
    assert len(fake.sent) == 1


@pytest.mark.parametrize("tcp", [False, True])
@pytest.mark.parametrize(
    ("method", "args", "address", "value"),
    [
        ("start", (), 0x6000, 1),
        ("stop", (), 0x6000, 0),
        ("restart", (), 0x6000, 2),
        ("clear_alarm", (), 0x6001, 0),
        ("critical_step1", (), 0x7000, 0x5A5A),
        ("critical_step2", (), 0x7001, 0xA5A5),
        ("set_modbus_id", (12,), 0x8000, 12),
    ],
)
def test_modbus_helpers_send_only_the_requested_operation(
    tcp: bool, method: str, args: tuple, address: int, value: int
) -> None:
    """Never add implicit critical steps, resets or alarm clearing to a helper."""
    client, fake = modbus_client(tcp, AccessModeEnum.READ_WRITE)
    getattr(client, method)(*args)
    pdu = fake.sent[0][7:] if tcp else fake.sent[0][1:-2]
    assert pdu == struct.pack(">BHHBH", 0x10, address, 1, 2, value)
    assert len(fake.sent) == 1
    assert client.settings.modbus_id == 11


def test_modbus_network_write_uses_cidr_and_keeps_endpoint() -> None:
    """Encode IP address low-word first and a prefix length, not a UDP dotted mask."""
    client, fake = modbus_client(True, AccessModeEnum.READ_WRITE)
    client.set_ip_address("192.168.1.34", "255.255.255.0")
    assert fake.sent[0][7:] == bytes.fromhex("10 5000 0003 06 0122 c0a8 0018")
    assert client.settings.host == "controller"


@pytest.mark.parametrize(
    ("register", "count"), [(R.SERIAL_NUMBER, 1), (R.CARD_TYPE, 6), (R.ENABLE_CMD, 1)]
)
def test_invalid_read_spans_never_reach_device(register: R, count: int) -> None:
    """Reject partial values, holes and write-only addresses before transmission."""
    client, fake = modbus_client(True)
    with pytest.raises(ValueError):
        client.read_holding_registers(register, count)
    assert not fake.sent


@pytest.mark.parametrize(
    ("register", "words"),
    [
        (R.VOUT_SETPOINT, [999]),
        (R.VOUT_RAMP_INTV, [2000]),
        (R.SW_MODE, [2]),
        (R.SW_MODE, [0x40]),
        (R.SW_MODE, [0x0C]),
        (R.SW_MODE, [0x30]),
        (R.IP_NETMASK, [33]),
        (R.KEEPALIVE, [999, 0]),
        (R.ENABLE_CMD, [3]),
        (R.CRITICAL_STEP1, [0]),
        (R.CRITICAL_STEP2, [0]),
        (R.MODBUS_ID, [0]),
        (R.MAC_ADDR, [0, 0, 0]),
        (R.VOUT_SETPOINT, [True]),
    ],
)
def test_invalid_raw_register_writes_never_reach_device(
    register: R, words: list[int]
) -> None:
    """Raw word writes enforce the same permissions and limits as typed helpers."""
    client, fake = modbus_client(True, AccessModeEnum.READ_WRITE)
    with pytest.raises((ValueError, TypeError)):
        client.write_multiple_registers(register, words)
    assert not fake.sent


@pytest.mark.parametrize("tcp", [False, True])
@pytest.mark.parametrize("ethernet", [False, True])
def test_modbus_sample_covers_all_readable_register_groups(
    tcp: bool, ethernet: bool
) -> None:
    """Omit network registers on non-Ethernet hardware without inventing zero data."""
    client, fake = modbus_client(tcp)
    fake.words[0x1000] = 2 if ethernet else 0
    fake.words.update({0x1003: 0x1100, 0x1004: 0x3322})
    sample = client.read_sample()
    assert sample.observed_at.utcoffset().total_seconds() == 0
    assert sample.registers[R.SERIAL_NUMBER] == 0x33221100
    assert (R.IP_ADDR in sample.registers) is ethernet
    assert (R.MAC_ADDR in sample.registers) is ethernet
    assert R.MODBUS_ID not in sample.registers
    assert R.ENABLE_CMD not in sample.registers
    assert len(fake.sent) == (5 if ethernet else 4)
    assert len(sample.registers) == (26 if ethernet else 22)
    with pytest.raises(TypeError):
        sample.registers[R.VOUT] = 0


@pytest.mark.parametrize("tcp", [False, True])
def test_modbus_exception_is_reported_without_retry(tcp: bool) -> None:
    """A device rejection is distinct from a timeout or malformed frame."""
    client, fake = modbus_client(tcp, AccessModeEnum.READ_WRITE, response=b"\x90\x03")
    with pytest.raises(SAESSIPPowerModbusError) as caught:
        client.start()
    assert caught.value.exception_code == 3
    assert caught.value.function is ModbusFunctionEnum.WRITE_MULTIPLE_REGISTERS
    assert len(fake.sent) == 1
    assert client.is_connected


@pytest.mark.parametrize("tcp", [False, True])
@pytest.mark.parametrize(
    "failure", ["short", "function", "read_length", "write_echo", "unit"]
)
def test_malformed_modbus_responses_close_transport_without_retry(
    tcp: bool, failure: str
) -> None:
    """Reject malformed frames and discard the stream to prevent stale reply reuse."""
    response = {
        "function": b"\x04\x02\x00\x01",
        "read_length": b"\x03\x02\x00\x01",
        "write_echo": bytes.fromhex("10 6000 0002"),
    }.get(failure)
    client, fake = modbus_client(tcp, AccessModeEnum.READ_WRITE, response=response)
    if failure == "short":
        fake.mutate = lambda frame: frame[:-1]
    if failure == "unit":
        fake.mutate = lambda frame: (
            (frame[:6] + b"\x0c" + frame[7:]) if tcp else b"\x0c" + frame[1:]
        )
    with pytest.raises((SAESSIPPowerCommunicationError, SAESSIPPowerProtocolError)):
        client.start() if failure == "write_echo" else client.read_register(
            R.SERIAL_NUMBER
        )
    assert len(fake.sent) == 1
    assert not client.is_connected
    assert fake.closed


def test_tcp_transaction_and_protocol_ids_are_validated() -> None:
    """Reject a stale transaction ID rather than treating it as the current reply."""
    client, fake = modbus_client(True)
    fake.mutate = lambda frame: b"\x00\x00" + frame[2:]
    with pytest.raises(SAESSIPPowerProtocolError):
        client.read_register(R.VOUT)
    assert fake.closed


def test_rtu_crc_and_broadcast_contract() -> None:
    """Verify an independent CRC vector and SAES-specific broadcast unit 255."""
    assert sip._modbus_crc(bytes.fromhex("01 03 0000 000a")) == bytes.fromhex("c5cd")
    client, fake = modbus_client(False)
    fake.mutate = lambda frame: frame[:-2] + b"\x00\x00"
    with pytest.raises(SAESSIPPowerProtocolError, match="CRC"):
        client.read_register(R.VOUT)
    stream = FakeStream(False)
    stream.read = Mock(side_effect=AssertionError("broadcast must not wait for an ACK"))
    broadcast = SAESSIPPowerModbusClient(
        ModbusRTUSettings("fake", modbus_id=255),
        access_mode=AccessModeEnum.READ_WRITE,
        connection_factory=lambda _: stream,
    )
    broadcast.connect()
    with pytest.raises(ValueError, match="broadcast"):
        broadcast.read_register(R.VOUT)
    broadcast.stop()
    assert stream.sent[0][:8] == bytes.fromhex("ff 10 6000 0001 02 00")
    assert len(stream.sent) == 1
    stream.read.assert_not_called()


def test_all_public_enum_class_names_end_in_enum() -> None:
    """Keep the user-requested naming convention for every public selector enum."""
    enums = [
        value
        for value in vars(sip).values()
        if isinstance(value, type)
        and issubclass(value, Enum)
        and value.__module__ == sip.__name__
    ]
    assert enums
    assert all(enum.__name__.endswith("Enum") for enum in enums)


@pytest.mark.parametrize("tcp", [False, True])
def test_modbus_switch_modes_use_enum_selectors(tcp: bool) -> None:
    """Encode named modes and reject invalid selector types or SW1 WINDOW."""
    client, fake = modbus_client(tcp, AccessModeEnum.READ_WRITE)
    client.set_switch_modes(
        SwitchModeEnum.SIMPLE, SwitchModeEnum.WINDOW, SwitchModeEnum.WINDOW
    )
    pdu = fake.sent[0][7:] if tcp else fake.sent[0][1:-2]
    assert pdu == bytes.fromhex("10 4003 0001 02 0029")
    with pytest.raises(TypeError):
        client.set_switch_modes(1, SwitchModeEnum.OFF, SwitchModeEnum.OFF)
    with pytest.raises(ValueError):
        client.set_switch_modes(
            SwitchModeEnum.WINDOW, SwitchModeEnum.OFF, SwitchModeEnum.OFF
        )
    with pytest.raises(TypeError):
        client.enable(1)
    assert len(fake.sent) == 1


@pytest.mark.parametrize("tcp", [False, True])
def test_modbus_write_timeout_never_retries(tcp: bool) -> None:
    """A sent write with no reply stays ambiguous; close without sending it again."""
    client, fake = modbus_client(tcp, AccessModeEnum.READ_WRITE)
    fake.read = Mock(side_effect=TimeoutError("synthetic timeout"))
    with pytest.raises(SAESSIPPowerCommunicationError):
        client.start()
    assert len(fake.sent) == 1
    assert fake.closed and not client.is_connected


@pytest.mark.parametrize("tcp", [False, True])
def test_modbus_reconnect_keeps_read_only_mode(tcp: bool) -> None:
    """Opening/closing/replacing a transport is command-free and cannot change mode."""
    client, fake = modbus_client(tcp)
    with pytest.raises(AttributeError):
        client.access_mode = AccessModeEnum.READ_WRITE
    client.reconnect()
    with pytest.raises(SAESSIPPowerPermissionError):
        client.clear_alarm()
    client.close()
    client.close()
    assert not fake.sent


def test_modbus_frame_gap_and_receive_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce the device's 4-ms inter-frame spacing and a bounded total read."""
    clock = [10.0]
    sleeps = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(sip.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(sip.time, "sleep", sleep)
    client, fake = modbus_client(True)
    client.read_register(R.VOUT)
    client.read_register(R.VOUT)
    assert sleeps == pytest.approx([0, 0.004])

    def slow_read(count: int) -> bytes:
        clock[0] += 4.0
        return b"\x00"

    fake.read = slow_read
    with pytest.raises(SAESSIPPowerCommunicationError, match="timed out"):
        client.read_register(R.VOUT)
    assert fake.closed


@pytest.mark.parametrize(
    ("settings", "args"),
    [
        (ModbusTCPSettings, {"host": "controller", "modbus_id": 0}),
        (ModbusTCPSettings, {"host": "controller", "modbus_id": 255}),
        (ModbusTCPSettings, {"host": "controller", "port": 65536}),
        (ModbusTCPSettings, {"host": "controller", "timeout_s": float("nan")}),
        (ModbusRTUSettings, {"port": "fake", "modbus_id": 0}),
        (ModbusRTUSettings, {"port": "fake", "modbus_id": 248}),
        (ModbusRTUSettings, {"port": "fake", "baudrate": 0}),
        (ModbusRTUSettings, {"port": "fake", "timeout_s": -1}),
    ],
)
def test_invalid_modbus_settings_rejected(settings: type, args: dict) -> None:
    """Fail locally on unsupported IDs, endpoint ranges and unbounded timeouts."""
    with pytest.raises((ValueError, TypeError)):
        settings(**args)


def test_production_tcp_adapter_with_mock_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the actual TCP adapter without opening a real socket."""
    stream = FakeStream(True)
    sock = Mock()
    sock.sendall.side_effect = stream.write
    sock.recv.side_effect = stream.read
    create = Mock(return_value=sock)
    monkeypatch.setattr(sip.socket, "create_connection", create)
    client = SAESSIPPowerModbusClient(ModbusTCPSettings("controller"))
    assert not create.called
    client.connect()
    create.assert_called_once_with(("controller", 502), 3.0)
    client.read_register(R.VOUT)
    client.close()
    sock.close.assert_called_once()
    assert len(stream.sent) == 1


def test_production_serial_adapter_with_mock_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise lazy optional import, 38400/8N2 defaults and short-write failure."""
    stream = FakeStream(False)
    port = Mock()

    def write(data: bytes) -> int:
        stream.write(data)
        return len(data)

    port.write.side_effect = write
    port.read.side_effect = stream.read
    factory = Mock(return_value=port)
    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=factory))
    client = SAESSIPPowerModbusClient(
        ModbusRTUSettings("fake"), access_mode=AccessModeEnum.READ_WRITE
    )
    assert not factory.called
    client.connect()
    factory.assert_called_once_with(
        port="fake",
        baudrate=38400,
        bytesize=8,
        parity="N",
        stopbits=2,
        timeout=3.0,
        write_timeout=3.0,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    client.read_register(R.VOUT)
    port.write.side_effect = None
    port.write.return_value = 1
    with pytest.raises(SAESSIPPowerCommunicationError):
        client.start()
    assert port.write.call_count == 2
    port.close.assert_called_once()
