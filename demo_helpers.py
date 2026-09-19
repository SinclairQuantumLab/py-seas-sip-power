"""Format demo snapshots and comparisons without device I/O."""

from collections.abc import Mapping
from datetime import datetime
from enum import Enum

from seas_sip_client import DeviceStatus, SourceSample


def _value(value: object) -> str:
    """Render a table value without hiding zero or unknown measurements."""
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return "Unavailable"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def format_fields(values: Mapping[object, object]) -> str:
    """Display every supplied field, including its unit-bearing name."""
    return "\n".join(
        ["| Field | Value |", "| :--- | ---: |"]
        + [f"| {_value(key)} | {_value(value)} |" for key, value in values.items()]
    )


def format_changes(
    before: Mapping[object, object],
    after: Mapping[object, object],
    requested: Mapping[object, object] | None = None,
) -> str:
    """Compare observed snapshots and optional targets without issuing commands."""
    requested = requested or {}
    rows = [
        "| Field | Before | Requested | After | Target observed |",
        "| :--- | ---: | ---: | ---: | :--- |",
    ]
    for key in dict.fromkeys([*before, *after, *requested]):
        target = _value(requested[key]) if key in requested else "—"
        match = "—"
        if key in requested:
            match = (
                "Unavailable"
                if after.get(key) is None
                else "Yes"
                if _value(after[key]) == target
                else "No"
            )
        rows.append(
            f"| {_value(key)} | {_value(before.get(key))} | {target} | "
            f"{_value(after.get(key))} | {match} |"
        )
    return "\n".join(rows)


def format_status(sample: SourceSample | DeviceStatus) -> str:
    """Format an acquired snapshot as Markdown without reading or controlling HV."""

    alarms = {
        "Global": sample.global_alarm,
        "Safe": sample.safe_alarm,
        "Interlock": sample.interlock_alarm,
        "Over temperature": sample.over_temperature_alarm,
        "Input voltage": sample.input_voltage_alarm,
        "Output over voltage": sample.output_over_voltage_alarm,
        "Output over current": sample.output_over_current_alarm,
        "Arcing": sample.arcing_alarm,
        "Communication": sample.communication_alarm,
    }
    active_alarms = ", ".join(name for name, active in alarms.items() if active)
    pressure = (
        f"{sample.pressure_torr:.3e} Torr"
        if sample.pressure_torr is not None
        else "Unavailable (conversion rate is zero)"
    )
    keepalive = "Unavailable"
    if sample.keepalive_interval_ms is not None:
        keepalive = (
            f"{sample.keepalive_interval_ms / 1000:g} s"
            if sample.keepalive_interval_ms
            else "Disabled (0 ms)"
        )
    rows = [
        ("HV enabled", "**ENABLED**" if sample.enabled else "**DISABLED**"),
        ("Output voltage", f"{sample.output_voltage_v:,} V"),
        ("Voltage setpoint", f"{sample.output_voltage_setpoint_v:,} V"),
        (
            "Output current",
            f"{sample.output_current_na:,} nA "
            f"({sample.output_current_na / 1000:,.3f} µA)",
        ),
        ("Pressure", pressure),
        ("Output power", f"{sample.output_power_w:.4g} W"),
        ("Input voltage", f"{sample.input_voltage_v:.1f} V"),
        (
            "Temperature",
            f"{sample.internal_temperature_k - 273.15:.1f} °C "
            f"({sample.internal_temperature_k:,} K)",
        ),
        ("Current gradient", sample.output_current_gradient),
        ("Keepalive interval", keepalive),
        ("Restart required", "**YES**" if sample.need_restart else "No"),
        ("Uptime", f"{sample.uptime_s:,} s"),
        ("Total working time", f"{sample.total_working_time_h:,} h"),
        ("Arcing events", f"{sample.arcing_events:,}"),
    ]
    return "\n".join(
        [
            f"### SIP POWER · {sample.serial_number}",
            f"Observed **{sample.observed_at:%Y-%m-%d %H:%M:%S} UTC** · "
            f"{sample.ip_address or 'Ethernet address unavailable'}",
            "",
            f"**Reported alarms:** {active_alarms or 'None reported'}",
            "",
            "| Measurement / state | Value |",
            "| :--- | ---: |",
            *(f"| {label} | {value} |" for label, value in rows),
        ]
    )
