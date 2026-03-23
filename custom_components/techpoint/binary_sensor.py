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
