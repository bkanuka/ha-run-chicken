"""Sensor platform for run_chicken."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .run_chicken_ble.models import RunChickenMotorMode, RunChickenScheduleMode

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import RunChickenConfigEntry
    from .coordinator import RunChickenCoordinator

#: The app's picker has 3 options per action, but the third is labeled
#: differently for open ("Sunrise") vs close ("Sunset") even though both
#: report the same underlying RunChickenScheduleMode.SUNRISE_SUNSET value.
_SCHEDULE_MODE_LABELS = {
    "open": {
        RunChickenScheduleMode.MANUAL: "Manual",
        RunChickenScheduleMode.SUNRISE_SUNSET: "Sunrise",
        RunChickenScheduleMode.TIMER: "Time",
        RunChickenScheduleMode.UNKNOWN: "Unknown",
    },
    "close": {
        RunChickenScheduleMode.MANUAL: "Manual",
        RunChickenScheduleMode.SUNRISE_SUNSET: "Sunset",
        RunChickenScheduleMode.TIMER: "Time",
        RunChickenScheduleMode.UNKNOWN: "Unknown",
    },
}

_MOTOR_MODE_LABELS = {
    RunChickenMotorMode.OFF: "Off",
    RunChickenMotorMode.ANTI_PINCH: "Anti-pinch",
    RunChickenMotorMode.POWER_MODE: "Power-mode",
    RunChickenMotorMode.UNKNOWN: "Unknown",
}


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: RunChickenConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Run-Chicken diagnostic/config sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RunChickenFirmwareVersionSensor(coordinator),
            RunChickenMotorModeSensor(coordinator),
            RunChickenScheduleModeSensor(coordinator, "open"),
            RunChickenScheduleModeSensor(coordinator, "close"),
            RunChickenScheduleOffsetSensor(coordinator, "open"),
            RunChickenScheduleOffsetSensor(coordinator, "close"),
            RunChickenOpenTimeSensor(coordinator),
            RunChickenCloseTimeSensor(coordinator),
            RunChickenRssiSensor(coordinator),
        ]
    )


class RunChickenSensorBase(CoordinatorEntity["RunChickenCoordinator"], SensorEntity):
    """Shared device-info wiring for Run-Chicken diagnostic sensors."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(self, coordinator: RunChickenCoordinator, key: str, name: str) -> None:
        """Initialize the sensor and its shared device info."""
        super().__init__(coordinator)
        self.run_chicken_device = coordinator.device
        self._attr_unique_id = f"run_chicken_{self.run_chicken_device.address}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self.run_chicken_device.address)},
            name=self.run_chicken_device.name,
            manufacturer=self.run_chicken_device.manufacturer,
            model=self.run_chicken_device.model,
        )


class RunChickenFirmwareVersionSensor(RunChickenSensorBase):
    """Reports the door's firmware version, e.g. "1.2.56"."""

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the firmware-version sensor."""
        super().__init__(coordinator, "firmware_version", "Firmware Version")

    @property
    def native_value(self) -> str | None:
        """Return the firmware version string."""
        return self.coordinator.data.firmware_version


class RunChickenMotorModeSensor(RunChickenSensorBase):
    """
    Reports the door's anti-pinch / power-mode selector.

    These two app toggles are mutually exclusive, so the door only ever
    reports one of: off, anti-pinch, or power-mode.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(_MOTOR_MODE_LABELS.values())

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the motor-mode sensor."""
        super().__init__(coordinator, "motor_mode", "Motor Mode")

    @property
    def native_value(self) -> str:
        """Return the current motor mode as a label."""
        return _MOTOR_MODE_LABELS[self.coordinator.data.motor_mode]


class RunChickenScheduleModeSensor(RunChickenSensorBase):
    """
    Reports whether open/close is set to Manual, Time, or Sunrise/Sunset.

    The app labels the third option "Sunrise" for open and "Sunset" for
    close, even though both report the same underlying protocol value.
    """

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: RunChickenCoordinator, action: str) -> None:
        """Initialize the schedule-mode sensor for ``action`` ("open" or "close")."""
        self._action = action
        self._labels = _SCHEDULE_MODE_LABELS[action]
        self._attr_options = list(self._labels.values())
        super().__init__(coordinator, f"{action}_schedule_mode", f"{action.title()} Schedule Mode")

    @property
    def native_value(self) -> str:
        """Return the current schedule mode as a label."""
        mode = getattr(self.coordinator.data, f"{self._action}_schedule_mode")
        return self._labels[mode]


class RunChickenScheduleOffsetSensor(RunChickenSensorBase):
    """
    Reports the Sunrise/Sunset offset in minutes for open/close.

    Only meaningful when the corresponding schedule mode is Sunrise/Sunset -
    the door reports 0 in Manual and Time modes, which would misleadingly
    read as "no offset" rather than "not applicable". Shows "-" instead
    whenever the mode isn't Sunrise/Sunset (and drops the "min" unit for
    that state too, so it doesn't render as "- min").
    """

    def __init__(self, coordinator: RunChickenCoordinator, action: str) -> None:
        """Initialize the offset sensor for ``action`` ("open" or "close")."""
        self._action = action
        super().__init__(coordinator, f"{action}_offset_minutes", f"{action.title()} Offset")

    @property
    def _in_sunrise_sunset_mode(self) -> bool:
        """Return whether this sensor's schedule mode is currently Sunrise/Sunset."""
        mode = getattr(self.coordinator.data, f"{self._action}_schedule_mode")
        return mode is RunChickenScheduleMode.SUNRISE_SUNSET

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return "min" only while the offset is meaningful."""
        return "min" if self._in_sunrise_sunset_mode else None

    @property
    def native_value(self) -> str:
        """Return the offset in minutes, or "-" if not in Sunrise/Sunset mode."""
        if not self._in_sunrise_sunset_mode:
            return "-"
        return str(getattr(self.coordinator.data, f"{self._action}_offset_minutes"))


class RunChickenTimeSensorBase(RunChickenSensorBase):
    """
    Reports the door's open/close time, converted to the HA instance's local time.

    The door reports a resolved time regardless of schedule mode (in
    Sunrise/Sunset mode it's the day's computed sunrise/sunset+offset time),
    but that's a moving daily calculation rather than a fixed setting, so
    this only surfaces a value in Time mode - Manual and Sunrise/Sunset
    show "-", matching the schedule-offset sensor's convention of "not
    applicable" over a misleading or confusing value.
    """

    def __init__(self, coordinator: RunChickenCoordinator, action: str) -> None:
        """Initialize the time sensor for ``action`` ("open" or "close")."""
        self._action = action
        super().__init__(coordinator, f"{action}_time", f"{action.title()} Time")

    @property
    def native_value(self) -> str:
        """Return the resolved time as a local "HH:MM" string, or "-" outside Time mode."""
        mode = getattr(self.coordinator.data, f"{self._action}_schedule_mode")
        resolved_time = getattr(self.coordinator.data, f"{self._action}_time")
        if mode is not RunChickenScheduleMode.TIMER or resolved_time is None:
            return "-"
        today_utc = dt_util.utcnow().replace(
            hour=resolved_time.hour, minute=resolved_time.minute, second=0, microsecond=0
        )
        return dt_util.as_local(today_utc).strftime("%H:%M")


class RunChickenOpenTimeSensor(RunChickenTimeSensorBase):
    """Reports the door's open time when in Time mode."""

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the open-time sensor."""
        super().__init__(coordinator, "open")


class RunChickenCloseTimeSensor(RunChickenTimeSensorBase):
    """
    Reports the door's close time when in Time mode.

    UNVERIFIED: relies on ``close_time_offset`` (protocol.py), which is
    hypothesized by symmetry with the confirmed open-time offset, not
    independently confirmed against a real Close->Time app setting.
    """

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the close-time sensor."""
        super().__init__(coordinator, "close")


class RunChickenRssiSensor(RunChickenSensorBase):
    """
    Reports real BLE advertisement RSSI, sourced from Home Assistant's own
    Bluetooth stack (not from anything in the door's status payload).

    A candidate byte in the status payload was investigated and ruled out as
    RSSI (it read a constant -76 on both doors regardless of their actual,
    differing signal strength) - this sensor uses the real value instead.
    """

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"

    def __init__(self, coordinator: RunChickenCoordinator) -> None:
        """Initialize the RSSI sensor."""
        super().__init__(coordinator, "rssi", "Signal Strength")

    @property
    def native_value(self) -> int | None:
        """Return the most recently seen advertisement RSSI, if any."""
        service_info = async_last_service_info(
            self.hass, self.run_chicken_device.address, connectable=True
        )
        return service_info.rssi if service_info else None
