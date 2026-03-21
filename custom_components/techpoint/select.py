from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TechPointCoordinator
from .device import make_device_context, build_device_info
from .util import find_by_id, normalize_id

"""Select entities.

We intentionally use *internal* option keys (lowercase snake_case) and rely on
Home Assistant entity state translations (translation_key + strings.json) to
present the user's language in the UI.

The TechPoint API expects the original enum strings: Normal/Release/
PermanentRelease/Secure/Block.
"""

OPTIONS = ["normal", "release", "permanent_release", "secure", "block"]

OPTION_TO_API = {
    "normal": "Normal",
    "release": "Release",
    "permanent_release": "PermanentRelease",
    "secure": "Secure",
    "block": "Block",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: TechPointCoordinator = data["coordinator"]

    entities: list[SelectEntity] = []
    snapshot = coord.data or {}
    for d in snapshot.get("doors", []):
        did = normalize_id(d.get("id"))
        if did is None:
            continue
        entities.append(TechPointDoorModeSelect(coord, entry.entry_id, d))
    async_add_entities(entities)


class TechPointDoorModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "door_mode"

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, door: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._door_id = normalize_id(door.get("id"))
        self._attr_unique_id = f"{entry_id}_door_{self._door_id}_mode"
        self._attr_options = OPTIONS

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        return find_by_id(snapshot.get("doors"), self._door_id)

    @property
    def name(self) -> str | None:
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        if str(base).lower().startswith("dør") or str(base).lower().startswith("door"):
            return f"{base} (Tilstand)"
        return f"Dør {base} (Tilstand)"

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        return build_device_info(ctx, grouping, "door", item_id=self._door_id, item_name=str(base))

    @property
    def current_option(self) -> str | None:
        door = self._current() or {}
        exc = door.get("exception")
        if exc == 1:
            return "block"
        if exc == 2:
            return "permanent_release"
        pos = door.get("position")
        return {
            1: "secure",  # Secured/Close
            2: "normal",  # Unsecure (normal drift)
            3: "release",  # Released
            4: "normal",  # Door physically open - not a mode
        }.get(pos, "normal")

    async def async_select_option(self, option: str) -> None:
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        api_value = OPTION_TO_API.get(option, option)
        await client.set_door_status(self._door_id, api_value)
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
