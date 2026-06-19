"""Config flow for the Run-Chicken integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from bleak.exc import BleakError
from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, MANUFACTURER_ID
from .run_chicken_ble import RunChickenDevice

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)


class RunChickenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Run-Chicken."""

    VERSION = 1

    _discovery_info: BluetoothServiceInfoBleak

    def __init__(self) -> None:
        """Initialize the config flow."""
        # Maps a device address to a human-readable label for the picker.
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        """Handle a bluetooth discovery and ask the user to confirm."""
        if MANUFACTURER_ID not in discovery_info.manufacturer_data:
            return self.async_abort(reason="not_run_chicken_device")

        _LOGGER.debug("Bluetooth discovery for Run-Chicken: %s", discovery_info.address)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm adding a device discovered over bluetooth, verifying it is reachable."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._async_try_connect(self._discovery_info.address)
            if error is None:
                return self.async_create_entry(title=self._discovery_info.name, data={})
            errors["base"] = error

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery_info.name},
            errors=errors,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show a list of discovered devices and let the user pick one."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            error = await self._async_try_connect(address)
            if error is None:
                return self.async_create_entry(title=self._discovered_devices[address], data={})
            errors["base"] = error

        # Skip devices that are already configured.
        current_addresses = self._async_current_ids()
        self._discovered_devices = {}
        for info in async_discovered_service_info(self.hass):
            address = info.address
            if address in current_addresses or address in self._discovered_devices:
                continue
            if MANUFACTURER_ID not in info.manufacturer_data:
                continue
            self._discovered_devices[address] = f"{info.name} ({address})" if info.name else address

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _async_try_connect(self, address: str) -> str | None:
        """
        Probe connectivity to the device at ``address``.

        Establishes a single BLE connection and immediately disconnects, leaving
        the device free for the entry setup to reconnect. Returns an error key
        (``cannot_connect``/``unknown``) on failure, or ``None`` on success.
        """
        ble_device = async_ble_device_from_address(self.hass, address, connectable=True)
        if ble_device is None:
            _LOGGER.debug("No connectable BLE device found for %s", address)
            return "cannot_connect"

        device = RunChickenDevice(ble_device)
        # The broad `except Exception` below is a deliberate safety net: a
        # connectivity probe must never surface a raw traceback in the config
        # flow, so any unexpected error is reported as "unknown" (mirroring Home
        # Assistant's own config-flow convention of catch-all -> "unknown").
        # noinspection PyBroadException
        try:
            await device.ensure_client_connected()
        except (BleakError, TimeoutError):
            _LOGGER.debug("Could not connect to Run-Chicken device %s", address, exc_info=True)
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error connecting to Run-Chicken device %s", address)
            return "unknown"
        finally:
            client = device.client
            if client is not None:
                await client.disconnect()
        return None
