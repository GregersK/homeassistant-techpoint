from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    entities: list[SwitchEntity] = []

    for out in (coord.data or {}).get("io_outputs", []):
        entities.append(TechPointOutputSwitch(coord, entry.entry_id, out))

    # Global door control switch (controller-level, one per entry).
    # Only create if the coordinator successfully polled this endpoint.
    snapshot = coord.data or {}
    if snapshot.get("global_door_control_active") is not None or hasattr(coord.client, "get_global_door_control"):
        entities.append(TechPointGlobalDoorControlSwitch(coord, entry.entry_id))

    if entities:
        async_add_entities(entities)


class TechPointOutputSwitch(CoordinatorEntity, SwitchEntity):
    """User-defined output (ioType=29). State 2=active/on, 0=passive/off."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, out: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._output_id = str(out.get("id", ""))
        self._attr_unique_id = f"{entry_id}_io_output_{self._output_id}"

    def _current(self) -> dict[str, Any] | None:
        for out in (self.coordinator.data or {}).get("io_outputs", []):
            if str(out.get("id", "")) == self._output_id:
                return out
        return None

    @property
    def name(self) -> str:
        out = self._current() or {}
        return out.get("name") or f"Output {self._output_id}"

    @property
    def is_on(self) -> bool | None:
        out = self._current()
        if out is None:
            return None
        return int(out.get("state", 0) or 0) == 2

    @property
    def device_info(self) -> DeviceInfo:
        grouping = self.coordinator.hass.data[DOMAIN][self._entry_id].get("device_grouping")
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self.coordinator.name)
        out = self._current() or {}
        return build_device_info(ctx, grouping, "output", item_id=self._output_id, item_name=out.get("name"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.set_io_userdefined(int(self._output_id), status=2)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.set_io_userdefined(int(self._output_id), status=0)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self) -> dict:
        out = self._current() or {}
        return {
            "output_id": self._output_id,
            "techpoint_id": out.get("techpoint"),
            "state_raw": out.get("state"),
            "last_changed": out.get("time"),
        }


class TechPointGlobalDoorControlSwitch(CoordinatorEntity, SwitchEntity):
    """Controller-level switch for TechPoint global door control.

    When ON, all doors where 'Enable global door control' is configured will open.
    Maps to GET/POST /access/globalDoorControl (API v1.13.0).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:door-open"

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_global_door_control"

    @property
    def name(self) -> str:
        return "Global door control"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self.coordinator.name,
        )

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get("global_door_control_active")

    @property
    def available(self) -> bool:
        return (self.coordinator.data or {}).get("global_door_control_active") is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.set_global_door_control(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        client = self.coordinator.hass.data[DOMAIN][self._entry_id]["client"]
        await client.set_global_door_control(False)
        await self.coordinator.async_request_refresh()
