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

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch doors, AIA area/zone status, user-defined I/O and cardholder count."""
        try:
            list_areas = getattr(self.client, "list_areas_status", None) or getattr(self.client, "list_areas", None)
            list_zones = getattr(self.client, "list_zones_status", None) or getattr(self.client, "list_zones", None)
            get_api_info = getattr(self.client, "get_api_info", None)
            get_io = getattr(self.client, "get_io_userdefined", None)
            list_cardholders_filter = getattr(self.client, "list_card_holders_filter", None)

            tasks: list = [self.client.list_doors()]
            task_keys = ["doors"]

            if list_areas:
                tasks.append(list_areas())
                task_keys.append("areas")
            if list_zones:
                tasks.append(list_zones())
                task_keys.append("zones")
            if get_api_info:
                tasks.append(get_api_info())
                task_keys.append("api_info")
            if get_io:
                tasks.append(get_io(28))
                task_keys.append("io_inputs")
                tasks.append(get_io(29))
                task_keys.append("io_outputs")
            if list_cardholders_filter:
                tasks.append(list_cardholders_filter({"cardHolderFilter": {"doNotFetchData": True}}))
                task_keys.append("cardholders_meta")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            data: Dict[str, Any] = {
                "doors": [], "areas": [], "zones": [], "api_info": {},
                "io_inputs": [], "io_outputs": [], "cardholder_count": None,
            }
            for key, val in zip(task_keys, results):
                if isinstance(val, Exception):
                    _LOGGER.debug("TechPoint: %s fetch failed: %s", key, val)
                    continue
                if key == "cardholders_meta":
                    data["cardholder_count"] = (val or {}).get("count") if isinstance(val, dict) else None
                else:
                    data[key] = val or data.get(key, [])

            return data
        except Exception as e:
            _LOGGER.warning("TechPoint update failed: %s", e)
            raise
