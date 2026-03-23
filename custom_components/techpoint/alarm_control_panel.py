from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TechPointCoordinator
from .device import make_device_context, build_device_info

# Expose ARM_AWAY as supported feature (DISARM requires no flag)
FEATURES = AlarmControlPanelEntityFeature.ARM_AWAY

# TechPoint state -> HA state
STATE_MAP = {
    1: "disarmed",            # Unset
    2: "armed_away",          # Set
    3: "armed_home",          # Partial set
    4: "disarmed",            # Disabled
    5: "armed_custom_bypass", # Isolated
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: TechPointCoordinator = data["coordinator"]
    entities: list[AlarmControlPanelEntity] = []

    snapshot = coord.data or {}
    for area in [x for x in snapshot.get("areas", []) if x.get("io_type") == 17]:
        entities.append(TechPointAreaAlarm(coord, entry.entry_id, area))

    async_add_entities(entities)


class TechPointAreaAlarm(CoordinatorEntity, AlarmControlPanelEntity):
    _attr_has_entity_name = True
    _attr_supported_features = FEATURES
    _attr_code_arm_required = False
    _attr_code_disarm_required = False

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, area: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._area_id = area["id"]
        self._io_id = area["io_id"]
        self._attr_unique_id = f"{entry_id}_area_{self._area_id}"

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        for a in snapshot.get("areas", []):
            if a.get("id") == self._area_id:
                return a
        return None

    @property
    def name(self) -> str | None:
        cur = self._current() or {}
        base = cur.get("name") or f"{self._area_id}"
        if str(base).lower().startswith("area") or str(base).lower().startswith("område"):
            return str(base)
        return f"Area {base}"

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        area = self._current() or {}
        base = area.get("name") or f"{self._area_id}"
        return build_device_info(ctx, grouping, "area", item_id=self._area_id, item_name=str(base))

    @property
    def state(self) -> str | None:
        area = self._current() or {}
        try:
            return STATE_MAP.get(int(area.get("state", 0)), "unknown")
        except Exception:  # noqa: BLE001
            return "unknown"

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        # TechPoint: command 2 = Unset (disarm)
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.intrusion_command([self._io_id], 2)
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        # TechPoint: command 3 = Set (arm)
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.intrusion_command([self._io_id], 3)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        area = self._current() or {}
        return {
            "area_id": self._area_id,
            "io_id": self._io_id,
            "raw": area.get("raw"),
        }
