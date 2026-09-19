"""Access SAES SIP POWER via UDP and Modbus with explicit read/write permissions."""

from __future__ import annotations

import socket
import struct
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import Enum, IntEnum
from ipaddress import IPv4Address, IPv4Network
from types import MappingProxyType
from typing import Protocol

DEFAULT_PORT = 2527
START_REQUEST = bytes((0x01, 0x01))
STOP_REQUEST = bytes((0x01, 0x02))
RESET_REQUEST = bytes((0x01, 0x03))
CLEAR_ALARM_REQUEST = bytes((0x01, 0x04))
READ_ALL_REQUEST = bytes((0x01, 0x05))
READ_ALL_RESPONSE_COMMAND = 0x80
PROTOCOL_VERSION = 0x01
READ_ALL_PAYLOAD_LENGTH = 300
READ_ALL_RESPONSE_LENGTH = 2 + READ_ALL_PAYLOAD_LENGTH


class AccessModeEnum(Enum):
    """Select device-read permission or explicit permission to modify the device."""

    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class ConnectionTypeEnum(Enum):
    """Choose the wire protocol once when constructing a device connection."""

    UDP = "udp"
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"


class AddressModeEnum(Enum):
    """Choose a unicast device or an explicit UDP/RTU broadcast destination."""

    UNICAST = "unicast"
    BROADCAST = "broadcast"


class CommandEnum(IntEnum):
    """Name the manufacturer's UDP commands (Rev. 4, section 9.2)."""

    START = 0x01
    STOP = 0x02
    RESET = 0x03
    CLEAR_ALARM = 0x04
    READ_ALL = 0x05
    SET_WORKING_PARAMETERS = 0x40
    SET_IP_ADDRESS = 0x41
    READ_ALL_ANSWER = 0x80


class SwitchModeEnum(IntEnum):
    """Select a documented comparator switch mode; SW1 cannot use WINDOW."""

    OFF = 0
    SIMPLE = 1
    WINDOW = 2


class UDPAddressModeEnum(Enum):
    """Select one controller or an explicitly configured broadcast destination."""

    UNICAST = "unicast"
    BROADCAST = "broadcast"


class SAESSIPPowerError(RuntimeError):
    """Identify failures produced at the SIP POWER source boundary.

    The exception contains sanitized context but never a raw frame. Callers use
    this common type when communication and malformed-response failures require
    the same collector-level reconnect policy.
    """


class SAESSIPPowerCommunicationError(SAESSIPPowerError):
    """Report a timeout or operating-system failure during controller access.

    The client raises this after one socket operation fails and performs no
    retry itself. The owning collector may replace the socket and retry once;
    no controller output or setting is changed by that recovery.
    """


class SAESSIPPowerProtocolError(SAESSIPPowerError):
    """Report a response that violates documented SIP POWER UDP framing.

    Invalid length, header values, or timestamp semantics fail the whole sample
    before normalization. The exception exposes no raw datagram, and the
    collector may reconnect and retry it like a source communication failure.
    """


class SAESSIPPowerPermissionError(SAESSIPPowerError, PermissionError):
    """Reject control or configuration writes from a read-only client."""


class SAESSIPPowerUnsupportedOperationError(SAESSIPPowerError):
    """Report an operation unavailable on the selected interface or hardware."""


class _AccessControlledClient:
    """Keep access mode fixed through the public API for the client's lifetime."""

    def __init__(self, access_mode: AccessModeEnum) -> None:
        """Reject strings, booleans and foreign enums instead of coercing them."""

        if not isinstance(access_mode, AccessModeEnum):
            raise TypeError("access_mode must be an AccessModeEnum member")
        self.__access_mode = access_mode

    @property
    def access_mode(self) -> AccessModeEnum:
        """Return the mode selected at construction; no public setter exists."""

        return self.__access_mode

    def _require_write(self) -> None:
        """Fail before any device I/O unless writes were explicitly enabled."""

        if self.__access_mode is not AccessModeEnum.READ_WRITE:
            raise SAESSIPPowerPermissionError(
                "device writes require a new client with AccessModeEnum.READ_WRITE"
            )


def _integer(name: str, value: int, minimum: int, maximum: int) -> None:
    """Validate a protocol integer without accepting bool or fractional values."""

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def _keepalive(value: int) -> None:
    """Validate the manual's disabled or at-least-one-second watchdog interval."""

    _integer("keepalive_interval_ms", value, 0, 0xFFFFFFFF)
    if 0 < value < 1000:
        raise ValueError("keepalive_interval_ms must be 0 or at least 1000")


class DatagramSocket(Protocol):
    """Describe connected UDP operations owned by the source client.

    Implementations select one peer, perform synchronous whole-datagram sends
    and receives under a configured timeout, and release their handle on close.
    The source client owns the instance and does not access it concurrently.
    """

    def settimeout(self, value: float | None) -> None:
        """Set the maximum blocking time for one socket operation."""

        ...

    def connect(self, address: tuple[str, int]) -> None:
        """Select the only peer from which datagrams will be accepted."""

        ...

    def send(self, data: bytes) -> int:
        """Send one datagram to the selected peer."""

        ...

    def recv(self, bufsize: int) -> bytes:
        """Receive one datagram from the selected peer."""

        ...

    def close(self) -> None:
        """Release the socket handle."""

        ...

    def setsockopt(self, level: int, option: int, value: int) -> None:
        """Configure explicit broadcast permission when requested."""

        ...


SocketFactory = Callable[[], DatagramSocket]


@dataclass(frozen=True)
class SAESSIPPowerSettings:
    """Hold network settings for one SIP POWER controller.

    ``host`` may be an IPv4 address or DNS name. ``port`` is normally the
    controller's hard-coded UDP port 2527, while ``timeout_s`` bounds each read.
    Instances contain no credentials and opening a client does not alter the
    controller.
    """

    host: str
    port: int = DEFAULT_PORT
    timeout_s: float = 3.0
    address_mode: UDPAddressModeEnum = UDPAddressModeEnum.UNICAST

    def __post_init__(self) -> None:
        """Require the explicit UDP destination-mode enum."""

        if not isinstance(self.address_mode, UDPAddressModeEnum):
            raise TypeError("address_mode must be a UDPAddressModeEnum member")


@dataclass(frozen=True)
class SourceSample:
    """Represent one complete current-state response from a SIP POWER.

    The sample exposes stable snake_case values decoded from the documented
    Read All response. ``observed_at`` is the host acquisition time in UTC
    because the controller supplies no observation timestamp. Electrical and
    timing units are explicit in attribute names. Alarm fields are latched
    controller states, not transient host-side errors.
    """

    observed_at: datetime
    serial_number: int
    has_ethernet: bool
    has_display: bool
    hardware_revision: str
    software_version: str
    output_current_na: int
    output_voltage_v: int
    input_voltage_v: float
    internal_temperature_k: int
    arcing_events: int
    total_working_time_h: int
    uptime_s: int
    enabled: bool
    need_restart: bool
    output_current_gradient: str
    global_alarm: bool
    safe_alarm: bool
    interlock_alarm: bool
    over_temperature_alarm: bool
    input_voltage_alarm: bool
    output_over_voltage_alarm: bool
    output_over_current_alarm: bool
    arcing_alarm: bool
    communication_alarm: bool
    switch_1_on: bool
    switch_2_on: bool
    switch_3_on: bool
    output_voltage_setpoint_v: int
    output_voltage_ramp_interval_ms: int
    switch_1_mode: str
    switch_2_mode: str
    switch_3_mode: str
    switch_1_threshold_na: int
    switch_2_min_threshold_na: int
    switch_2_max_threshold_na: int
    switch_3_min_threshold_na: int
    switch_3_max_threshold_na: int
    keepalive_interval_ms: int
    conversion_rate_a_per_torr: int
    modbus_id: int
    ip_address: str
    ip_netmask: str
    mac_address: str
    output_power_w: float
    pressure_torr: float | None

    @property
    def device_id(self) -> str:
        """Return the controller serial number as its stable record identity."""

        return str(self.serial_number)


@dataclass(frozen=True)
class WorkingParameters:
    """Hold the complete 34-byte Set Working Parameters payload, with explicit units.

    All fields are required because UDP replaces the whole parameter block.
    Use from_sample and dataclasses.replace to retain other observed settings.
    This is a snapshot, not an atomic read-modify-write transaction.
    """

    output_voltage_setpoint_v: int
    output_voltage_ramp_interval_ms: int
    switch_1_mode: SwitchModeEnum
    switch_2_mode: SwitchModeEnum
    switch_3_mode: SwitchModeEnum
    switch_1_threshold_na: int
    switch_2_min_threshold_na: int
    switch_2_max_threshold_na: int
    switch_3_min_threshold_na: int
    switch_3_max_threshold_na: int
    keepalive_interval_ms: int
    conversion_rate_a_per_torr: int
    modbus_id: int

    def __post_init__(self) -> None:
        """Validate documented ranges and wire widths before constructing a write."""

        _integer(
            "output_voltage_setpoint_v", self.output_voltage_setpoint_v, 1000, 6000
        )
        _integer(
            "output_voltage_ramp_interval_ms",
            self.output_voltage_ramp_interval_ms,
            1000,
            60000,
        )
        for name in ("switch_1_mode", "switch_2_mode", "switch_3_mode"):
            if not isinstance(getattr(self, name), SwitchModeEnum):
                raise TypeError(f"{name} must be a SwitchModeEnum member")
        if self.switch_1_mode is SwitchModeEnum.WINDOW:
            raise ValueError("SW1 supports only OFF and SIMPLE")
        for name in (
            "switch_1_threshold_na",
            "switch_2_min_threshold_na",
            "switch_2_max_threshold_na",
            "switch_3_min_threshold_na",
            "switch_3_max_threshold_na",
        ):
            _integer(name, getattr(self, name), 0, 0xFFFFFFFF)
        _keepalive(self.keepalive_interval_ms)
        _integer(
            "conversion_rate_a_per_torr", self.conversion_rate_a_per_torr, 0, 65535
        )
        _integer("modbus_id", self.modbus_id, 1, 247)

    @classmethod
    def from_sample(cls, sample: SourceSample) -> WorkingParameters:
        """Copy the reported block; reject reserved switch modes on write conversion."""

        return cls(
            sample.output_voltage_setpoint_v,
            sample.output_voltage_ramp_interval_ms,
            SwitchModeEnum[sample.switch_1_mode],
            SwitchModeEnum[sample.switch_2_mode],
            SwitchModeEnum[sample.switch_3_mode],
            sample.switch_1_threshold_na,
            sample.switch_2_min_threshold_na,
            sample.switch_2_max_threshold_na,
            sample.switch_3_min_threshold_na,
            sample.switch_3_max_threshold_na,
            sample.keepalive_interval_ms,
            sample.conversion_rate_a_per_torr,
            sample.modbus_id,
        )

    def to_payload(self) -> bytes:
        """Encode the manual's big-endian 34-byte UDP parameter block."""

        modes = (
            int(self.switch_1_mode)
            | (self.switch_2_mode << 2)
            | (self.switch_3_mode << 4)
        )
        return struct.pack(
            ">HIBIIIIIIHB",
            self.output_voltage_setpoint_v,
            self.output_voltage_ramp_interval_ms,
            modes,
            self.switch_1_threshold_na,
            self.switch_2_min_threshold_na,
            self.switch_2_max_threshold_na,
            self.switch_3_min_threshold_na,
            self.switch_3_max_threshold_na,
            self.keepalive_interval_ms,
            self.conversion_rate_a_per_torr,
            self.modbus_id,
        )


def _ip_payload(ip_address: str, ip_netmask: str) -> bytes:
    """Encode IPv4 address and a contiguous dotted-decimal subnet mask."""

    address = IPv4Address(ip_address)
    mask = IPv4Address(ip_netmask)
    if IPv4Network(f"0.0.0.0/{mask}").netmask != mask:
        raise ValueError("ip_netmask must be a netmask, not an inverted host mask")
    return address.packed + mask.packed


def _udp_socket() -> DatagramSocket:
    """Create the IPv4 UDP socket used by production clients."""

    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def _u16(payload: bytes, offset: int) -> int:
    """Decode one network-order unsigned 16-bit integer from a payload."""

    return struct.unpack_from(">H", payload, offset)[0]


def _u32(payload: bytes, offset: int) -> int:
    """Decode one network-order unsigned 32-bit integer from a payload."""

    return struct.unpack_from(">I", payload, offset)[0]


def _revision(value: int) -> str:
    """Format the manual's major-byte/minor-byte revision representation."""

    return f"{value >> 8}.{value & 0xFF}"


def _switch_mode(value: int) -> str:
    """Return a stable name for a two-bit switch operating mode."""

    return {0: "OFF", 1: "SIMPLE", 2: "WINDOW"}.get(value, "RESERVED")


def parse_read_all_response(
    response: bytes, *, observed_at: datetime | None = None
) -> SourceSample:
    """Decode one documented 302-byte Read All Answer datagram.

    Args:
        response: Complete UDP datagram including version and command bytes.
        observed_at: Optional acquisition timestamp for deterministic tests. When
            omitted, the parser stamps successful acquisition with current UTC.

    Returns:
        A complete normalized controller snapshot.

    Raises:
        SAESSIPPowerProtocolError: If length, version, command, or timestamp is
            invalid. Reserved payload bytes are intentionally ignored.
    """

    if len(response) != READ_ALL_RESPONSE_LENGTH:
        raise SAESSIPPowerProtocolError(
            "Read All response must be exactly "
            f"{READ_ALL_RESPONSE_LENGTH} bytes; received {len(response)}"
        )
    if response[0] != PROTOCOL_VERSION:
        raise SAESSIPPowerProtocolError(
            f"unexpected protocol version 0x{response[0]:02x}"
        )
    if response[1] != READ_ALL_RESPONSE_COMMAND:
        raise SAESSIPPowerProtocolError(
            f"unexpected response command 0x{response[1]:02x}"
        )
    timestamp = observed_at or datetime.now(UTC)
    if timestamp.utcoffset() is None:
        raise SAESSIPPowerProtocolError("observation timestamp must be timezone-aware")

    payload = response[2:]
    card_type = _u16(payload, 0)
    hardware_code = _u16(payload, 2)
    software_version = _u16(payload, 4)
    output_current_na = _u32(payload, 10)
    output_voltage_v = _u16(payload, 14)
    status = _u16(payload, 32)
    switch_status = payload[34]
    switch_modes = payload[106]
    conversion_rate = _u16(payload, 131)
    output_power_w = output_current_na * 1e-9 * output_voltage_v
    pressure_torr = (
        output_current_na * 1e-9 / conversion_rate if conversion_rate else None
    )
    gradient_value = (status >> 2) & 0b11
    gradient = {0: "HOLD", 1: "UP", 2: "DOWN"}.get(gradient_value, "RESERVED")

    return SourceSample(
        observed_at=timestamp.astimezone(UTC),
        serial_number=_u32(payload, 6),
        has_ethernet=bool(card_type & (1 << 1)),
        has_display=bool(card_type & 1),
        hardware_revision=_revision(hardware_code),
        software_version=_revision(software_version),
        output_current_na=output_current_na,
        output_voltage_v=output_voltage_v,
        input_voltage_v=_u16(payload, 16) / 10.0,
        internal_temperature_k=_u16(payload, 20),
        arcing_events=_u16(payload, 22),
        total_working_time_h=_u32(payload, 24),
        uptime_s=_u32(payload, 28),
        enabled=bool(status & (1 << 0)),
        need_restart=bool(status & (1 << 1)),
        output_current_gradient=gradient,
        global_alarm=bool(status & (1 << 4)),
        safe_alarm=bool(status & (1 << 5)),
        interlock_alarm=bool(status & (1 << 6)),
        over_temperature_alarm=bool(status & (1 << 7)),
        input_voltage_alarm=bool(status & (1 << 8)),
        output_over_voltage_alarm=bool(status & (1 << 9)),
        output_over_current_alarm=bool(status & (1 << 10)),
        arcing_alarm=bool(status & (1 << 11)),
        communication_alarm=bool(status & (1 << 12)),
        switch_1_on=bool(switch_status & (1 << 0)),
        switch_2_on=bool(switch_status & (1 << 1)),
        switch_3_on=bool(switch_status & (1 << 2)),
        output_voltage_setpoint_v=_u16(payload, 100),
        output_voltage_ramp_interval_ms=_u32(payload, 102),
        switch_1_mode=_switch_mode(switch_modes & 0b11),
        switch_2_mode=_switch_mode((switch_modes >> 2) & 0b11),
        switch_3_mode=_switch_mode((switch_modes >> 4) & 0b11),
        switch_1_threshold_na=_u32(payload, 107),
        switch_2_min_threshold_na=_u32(payload, 111),
        switch_2_max_threshold_na=_u32(payload, 115),
        switch_3_min_threshold_na=_u32(payload, 119),
        switch_3_max_threshold_na=_u32(payload, 123),
        keepalive_interval_ms=_u32(payload, 127),
        conversion_rate_a_per_torr=conversion_rate,
        modbus_id=payload[133],
        ip_address=str(IPv4Address(payload[200:204])),
        ip_netmask=str(IPv4Address(payload[204:208])),
        mac_address=":".join(f"{byte:02X}" for byte in payload[208:214]),
        output_power_w=output_power_w,
        pressure_torr=pressure_torr,
    )


class SAESSIPPowerClient(_AccessControlledClient):
    """Own one synchronous SAES SIP POWER UDP endpoint.

    ``read_sample`` uses Read All (0x05). Explicit ``start`` and ``stop`` calls
    switch the pump HV output; they do not switch the controller's input power.
    Reset, Clear Alarm, Set Working Parameters and Set IP Address are explicit
    writes too. All writes require AccessModeEnum.READ_WRITE at construction.
    ``connect`` creates a connected UDP socket so replies are accepted only from
    the configured controller, and ``read_sample`` returns one fully normalized
    :class:`SourceSample`. The controller supplies no time, so successful reads
    receive an aware UTC host-acquisition timestamp.

    A socket timeout, send error, or receive error is exposed as
    :class:`SAESSIPPowerCommunicationError`; malformed replies are exposed as
    :class:`SAESSIPPowerProtocolError`. This class performs no internal retry:
    the collector owns the one reconnect-and-retry policy. ``close`` is
    idempotent, and the instance can reconnect after close. Calls are blocking,
    one instance supports one device, and concurrent use is unsupported.

    Args:
        settings: Validated controller host, UDP port, and timeout.
        access_mode: READ_ONLY by default; READ_WRITE permits explicit commands.
        socket_factory: Injectable factory used by offline tests.
    """

    def __init__(
        self,
        settings: SAESSIPPowerSettings,
        *,
        access_mode: AccessModeEnum = AccessModeEnum.READ_ONLY,
        socket_factory: SocketFactory = _udp_socket,
    ) -> None:
        """Store settings and factory without opening a socket."""

        super().__init__(access_mode)
        self.settings = settings
        self._socket_factory = socket_factory
        self._socket: DatagramSocket | None = None

    @property
    def is_connected(self) -> bool:
        """Report whether this instance currently owns a UDP socket."""

        return self._socket is not None

    def connect(self) -> None:
        """Create the socket and select the configured controller as its peer."""

        if self._socket is not None:
            return
        udp_socket = self._socket_factory()
        try:
            udp_socket.settimeout(self.settings.timeout_s)
            if self.settings.address_mode is UDPAddressModeEnum.BROADCAST:
                udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_socket.connect((self.settings.host, self.settings.port))
        except OSError as error:
            udp_socket.close()
            raise SAESSIPPowerCommunicationError(
                f"could not prepare UDP endpoint {self.settings.host}:"
                f"{self.settings.port}: {error}"
            ) from error
        self._socket = udp_socket

    def reconnect(self) -> None:
        """Replace any existing socket with a fresh endpoint."""

        self.close()
        self.connect()

    def read_sample(self) -> SourceSample:
        """Request and decode one current snapshot from the controller."""

        if self.settings.address_mode is UDPAddressModeEnum.BROADCAST:
            raise ValueError("Read All is not supported for a broadcast destination")
        udp_socket = self._socket
        if udp_socket is None:
            raise SAESSIPPowerCommunicationError("client is not connected")
        try:
            sent = udp_socket.send(READ_ALL_REQUEST)
            if sent != len(READ_ALL_REQUEST):
                raise SAESSIPPowerCommunicationError(
                    f"incomplete UDP request: sent {sent} of {len(READ_ALL_REQUEST)} bytes"
                )
            response = udp_socket.recv(4096)
        except SAESSIPPowerCommunicationError:
            raise
        except OSError as error:
            raise SAESSIPPowerCommunicationError(
                f"Read All failed for {self.settings.host}:{self.settings.port}: {error}"
            ) from error
        return parse_read_all_response(response)

    def read_all(self) -> SourceSample:
        """Issue Read All using the manual's name; read_sample remains compatible."""

        return self.read_sample()

    def start(self) -> None:
        """Send Start once to enable HV output, without waiting for an ACK.

        Read back status with ``read_sample`` to check the result. If the
        controller's keepalive watchdog is enabled, continue polling through
        this client more frequently than ``keepalive_interval_ms``. Otherwise
        the controller stops output and raises its communication alarm.
        """

        self._send_control(START_REQUEST)

    def stop(self) -> None:
        """Send Stop once to disable HV output; read status to check the result.

        The controller remains powered and reachable. Closing this client
        alone does not send Stop. Neither command has a UDP acknowledgment.
        """

        self._send_control(STOP_REQUEST)

    def reset(self) -> None:
        """Send Reset once for the manual's repeated-arcing/overcurrent stop state.

        This is an explicit output-affecting command, not a connection reset or
        factory reset. There is no UDP ACK; inspect a subsequent Read All.
        """

        self._send_control(RESET_REQUEST)

    def clear_alarm(self) -> None:
        """Send Clear Alarm once to reset alarm latches; never invoked implicitly."""

        self._send_control(CLEAR_ALARM_REQUEST)

    def set_working_parameters(self, parameters: WorkingParameters) -> None:
        """Send the complete parameter block once, without a read or automatic retry."""

        self._require_write()
        if not isinstance(parameters, WorkingParameters):
            raise TypeError("parameters must be WorkingParameters")
        self._send_control(
            bytes((1, CommandEnum.SET_WORKING_PARAMETERS)) + parameters.to_payload()
        )

    def set_ip_address(self, ip_address: str, ip_netmask: str) -> None:
        """Send IP address and netmask once; keep the current endpoint unchanged.

        Subsequent requests still target the old address. The caller must create
        a client for the new address after independently verifying the change.
        """

        self._require_write()
        self._send_control(
            bytes((1, CommandEnum.SET_IP_ADDRESS)) + _ip_payload(ip_address, ip_netmask)
        )

    def _send_control(self, request: bytes) -> None:
        """Send one control datagram without receiving or automatically retrying."""

        self._require_write()
        udp_socket = self._socket
        if udp_socket is None:
            raise SAESSIPPowerCommunicationError("client is not connected")
        try:
            sent = udp_socket.send(request)
        except OSError as error:
            raise SAESSIPPowerCommunicationError(
                f"control send failed for {self.settings.host}:"
                f"{self.settings.port}: {error}"
            ) from error
        if sent != len(request):
            raise SAESSIPPowerCommunicationError(
                f"incomplete UDP request: sent {sent} of {len(request)} bytes"
            )

    def close(self) -> None:
        """Release the owned socket idempotently without changing HV output."""

        udp_socket, self._socket = self._socket, None
        if udp_socket is not None:
            udp_socket.close()


class ModbusFunctionEnum(IntEnum):
    """List the only Modbus functions implemented by SIP POWER."""

    READ_HOLDING_REGISTERS = 0x03
    WRITE_MULTIPLE_REGISTERS = 0x10


class EnableCommandEnum(IntEnum):
    """Select the manual's ENABLE command register value."""

    STOP = 0
    START = 1
    RESTART = 2


class ModbusRegisterEnum(IntEnum):
    """Name every register in Rev. 4, sections 9.1.2 and 9.1.3.

    Addresses are zero-based wire addresses. CRITICAL_STEP2 corrects the
    duplicated CRITICAL_STEP1 label at 0x7001 in the manual.
    """

    CARD_TYPE = 0x1000
    HW_CODE = 0x1001
    SW_VERSION = 0x1002
    SERIAL_NUMBER = 0x1003
    LIFE_TIME = 0x2000
    TEMPERATURE = 0x3000
    ARCING_NUMBER = 0x3001
    STATUS = 0x3002
    SW_STATUS = 0x3003
    UPTIME = 0x3004
    VIN = 0x3006
    VOUT = 0x3007
    IOUT = 0x3008
    VOUT_SETPOINT = 0x4000
    VOUT_RAMP_INTV = 0x4001
    SW_MODE = 0x4003
    SW1_THR = 0x4004
    SW2_THR_MIN = 0x4006
    SW2_THR_MAX = 0x4008
    SW3_THR_MIN = 0x400A
    SW3_THR_MAX = 0x400C
    CONV_RATE = 0x400E
    IP_ADDR = 0x5000
    IP_NETMASK = 0x5002
    MAC_ADDR = 0x5003
    KEEPALIVE = 0x5006
    ENABLE_CMD = 0x6000
    ALARM_CLEAR = 0x6001
    CRITICAL_STEP1 = 0x7000
    CRITICAL_STEP2 = 0x7001
    MODBUS_ID = 0x8000


# Word counts and register permissions, including Ethernet-only registers.
_REGISTER_LAYOUT: dict[ModbusRegisterEnum, tuple[int, str]] = {
    ModbusRegisterEnum.CARD_TYPE: (1, "r"),
    ModbusRegisterEnum.HW_CODE: (1, "r"),
    ModbusRegisterEnum.SW_VERSION: (1, "r"),
    ModbusRegisterEnum.SERIAL_NUMBER: (2, "r"),
    ModbusRegisterEnum.LIFE_TIME: (2, "r"),
    ModbusRegisterEnum.TEMPERATURE: (1, "r"),
    ModbusRegisterEnum.ARCING_NUMBER: (1, "r"),
    ModbusRegisterEnum.STATUS: (1, "r"),
    ModbusRegisterEnum.SW_STATUS: (1, "r"),
    ModbusRegisterEnum.UPTIME: (2, "r"),
    ModbusRegisterEnum.VIN: (1, "r"),
    ModbusRegisterEnum.VOUT: (1, "r"),
    ModbusRegisterEnum.IOUT: (2, "r"),
    ModbusRegisterEnum.VOUT_SETPOINT: (1, "rw"),
    ModbusRegisterEnum.VOUT_RAMP_INTV: (2, "rw"),
    ModbusRegisterEnum.SW_MODE: (1, "rw"),
    ModbusRegisterEnum.SW1_THR: (2, "rw"),
    ModbusRegisterEnum.SW2_THR_MIN: (2, "rw"),
    ModbusRegisterEnum.SW2_THR_MAX: (2, "rw"),
    ModbusRegisterEnum.SW3_THR_MIN: (2, "rw"),
    ModbusRegisterEnum.SW3_THR_MAX: (2, "rw"),
    ModbusRegisterEnum.CONV_RATE: (1, "rw"),
    ModbusRegisterEnum.IP_ADDR: (2, "rw"),
    ModbusRegisterEnum.IP_NETMASK: (1, "rw"),
    ModbusRegisterEnum.MAC_ADDR: (3, "r"),
    ModbusRegisterEnum.KEEPALIVE: (2, "rw"),
    ModbusRegisterEnum.ENABLE_CMD: (1, "w"),
    ModbusRegisterEnum.ALARM_CLEAR: (1, "w"),
    ModbusRegisterEnum.CRITICAL_STEP1: (1, "w"),
    ModbusRegisterEnum.CRITICAL_STEP2: (1, "w"),
    ModbusRegisterEnum.MODBUS_ID: (1, "w"),
}


def _register_span(
    start: ModbusRegisterEnum, count: int, permission: str
) -> list[ModbusRegisterEnum]:
    """Reject holes, disallowed access and partial multi-word registers locally."""

    if not isinstance(start, ModbusRegisterEnum):
        raise TypeError("start_address must be a ModbusRegisterEnum member")
    _integer("count", count, 1, 125 if permission == "r" else 123)
    address, end = int(start), int(start) + count
    registers = []
    while address < end:
        try:
            register = ModbusRegisterEnum(address)
        except ValueError as error:
            raise ValueError(f"undefined register address 0x{address:04x}") from error
        width, allowed = _REGISTER_LAYOUT[register]
        if permission not in allowed or address + width > end:
            raise ValueError(f"invalid {permission} span for {register.name}")
        registers.append(register)
        address += width
    return registers


def _validate_register_value(register: ModbusRegisterEnum, value: int) -> None:
    """Apply documented write limits, including reserved mode/command bits."""

    width, _ = _REGISTER_LAYOUT[register]
    _integer(register.name, value, 0, (1 << (16 * width)) - 1)
    if register is ModbusRegisterEnum.VOUT_SETPOINT:
        _integer(register.name, value, 1000, 6000)
    elif register is ModbusRegisterEnum.VOUT_RAMP_INTV:
        _integer(register.name, value, 1000, 60000)
    elif register is ModbusRegisterEnum.SW_MODE:
        if value >> 6 or value & 3 > 1 or (value >> 2) & 3 > 2 or (value >> 4) & 3 > 2:
            raise ValueError("invalid SW_MODE or reserved bits")
    elif register is ModbusRegisterEnum.IP_NETMASK:
        _integer(register.name, value, 0, 32)
    elif register is ModbusRegisterEnum.KEEPALIVE:
        _keepalive(value)
    elif register is ModbusRegisterEnum.ENABLE_CMD:
        EnableCommandEnum(value)
    elif register is ModbusRegisterEnum.MODBUS_ID:
        _integer(register.name, value, 1, 247)
    elif register in (
        ModbusRegisterEnum.CRITICAL_STEP1,
        ModbusRegisterEnum.CRITICAL_STEP2,
    ):
        expected = 0x5A5A if register is ModbusRegisterEnum.CRITICAL_STEP1 else 0xA5A5
        if value != expected:
            raise ValueError(f"{register.name} requires 0x{expected:04x}")


@dataclass(frozen=True)
class ModbusTCPSettings:
    """Select a Modbus TCP endpoint and the device's required unit ID."""

    host: str
    port: int = 502
    modbus_id: int = 11
    timeout_s: float = 3.0

    def __post_init__(self) -> None:
        """Validate transport limits without opening a connection."""

        _integer("port", self.port, 1, 65535)
        _integer("modbus_id", self.modbus_id, 1, 247)
        if not 0 < self.timeout_s < float("inf"):
            raise ValueError("timeout_s must be positive and finite")


@dataclass(frozen=True)
class ModbusRTUSettings:
    """Select RS485 at the manual's 38400 baud, 8N2, no-flow-control defaults.

    SIP POWER documents broadcast unit 255 (not standard Modbus unit 0).
    Broadcast instances can only write and never wait for a response.
    """

    port: str
    modbus_id: int = 11
    timeout_s: float = 3.0
    baudrate: int = 38400

    def __post_init__(self) -> None:
        """Validate the unit ID, baud rate and timeout before serial access."""

        _integer("modbus_id", self.modbus_id, 1, 255)
        if 247 < self.modbus_id < 255:
            raise ValueError("modbus_id must be 1..247 or the documented broadcast 255")
        _integer("baudrate", self.baudrate, 1, 1000000)
        if not 0 < self.timeout_s < float("inf"):
            raise ValueError("timeout_s must be positive and finite")


@dataclass(frozen=True)
class ModbusSample:
    """Hold decoded official register values and UTC completion time.

    A sample is several Modbus reads, not an atomic UDP Read All snapshot.
    Values retain the manual's units (VIN is dV, IP_NETMASK is CIDR prefix length).
    Ethernet-only registers are absent when CARD_TYPE has no Ethernet flag.
    Write-only registers, including MODBUS_ID, cannot be observed by Modbus.
    """

    observed_at: datetime
    registers: Mapping[ModbusRegisterEnum, int]


class SAESSIPPowerModbusError(SAESSIPPowerError):
    """Report an exception response returned by the Modbus device."""

    def __init__(self, function: ModbusFunctionEnum, exception_code: int) -> None:
        """Retain the function and device exception code without logging a frame."""

        self.function = function
        self.exception_code = exception_code
        super().__init__(f"{function.name}: Modbus exception 0x{exception_code:02x}")


class ModbusConnection(Protocol):
    """Describe a byte stream for injectable TCP/RTU offline tests."""

    def write(self, data: bytes) -> None:
        """Send a frame completely or raise; never resend a command."""
        ...

    def read(self, count: int) -> bytes:
        """Read up to count bytes under the current timeout."""
        ...

    def settimeout(self, seconds: float) -> None:
        """Set the remaining receive deadline."""
        ...

    def close(self) -> None:
        """Close the transport without any device command."""
        ...


class _TCPConnection:
    """Adapt a connected socket to the minimal Modbus byte-stream interface."""

    def __init__(self, settings: ModbusTCPSettings) -> None:
        """Open TCP without sending any Modbus command."""
        self.socket = socket.create_connection(
            (settings.host, settings.port), settings.timeout_s
        )

    def write(self, data: bytes) -> None:
        """Send one complete TCP ADU."""
        self.socket.sendall(data)

    def read(self, count: int) -> bytes:
        """Receive up to count bytes."""
        return self.socket.recv(count)

    def settimeout(self, seconds: float) -> None:
        """Bound the next socket operation."""
        self.socket.settimeout(seconds)

    def close(self) -> None:
        """Release TCP without a control command."""
        self.socket.close()


class _RTUConnection:
    """Adapt optional pySerial to the SIP POWER 8N2 serial interface."""

    def __init__(self, settings: ModbusRTUSettings) -> None:
        """Open serial only on explicit connect; import pySerial only for RTU."""
        try:
            import serial
        except ImportError as error:
            raise ImportError("RS485 requires py-seas-sip-power[serial]") from error
        self.serial = serial.Serial(
            port=settings.port,
            baudrate=settings.baudrate,
            bytesize=8,
            parity="N",
            stopbits=2,
            timeout=settings.timeout_s,
            write_timeout=settings.timeout_s,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def write(self, data: bytes) -> None:
        """Write once and reject a short serial write without retrying."""
        if self.serial.write(data) != len(data):
            raise OSError("incomplete Modbus RTU write")

    def read(self, count: int) -> bytes:
        """Read up to count serial bytes."""
        return self.serial.read(count)

    def settimeout(self, seconds: float) -> None:
        """Bound the next serial read."""
        self.serial.timeout = seconds

    def close(self) -> None:
        """Release serial without a control command."""
        self.serial.close()


ModbusSettings = ModbusTCPSettings | ModbusRTUSettings
ModbusConnectionFactory = Callable[[ModbusSettings], ModbusConnection]


def _modbus_connection(settings: ModbusSettings) -> ModbusConnection:
    """Open the transport selected by the typed settings object."""
    return (
        _TCPConnection(settings)
        if isinstance(settings, ModbusTCPSettings)
        else _RTUConnection(settings)
    )


def _modbus_crc(data: bytes) -> bytes:
    """Compute CRC-16/Modbus and return the low-byte-first wire representation."""
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class SAESSIPPowerModbusClient(_AccessControlledClient):
    """Access all official SIP POWER registers over Modbus TCP or RTU.

    Only functions 0x03 and 0x10 are used, even for single-register writes.
    Register words are big-endian; multi-word values are low-word first.
    Calls are synchronous and must not overlap. No write is retried. Malformed
    or incomplete responses close the transport to avoid reusing a stale frame;
    reconnect remains an explicit caller action and never sends device commands.
    """

    def __init__(
        self,
        settings: ModbusSettings,
        *,
        access_mode: AccessModeEnum = AccessModeEnum.READ_ONLY,
        connection_factory: ModbusConnectionFactory = _modbus_connection,
    ) -> None:
        """Store transport and immutable public access mode without connecting."""
        super().__init__(access_mode)
        if not isinstance(settings, (ModbusTCPSettings, ModbusRTUSettings)):
            raise TypeError("settings must be ModbusTCPSettings or ModbusRTUSettings")
        self.settings = settings
        self._connection_factory = connection_factory
        self._connection: ModbusConnection | None = None
        self._transaction_id = 0
        self._last_frame_end = 0.0

    @property
    def is_connected(self) -> bool:
        """Report whether the client currently owns a transport."""
        return self._connection is not None

    def connect(self) -> None:
        """Open TCP or serial without sending any device command."""
        if self._connection is None:
            try:
                self._connection = self._connection_factory(self.settings)
            except OSError as error:
                raise SAESSIPPowerCommunicationError(
                    "could not open Modbus transport"
                ) from error

    def close(self) -> None:
        """Release the transport idempotently without Stop, Reset or alarm clearing."""
        connection, self._connection = self._connection, None
        if connection is not None:
            connection.close()

    def reconnect(self) -> None:
        """Replace the transport without changing the device or access mode."""
        self.close()
        self.connect()

    def _read_exact(self, count: int, deadline: float) -> bytes:
        """Handle fragmented responses under a single overall receive deadline."""
        connection = self._connection
        if connection is None:
            raise SAESSIPPowerCommunicationError("client is not connected")
        result = bytearray()
        while len(result) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SAESSIPPowerCommunicationError("Modbus response timed out")
            connection.settimeout(remaining)
            part = connection.read(count - len(result))
            if not part:
                raise SAESSIPPowerCommunicationError("incomplete Modbus response")
            result.extend(part)
        return bytes(result)

    def _exchange(self, function: ModbusFunctionEnum, payload: bytes) -> bytes:
        """Apply access checks at the common transport boundary before any I/O."""
        if not isinstance(function, ModbusFunctionEnum):
            raise TypeError("function must be a ModbusFunctionEnum member")
        if function is ModbusFunctionEnum.WRITE_MULTIPLE_REGISTERS:
            self._require_write()
        broadcast = (
            isinstance(self.settings, ModbusRTUSettings)
            and self.settings.modbus_id == 255
        )
        if broadcast and function is ModbusFunctionEnum.READ_HOLDING_REGISTERS:
            raise ValueError("Modbus broadcast reads are not supported")
        connection = self._connection
        if connection is None:
            raise SAESSIPPowerCommunicationError("client is not connected")
        # The device requires at least 4 ms between frames (Rev. 4, p. 30).
        time.sleep(max(0.0, 0.004 - (time.monotonic() - self._last_frame_end)))
        pdu = bytes((function,)) + payload
        try:
            connection.settimeout(self.settings.timeout_s)
            if isinstance(self.settings, ModbusTCPSettings):
                self._transaction_id = (self._transaction_id + 1) & 0xFFFF
                frame = (
                    struct.pack(
                        ">HHHB",
                        self._transaction_id,
                        0,
                        len(pdu) + 1,
                        self.settings.modbus_id,
                    )
                    + pdu
                )
                connection.write(frame)
                deadline = time.monotonic() + self.settings.timeout_s
                header = self._read_exact(7, deadline)
                transaction, protocol, length, unit = struct.unpack(">HHHB", header)
                if (
                    transaction != self._transaction_id
                    or protocol != 0
                    or unit != self.settings.modbus_id
                    or not 2 <= length <= 254
                ):
                    raise SAESSIPPowerProtocolError("invalid Modbus TCP header")
                response = self._read_exact(length - 1, deadline)
            else:
                frame = bytes((self.settings.modbus_id,)) + pdu
                frame += _modbus_crc(frame)
                connection.write(frame)
                if broadcast:
                    # Account for queued 8N2 serial bytes before starting the gap timer.
                    time.sleep(len(frame) * 11 / self.settings.baudrate)
                    return b""
                deadline = time.monotonic() + self.settings.timeout_s
                header = self._read_exact(2, deadline)
                if header[0] != self.settings.modbus_id:
                    raise SAESSIPPowerProtocolError("unexpected Modbus RTU unit ID")
                if header[1] == function | 0x80:
                    frame = header + self._read_exact(3, deadline)
                elif header[1] != function:
                    raise SAESSIPPowerProtocolError("unexpected Modbus RTU function")
                elif function is ModbusFunctionEnum.READ_HOLDING_REGISTERS:
                    size = self._read_exact(1, deadline)
                    if size[0] > 250 or size[0] % 2:
                        raise SAESSIPPowerProtocolError("invalid Modbus RTU byte count")
                    frame = header + size + self._read_exact(size[0] + 2, deadline)
                else:
                    frame = header + self._read_exact(6, deadline)
                if _modbus_crc(frame[:-2]) != frame[-2:]:
                    raise SAESSIPPowerProtocolError("invalid Modbus RTU CRC")
                response = frame[1:-2]
            if response[0] == function | 0x80:
                if len(response) != 2:
                    raise SAESSIPPowerProtocolError("invalid Modbus exception length")
                raise SAESSIPPowerModbusError(function, response[1])
            if response[0] != function:
                raise SAESSIPPowerProtocolError("unexpected Modbus response function")
            if function is ModbusFunctionEnum.READ_HOLDING_REGISTERS:
                expected_bytes = struct.unpack(">H", payload[2:4])[0] * 2
                if len(response) != expected_bytes + 2 or response[1] != expected_bytes:
                    raise SAESSIPPowerProtocolError(
                        "invalid Modbus read response length"
                    )
            elif response[1:] != payload[:4]:
                raise SAESSIPPowerProtocolError(
                    "Modbus write echo does not match request"
                )
            return response[1:]
        except OSError as error:
            self.close()
            raise SAESSIPPowerCommunicationError(
                "Modbus transport operation failed"
            ) from error
        except (SAESSIPPowerCommunicationError, SAESSIPPowerProtocolError):
            self.close()
            raise
        finally:
            self._last_frame_end = time.monotonic()

    def read_holding_registers(
        self, start_address: ModbusRegisterEnum, count: int
    ) -> tuple[int, ...]:
        """Read a complete contiguous register span using function 0x03."""
        _register_span(start_address, count, "r")
        response = self._exchange(
            ModbusFunctionEnum.READ_HOLDING_REGISTERS,
            struct.pack(">HH", start_address, count),
        )
        return struct.unpack(f">{count}H", response[1:])

    def write_multiple_registers(
        self, start_address: ModbusRegisterEnum, values: Sequence[int]
    ) -> None:
        """Write validated 16-bit words once using function 0x10, even for one word.

        Multi-word values must be supplied low-word first. Device exceptions and
        transport failures propagate; ambiguous writes are never retried.
        """
        self._require_write()
        words = tuple(values)
        registers = _register_span(start_address, len(words), "w")
        for value in words:
            _integer("register word", value, 0, 65535)
        offset = 0
        for register in registers:
            width = _REGISTER_LAYOUT[register][0]
            value = sum(words[offset + index] << (16 * index) for index in range(width))
            _validate_register_value(register, value)
            offset += width
        self._exchange(
            ModbusFunctionEnum.WRITE_MULTIPLE_REGISTERS,
            struct.pack(">HHB", start_address, len(words), len(words) * 2)
            + struct.pack(f">{len(words)}H", *words),
        )

    def read_register(self, register: ModbusRegisterEnum) -> int:
        """Read and combine all words of one named register, low-word first."""
        if not isinstance(register, ModbusRegisterEnum):
            raise TypeError("register must be a ModbusRegisterEnum member")
        words = self.read_holding_registers(register, _REGISTER_LAYOUT[register][0])
        return sum(value << (16 * index) for index, value in enumerate(words))

    def write_register(self, register: ModbusRegisterEnum, value: int) -> None:
        """Validate and encode one named register, then use Write Multiple Registers."""
        self._require_write()
        if not isinstance(register, ModbusRegisterEnum):
            raise TypeError("register must be a ModbusRegisterEnum member")
        _validate_register_value(register, value)
        width = _REGISTER_LAYOUT[register][0]
        self.write_multiple_registers(
            register, tuple((value >> (16 * i)) & 65535 for i in range(width))
        )

    def read_sample(self) -> ModbusSample:
        """Read all readable register groups; omit unsupported Ethernet registers."""
        values: dict[ModbusRegisterEnum, int] = {}
        groups = [
            (ModbusRegisterEnum.CARD_TYPE, 5),
            (ModbusRegisterEnum.LIFE_TIME, 2),
            (ModbusRegisterEnum.TEMPERATURE, 10),
            (ModbusRegisterEnum.VOUT_SETPOINT, 15),
        ]
        for start, count in groups:
            words = self.read_holding_registers(start, count)
            for register in _register_span(start, count, "r"):
                offset = int(register) - int(start)
                width = _REGISTER_LAYOUT[register][0]
                values[register] = sum(
                    words[offset + i] << (16 * i) for i in range(width)
                )
        if values[ModbusRegisterEnum.CARD_TYPE] & 2:
            words = self.read_holding_registers(ModbusRegisterEnum.IP_ADDR, 8)
            for register in _register_span(ModbusRegisterEnum.IP_ADDR, 8, "r"):
                offset = int(register) - int(ModbusRegisterEnum.IP_ADDR)
                width = _REGISTER_LAYOUT[register][0]
                values[register] = sum(
                    words[offset + i] << (16 * i) for i in range(width)
                )
        return ModbusSample(datetime.now(UTC), MappingProxyType(values))

    def enable(self, command: EnableCommandEnum) -> None:
        """Write the manual's ENABLE_CMD using an explicit enum value."""
        self._require_write()
        if not isinstance(command, EnableCommandEnum):
            raise TypeError("command must be an EnableCommandEnum member")
        self.write_register(ModbusRegisterEnum.ENABLE_CMD, command)

    def start(self) -> None:
        """Write ENABLE_START once; keepalive polling remains the caller's job."""
        self.enable(EnableCommandEnum.START)

    def stop(self) -> None:
        """Write ENABLE_STOP once without closing the connection."""
        self.enable(EnableCommandEnum.STOP)

    def restart(self) -> None:
        """Write ENABLE_RESTART for the NEED_RESTART state, without implicit Stop."""
        self.enable(EnableCommandEnum.RESTART)

    def clear_alarm(self) -> None:
        """Write ALARM_CLEAR once; the manual requires no particular value."""
        self.write_register(ModbusRegisterEnum.ALARM_CLEAR, 0)

    def critical_step1(self) -> None:
        """Explicitly write 0x5a5a to the first Modbus-ID change prerequisite."""
        self.write_register(ModbusRegisterEnum.CRITICAL_STEP1, 0x5A5A)

    def critical_step2(self) -> None:
        """Explicitly write 0xa5a5 to the second Modbus-ID change prerequisite."""
        self.write_register(ModbusRegisterEnum.CRITICAL_STEP2, 0xA5A5)

    def set_modbus_id(self, modbus_id: int) -> None:
        """Write MODBUS_ID only; the caller must explicitly perform critical steps.

        The client keeps its original unit ID. Create a client for the new ID
        after the change; no automatic retargeting or retry is performed.
        """
        self.write_register(ModbusRegisterEnum.MODBUS_ID, modbus_id)

    def set_ip_address(self, ip_address: str, ip_netmask: str) -> None:
        """Write IP_ADDR and CIDR IP_NETMASK; leave the current endpoint unchanged."""
        self._require_write()
        payload = _ip_payload(ip_address, ip_netmask)
        address = int.from_bytes(payload[:4], "big")
        prefix = IPv4Network(f"0.0.0.0/{ip_netmask}").prefixlen
        self.write_multiple_registers(
            ModbusRegisterEnum.IP_ADDR, (address & 65535, address >> 16, prefix)
        )

    def set_switch_modes(
        self,
        switch_1: SwitchModeEnum,
        switch_2: SwitchModeEnum,
        switch_3: SwitchModeEnum,
    ) -> None:
        """Write SW_MODE with typed selectors; change no thresholds or other settings."""
        self._require_write()
        for mode in (switch_1, switch_2, switch_3):
            if not isinstance(mode, SwitchModeEnum):
                raise TypeError("switch modes must be SwitchModeEnum members")
        self.write_register(
            ModbusRegisterEnum.SW_MODE,
            int(switch_1) | (switch_2 << 2) | (switch_3 << 4),
        )


@dataclass(frozen=True)
class DeviceStatus:
    """Represent one device snapshot with identical field names/units on all transports.

    Unobservable fields are None; no configured or cached value pretends to be
    a measurement. Modbus snapshots span multiple requests (is_single_response=False).
    """

    observed_at: datetime
    serial_number: int
    has_ethernet: bool
    has_display: bool
    hardware_revision: str
    software_version: str
    output_current_na: int
    output_voltage_v: int
    input_voltage_v: float
    internal_temperature_k: int
    arcing_events: int
    total_working_time_h: int
    uptime_s: int
    enabled: bool
    need_restart: bool
    output_current_gradient: str
    global_alarm: bool
    safe_alarm: bool
    interlock_alarm: bool
    over_temperature_alarm: bool
    input_voltage_alarm: bool
    output_over_voltage_alarm: bool
    output_over_current_alarm: bool
    arcing_alarm: bool
    communication_alarm: bool
    switch_1_on: bool
    switch_2_on: bool
    switch_3_on: bool
    output_voltage_setpoint_v: int
    output_voltage_ramp_interval_ms: int
    switch_1_mode: str
    switch_2_mode: str
    switch_3_mode: str
    switch_1_threshold_na: int
    switch_2_min_threshold_na: int
    switch_2_max_threshold_na: int
    switch_3_min_threshold_na: int
    switch_3_max_threshold_na: int
    keepalive_interval_ms: int | None
    conversion_rate_a_per_torr: int
    modbus_id: int | None
    ip_address: str | None
    ip_netmask: str | None
    mac_address: str | None
    output_power_w: float
    pressure_torr: float | None

    is_single_response: bool = True

    @property
    def device_id(self) -> str:
        """Return the controller serial number as its stable record identity."""

        return str(self.serial_number)


@dataclass(frozen=True)
class ConnectionSettings:
    """Select a connection without exposing framing or register details.

    address is an IP/hostname for Ethernet or a serial port for RTU. port defaults
    to 2527 for UDP and 502 for TCP; RTU uses baudrate and fixed 8N2. modbus_id is
    the unicast unit selection; RTU broadcast internally uses SAES unit 255.
    """

    address: str
    connection_type: ConnectionTypeEnum = ConnectionTypeEnum.UDP
    port: int | None = None
    timeout_s: float = 3.0
    modbus_id: int = 11
    baudrate: int = 38400
    address_mode: AddressModeEnum = AddressModeEnum.UNICAST

    def __post_init__(self) -> None:
        """Validate selection and defaults before any device I/O."""
        if not isinstance(self.connection_type, ConnectionTypeEnum):
            raise TypeError("connection_type must be a ConnectionTypeEnum member")
        if not isinstance(self.address_mode, AddressModeEnum):
            raise TypeError("address_mode must be an AddressModeEnum member")
        if not isinstance(self.address, str) or not self.address.strip():
            raise ValueError("address must be a nonempty hostname/IP or serial port")
        _integer("modbus_id", self.modbus_id, 1, 247)
        _integer("baudrate", self.baudrate, 1, 1000000)
        if not 0 < self.timeout_s < float("inf"):
            raise ValueError("timeout_s must be positive and finite")
        if self.connection_type is ConnectionTypeEnum.MODBUS_RTU:
            if self.port is not None:
                raise ValueError(
                    "RTU uses address as the serial port, not a TCP/UDP port"
                )
        else:
            if self.port is None:
                object.__setattr__(
                    self,
                    "port",
                    2527 if self.connection_type is ConnectionTypeEnum.UDP else 502,
                )
            _integer("port", self.port, 1, 65535)
        if (
            self.connection_type is ConnectionTypeEnum.MODBUS_TCP
            and self.address_mode is AddressModeEnum.BROADCAST
        ):
            raise SAESSIPPowerUnsupportedOperationError(
                "Modbus TCP has no broadcast mode"
            )

    def with_ip_address(self, ip_address: str) -> ConnectionSettings:
        """Prepare an explicit reconnection target; RTU retains its serial port.

        This only returns settings. It performs no I/O and never retargets an
        existing device instance. Use after explicitly changing the device IP.
        """
        address = str(IPv4Address(ip_address))
        if self.connection_type is ConnectionTypeEnum.MODBUS_RTU:
            return self
        return replace(self, address=address)

    def with_modbus_id(self, modbus_id: int) -> ConnectionSettings:
        """Prepare the unit selection after an explicit ID change, without I/O."""
        return replace(self, modbus_id=modbus_id)

    def for_broadcast(self, *, udp_address: str | None = None) -> ConnectionSettings:
        """Prepare broadcast settings; RTU retains its bus and uses unit 255.

        UDP requires an explicit broadcast destination. TCP rejects broadcast.
        No discovery, connection or device operation is performed here.
        """
        address = self.address
        if self.connection_type is ConnectionTypeEnum.UDP:
            if not udp_address:
                raise ValueError("UDP broadcast requires udp_address")
            address = udp_address
        return replace(self, address=address, address_mode=AddressModeEnum.BROADCAST)


def _normalized_modbus_status(sample: ModbusSample) -> DeviceStatus:
    """Convert Modbus register units/flags to the common observed-state schema."""
    r = ModbusRegisterEnum
    values = sample.registers
    flags = values[r.STATUS]
    modes = values[r.SW_MODE]
    ethernet = bool(values[r.CARD_TYPE] & 2)
    current = values[r.IOUT]
    voltage = values[r.VOUT]
    conversion = values[r.CONV_RATE]
    return DeviceStatus(
        observed_at=sample.observed_at,
        serial_number=values[r.SERIAL_NUMBER],
        has_ethernet=ethernet,
        has_display=bool(values[r.CARD_TYPE] & 1),
        hardware_revision=_revision(values[r.HW_CODE]),
        software_version=_revision(values[r.SW_VERSION]),
        output_current_na=current,
        output_voltage_v=voltage,
        input_voltage_v=values[r.VIN] / 10.0,
        internal_temperature_k=values[r.TEMPERATURE],
        arcing_events=values[r.ARCING_NUMBER],
        total_working_time_h=values[r.LIFE_TIME],
        uptime_s=values[r.UPTIME],
        enabled=bool(flags & 1),
        need_restart=bool(flags & 2),
        output_current_gradient={0: "HOLD", 1: "UP", 2: "DOWN"}.get(
            (flags >> 2) & 3, "RESERVED"
        ),
        global_alarm=bool(flags & (1 << 4)),
        safe_alarm=bool(flags & (1 << 5)),
        interlock_alarm=bool(flags & (1 << 6)),
        over_temperature_alarm=bool(flags & (1 << 7)),
        input_voltage_alarm=bool(flags & (1 << 8)),
        output_over_voltage_alarm=bool(flags & (1 << 9)),
        output_over_current_alarm=bool(flags & (1 << 10)),
        arcing_alarm=bool(flags & (1 << 11)),
        communication_alarm=bool(flags & (1 << 12)),
        switch_1_on=bool(values[r.SW_STATUS] & 1),
        switch_2_on=bool(values[r.SW_STATUS] & 2),
        switch_3_on=bool(values[r.SW_STATUS] & 4),
        output_voltage_setpoint_v=values[r.VOUT_SETPOINT],
        output_voltage_ramp_interval_ms=values[r.VOUT_RAMP_INTV],
        switch_1_mode=_switch_mode(modes & 3),
        switch_2_mode=_switch_mode((modes >> 2) & 3),
        switch_3_mode=_switch_mode((modes >> 4) & 3),
        switch_1_threshold_na=values[r.SW1_THR],
        switch_2_min_threshold_na=values[r.SW2_THR_MIN],
        switch_2_max_threshold_na=values[r.SW2_THR_MAX],
        switch_3_min_threshold_na=values[r.SW3_THR_MIN],
        switch_3_max_threshold_na=values[r.SW3_THR_MAX],
        keepalive_interval_ms=values[r.KEEPALIVE] if ethernet else None,
        conversion_rate_a_per_torr=conversion,
        modbus_id=None,  # Write-only: the configured unit is not an observation.
        ip_address=str(IPv4Address(values[r.IP_ADDR])) if ethernet else None,
        ip_netmask=str(IPv4Network(f"0.0.0.0/{values[r.IP_NETMASK]}").netmask)
        if ethernet
        else None,
        mac_address=":".join(
            f"{byte:02X}" for byte in values[r.MAC_ADDR].to_bytes(6, "big")
        )
        if ethernet
        else None,
        output_power_w=current * 1e-9 * voltage,
        pressure_torr=current * 1e-9 / conversion if conversion else None,
        is_single_response=False,
    )


_PARAMETER_REGISTERS = {
    "output_voltage_setpoint_v": ModbusRegisterEnum.VOUT_SETPOINT,
    "output_voltage_ramp_interval_ms": ModbusRegisterEnum.VOUT_RAMP_INTV,
    "switch_1_threshold_na": ModbusRegisterEnum.SW1_THR,
    "switch_2_min_threshold_na": ModbusRegisterEnum.SW2_THR_MIN,
    "switch_2_max_threshold_na": ModbusRegisterEnum.SW2_THR_MAX,
    "switch_3_min_threshold_na": ModbusRegisterEnum.SW3_THR_MIN,
    "switch_3_max_threshold_na": ModbusRegisterEnum.SW3_THR_MAX,
    "keepalive_interval_ms": ModbusRegisterEnum.KEEPALIVE,
    "conversion_rate_a_per_torr": ModbusRegisterEnum.CONV_RATE,
}


class SAESSIPPower(_AccessControlledClient):
    """Expose one device API over UDP, Modbus TCP or Modbus RTU.

    Select ConnectionSettings once. All reads return DeviceStatus with the same
    names and units; unavailable observations are None. Writes retain explicit
    device semantics while this layer handles protocol encodings and required
    configuration sequences. No retries, heartbeat, automatic readback or Stop
    on close are added. Old transport clients remain available for compatibility.
    """

    def __init__(
        self,
        settings: ConnectionSettings,
        *,
        access_mode: AccessModeEnum = AccessModeEnum.READ_ONLY,
    ) -> None:
        """Store an immutable connection/access choice without opening a device."""
        super().__init__(access_mode)
        if not isinstance(settings, ConnectionSettings):
            raise TypeError("settings must be ConnectionSettings")
        self.__settings = settings
        self._udp: SAESSIPPowerClient | None = None
        self._modbus: SAESSIPPowerModbusClient | None = None
        if settings.connection_type is ConnectionTypeEnum.UDP:
            self._udp = SAESSIPPowerClient(
                SAESSIPPowerSettings(
                    settings.address,
                    settings.port,
                    settings.timeout_s,
                    UDPAddressModeEnum[settings.address_mode.name],
                ),
                access_mode=access_mode,
            )
            self._backend = self._udp
        else:
            transport_settings = (
                ModbusTCPSettings(
                    settings.address,
                    settings.port,
                    settings.modbus_id,
                    settings.timeout_s,
                )
                if settings.connection_type is ConnectionTypeEnum.MODBUS_TCP
                else ModbusRTUSettings(
                    settings.address,
                    255
                    if settings.address_mode is AddressModeEnum.BROADCAST
                    else settings.modbus_id,
                    settings.timeout_s,
                    settings.baudrate,
                )
            )
            self._modbus = SAESSIPPowerModbusClient(
                transport_settings, access_mode=access_mode
            )
            self._backend = self._modbus

    @property
    def settings(self) -> ConnectionSettings:
        """Return the selected connection; setters never silently retarget it."""
        return self.__settings

    @property
    def is_connected(self) -> bool:
        """Report local connection ownership without probing the device."""
        return self._backend.is_connected

    @property
    def status(self) -> DeviceStatus:
        """Acquire a fresh normalized snapshot; this property performs device I/O."""
        return self.read_sample()

    def connect(self) -> None:
        """Open the selected transport without issuing any device commands."""
        self._backend.connect()

    def close(self) -> None:
        """Close the transport without Stop or any other device command."""
        self._backend.close()

    def reconnect(self) -> None:
        """Reopen the same endpoint with the same access permission."""
        self._backend.reconnect()

    def read_sample(self) -> DeviceStatus:
        """Read device state in common units, never from a last-write cache."""
        if self.settings.address_mode is AddressModeEnum.BROADCAST:
            raise SAESSIPPowerUnsupportedOperationError(
                "broadcast connections cannot read"
            )
        if self._udp is not None:
            return DeviceStatus(**asdict(self._udp.read_sample()))
        return _normalized_modbus_status(self._modbus.read_sample())

    def read_all(self) -> DeviceStatus:
        """Read all observable device state, using the same API on every transport."""
        return self.read_sample()

    def start(self) -> None:
        """Explicitly enable HV once; use separate reads to observe the result."""
        self._require_write()
        self._backend.start()

    def stop(self) -> None:
        """Explicitly disable HV once without closing the transport."""
        self._require_write()
        self._backend.stop()

    def reset(self) -> None:
        """Issue UDP Reset or the corresponding Modbus Restart operation once."""
        self._require_write()
        if self._udp is not None:
            self._udp.reset()
        else:
            self._modbus.restart()

    def restart(self) -> None:
        """Use the Modbus manual's alias for the common Reset/Restart operation."""
        self.reset()

    def clear_alarm(self) -> None:
        """Explicitly clear alarm latches; never called as a side effect."""
        self._require_write()
        self._backend.clear_alarm()

    def enable(self, command: EnableCommandEnum) -> None:
        """Select Stop, Start or Restart with the same enum on every transport."""
        self._require_write()
        if not isinstance(command, EnableCommandEnum):
            raise TypeError("command must be an EnableCommandEnum member")
        {
            EnableCommandEnum.STOP: self.stop,
            EnableCommandEnum.START: self.start,
            EnableCommandEnum.RESTART: self.restart,
        }[command]()

    def _require_ethernet(self) -> None:
        """Reject unavailable Ethernet settings before a unicast Modbus write."""
        if (
            self._modbus is not None
            and self.settings.address_mode is AddressModeEnum.UNICAST
        ):
            if not self._modbus.read_register(ModbusRegisterEnum.CARD_TYPE) & 2:
                raise SAESSIPPowerUnsupportedOperationError(
                    "device has no Ethernet settings"
                )

    def set_ip_address(self, ip_address: str, ip_netmask: str) -> None:
        """Write dotted IPv4 address/mask using the selected protocol's encoding.

        The existing connection remains unchanged. Prepare settings with
        with_ip_address and construct a new instance for explicit readback.
        """
        self._require_write()
        _ip_payload(ip_address, ip_netmask)
        self._require_ethernet()
        self._backend.set_ip_address(ip_address, ip_netmask)

    def set_modbus_id(self, modbus_id: int) -> None:
        """Explicitly change the device ID, including required protocol steps.

        UDP updates the working-parameter block. Modbus sends critical step 1,
        critical step 2, then ID exactly once each. Any failure stops the sequence;
        no retry/rollback occurs. The current connection keeps its original ID.
        """
        self._require_write()
        _integer("modbus_id", modbus_id, 1, 247)
        if self._udp is not None:
            self.set_working_parameters(modbus_id=modbus_id)
        else:
            self._modbus.critical_step1()
            self._modbus.critical_step2()
            self._modbus.set_modbus_id(modbus_id)

    def set_switch_modes(
        self,
        switch_1: SwitchModeEnum,
        switch_2: SwitchModeEnum,
        switch_3: SwitchModeEnum,
    ) -> None:
        """Set the three comparator modes without exposing packed register bits."""
        self._require_write()
        self.set_working_parameters(
            switch_1_mode=switch_1,
            switch_2_mode=switch_2,
            switch_3_mode=switch_3,
        )

    def set_working_parameters(
        self,
        parameters: WorkingParameters | None = None,
        *,
        output_voltage_setpoint_v: int | None = None,
        output_voltage_ramp_interval_ms: int | None = None,
        switch_1_mode: SwitchModeEnum | None = None,
        switch_2_mode: SwitchModeEnum | None = None,
        switch_3_mode: SwitchModeEnum | None = None,
        switch_1_threshold_na: int | None = None,
        switch_2_min_threshold_na: int | None = None,
        switch_2_max_threshold_na: int | None = None,
        switch_3_min_threshold_na: int | None = None,
        switch_3_max_threshold_na: int | None = None,
        keepalive_interval_ms: int | None = None,
        conversion_rate_a_per_torr: int | None = None,
        modbus_id: int | None = None,
    ) -> None:
        """Write a complete block or named changes with the same units on all links.

        None leaves a field unchanged. All supplied values are validated before
        I/O. UDP partial updates first read the full block, then send it once;
        coordinate competing writers. Modbus encodes only affected registers,
        reading packed switch modes only when preserving unspecified modes.
        Multiple Modbus requests may partially succeed; no rollback/retry occurs.
        Broadcast UDP needs a complete WorkingParameters block because it cannot
        read. Broadcast Modbus mode changes must specify all three modes.
        """
        self._require_write()
        changes = {
            "output_voltage_setpoint_v": output_voltage_setpoint_v,
            "output_voltage_ramp_interval_ms": output_voltage_ramp_interval_ms,
            "switch_1_mode": switch_1_mode,
            "switch_2_mode": switch_2_mode,
            "switch_3_mode": switch_3_mode,
            "switch_1_threshold_na": switch_1_threshold_na,
            "switch_2_min_threshold_na": switch_2_min_threshold_na,
            "switch_2_max_threshold_na": switch_2_max_threshold_na,
            "switch_3_min_threshold_na": switch_3_min_threshold_na,
            "switch_3_max_threshold_na": switch_3_max_threshold_na,
            "keepalive_interval_ms": keepalive_interval_ms,
            "conversion_rate_a_per_torr": conversion_rate_a_per_torr,
            "modbus_id": modbus_id,
        }
        changes = {name: value for name, value in changes.items() if value is not None}
        if parameters is not None:
            if not isinstance(parameters, WorkingParameters):
                raise TypeError("parameters must be WorkingParameters")
            if changes:
                raise ValueError(
                    "use a complete parameter object or named changes, not both"
                )
            changes = asdict(parameters)
        if not changes:
            raise ValueError("provide at least one working parameter")
        # A valid validation-only baseline; these values are never sent or cached.
        baseline = WorkingParameters(
            1000,
            1000,
            SwitchModeEnum.OFF,
            SwitchModeEnum.OFF,
            SwitchModeEnum.OFF,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            11,
        )
        replace(baseline, **changes)
        if self._udp is not None:
            if parameters is None:
                if self.settings.address_mode is AddressModeEnum.BROADCAST:
                    raise SAESSIPPowerUnsupportedOperationError(
                        "UDP broadcast requires a complete WorkingParameters block"
                    )
                parameters = replace(
                    WorkingParameters.from_sample(self._udp.read_sample()), **changes
                )
            self._udp.set_working_parameters(parameters)
            return
        self._write_modbus_parameters(changes)

    def _write_modbus_parameters(
        self, changes: dict[str, int | SwitchModeEnum]
    ) -> None:
        """Resolve packed fields and contiguous writes before emitting parameters."""
        r = ModbusRegisterEnum
        modes = ("switch_1_mode", "switch_2_mode", "switch_3_mode")
        selected_modes = {name for name in modes if name in changes}
        if selected_modes and len(selected_modes) < 3:
            if self.settings.address_mode is AddressModeEnum.BROADCAST:
                raise SAESSIPPowerUnsupportedOperationError(
                    "broadcast switch updates require all three modes"
                )
        if "keepalive_interval_ms" in changes:
            self._require_ethernet()
        registers = {
            _PARAMETER_REGISTERS[key]: int(value)
            for key, value in changes.items()
            if key in _PARAMETER_REGISTERS
        }
        if selected_modes:
            packed = (
                self._modbus.read_register(r.SW_MODE) if len(selected_modes) < 3 else 0
            )
            for index, name in enumerate(modes):
                if name in changes:
                    packed = (packed & ~(3 << (2 * index))) | (
                        int(changes[name]) << (2 * index)
                    )
            registers[r.SW_MODE] = packed
        for register, value in registers.items():
            _validate_register_value(register, value)
        start: ModbusRegisterEnum | None = None
        words: list[int] = []
        for register, value in sorted(registers.items()):
            if start is not None and int(register) != int(start) + len(words):
                self._modbus.write_multiple_registers(start, words)
                start, words = None, []
            if start is None:
                start = register
            words.extend(
                (value >> (16 * i)) & 65535
                for i in range(_REGISTER_LAYOUT[register][0])
            )
        if start is not None:
            self._modbus.write_multiple_registers(start, words)
        if "modbus_id" in changes:
            self.set_modbus_id(changes["modbus_id"])
