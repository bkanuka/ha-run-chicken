"""Custom types for run_chicken."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import RunChickenApiClient
    from .coordinator import BlueprintDataUpdateCoordinator


type RunChickenConfigEntry = ConfigEntry[RunChickenData]


@dataclass
class RunChickenData:
    """Data for the Blueprint integration."""

    client: RunChickenApiClient
    coordinator: BlueprintDataUpdateCoordinator
    integration: Integration
