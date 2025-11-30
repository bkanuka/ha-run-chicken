"""Cover platform for run_chicken."""



from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

ENTITY_DESCRIPTIONS = (
    CoverEntityDescription(
        key="run_chicken",
        name="Run Chicken Cover",
        device_class=CoverDeviceClass.DOOR,
    )
)

class RunChickenCoverEntity(CoverEntity):
    """Run Chicken Cover."""
