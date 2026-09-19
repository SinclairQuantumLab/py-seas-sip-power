# SAES SIP POWER protocol

## Status

The primary device API is now SAESSIPPower(ConnectionSettings(...)), with
ConnectionTypeEnum selecting UDP, Modbus TCP or RTU once. The transport clients
described below remain compatible low-level implementations. The common layer
returns DeviceStatus with the same fields/units on all three links. VIN becomes
V, masks become dotted strings, status/switch bits are decoded, and pressure and
power use the same conversion as UDP. Unavailable observations are None:
Modbus ID is write-only; non-Ethernet Modbus cards have no network/keepalive values.
is_single_response distinguishes a single UDP answer from multiple Modbus reads;
it does not claim physical measurement simultaneity.

Common set_working_parameters accepts named fields. Partial UDP updates read
the current complete block and send one updated block. Modbus updates affected
registers, preserves packed mode fields and groups contiguous words internally.
All supplied targets are validated and READ_WRITE checked before I/O. Full UDP
broadcast parameters and full Modbus broadcast switch modes must be supplied
because a broadcast cannot perform preservation reads. No result is cached as
an observed setting; explicit reads are still required after writes.

Common set_modbus_id performs its required protocol procedure: UDP parameter
update, or Modbus critical step 1 then step 2 then ID. This is one explicitly
requested semantic configuration action, with no other controls, retry or
rollback. A failing step aborts immediately. The raw Modbus setter below retains
its original one-register contract. Setters never retarget a connection;
ConnectionSettings.with_ip_address/with_modbus_id prepare a new explicit endpoint.

The read parser and historical device evidence remain stable. On 2026-09-18,
the user authorized full Rev. 4 UDP/Modbus support with construction-time access
permissions. The additional features are offline-tested, not hardware-qualified.
This library owns no InfluxDB schema. The consuming relay remains read-only.
See VALIDATION.md for current evidence boundaries.

## Sources and acquisition choice

- Primary source: `device-docs/saes-sip_power-user_manual-rev_4.pdf`, document
  M.HIST.0109.23 Rev. 4, dated September 15, 2022.
- Relevant manual sections: 9 (remote communication), 9.2 (Ethernet UDP), and
  9.2.3 (Read All Answer), pages 30 and 46-51.
- UDP uses synchronous snapshot polling over IPv4. Modbus TCP and RS485 RTU
  use the same register map with transport-specific framing. The controller has
  no observation timestamp, so a successful UDP parse
  is stamped with the host's aware UTC acquisition time.

## Verified UDP framing

- The controller listens on hard-coded UDP port 2527.
- Request and response payload values use network byte order (big-endian).
- A packet begins with one version byte and one command byte.
- Read All request is exactly `version=0x01, command=0x05` with no payload.
- Read All Answer is exactly 302 bytes: `version=0x01, command=0x80`, followed
  by the 300-byte payload described in the manual.
- The client uses a connected UDP socket, which restricts accepted responses to
  the configured controller endpoint.
- The client now exposes Start (`01 01`) and Stop (`01 02`), per Rev. 4
  section 9.2, page 46. Both control HV output, with no payload or ACK. Callers
  use Read All afterward to observe enabled state, voltage, and alarms.
  Commands are sent once; there is no automatic control retry or confirmation.
- The InfluxDB relay still sends only Read All. Reset, Clear Alarm, Set Working
  Parameters, and Set IP Address are explicit library APIs requiring READ_WRITE.
- Keepalive is unchanged unless explicitly written. After remote Start/Reset,
  poll through the same client
  within the configured interval or HV stops with a communication alarm
  (sections 9.2.1 and 9.2.3). Closing the socket does not issue Stop.

## Read All payload boundaries

Payload byte offsets below exclude the two-byte packet header.

| Bytes | Values |
| --- | --- |
| 0-9 | Card flags, hardware revision, software version, serial number |
| 10-19 | Output current [nA], output voltage [V], input voltage [dV], reserved |
| 20-34 | Temperature [K], arcs, hours, uptime [s], status, switch status |
| 35-99 | Reserved |
| 100-133 | Set point, ramp, switch modes/thresholds, keepalive, conversion, Modbus ID |
| 134-199 | Reserved |
| 200-213 | IPv4 address, netmask, MAC address |
| 214-299 | Reserved |

The text below the page-48 table says "Bit 48:55 - Card type," but the table
and every subsequent field boundary place Card Type at payload bits 0:15. The
parser follows the table; treating 48:55 as Card Type would overlap the serial
number and make the remainder inconsistent.

The manual states that the conversion rate in A/Torr is useful for calculating
pressure from output current. The normalized optional pressure is therefore
`output_current_na * 1e-9 / conversion_rate_a_per_torr` when the reported rate
is nonzero. A zero conversion rate yields `pressure_torr=None`; the application
keeps that normalized value in its local record dictionary, and the pinned
InfluxDB client omits it when serializing line protocol.

## Current live evidence

On 2026-08-28 (America/Chicago), the configured controller at
`192.168.50.34:2527` answered both the initial transport probe and the completed
app's read-only dry-run. Both responses had the documented 302-byte framing.
The app parsed serial 25040035, hardware 2.2, software 2.0, reported IP
192.168.50.34, and input 24.0 V. Only normalized values were printed; no raw
frame was logged or committed, no control command was sent, and no InfluxDB
write occurred.

## Full command and access contract

AccessModeEnum.READ_ONLY is the default for both clients. READ_WRITE is required
for all six UDP writing commands, every Modbus write helper, direct register
writes and broadcast writes. A shared guard rejects writes before device I/O;
reconnect preserves mode and there is no public setter. Inputs must be enum
members. This protects against accidental API use, not hostile Python code or
another program's network access. Read requests may refresh the device watchdog.

| UDP command | Request | Payload |
| --- | --- | --- |
| Start | 01 01 | none |
| Stop | 01 02 | none |
| Reset | 01 03 | none |
| Clear Alarm | 01 04 | none |
| Read All | 01 05 | none; response 01 80 + 300 bytes |
| Set Working Parameters | 01 40 | 34 bytes |
| Set IP Address | 01 41 | IPv4 address + netmask, 4 bytes each |

Read All Answer is device-originated and has a parser, not a send method.
Reset addresses the manual's repeated-arcing/overcurrent stop condition; it is
not a factory or network reset. Configuration setters do not implicitly issue
any other command or update the client's endpoint. UDP writes never receive ACKs.

WorkingParameters uses the payload boundaries in sections 9.2.1 and 9.2.3:
voltage u16 at 0, ramp u32 at 2, packed modes u8 at 6, five thresholds u32 at
7/11/15/19/23, keepalive u32 at 27, conversion u16 at 31, Modbus ID u8 at 33.
All fields are required; from_sample plus dataclasses.replace preserves the
caller-selected snapshot but cannot prevent another client's concurrent changes.
Voltage is 1000..6000 V; ramp is 1000..60000 ms; keepalive is 0 or 1000..2^32-1 ms;
Modbus ID is 1..247. Other unsigned widths are enforced, with zero conversion
allowed. SwitchModeEnum is mandatory: SW1 OFF/SIMPLE; SW2 and SW3 OFF/SIMPLE/WINDOW.
Reserved input modes cannot be written back. IP masks must be contiguous IPv4 masks.

UDPAddressModeEnum.BROADCAST explicitly enables SO_BROADCAST for the configured
destination. It sends each requested control/configuration datagram once; Read
All is rejected locally. There is no automatic network discovery or fan-out.

## Modbus TCP and RTU

Sources: manual sections 8.4 and 9.1, pages 29–45;
[Modbus Application Protocol V1.1b3](https://www.modbus.org/file/secure/modbusprotocolspecification.pdf),
[TCP messaging guide](https://www.modbus.org/file/secure/messagingimplementationguide.pdf),
[serial line guide](https://www.modbus.org/file/secure/modbusoverserial.pdf), and
[pySerial API](https://pyserial.readthedocs.io/en/latest/pyserial_api.html).

- Functions 0x03 Read Holding Registers and 0x10 Write Multiple Registers only.
  Single-register writes also use 0x10; unsupported function 0x06 is never used.
- Byte order is big-endian within each 16-bit word. Multi-word integers use the
  least-significant word first (manual example 0x33221100 -> 0x1100, 0x3322).
- All 31 documented register entries appear in ModbusRegisterEnum. Complete
  field boundaries, contiguous spans and R/W permissions are validated before I/O.
  Raw word writes also enforce semantic limits on settings and command values.
- TCP uses MBAP framing, protocol ID 0, unit ID 1..247, transaction matching and
  standard default port 502. RTU uses CRC-16/Modbus, low CRC byte first, defaults
  38400 baud / 8N2 / no flow control, and the documented slave ID 11.
- SAES page 29 specifies RTU broadcast ID 255, unlike standard Modbus ID 0.
  The implementation follows SAES, sends no read to 255 and awaits no write
  reply. This device-specific behavior still needs hardware qualification.
- Inter-frame spacing is at least 4 ms (manual p. 30). Fragmented reads share a
  bounded deadline. TCP headers, RTU CRC, function/length/unit and write echoes
  are checked. No automatic retry occurs. A malformed/incomplete response closes
  the stream to prevent accepting a stale reply; reconnect is explicit.
- Device exceptions preserve function and exception code in
  SAESSIPPowerModbusError. A valid exception leaves the connection open.
- read_sample returns ModbusSample: immutable decoded integer registers and
  aware UTC completion time. It performs four reads, or five with Ethernet.
  Ethernet-only registers are omitted on non-Ethernet cards. A multi-read sample
  is not atomic and cannot observe the write-only MODBUS_ID register.
- Network IP_ADDR is u32 low-word first; IP_NETMASK is a one-word CIDR prefix,
  unlike UDP's four-byte netmask. MAC_ADDR occupies three low-word-first words.
- ENABLE_CMD values are EnableCommandEnum.STOP=0, START=1, RESTART=2. The manual
  names this recovery operation Restart, while UDP uses Reset. ALARM_CLEAR takes
  any word value; the convenience method writes 0.
- Modbus ID writes require explicit CRITICAL_STEP1=0x5a5a at 0x7000 then
  CRITICAL_STEP2=0xa5a5 at 0x7001. set_modbus_id writes only 0x8000; no prerequisite
  is inserted automatically. Existing clients retain their original IP/unit ID.

Additional manual errata: SW1 mode prose incorrectly says SW2, despite the
SW1 heading and bit range; only OFF/SIMPLE are permitted. The second critical
step is mislabeled CRITICAL_STEP1 at 0x7001; the enum uses CRITICAL_STEP2 to
distinguish it. CONV_RATE is a one-word/u16 value per both maps despite the
Modbus prose saying bits 31:0. These interpretations follow the explicit maps.
