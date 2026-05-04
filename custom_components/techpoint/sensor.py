from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, SIGNAL_EVENT_LOG_UPDATED
from .coordinator import TechPointCoordinator
from .device import make_device_context, build_device_info
from .util import find_by_id, normalize_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TechPoint sensors."""

    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TechPointCoordinator = data["coordinator"]

    snapshot = coordinator.data or {}
    doors = snapshot.get("doors") or []

    entities: list[SensorEntity] = []
    for door in doors:
        entities.append(
            TechPointDoorStatusSensor(
                coordinator,
                entry.entry_id,
                data.get("device_grouping"),
                # Use the configured controller name (e.g. "TP-LAN"), not the entry_id.
                coordinator.name,
                door,
            )
        )


    # Cardholder count (if API supports it)
    if snapshot.get("cardholder_count") is not None or hasattr(coordinator.client, "list_card_holders_filter"):
        entities.append(TechPointCardholderCountSensor(coordinator, entry.entry_id, coordinator.name))

    # Realtime helpers
    # 1) Human readable, single-line "latest event" (best for dashboards)
    entities.append(TechPointEventLogLineSensor(hass, entry.entry_id, coordinator.name))
    # 2) Structured latest event (key fields as attributes)
    entities.append(TechPointLastEventSensor(hass, entry.entry_id, coordinator.name))
    # 3) Rolling event log sensor (keeps last N events in attributes)
    entities.append(TechPointEventLogSensor(hass, entry.entry_id, coordinator.name))
    # 4) Webhook URL (copy/paste into TechPoint UI)
    entities.append(TechPointWebhookUrlSensor(hass, entry.entry_id, coordinator.name))

    if entities:
        async_add_entities(entities)


class TechPointDoorStatusSensor(CoordinatorEntity, SensorEntity):
    """Human friendly physical status for a door (open/held/forced/offline, etc.)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TechPointCoordinator,
        entry_id: str,
        grouping: str | None,
        controller_name: str,
        door: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._grouping = grouping
        self._controller_name = controller_name

        self._door_id = normalize_id(door.get("id"))
        self._door_name = (door.get("name") or str(self._door_id)).strip()

        self._attr_unique_id = f"{entry_id}_door_{self._door_id}_status"

    def _current(self) -> dict[str, Any] | None:
        snapshot = self.coordinator.data or {}
        return find_by_id(snapshot.get("doors") or [], self._door_id)

    @property
    def name(self) -> str:
        base = self._door_name
        if base and not base.lower().startswith("dør"):
            base = f"Dør {base}"
        return f"{base} (Status)"

    @property
    def device_info(self) -> DeviceInfo:
        ctx = make_device_context(self.coordinator.hass, self._entry_id, self._controller_name)
        return build_device_info(
            ctx,
            self._grouping,
            "door",
            item_id=self._door_id,
            item_name=self._door_name,
        )

    @property
    def native_value(self) -> Any:
        d = self._current() or {}
        return d.get("status_text")

    @property
    def icon(self) -> str:
        d = self._current() or {}
        try:
            exc = int(d.get("exception") or 0)
        except Exception:  # noqa: BLE001
            exc = 0
        try:
            pos = int(d.get("position") or 0)
        except Exception:  # noqa: BLE001
            pos = 0

        if exc == 5:
            return "mdi:door-open"
        if exc == 4:
            return "mdi:door-open"
        if exc == 6:
            return "mdi:lan-disconnect"
        if pos == 4:
            return "mdi:door-open"
        return "mdi:door-closed"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._current() or {}
        return {
            "door_id": self._door_id,
            "position": d.get("position"),
            "position_text": d.get("position_text"),
            "position_cause": d.get("positionCause"),
            "position_cause_text": d.get("position_cause_text"),
            "exception": d.get("exception"),
            "exception_text": d.get("exception_text"),
            "intrusion_state": d.get("intrusionState"),
            "intrusion_state_text": d.get("intrusion_state_text"),
        }



class TechPointCardholderCountSensor(CoordinatorEntity, SensorEntity):
    """Total number of cardholders registered in TechPoint."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:account-group"
    _attr_native_unit_of_measurement = "cardholders"

    def __init__(self, coordinator: TechPointCoordinator, entry_id: str, controller_name: str) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._controller_name = controller_name
        self._attr_unique_id = f"{entry_id}_cardholder_count"

    @property
    def name(self) -> str:
        return "Cardholder count"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._controller_name,
        )

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("cardholder_count")


class TechPointEventLogLineSensor(SensorEntity):
    """Latest TechPoint event as a human readable single line."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, controller_name: str) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._controller_name = controller_name
        self._attr_unique_id = f"{entry_id}_event_log_line"
        self._attr_translation_key = "event_log_line"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(
            self.hass,
            f"{SIGNAL_EVENT_LOG_UPDATED}_{self._entry_id}",
            self.async_write_ha_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._controller_name,
        )

    def _latest(self) -> dict[str, Any] | None:
        data = (self.hass.data.get(DOMAIN) or {}).get(self._entry_id) or {}
        return data.get("last_event_parsed")

    @property
    def native_value(self) -> Any:
        last = self._latest()
        if not isinstance(last, dict):
            return "No events yet"
        line = last.get("line")
        return str(line) if line else "No events yet"

    @property
    def icon(self) -> str:
        last = self._latest()
        if not isinstance(last, dict):
            return "mdi:format-list-bulleted"
        cat = (last.get("category") or "").lower()
        if cat == "door":
            return "mdi:door"
        if cat == "alarm":
            return "mdi:alarm-light"
        if cat == "tamper":
            return "mdi:alert"
        if cat == "error":
            return "mdi:alert-circle"
        return "mdi:information-outline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._latest() or {}
        if not isinstance(last, dict):
            last = {}
        # Keep attributes small and useful for dashboards/automations
        return {
            "time": last.get("time"),
            "category": last.get("category"),
            "door": last.get("door"),
            "reader": last.get("reader"),
            "who": last.get("who"),
            "action": last.get("action"),
            "card_badge": last.get("card_badge"),
            "chip_serial": last.get("chip_serial"),
            "type_id": last.get("type_id"),
            "type_name": last.get("type_name"),
        }


class TechPointLastEventSensor(SensorEntity):
    """Latest TechPoint event as structured attributes."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"

    def __init__(self, hass: HomeAssistant, entry_id: str, controller_name: str) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._controller_name = controller_name
        self._attr_unique_id = f"{entry_id}_last_event"
        self._attr_translation_key = "last_event"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = async_dispatcher_connect(
            self.hass,
            f"{SIGNAL_EVENT_LOG_UPDATED}_{self._entry_id}",
            self.async_write_ha_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._controller_name,
        )

    def _latest(self) -> dict[str, Any] | None:
        data = (self.hass.data.get(DOMAIN) or {}).get(self._entry_id) or {}
        return data.get("last_event_parsed")

    @property
    def native_value(self) -> Any:
        last = self._latest()
        if not isinstance(last, dict):
            return "No events yet"
        return str(last.get("summary") or last.get("type_name") or "Event")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._latest()
        if not isinstance(last, dict):
            return {}
        # Expose everything parsed (still compact)
        return dict(last)


class TechPointEventLogSensor(SensorEntity):
    """Rolling TechPoint event log (last N events) for dashboards."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, hass: HomeAssistant, entry_id: str, controller_name: str) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._controller_name = controller_name
        self._attr_unique_id = f"{entry_id}_event_log"
        self._attr_translation_key = "event_log"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        # Update whenever webhook handler appends to log
        self._unsub = async_dispatcher_connect(
            self.hass,
            f"{SIGNAL_EVENT_LOG_UPDATED}_{self._entry_id}",
            self.async_write_ha_state,
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        # Attach to controller device
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._controller_name,
        )

    def _log(self) -> list[dict[str, Any]]:
        data = (self.hass.data.get(DOMAIN) or {}).get(self._entry_id) or {}
        log = data.get("event_log") or []
        return log if isinstance(log, list) else []

    @property
    def native_value(self) -> Any:
        # Show a short summary of the newest entry
        log = self._log()
        if not log:
            return "No events yet"
        last = log[-1]
        t = last.get("type_name") or last.get("type_id") or "Event"
        # Try to show door/reader hint
        dv = last.get("details_values") or []
        hint = ""
        if isinstance(dv, list) and dv:
            hint = f" – {dv[0]}"
        return f"{t}{hint}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        log = self._log()
        last = log[-1] if log else None
        return {
            "count": len(log),
            "last": last,
            # Full rolling log (newest last)
            "events": log,
        }


class TechPointWebhookUrlSensor(SensorEntity):
    """Expose the HA webhook URL for easy copy/paste into TechPoint UI."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:webhook"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry_id: str, controller_name: str) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._controller_name = controller_name
        self._attr_unique_id = f"{entry_id}_webhook_url"
        self._attr_translation_key = "webhook_url"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._controller_name,
        )

    @property
    def native_value(self) -> Any:
        data = (self.hass.data.get(DOMAIN) or {}).get(self._entry_id) or {}
        url = data.get("webhook_url")
        if url:
            return str(url)
        # If realtime isn't enabled yet, we still can show the URL we *would* use.
        try:
            from .webhook import get_webhook_url  # local import to avoid cycles

            return get_webhook_url(self.hass, self._entry_id)
        except Exception:  # noqa: BLE001
            return ""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = (self.hass.data.get(DOMAIN) or {}).get(self._entry_id) or {}
        return {
            "auth_type": "None",
            "techpoint_endpoint": "/events/webhook",
            "webhook_id": data.get("webhook_id"),
            "event_filter": data.get("webhook_filter"),
            "registered_at": data.get("webhook_registered_at"),
        }

