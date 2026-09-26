from __future__ import annotations
from typing import Any, Dict
from datetime import timedelta
import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Backoff schedule (seconds) applied per optional resource key after a fetch
# failure, so a transient glitch heals itself instead of disabling that data
# type until the integration is reloaded. Capped at the last value.
_RETRY_BACKOFF_S = (30, 60, 120, 300)


class TechPointCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client,
        name: str,
        update_interval_s: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=timedelta(seconds=update_interval_s),
        )
        self.client = client
        # Per-key failure bookkeeping for optional resources: consecutive failure
        # count and the monotonic time before which we won't retry that key.
        # A transient failure backs off and retries on its own — it never
        # permanently disables a data type the way an unconditional "skip
        # forever" flag would (that previously required a full integration
        # reload to recover from a single blip).
        self._key_fail_count: dict[str, int] = {}
        self._key_retry_after: dict[str, float] = {}
        # Keys whose fetch succeeded on the most recent poll cycle. Used to gate
        # stale-entity cleanup so a single transient API failure (which leaves
        # that key's data empty for the cycle) can never be mistaken for a
        # door/zone/output that was actually removed on the controller.
        self.last_cycle_ok_keys: set[str] = set()

    def _due_for_retry(self, key: str, now: float) -> bool:
        return now >= self._key_retry_after.get(key, 0.0)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch doors, AIA area/zone status, user-defined I/O, cardholder count, and controller state."""
        try:
            list_areas = getattr(self.client, "list_areas_status", None) or getattr(self.client, "list_areas", None)
            list_zones = getattr(self.client, "list_zones_status", None) or getattr(self.client, "list_zones", None)
            get_api_info = getattr(self.client, "get_api_info", None)
            get_io = getattr(self.client, "get_io_userdefined", None)
            list_cardholders_filter = getattr(self.client, "list_card_holders_filter", None)
            get_global_door_control = getattr(self.client, "get_global_door_control", None)
            get_threat_level = getattr(self.client, "get_threat_level", None)

            now = time.monotonic()
            tasks: list = [self.client.list_doors()]
            task_keys = ["doors"]

            if list_areas and self._due_for_retry("areas", now):
                tasks.append(list_areas())
                task_keys.append("areas")
            if list_zones and self._due_for_retry("zones", now):
                tasks.append(list_zones())
                task_keys.append("zones")
            if get_api_info and self._due_for_retry("api_info", now):
                tasks.append(get_api_info())
                task_keys.append("api_info")
            if get_io and self._due_for_retry("io_inputs", now):
                tasks.append(get_io(28))
                task_keys.append("io_inputs")
            if get_io and self._due_for_retry("io_outputs", now):
                tasks.append(get_io(29))
                task_keys.append("io_outputs")
            if list_cardholders_filter and self._due_for_retry("cardholders_meta", now):
                tasks.append(list_cardholders_filter({"cardHolderFilter": {"doNotFetchData": True}}))
                task_keys.append("cardholders_meta")
            if get_global_door_control and self._due_for_retry("global_door_control", now):
                tasks.append(get_global_door_control())
                task_keys.append("global_door_control")
            if get_threat_level and self._due_for_retry("threat_level", now):
                tasks.append(get_threat_level())
                task_keys.append("threat_level")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            data: Dict[str, Any] = {
                "doors": [], "areas": [], "zones": [], "api_info": {},
                "io_inputs": [], "io_outputs": [], "cardholder_count": None,
                "global_door_control_active": None, "threat_level": None,
            }
            ok_keys: set[str] = set()
            for key, val in zip(task_keys, results):
                if isinstance(val, Exception):
                    if key != "doors":
                        count = self._key_fail_count.get(key, 0) + 1
                        self._key_fail_count[key] = count
                        backoff = _RETRY_BACKOFF_S[min(count, len(_RETRY_BACKOFF_S)) - 1]
                        self._key_retry_after[key] = now + backoff
                        _LOGGER.warning(
                            "TechPoint: %s fetch failed (retrying in %ss): %s",
                            key,
                            backoff,
                            val,
                        )
                    else:
                        _LOGGER.debug("TechPoint: %s fetch failed: %s", key, val)
                    continue
                if key != "doors":
                    self._key_fail_count.pop(key, None)
                    self._key_retry_after.pop(key, None)
                ok_keys.add(key)
                if key == "cardholders_meta":
                    data["cardholder_count"] = (val or {}).get("count") if isinstance(val, dict) else None
                elif key == "global_door_control":
                    data["global_door_control_active"] = (val or {}).get("status", {}).get("active")
                elif key == "threat_level":
                    data["threat_level"] = (val or {}).get("currentThreatLevel", {}).get("level")
                else:
                    data[key] = val or data.get(key, [])

            self.last_cycle_ok_keys = ok_keys
            return data
        except Exception as e:
            _LOGGER.warning("TechPoint update failed: %s", e)
            raise
