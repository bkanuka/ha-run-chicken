"""Config flow for the Run-Chicken integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.bluetooth import async_discovered_service_info
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, MANUFACTURER_ID

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
        """Confirm adding a device discovered over bluetooth."""
        if user_input is not None:
            return self.async_create_entry(title=self._discovery_info.name, data={})

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery_info.name},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show a list of discovered devices and let the user pick one."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._discovered_devices[address], data={})

        # Skip devices already set up or being set up in another in-progress flow.
        addresses_in_use = self._async_current_ids() | {
            flow["context"]["unique_id"] for flow in self._async_in_progress() if "unique_id" in flow["context"]
        }
        self._discovered_devices = {}
        for info in async_discovered_service_info(self.hass):
            address = info.address
            if address in addresses_in_use or address in self._discovered_devices:
                continue
            if MANUFACTURER_ID not in info.manufacturer_data:
                continue
            self._discovered_devices[address] = f"{info.name} ({address})" if info.name else address

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices)})
        return self.async_show_form(step_id="user", data_schema=schema)
