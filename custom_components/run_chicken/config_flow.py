"""Config flow for the Run-Chicken integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, MANUFACTURER_ID

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


class RunChickenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Run-Chicken."""

    VERSION = 1

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfo) -> FlowResult:
        """Handle a bluetooth discovery. Add immediately without prompts."""
        address = discovery_info.address
        if MANUFACTURER_ID not in discovery_info.manufacturer_data:
            return self.async_abort(reason="not_run_chicken_device")

        _LOGGER.debug("Bluetooth discovery for Run-Chicken: %s", address)

        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        # Create the entry right away; we identify devices by address only
        return self.async_create_entry(title=address, data={})

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show list of discovered devices (by address) and let user pick one."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=address, data={})

        # Collect available devices with matching manufacturer id
        options: dict[str, str] = {}
        current_ids = {entry.unique_id for entry in self._async_current_entries() if entry.unique_id}
        for info in async_discovered_service_info(self.hass):
            addr = info.address
            if addr in current_ids or addr in options:
                continue
            if MANUFACTURER_ID not in info.manufacturer_data:
                continue
            # List entry shows address and manufacturer id
            options[addr] = f"{addr}"

        if not options:
            return self.async_abort(reason="No devices found")

        schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)})
        return self.async_show_form(step_id="user", data_schema=schema)
