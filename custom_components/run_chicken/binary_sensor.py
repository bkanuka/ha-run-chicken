"""Binary sensor platform for run_chicken."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .data import RunChickenConfigEntry

ENTITY_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="run_chicken",
        name="Run Chicken Binary Sensor",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


from homeassistant import config_entries
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.bluetooth.active_update_processor import (
    ActiveBluetoothProcessorCoordinator,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from run_chicken.run_chicken_ble.const import DOMAIN


def sensor_update_to_bluetooth_data_update(parsed_data):
    """Convert a sensor update to a Bluetooth data update."""
    # This function must convert the parsed_data
    # from your library's update_method to a `PassiveBluetoothDataUpdate`
    return PassiveBluetoothDataUpdate(
        devices={},
        entity_descriptions={},
        entity_data={},
        entity_names={},
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the example BLE sensors."""
    coordinator: ActiveBluetoothProcessorCoordinator = hass.data[DOMAIN][
        entry.entry_id
    ]
    processor = PassiveBluetoothDataProcessor(sensor_update_to_bluetooth_data_update)
    entry.async_on_unload(
        processor.async_add_entities_listener(
            RunChickenSensorEntity, async_add_entities
        )
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class RunChickenSensorEntity(PassiveBluetoothProcessorEntity, BinarySensorEntity):
    """Representation of an example BLE sensor."""

    @property
    def native_value(self) -> float | int | str | None:
        """Return the native value."""
        return self.processor.entity_data.get(self.entity_key)

