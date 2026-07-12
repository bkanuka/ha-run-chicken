"""Shared base class for Run-Chicken entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

if TYPE_CHECKING:
    from .coordinator import RunChickenCoordinator


class RunChickenEntity(CoordinatorEntity["RunChickenCoordinator"]):
    """
    Base for Run-Chicken entities: shared device identity and settings writes.

    Subclasses get the standard device-registry wiring and a helper that
    performs a read-modify-write of the door's settings and then refreshes the
    coordinator so the new state is reflected promptly.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: RunChickenCoordinator, key: str) -> None:
        """Initialize with a stable per-device ``key`` for the unique id."""
        super().__init__(coordinator)
        self.run_chicken_device = coordinator.device
        self._attr_unique_id = f"run_chicken_{self.run_chicken_device.address}_{key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, self.run_chicken_device.address)},
            name=self.run_chicken_device.name,
            manufacturer=self.run_chicken_device.manufacturer,
            model=self.run_chicken_device.model,
        )

    async def _async_write_settings(self, **changes: object) -> None:
        """
        Apply a settings change, surfacing incomplete-state errors to the user.

        Merges ``changes`` onto the latest snapshot and writes them; a
        ``ValueError`` (e.g. the door hasn't been read yet) becomes a
        ``HomeAssistantError`` so the UI shows a clear message instead of a
        traceback.
        """
        try:
            await self.run_chicken_device.async_write_settings(self.coordinator.data, **changes)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()


class RunChickenConditionallyVisibleEntity(RunChickenEntity):
    """
    A Run-Chicken entity that hides itself from default dashboards when its value isn't meaningful.

    Mirrors ``RunChickenConditionallyVisibleSensor`` in sensor.py: it toggles
    the entity-registry ``hidden_by`` flag based on ``_is_applicable`` (which
    subclasses override), so the entity drops out of auto-generated
    dashboards/areas while not applicable but still exists and reappears
    automatically. Never overrides a hidden/visible state the user set
    themselves - only ever toggles a state this class previously set.
    """

    @property
    def _is_applicable(self) -> bool:
        """Return whether this entity's value is currently meaningful. Subclasses must override."""
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Sync visibility once at startup, in addition to the normal coordinator listener."""
        await super().async_added_to_hass()
        self._sync_visibility()

    def _handle_coordinator_update(self) -> None:
        """Sync visibility on every coordinator update, then write state as normal."""
        self._sync_visibility()
        super()._handle_coordinator_update()

    def _sync_visibility(self) -> None:
        """Hide/unhide this entity based on ``_is_applicable``, without overriding a user's own choice."""
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is None:
            return
        hidden_by_us = entry.hidden_by is er.RegistryEntryHider.INTEGRATION
        if entry.hidden_by is not None and not hidden_by_us:
            return  # Hidden by the user (or something else) - leave it alone.
        if self._is_applicable and hidden_by_us:
            registry.async_update_entity(self.entity_id, hidden_by=None)
        elif not self._is_applicable and not hidden_by_us:
            registry.async_update_entity(self.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION)
