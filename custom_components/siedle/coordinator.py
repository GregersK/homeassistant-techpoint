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
        """Fetch doors plus AIA area/zone status from the TechPoint client.

        Supports both LAN and cloud clients by falling back to list_areas/list_zones
        if list_areas_status/list_zones_status are not implemented.
        """
        try:
            # Foretræk eksplicitte *status*-metoder (LAN), men fald tilbage til plain list (Cloud)
            list_areas = getattr(self.client, "list_areas_status", None) or getattr(
                self.client,
                "list_areas",
                None,
            )
            list_zones = getattr(self.client, "list_zones_status", None) or getattr(
                self.client,
                "list_zones",
                None,
            )

            get_api_info = getattr(self.client, "get_api_info", None)

            if list_areas is None or list_zones is None:
                _LOGGER.debug(
                    "TechPoint client %s has no area/zone methods; returning doors only",
                    type(self.client).__name__,
                )
                doors = await self.client.list_doors()
                api_info = {}
                if get_api_info:
                    try:
                        api_info = await get_api_info()
                    except Exception:
                        _LOGGER.debug("Siedle SC-600: get_api_info failed", exc_info=True)
                return {"doors": doors or [], "areas": [], "zones": [], "api_info": api_info or {}}

            tasks = [
                self.client.list_doors(),
                list_areas(),
                list_zones(),
            ]
            if get_api_info:
                tasks.append(get_api_info())

            res = await asyncio.gather(*tasks)
            doors, areas, zones = res[0], res[1], res[2]
            api_info = res[3] if get_api_info and len(res) > 3 else {}
            return {
                "doors": doors or [],
                "areas": areas or [],
                "zones": zones or [],
                "api_info": api_info or {},
            }
        except Exception as e:
            _LOGGER.warning("TechPoint update failed: %s", e)
            raise
