from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TechPointCoordinator
from .device import DeviceContext, build_device_info
from .util import find_by_id, normalize_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TechPoint door pulse buttons from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coord: TechPointCoordinator = data["coordinator"]
    entities: list[ButtonEntity] = []

    snapshot = coord.data or {}
    for door in snapshot.get("doors", []):
        did = normalize_id(door.get("id"))
        if did is None:
            continue
        entities.append(TechPointDoorPulseButton(coord, entry.entry_id, door))

    if entities:
        async_add_entities(entities)


class TechPointDoorPulseButton(CoordinatorEntity, ButtonEntity):
    """Momentary 'pulse open' button for a single door."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TechPointCoordinator,
        entry_id: str,
        door: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._door_id = normalize_id(door.get("id"))
        self._attr_unique_id = f"{entry_id}_door_{self._door_id}_pulse"

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        return find_by_id(snapshot.get("doors"), self._door_id)

    @property
    def name(self) -> str | None:
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        if str(base).lower().startswith("dør") or str(base).lower().startswith("door"):
            return f"{base} (Pulse åbning)"
        return f"Dør {base} (Pulse åbning)"

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = DeviceContext(entry_id=self._entry_id, controller_name=self.coordinator.name)
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        return build_device_info(ctx, grouping, "door", item_id=self._door_id, item_name=str(base))

    async def async_press(self) -> None:
        """Send a pulse (Release) command to the door and refresh state."""
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.set_door_status(self._door_id, "Release")
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        door = self._current() or {}
        return {
            "entry_id": self._entry_id,
            "door_id": self._door_id,
            "raw_id": door.get("id"),
            "raw": door.get("raw"),
        }
