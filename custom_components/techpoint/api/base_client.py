from __future__ import annotations
from typing import Any, Dict, List, Optional
from homeassistant.core import HomeAssistant

class BaseApiClient:
    def __init__(self, hass: HomeAssistant, base_url: str, entry_data: Dict[str, Any]) -> None:
        self.hass = hass
        self.base_url = base_url.rstrip("/")
        self.data = entry_data

    # ---- Doors / Areas ----
    async def list_doors(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def set_door_status(self, door_id: str | int, status: str) -> Any:
        raise NotImplementedError

    async def list_areas(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def area_command(self, area_id: str | int, command: str) -> Any:
        raise NotImplementedError

    # ---- Users / Cards ----
    async def list_users(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def create_user(self, body: Dict[str, Any]) -> Any:
        raise NotImplementedError

    async def update_user(self, user_id: str | int, body: Dict[str, Any]) -> Any:
        raise NotImplementedError

    async def delete_user(self, user_id: str | int) -> Any:
        raise NotImplementedError

    async def set_user_groups(self, user_id: str | int, add: List[int], remove: List[int]) -> Any:
        raise NotImplementedError

    async def list_cards(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def list_user_cards(self, user_id: str | int) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def create_user_card(self, user_id: str | int, body: Dict[str, Any]) -> Any:
        raise NotImplementedError

    async def update_card(self, card_id: str | int, body: Dict[str, Any]) -> Any:
        raise NotImplementedError

    async def delete_card(self, card_id: str | int) -> Any:
        raise NotImplementedError

    # ---- Zones / Events ----
    async def list_zones(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def update_zone(self, zone_id: str | int, body: Dict[str, Any]) -> Any:
        raise NotImplementedError

    async def get_events(self, params: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # ---- Generic ----
    async def call_api(self, method: str, path: str, params: Optional[Dict[str, Any]], body: Optional[Any]) -> Any:
        raise NotImplementedError
