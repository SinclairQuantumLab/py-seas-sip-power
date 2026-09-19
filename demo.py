# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: py-seas-sip-power (3.11.14)
#     language: python
#     name: python3
# ---

# %% [markdown] tags=["read-only"]
# # SIP POWER — one device API
#
# ## Part 1 — read-only tests
# Choose **UDP, Modbus TCP or Modbus RTU once** in Connection settings.
# All later reads, state fields, controls and setting methods are identical.
# Complete the desired read tests and close, then stop at **End of read-only tests**.
# Optional write tests are below that boundary and create a new READ_WRITE instance.
#
# Use this checkout's .venv. Edit connection values directly below; no settings file.
# Run individual cells, not Run All;
# do not execute demo.py as a script. Only the .py source is tracked. Saved outputs
# and counts are historical local runs; repeat read cells for current observations.
# Reads can refresh an existing keepalive watchdog. There is no background polling.
# After updating the library, restart an existing kernel before Display setup so
# the new API is imported. Saved outputs remain historical; a new run needs Connect.

# %% [markdown] tags=["read-only"]
# ## Display setup
# Formatting an acquired sample performs no device I/O.

# %% tags=["display-setup", "read-only"]
import time
from dataclasses import asdict

from IPython.display import Markdown, display

from demo_helpers import format_changes, format_fields, format_status
from seas_sip_client import (
    AccessModeEnum,
    ConnectionSettings,
    ConnectionTypeEnum,
    EnableCommandEnum,
    SAESSIPPower,
    SwitchModeEnum,
)

# %% [markdown] tags=["read-only"]
# ## Connection settings — select the interface here
# Set connection_type and identifier directly in this test/demo cell.
# identifier is the controller IP/hostname for UDP/TCP, or the serial device for RTU.
# RTU needs the serial extra. This cell does not open a connection.

# %% tags=["connection-settings", "read-only"]
connection_type = ConnectionTypeEnum.UDP
# UDP / MODBUS_TCP: IP or hostname, e.g. "192.168.1.20" (without :port).
# MODBUS_RTU: serial device, e.g. "COM3" on Windows or "/dev/ttyUSB0" on Linux.
identifier = "192.168.50.34"

# Network ports default to UDP 2527 / TCP 502; RTU defaults to 38400 baud, 8N2.
# For custom settings, add port=... (UDP/TCP) or baudrate=... (RTU) below.
# modbus_id selects the Modbus target; it is not an observed value or a device write.
connection = ConnectionSettings(
    identifier,
    connection_type=connection_type,
    timeout_s=3.0,
    modbus_id=11,
)
display(Markdown(format_fields(asdict(connection))))

# %% [markdown] tags=["read-only"]
# ## Connect — read only

# %% tags=["connect", "read-only"]
client = SAESSIPPower(connection, access_mode=AccessModeEnum.READ_ONLY)
client.connect()
print("Connected:", client.is_connected, "Access:", client.access_mode.name)

# %% [markdown] tags=["read-only"]
# ## Read current status
# All interfaces return DeviceStatus, in the same units and field names.

# %% tags=["sample", "read-only"]
status = client.read_sample()
# display(Markdown(format_status(status)))

# %% [markdown] tags=["read-only"]
# ### Every observed field
# Voltage is V, current/thresholds are nA, input voltage is V, temperatures are K,
# time fields include their units, and addresses/masks are dotted IPv4 strings.
# None means unavailable, never a fabricated zero or the last value commanded.
# For example Modbus cannot read modbus_id; the connection's selected ID is shown
# in connection settings separately. is_single_response distinguishes one UDP response
# from the multi-request Modbus snapshot. observed_at is an aware UTC host time.

# %% tags=["all-fields", "read-only"]
display(Markdown(format_fields(asdict(status))))
print("Device ID:", status.device_id)

# %% [markdown] tags=["read-only"]
# ### Read All — a fresh complete snapshot on the selected interface

# %% tags=["read-all", "read-only"]
all_status = client.read_all()
display(Markdown(format_status(all_status)))

# %% [markdown] tags=["read-only"]
# ### Status property — also performs a fresh read
# Store the result once to inspect several fields without additional I/O.

# %% tags=["status-property", "read-only"]
property_status = client.status
display(Markdown(format_status(property_status)))

# %% [markdown] tags=["read-only"]
# ### Working parameters — same names on every connection

# %% tags=["parameters", "read-only"]
parameter_names = (
    "output_voltage_setpoint_v",
    "output_voltage_ramp_interval_ms",
    "switch_1_mode",
    "switch_2_mode",
    "switch_3_mode",
    "switch_1_threshold_na",
    "switch_2_min_threshold_na",
    "switch_2_max_threshold_na",
    "switch_3_min_threshold_na",
    "switch_3_max_threshold_na",
    "keepalive_interval_ms",
    "conversion_rate_a_per_torr",
    "modbus_id",
)
display(
    Markdown(format_fields({name: getattr(status, name) for name in parameter_names}))
)

# %% [markdown] tags=["read-only"]
# ## Read 10 samples
# Only reads are sent. Repeat this cell to continue polling.

# %% tags=["read-samples", "read-only"]
poll_s = (
    min(1.0, status.keepalive_interval_ms / 2000)
    if status.keepalive_interval_ms
    else 1.0
)
for _ in range(10):
    status = client.read_sample()
    print(
        status.observed_at,
        "enabled:",
        status.enabled,
        "V:",
        status.output_voltage_v,
        "nA:",
        status.output_current_na,
        "alarm:",
        status.global_alarm,
    )
    time.sleep(poll_s)
display(Markdown(format_status(status)))

# %% [markdown] tags=["read-only"]
# ## Read back current status
# Repeat independently without sending any control command.

# %% tags=["readback", "read-only"]
time.sleep(0.1)
status = client.read_sample()
display(Markdown(format_status(status)))

# %% [markdown] tags=["read-only"]
# ### Reconnect, then read
# The endpoint and READ_ONLY permission remain unchanged.

# %% tags=["reconnect", "read-only"]
client.reconnect()
print(client.is_connected, client.access_mode.name)

# %% tags=["reconnect-read", "read-only"]
reconnected = client.read_sample()
display(Markdown(format_status(reconnected)))

# %% [markdown] tags=["read-only"]
# ### Close connection
# Closing does not send Stop or change HV.

# %% tags=["close", "read-only"]
client.close()
print("Connected:", client.is_connected)

# %% [markdown] tags=["read-only"]
# ---
# # End of read-only tests
# Read-only users can stop here. Everything below is optional write testing.
# Use only Display setup and Connection settings if starting Part 2 directly.

# %% [markdown] tags=["read-write"]
# # Part 2 — optional read/write tests
#
# The same tests below run over the connection selected above. A new instance
# explicitly uses READ_WRITE. Each operation has separate **Before → Write → After**
# cells. Repeating After only reads. Start enables real HV; Stop disables it;
# Reset/Restart can affect HV. Do not Run All. No retries, automatic restore,
# alarm clearing, interlock override or Stop on close is added.
#
# Parameter targets initially copy observed values; edit the intended target in
# Before to test a change. Same-value writes exercise transmission/readback only.
# After cells display three fresh samples and before/target/after comparisons.
# They stop polling when the cell finishes: after Start/Reset/Restart continue
# reads within the active keepalive interval, or explicitly Stop if intended.
# Observations do not prove acceptance or complete physical settling.

# %% tags=["connect", "read-write"]
client = SAESSIPPower(connection, access_mode=AccessModeEnum.READ_WRITE)
client.connect()
print("Connected:", client.is_connected, "Access:", client.access_mode.name)

# %% [markdown] tags=["read-write"]
# ## Start — enable HV

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["start-before", "read-write"]
before = client.read_all()
time.sleep(0.1)
display(Markdown(format_status(before)))

# %% [markdown] tags=["read-write"]
# ### Write — explicit control

# %% tags=["start-write", "read-write"]
client.start()

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["start-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(Markdown(format_changes(asdict(before), asdict(after), {"enabled": True})))

# %% [markdown] tags=["read-write"]
# ## Stop — disable HV

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["stop-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))

# %% [markdown] tags=["read-write"]
# ### Write — explicit control

# %% tags=["stop-write", "read-write"]
client.stop()

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["stop-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(Markdown(format_changes(asdict(before), asdict(after), {"enabled": False})))

# %% [markdown] tags=["read-write"]
# ## Reset / Restart — recovery

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["reset-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))

# %% [markdown] tags=["read-write"]
# ### Write — explicit control

# %% tags=["reset-write", "read-write"]
client.reset()

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["reset-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(Markdown(format_changes(asdict(before), asdict(after), {})))

# %% [markdown] tags=["read-write"]
# ## Restart — alias for the same recovery operation

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["restart-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))

# %% [markdown] tags=["read-write"]
# ### Write — explicit control

# %% tags=["restart-write", "read-write"]
client.restart()

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["restart-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(Markdown(format_changes(asdict(before), asdict(after), {})))

# %% [markdown] tags=["read-write"]
# ## Clear Alarm — inspect latched and active alarms

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["clear_alarm-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))

# %% [markdown] tags=["read-write"]
# ### Write — explicit control

# %% tags=["clear_alarm-write", "read-write"]
client.clear_alarm()

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["clear_alarm-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(Markdown(format_changes(asdict(before), asdict(after), {})))

# %% [markdown] tags=["read-write"]
# ## Enable command enum — STOP / START / RESTART

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["enable-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
enable_command = EnableCommandEnum.STOP

# %% [markdown] tags=["read-write"]
# ### Write — explicit control

# %% tags=["enable-write", "read-write"]
client.enable(enable_command)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["enable-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(Markdown(format_changes(asdict(before), asdict(after), {})))

# %% [markdown] tags=["read-write"]
# ## Working-parameter tests
# Use the same named arguments for every interface. The library preserves the
# other parameters, packs modes, selects registers or encodes the UDP block.
# UDP partial changes include a fresh preservation read; coordinate concurrent
# writers. Multiple requested changes may require multiple Modbus writes and can
# partially succeed. There is no rollback. Skip Ethernet-only settings when
# status.has_ethernet is false or the corresponding observation is unavailable.

# %% [markdown] tags=["read-write"]
# ## Set output_voltage_setpoint_v [V]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["output_voltage_setpoint_v-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.output_voltage_setpoint_v
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["output_voltage_setpoint_v-write", "read-write"]
client.set_working_parameters(output_voltage_setpoint_v=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["output_voltage_setpoint_v-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"output_voltage_setpoint_v": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set output_voltage_ramp_interval_ms [ms]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["output_voltage_ramp_interval_ms-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.output_voltage_ramp_interval_ms
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["output_voltage_ramp_interval_ms-write", "read-write"]
client.set_working_parameters(output_voltage_ramp_interval_ms=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["output_voltage_ramp_interval_ms-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before),
            asdict(after),
            {"output_voltage_ramp_interval_ms": target_value},
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_1_mode [OFF / SIMPLE]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_1_mode-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = SwitchModeEnum[before.switch_1_mode]
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_1_mode-write", "read-write"]
client.set_working_parameters(switch_1_mode=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_1_mode-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(asdict(before), asdict(after), {"switch_1_mode": target_value})
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_2_mode [OFF / SIMPLE / WINDOW]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_2_mode-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = SwitchModeEnum[before.switch_2_mode]
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_2_mode-write", "read-write"]
client.set_working_parameters(switch_2_mode=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_2_mode-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(asdict(before), asdict(after), {"switch_2_mode": target_value})
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_3_mode [OFF / SIMPLE / WINDOW]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_3_mode-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = SwitchModeEnum[before.switch_3_mode]
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_3_mode-write", "read-write"]
client.set_working_parameters(switch_3_mode=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_3_mode-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(asdict(before), asdict(after), {"switch_3_mode": target_value})
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_1_threshold_na [nA]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_1_threshold_na-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.switch_1_threshold_na
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_1_threshold_na-write", "read-write"]
client.set_working_parameters(switch_1_threshold_na=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_1_threshold_na-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"switch_1_threshold_na": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_2_min_threshold_na [nA]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_2_min_threshold_na-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.switch_2_min_threshold_na
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_2_min_threshold_na-write", "read-write"]
client.set_working_parameters(switch_2_min_threshold_na=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_2_min_threshold_na-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"switch_2_min_threshold_na": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_2_max_threshold_na [nA]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_2_max_threshold_na-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.switch_2_max_threshold_na
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_2_max_threshold_na-write", "read-write"]
client.set_working_parameters(switch_2_max_threshold_na=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_2_max_threshold_na-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"switch_2_max_threshold_na": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_3_min_threshold_na [nA]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_3_min_threshold_na-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.switch_3_min_threshold_na
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_3_min_threshold_na-write", "read-write"]
client.set_working_parameters(switch_3_min_threshold_na=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_3_min_threshold_na-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"switch_3_min_threshold_na": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set switch_3_max_threshold_na [nA]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch_3_max_threshold_na-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.switch_3_max_threshold_na
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["switch_3_max_threshold_na-write", "read-write"]
client.set_working_parameters(switch_3_max_threshold_na=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch_3_max_threshold_na-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"switch_3_max_threshold_na": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set keepalive_interval_ms [ms; requires Ethernet; 0 disables the watchdog]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["keepalive_interval_ms-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.keepalive_interval_ms
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["keepalive_interval_ms-write", "read-write"]
client.set_working_parameters(keepalive_interval_ms=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["keepalive_interval_ms-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"keepalive_interval_ms": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set conversion_rate_a_per_torr [A/Torr]

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["conversion_rate_a_per_torr-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_value = before.conversion_rate_a_per_torr
print("Requested:", target_value)

# %% [markdown] tags=["read-write"]
# ### Write — one explicit semantic setting change

# %% tags=["conversion_rate_a_per_torr-write", "read-write"]
client.set_working_parameters(conversion_rate_a_per_torr=target_value)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["conversion_rate_a_per_torr-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before), asdict(after), {"conversion_rate_a_per_torr": target_value}
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set several working parameters together
# Encoding, register grouping and word order are internal.

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["parameter-group-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_voltage = before.output_voltage_setpoint_v
target_ramp = before.output_voltage_ramp_interval_ms

# %% [markdown] tags=["read-write"]
# ### Write — voltage and ramp together

# %% tags=["parameter-group-write", "read-write"]
client.set_working_parameters(
    output_voltage_setpoint_v=target_voltage,
    output_voltage_ramp_interval_ms=target_ramp,
)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["parameter-group-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before),
            asdict(after),
            {
                "output_voltage_setpoint_v": target_voltage,
                "output_voltage_ramp_interval_ms": target_ramp,
            },
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set three switch modes together
# Enum values are the same on every interface; SW1 cannot use WINDOW.

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["switch-modes-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
switch_1 = SwitchModeEnum[before.switch_1_mode]
switch_2 = SwitchModeEnum[before.switch_2_mode]
switch_3 = SwitchModeEnum[before.switch_3_mode]

# %% [markdown] tags=["read-write"]
# ### Write — three comparator modes

# %% tags=["switch-modes-write", "read-write"]
client.set_switch_modes(switch_1, switch_2, switch_3)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["switch-modes-after", "read-write"]
for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before),
            asdict(after),
            {
                "switch_1_mode": switch_1,
                "switch_2_mode": switch_2,
                "switch_3_mode": switch_3,
            },
        )
    )
)

# %% [markdown] tags=["read-write"]
# ## Set Modbus ID
# Choose a desired ID, initially the configured connection ID. An unavailable
# observed ID stays None. The single method handles the required protocol steps
# internally; failure stops immediately without retry. After explicitly reconnects
# at the selected ID, compares serial number and reads state. Modbus does not make
# its write-only ID readable: reachability/identity are the available confirmation.

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["modbus-id-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_modbus_id = connection.modbus_id
print("Configured ID:", connection.modbus_id, "Observed ID:", before.modbus_id)
print("Requested ID:", target_modbus_id)

# %% [markdown] tags=["read-write"]
# ### Write — explicit ID change

# %% tags=["modbus-id-write", "read-write"]
client.set_modbus_id(target_modbus_id)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["modbus-id-after", "read-write"]
client.close()
connection = connection.with_modbus_id(target_modbus_id)
client = SAESSIPPower(connection, access_mode=AccessModeEnum.READ_WRITE)
client.connect()
print("Configured ID for readback:", connection.modbus_id)

for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(asdict(before), asdict(after), {"modbus_id": target_modbus_id})
    )
)

# %% [markdown] tags=["read-write"]
# ## Set IP address and netmask — Ethernet-equipped controllers
# Skip if network observations are unavailable. Targets initially retain the
# observed address/mask. For a real change choose a reachable unused address.
# The method always takes dotted IPv4 strings. Connection settings prepare the
# correct readback endpoint: Ethernet moves to the new IP, RTU keeps its serial
# port. The setter never silently retargets the existing instance. Compare identity
# as well as IP/mask; recovery is manual if the new address is unreachable.

# %% [markdown] tags=["read-write"]
# ### Before — fresh state, alarms and intended target

# %% tags=["ip-address-before", "read-write"]
before = client.read_all()
display(Markdown(format_status(before)))
target_ip = before.ip_address
target_netmask = before.ip_netmask
display(Markdown(format_fields({"IP": target_ip, "Netmask": target_netmask})))

# %% [markdown] tags=["read-write"]
# ### Write — network address and mask

# %% tags=["ip-address-write", "read-write"]
client.set_ip_address(target_ip, target_netmask)

# %% [markdown] tags=["read-write"]
# ### After — repeat for more observations; no command is resent

# %% tags=["ip-address-after", "read-write"]
client.close()
connection = connection.with_ip_address(target_ip)
client = SAESSIPPower(connection, access_mode=AccessModeEnum.READ_WRITE)
client.connect()

for _ in range(3):
    time.sleep(0.1)
    after = client.read_sample()
    display(Markdown(format_status(after)))
display(
    Markdown(
        format_changes(
            asdict(before),
            asdict(after),
            {"ip_address": target_ip, "ip_netmask": target_netmask},
        )
    )
)

# %% [markdown] tags=["read-write"]
# ### Close before optional broadcast testing
# Close does not disable HV.

# %% tags=["close", "read-write"]
client.close()

# %% [markdown] tags=["read-write"]
# ## Optional broadcast — one Stop, then individual readbacks
# Requires a UDP or RTU connection selection; TCP does not support broadcast.
# For UDP set broadcast_identifier below; RTU retains its bus and uses
# the manufacturer's broadcast ID internally. The observer list below contains
# unicast ConnectionSettings objects; add every intended target explicitly.
# **Every receiving controller can stop, even if omitted from the observer list.**
# There is no broadcast ACK. Observe each identified target through unicast.
# Only one observer/serial connection is open at a time on any interface.

# %% tags=["broadcast-before", "read-write"]
broadcast_identifier = "192.168.1.255"  # UDP subnet broadcast; ignored for RTU.
observer_connections = [connection]  # Add other intended unicast targets here.
broadcast_before = []
for observer_connection in observer_connections:
    observer = SAESSIPPower(observer_connection, access_mode=AccessModeEnum.READ_ONLY)
    observer.connect()
    observed = observer.read_sample()
    broadcast_before.append(observed)
    display(Markdown(format_status(observed)))
    observer.close()
broadcast_connection = connection.for_broadcast(
    udp_address=broadcast_identifier,
)
broadcaster = SAESSIPPower(broadcast_connection, access_mode=AccessModeEnum.READ_WRITE)
broadcaster.connect()

# %% [markdown] tags=["read-write"]
# ### Write — one explicit broadcast Stop

# %% tags=["broadcast-write", "read-write"]
broadcaster.stop()

# %% [markdown] tags=["read-write"]
# ### After — unicast observations, without repeating the broadcast

# %% tags=["broadcast-after", "read-write"]
broadcaster.close()
for observer_connection, previous in zip(
    observer_connections, broadcast_before, strict=True
):
    observer = SAESSIPPower(observer_connection, access_mode=AccessModeEnum.READ_ONLY)
    observer.connect()
    for _ in range(3):
        time.sleep(0.1)
        observed = observer.read_sample()
        display(Markdown(format_status(observed)))
    display(
        Markdown(format_changes(asdict(previous), asdict(observed), {"enabled": False}))
    )
    observer.close()

# %% [markdown] tags=["read-write"]
# ## End of selected tests
# Close any connection you opened. Closing never disables HV. Use the explicit
# Stop test and its readbacks if that is the intended final state. Restore settings
# only by deliberately selecting their named setting tests with recorded targets.
