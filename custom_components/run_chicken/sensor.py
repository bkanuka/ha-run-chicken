"""
Sensor platform for run_chicken.

Battery: the door reports a raw byte proportional to the battery voltage
(volts ~= 2.07 + 0.0115 * raw on a T-50 with 2x AA; fitted to multimeter and app readings from two doors). It is
exposed as voltage (idle and under motor load) and as a percentage following an
alkaline discharge curve. The official app shows ~0.35 V more than a
multimeter and counts its percentage down per operation rather than measuring.

Schedule: newer T-50 firmware (1.2.x) echoes its location, modes and the
open/close times it computed; these are exposed as next-occurrence timestamps
and mode sensors.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfElectricPotential
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RunChickenCoordinator

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry
    from .run_chicken_ble.models import RunChickenDeviceData

#: Raw battery counts per volt (2x AA T-50, multimeter-calibrated).
#: volts ~= BATTERY_VOLT_OFFSET + BATTERY_VOLT_PER_COUNT * raw, fitted to five
#: reference points from two T50 doors (FW 1.2.56): multimeter at 3.08 V,
#: 3.23 V and 2.61 V, plus two app readings corrected by the app's ~+0.35 V
#: bias. All points lie within +/-0.03 V of the line.
BATTERY_VOLT_OFFSET = 2.07
BATTERY_VOLT_PER_COUNT = 0.0115
#: Cells in series.
BATTERY_CELLS = 2
#: State of charge vs. per-cell voltage for an alkaline AA at light load
#: (approximate discharge curve). A door whose cells were found at ~1.15 V each
#: (rested) had already stopped working, so 0 % is placed a little above that.
ALKALINE_CURVE: tuple[tuple[float, int], ...] = (
    (1.20, 0),
    (1.24, 10),
    (1.29, 20),
    (1.33, 30),
    (1.36, 40),
    (1.39, 50),
    (1.42, 60),
    (1.45, 70),
    (1.48, 80),
    (1.52, 90),
    (1.58, 100),
)

#: Known schedule mode values.
MODE_NAMES = {0: "manual", 1: "sun", 2: "manual"}
MODE_OPTIONS = ["sun", "manual", "other"]


def raw_to_volts(raw: int | None) -> float | None:
    """Convert the raw battery byte to volts."""
    return None if raw is None else round(BATTERY_VOLT_OFFSET + BATTERY_VOLT_PER_COUNT * raw, 2)


def raw_to_percent(raw: int | None) -> int | None:
    """Estimate state of charge from the raw battery byte (alkaline curve)."""
    volts = raw_to_volts(raw)
    if volts is None:
        return None
    cell = volts / BATTERY_CELLS
    if cell <= ALKALINE_CURVE[0][0]:
        return 0
    for (v_lo, p_lo), (v_hi, p_hi) in pairwise(ALKALINE_CURVE):
        if cell <= v_hi:
            return round(p_lo + (cell - v_lo) / (v_hi - v_lo) * (p_hi - p_lo))
    return 100


def mode_name(mode: int | None) -> str | None:
    """Map a raw schedule mode to an enum option."""
    if mode is None:
        return None
    return MODE_NAMES.get(mode, "other")


@dataclass(frozen=True, kw_only=True)
class RunChickenSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[RunChickenDeviceData], Any]
    #: Keep the last non-None value instead of going unknown (battery values
    #: are only present in some frames).
    keep_last: bool = False


SENSORS: tuple[RunChickenSensorDescription, ...] = (
    RunChickenSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: raw_to_percent(d.battery_raw),
        keep_last=True,
    ),
    RunChickenSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: raw_to_volts(d.battery_raw),
        keep_last=True,
    ),
    RunChickenSensorDescription(
        key="battery_voltage_under_load",
        translation_key="battery_voltage_under_load",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: raw_to_volts(d.battery_raw_under_load),
        keep_last=True,
    ),
    RunChickenSensorDescription(
        key="scheduled_open",
        translation_key="scheduled_open",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.schedule.open_time if d.schedule else None,
    ),
    RunChickenSensorDescription(
        key="scheduled_close",
        translation_key="scheduled_close",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.schedule.close_time if d.schedule else None,
    ),
    RunChickenSensorDescription(
        key="open_mode",
        translation_key="open_mode",
        device_class=SensorDeviceClass.ENUM,
        options=MODE_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: mode_name(d.schedule.open_mode) if d.schedule else None,
    ),
    RunChickenSensorDescription(
        key="close_mode",
        translation_key="close_mode",
        device_class=SensorDeviceClass.ENUM,
        options=MODE_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: mode_name(d.schedule.close_mode) if d.schedule else None,
    ),
)


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Run-Chicken sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [RunChickenSensor(coordinator, d) for d in SENSORS]
    entities.append(RunChickenBatteryRawSensor(coordinator))
    async_add_entities(entities)


def _device_info(coordinator: RunChickenCoordinator) -> DeviceInfo:
    """Device info shared with the cover, so all entities land on one device."""
    device = coordinator.device
    return DeviceInfo(
        connections={(CONNECTION_BLUETOOTH, device.address)},
        name=device.name,
        manufacturer=device.manufacturer,
        model=device.model,
    )


class RunChickenSensor(CoordinatorEntity[RunChickenCoordinator], SensorEntity):
    """A Run-Chicken sensor driven by a description's ``value_fn``."""

    _attr_has_entity_name = True
    entity_description: RunChickenSensorDescription

    def __init__(self, coordinator: RunChickenCoordinator, description: RunChickenSensorDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"run_chicken_{coordinator.device.address}_{description.key}"
        self._attr_device_info = _device_info(coordinator)
        self._value: Any = None
        self._update_value()

    def _update_value(self) -> None:
        data = self.coordinator.data
        value = self.entity_description.value_fn(data) if data is not None else None
        if value is not None or not self.entity_description.keep_last:
            self._value = value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the value and write state."""
        self._update_value()
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self._value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose configured offsets and modes on the schedule sensors."""
        data = self.coordinator.data
        if data is None or data.schedule is None:
            return None
        s = data.schedule
        key = self.entity_description.key
        if key == "scheduled_open":
            return {"offset_minutes": s.open_offset, "mode": mode_name(s.open_mode)}
        if key == "scheduled_close":
            return {"offset_minutes": s.close_offset, "mode": mode_name(s.close_mode)}
        if key == "open_mode":
            return {"raw_mode": s.open_mode}
        if key == "close_mode":
            return {"raw_mode": s.close_mode}
        return None


class RunChickenBatteryRawSensor(CoordinatorEntity[RunChickenCoordinator], SensorEntity):
    """
    Raw battery byte (payload[13]) plus undecoded payload bytes.

    Kept as a diagnostic aid for further reverse engineering.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "battery_raw"
    _attr_icon = "mdi:battery-unknown"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the raw battery sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"run_chicken_{coordinator.device.address}_battery_raw"
        self._attr_device_info = _device_info(coordinator)
        self._last_value: int | None = None
        self._last_load_value: int | None = None
        self._last_payload: bytes = b""
        self._update_from_coordinator()

    def _update_from_coordinator(self) -> None:
        data = self.coordinator.data
        if data is None:
            return
        if data.battery_raw is not None:
            self._last_value = data.battery_raw
        if data.battery_raw_under_load is not None:
            self._last_load_value = data.battery_raw_under_load
        if data.raw_payload:
            self._last_payload = data.raw_payload

    @callback
    def _handle_coordinator_update(self) -> None:
        """Store the newest reading and write state."""
        self._update_from_coordinator()
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        """Return the last raw battery byte."""
        return self._last_value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return undecoded payload bytes for reverse engineering."""
        p = self._last_payload
        attrs: dict[str, Any] = {
            "battery_raw_under_load": self._last_load_value,
            "frame_type": f"0x{p[0]:02x}" if p else None,
            "payload_hex": p.hex(),
        }
        if len(p) >= 20:  # noqa: PLR2004 - known payload length
            attrs.update(
                {
                    "latitude": struct.unpack_from("<h", p, 9)[0],
                    "longitude": struct.unpack_from("<h", p, 11)[0],
                    "byte_15": p[15],
                }
            )
        if len(p) > 56:  # noqa: PLR2004 - longer firmware payload
            attrs.update(
                {
                    "byte_41_anti_pinch": p[41],
                    "byte_42": p[42],
                    "byte_52": p[52],
                    "byte_56": f"0x{p[56]:02x}",
                }
            )
        return attrs
