from __future__ import annotations
from typing import Any, Dict
from datetime import timedelta
import asyncio
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class TechPointCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client,
        name: str,
        update_interval_s: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=update_interval_s),
        )
        self.client = client
        # Keys that have failed at least once — skipped on subsequent polls
        # to avoid spamming the controller's error log. Reset on reload.
        self._disabled_keys: set[str] = set()
        # Keys whose fetch succeeded on the most recent poll cycle. Used to gate
        # stale-entity cleanup so a single transient API failure (which leaves
        # that key's data empty for the cycle) can never be mistaken for a
        # door/zone/output that was actually removed on the controller.
        self.last_cycle_ok_keys: set[str] = set()

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

            tasks: list = [self.client.list_doors()]
            task_keys = ["doors"]

            if list_areas and "areas" not in self._disabled_keys:
                tasks.append(list_areas())
                task_keys.append("areas")
            if list_zones and "zones" not in self._disabled_keys:
                tasks.append(list_zones())
                task_keys.append("zones")
            if get_api_info and "api_info" not in self._disabled_keys:
                tasks.append(get_api_info())
                task_keys.append("api_info")
            if get_io and "io_inputs" not in self._disabled_keys:
                tasks.append(get_io(28))
                task_keys.append("io_inputs")
            if get_io and "io_outputs" not in self._disabled_keys:
                tasks.append(get_io(29))
                task_keys.append("io_outputs")
            if list_cardholders_filter and "cardholders_meta" not in self._disabled_keys:
                tasks.append(list_cardholders_filter({"cardHolderFilter": {"doNotFetchData": True}}))
                task_keys.append("cardholders_meta")
            if get_global_door_control and "global_door_control" not in self._disabled_keys:
                tasks.append(get_global_door_control())
                task_keys.append("global_door_control")
            if get_threat_level and "threat_level" not in self._disabled_keys:
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
                    # First failure for this optional key: disable it for this session
                    # so we don't keep spamming TechPoint with failing requests.
                    if key != "doors":
                        self._disabled_keys.add(key)
                        _LOGGER.warning(
                            "TechPoint: %s fetch failed (disabled until reload): %s",
                            key,
                            val,
                        )
                    else:
                        _LOGGER.debug("TechPoint: %s fetch failed: %s", key, val)
                    continue
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
