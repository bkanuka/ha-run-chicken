"""Config flow for the Run-Chicken integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components.bluetooth import async_discovered_service_info
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN, MANUFACTURER_ID

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


class RunChickenConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Run-Chicken."""

    VERSION = 1

    _discovery_info: BluetoothServiceInfoBleak

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> FlowResult:
        """Handle a bluetooth discovery and ask the user to confirm."""
        if MANUFACTURER_ID not in discovery_info.manufacturer_data:
            return self.async_abort(reason="not_run_chicken_device")

        _LOGGER.debug("Bluetooth discovery for Run-Chicken: %s", discovery_info.address)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm adding a device discovered over bluetooth."""
        if user_input is not None:
            return self.async_create_entry(title=self._discovery_info.name, data={})

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery_info.name},
        )

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
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)})
        return self.async_show_form(step_id="user", data_schema=schema)
