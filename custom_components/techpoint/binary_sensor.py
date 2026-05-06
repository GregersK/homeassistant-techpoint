from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TechPointCoordinator
from .device import make_device_context, build_device_info
from .util import find_by_id, normalize_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: TechPointCoordinator = data["coordinator"]
    entities: list[BinarySensorEntity] = []

    snapshot = coord.data or {}
    for zone in [x for x in snapshot.get("zones", []) if x.get("io_type") == 16]:
        entities.append(TechPointZoneSensor(coord, entry.entry_id, zone))

    for inp in snapshot.get("io_inputs", []):
        entities.append(TechPointInputSensor(coord, entry.entry_id, inp))

    for door in snapshot.get("doors", []):
        did = normalize_id(door.get("id"))
        if did is None:
            continue
        entities.append(TechPointDoorOpenSensor(coord, entry.entry_id, door))
        entities.append(TechPointDoorSabotageSensor(coord, entry.entry_id, door))

    if entities:
        async_add_entities(entities)


class TechPointZoneSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, zone: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._zone_id = zone.get("id")
        self._io_id = zone.get("io_id")
        self._attr_unique_id = f"{entry_id}_zone_{self._zone_id}"

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        for z in snapshot.get("zones", []):
            if z.get("id") == self._zone_id:
                return z
        return None

    @property
    def name(self) -> str | None:
        z = self._current() or {}
        base = z.get("name") or f"{self._zone_id}"
        if str(base).lower().startswith("zone"):
            return str(base)
        return f"Zone {base}"

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        z = self._current() or {}
        base = z.get("name") or f"{self._zone_id}"
        return build_device_info(ctx, grouping, "zone", item_id=self._zone_id, item_name=str(base))

    @property
    def is_on(self) -> bool | None:
        # On if armed/alarm etc. Keep it simple:
        z = self._current()
        if not z:
            return None
        st = int(z.get("state", 0) or 0)
        flags = z.get("state_flags") or []
        return st in (2, 3) or (2 in flags)

    @property
    def extra_state_attributes(self):
        z = self._current() or {}
        return {
            "zone_id": self._zone_id,
            "io_id": self._io_id,
            "raw": z,
        }


class TechPointInputSensor(CoordinatorEntity, BinarySensorEntity):
    """User-defined input (ioType=28). State 2=active, 0=passive."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, inp: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._input_id = str(inp.get("id", ""))
        self._attr_unique_id = f"{entry_id}_io_input_{self._input_id}"

    def _current(self) -> dict[str, Any] | None:
        for inp in (self.coordinator.data or {}).get("io_inputs", []):
            if str(inp.get("id", "")) == self._input_id:
                return inp
        return None

    @property
    def name(self) -> str:
        inp = self._current() or {}
        return inp.get("name") or f"Input {self._input_id}"

    @property
    def is_on(self) -> bool | None:
        inp = self._current()
        if inp is None:
            return None
        return int(inp.get("state", 0) or 0) == 2

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        inp = self._current() or {}
        return build_device_info(ctx, grouping, "input", item_id=self._input_id, item_name=inp.get("name"))

    @property
    def extra_state_attributes(self) -> dict:
        inp = self._current() or {}
        return {
            "input_id": self._input_id,
            "techpoint_id": inp.get("techpoint"),
            "state_raw": inp.get("state"),
            "last_changed": inp.get("time"),
        }


class TechPointDoorOpenSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is ON when a door is physically open (position=4).

    Useful for automations such as "door held open" alerts.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, door: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._door_id = normalize_id(door.get("id"))
        self._attr_unique_id = f"{entry_id}_door_{self._door_id}_open"

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        return find_by_id(snapshot.get("doors"), self._door_id)

    @property
    def name(self) -> str:
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        return f"{base} (Åben)"

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        return build_device_info(ctx, grouping, "door", item_id=self._door_id, item_name=str(base))

    @property
    def is_on(self) -> bool | None:
        door = self._current()
        if door is None:
            return None
        try:
            return int(door.get("position") or 0) == 4
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict:
        door = self._current() or {}
        return {
            "door_id": self._door_id,
            "position": door.get("position"),
            "position_text": door.get("position_text"),
        }


class TechPointDoorSabotageSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that is ON when a door reports a sabotage condition.

    Uses the issabotage field from doorStatus (API v1.13.0).
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.TAMPER

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, door: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._door_id = normalize_id(door.get("id"))
        self._attr_unique_id = f"{entry_id}_door_{self._door_id}_sabotage"

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        return find_by_id(snapshot.get("doors"), self._door_id)

    @property
    def name(self) -> str:
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        return f"{base} (Sabotage)"

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        door = self._current() or {}
        base = door.get("name") or f"{self._door_id}"
        return build_device_info(ctx, grouping, "door", item_id=self._door_id, item_name=str(base))

    @property
    def is_on(self) -> bool | None:
        door = self._current()
        if door is None:
            return None
        sabotage = door.get("issabotage")
        if sabotage is None:
            return None
        return bool(sabotage)

    @property
    def extra_state_attributes(self) -> dict:
        door = self._current() or {}
        return {
            "door_id": self._door_id,
            "issabotage": door.get("issabotage"),
        }
