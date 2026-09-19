"""Provide synthetic controller transports for device and notebook tests."""

from __future__ import annotations

import struct
import time
from pathlib import Path
from unittest.mock import Mock

import IPython.display
import pytest
from test_commands_and_modbus import FakeStream
from test_seas_sip_client import FakeSocket, read_all_response

import seas_sip_client as sip
from seas_sip_client import ModbusRegisterEnum as R
from seas_sip_client import SAESSIPPowerClient, SAESSIPPowerModbusClient

SOURCE = Path(__file__).resolve().parents[1] / "demo.py"
WRITE_ONLY = {
    R.ENABLE_CMD,
    R.ALARM_CLEAR,
    R.CRITICAL_STEP1,
    R.CRITICAL_STEP2,
    R.MODBUS_ID,
}
ETHERNET = {R.IP_ADDR, R.IP_NETMASK, R.MAC_ADDR, R.KEEPALIVE}
WRITABLE = {
    R.VOUT_SETPOINT,
    R.VOUT_RAMP_INTV,
    R.SW_MODE,
    R.SW1_THR,
    R.SW2_THR_MIN,
    R.SW2_THR_MAX,
    R.SW3_THR_MIN,
    R.SW3_THR_MAX,
    R.CONV_RATE,
    R.IP_ADDR,
    R.IP_NETMASK,
    R.KEEPALIVE,
} | WRITE_ONLY


class NotebookUDP(FakeSocket):
    """Respond to notebook UDP calls with a mutable synthetic payload."""

    def __init__(self, lab: NotebookLab, settings: sip.SAESSIPPowerSettings) -> None:
        """Share one fake controller across reconnects and observer clients."""
        super().__init__([])
        self.lab = lab
        self.settings = settings

    def send(self, data: bytes) -> int:
        """Apply explicit commands to synthetic state and log every request."""
        self.lab.events.append(("udp", data[1], data, self.settings))
        payload = self.lab.payload
        if data[1] in (1, 2, 3):
            status = struct.unpack_from(">H", payload, 32)[0]
            enabled = data[1] != 2
            struct.pack_into(">H", payload, 32, (status & ~3) | int(enabled))
            struct.pack_into(">H", payload, 14, 5000 if enabled else 0)
        elif data[1] == 4:
            status = struct.unpack_from(">H", payload, 32)[0]
            struct.pack_into(">H", payload, 32, status & 15)
        elif data[1] == 0x40:
            payload[100:134] = data[2:]
        elif data[1] == 0x41:
            payload[200:208] = data[2:]
        return super().send(data)

    def recv(self, bufsize: int) -> bytes:
        """Return current synthetic state for a Read All request."""
        assert self.sent[-1] == b"\x01\x05"
        return b"\x01\x80" + bytes(self.lab.payload)

    def setsockopt(self, level: int, option: int, value: int) -> None:
        """Accept broadcast configuration without opening an OS socket."""


class NotebookStream(FakeStream):
    """Use real client framing against an in-memory Modbus controller."""

    def __init__(
        self, lab: NotebookLab, settings: sip.ModbusTCPSettings | sip.ModbusRTUSettings
    ) -> None:
        """Share registers and enforce exclusive use of the mock serial port."""
        super().__init__(isinstance(settings, sip.ModbusTCPSettings))
        self.lab = lab
        self.settings = settings
        self.words = lab.words
        if not self.tcp:
            assert not any(
                not stream.tcp and not stream.closed for stream in lab.streams
            )
        lab.streams.append(self)

    def write(self, data: bytes) -> None:
        """Record reads/writes and change state before producing the fake reply."""
        pdu = data[7:] if self.tcp else data[1:-2]
        self.lab.events.append(("modbus", pdu[0], pdu, self.settings))
        start, count = struct.unpack(">HH", pdu[1:5])
        if pdu[0] == 16:
            values = struct.unpack(f">{count}H", pdu[6:])
            self.words.update({start + i: value for i, value in enumerate(values)})
            if start == R.ENABLE_CMD:
                enabled = values[0] != 0
                self.words[R.STATUS] = (self.words[R.STATUS] & ~3) | int(enabled)
                self.words[R.VOUT] = 5000 if enabled else 0
            elif start == R.ALARM_CLEAR:
                self.words[R.STATUS] &= 15
        super().write(data)


class NotebookLab:
    """Provide typed clients with fake transports and captured display output."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ethernet: bool = True
    ) -> None:
        """Block real adapters before any notebook code is evaluated."""
        self.payload = bytearray(read_all_response()[2:])
        self.events: list[tuple[str, int, bytes, object]] = []
        self.streams: list[NotebookStream] = []
        self.clients: list[SAESSIPPowerClient | SAESSIPPowerModbusClient] = []
        self.words: dict[int, int] = {}
        values = {
            R.CARD_TYPE: 3 if ethernet else 1,
            R.HW_CODE: 0x0102,
            R.SW_VERSION: 0x0304,
            R.SERIAL_NUMBER: 123456,
            R.LIFE_TIME: 100,
            R.TEMPERATURE: 300,
            R.ARCING_NUMBER: 7,
            R.STATUS: 0x40,
            R.SW_STATUS: 5,
            R.UPTIME: 200,
            R.VIN: 240,
            R.VOUT: 0,
            R.IOUT: 1000,
            R.VOUT_SETPOINT: 5000,
            R.VOUT_RAMP_INTV: 2000,
            R.SW_MODE: 9,
            R.SW1_THR: 11,
            R.SW2_THR_MIN: 12,
            R.SW2_THR_MAX: 13,
            R.SW3_THR_MIN: 14,
            R.SW3_THR_MAX: 15,
            R.CONV_RATE: 20,
            R.IP_ADDR: 0xC0A83222,
            R.IP_NETMASK: 24,
            R.MAC_ADDR: 0x001122AABBCC,
            R.KEEPALIVE: 30000,
        }
        double_words = {
            R.SERIAL_NUMBER,
            R.LIFE_TIME,
            R.UPTIME,
            R.IOUT,
            R.VOUT_RAMP_INTV,
            R.SW1_THR,
            R.SW2_THR_MIN,
            R.SW2_THR_MAX,
            R.SW3_THR_MIN,
            R.SW3_THR_MAX,
            R.IP_ADDR,
            R.KEEPALIVE,
        }
        for register, value in values.items():
            width = (
                3 if register is R.MAC_ADDR else 2 if register in double_words else 1
            )
            for index in range(width):
                self.words[int(register) + index] = (value >> (16 * index)) & 65535
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(time, "sleep", lambda _: None)
        forbidden = Mock(
            side_effect=AssertionError("Real device adapters are forbidden")
        )
        monkeypatch.setattr(sip.socket, "socket", forbidden)
        monkeypatch.setattr(sip, "_TCPConnection", forbidden)
        monkeypatch.setattr(sip, "_RTUConnection", forbidden)
        monkeypatch.setattr(sip, "SAESSIPPowerClient", self.udp_client)
        monkeypatch.setattr(sip, "SAESSIPPowerModbusClient", self.modbus_client)
        self.display = Mock()
        monkeypatch.setattr(IPython.display, "display", self.display)

    def udp_client(
        self, settings: sip.SAESSIPPowerSettings, *, access_mode: sip.AccessModeEnum
    ) -> SAESSIPPowerClient:
        """Inject a new fake socket for each connection/reconnection."""
        client = SAESSIPPowerClient(
            settings,
            access_mode=access_mode,
            socket_factory=lambda: NotebookUDP(self, settings),
        )
        self.clients.append(client)
        return client

    def modbus_client(
        self,
        settings: sip.ModbusTCPSettings | sip.ModbusRTUSettings,
        *,
        access_mode: sip.AccessModeEnum,
    ) -> SAESSIPPowerModbusClient:
        """Use real access guards and protocol encoding against fake streams."""
        client = SAESSIPPowerModbusClient(
            settings,
            access_mode=access_mode,
            connection_factory=lambda selected: NotebookStream(self, selected),
        )
        self.clients.append(client)
        return client


def is_read(event: tuple[str, int, bytes, object]) -> bool:
    """Distinguish actual protocol reads from any write/control request."""
    return event[1] == (5 if event[0] == "udp" else 3)
