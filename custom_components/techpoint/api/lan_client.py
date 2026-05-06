from __future__ import annotations
import asyncio, json, logging as _logging
from typing import Any, Dict, Optional, List, Union

_LOGGER = _logging.getLogger(__name__)
from aiohttp import ClientError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL_LAN

from .base_client import BaseApiClient
from ..endpoints_lan import (
    PATH_DOORS_CONFIG,
    PATH_DOORS_STATUS_LIST,
    PATH_DOOR_COMMAND,
    build_doors_status_body,
    build_door_command,
    PATH_INTRUSION_STATUS,
    PATH_INTRUSION_COMMAND,
    PATH_INTRUSION_AREAS_CONFIG,
    PATH_INTRUSION_ZONES_CONFIG,
    PATH_INTRUSION_PROFILES,
    build_intrusion_filter,
    PATH_ACCESS_GROUPS,
    PATH_ACCESS_STATIC_TYPES,
    PATH_CARD_HOLDERS,
    PATH_CARD_HOLDERS_FILTER,
    PATH_CARDS,
    PATH_CARDS_FILTER,
    PATH_EVENTS_WEBHOOK,
    PATH_EVENTS_STATIC_TYPES,
    PATH_GLOBAL_DOOR_CONTROL,
    PATH_THREAT_LEVEL,
    PATH_IO_USERDEFINED,
    map_doors_status_response,
    map_intrusion_status_response,
    map_access_groups_response,
    map_card_list_response,
    map_user_list_response,
)


def _int_id(v: Any) -> Optional[int]:
    """Normalisér id-felter (kan være int, str, {'id': 1}, eller {'id': {'id': 1}})."""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except Exception:
            return None
    if isinstance(v, dict):
        inner = v.get("id") or v.get("Id")
        if isinstance(inner, dict):
            inner = inner.get("id") or inner.get("Id")
        return _int_id(inner)
    try:
        return int(v)
    except Exception:
        return None

def _norm_id(x: Any) -> Any:
    if isinstance(x, dict):
        return x.get("id") or x.get("Id") or x.get("doorId") or x.get("userId")
    return x

def _records(js: Any) -> list[dict[str, Any]]:
    """Return records list from TechPoint responses (handles firmware variations)."""
    if js is None:
        return []
    if isinstance(js, list):
        # Some endpoints may return bare arrays
        return [x for x in js if isinstance(x, dict)]
    if isinstance(js, dict):
        recs = js.get("records")
        if recs is None:
            recs = js.get("items")
        if recs is None:
            recs = js.get("doors")
        if recs is None:
            recs = js.get("areas")
        if recs is None:
            recs = js.get("zones")
        if isinstance(recs, list):
            return [x for x in recs if isinstance(x, dict)]
        return []
    return []

def _io_records(js: Any) -> list[dict[str, Any]]:
    """Return records list from IO userdefined response (handles extra field name variants)."""
    if js is None:
        return []
    if isinstance(js, list):
        return [x for x in js if isinstance(x, dict)]
    if isinstance(js, dict):
        for key in ("records", "items", "ios", "ioRecords", "ioList", "userDefinedIOs"):
            recs = js.get(key)
            if isinstance(recs, list):
                return [x for x in recs if isinstance(x, dict)]
        return []
    return []

class LanApiClient(BaseApiClient):
    """LAN klient med Basic eller Bearer alt efter din konfiguration."""

    def __init__(self, hass, base_url, entry_data) -> None:
        super().__init__(hass, base_url, entry_data)
        verify_ssl = bool(entry_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL_LAN))
        self.session = async_get_clientsession(hass, verify_ssl=verify_ssl)
        self._token = entry_data.get("lan_token")
        self._intrusion_profile_id: Optional[int] = None

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _request(
        self, method: str, path: str, params: Optional[Dict[str, Any]] = None, body: Optional[Any] = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._headers()
        # TechPoint requires Content-Type: application/json AND a valid JSON body on every
        # request (RapidJSON parser rejects missing body when Content-Type is set). Send {}
        # for requests that have no explicit body.
        effective_body = body if body is not None else {}
        auth = None
        if self.data.get("lan_username") or self.data.get("lan_password"):
            from aiohttp import BasicAuth
            auth = BasicAuth(self.data.get("lan_username") or "", self.data.get("lan_password") or "")
        try:
            async with self.session.request(method, url, headers=headers, params=params, json=effective_body, auth=auth, timeout=25) as resp:
                # Giv bedre fejlbeskeder end aiohttp's raise_for_status (som ikke viser body)
                if resp.status >= 400:
                    txt = await resp.text()
                    try:
                        js_err = json.loads(txt) if txt else None
                    except Exception:
                        js_err = None
                    detail = js_err or txt
                    raise RuntimeError(
                        f"LAN API error: {resp.status}, message={detail}, url='{url}'"
                    )
                ctype = resp.headers.get("Content-Type", "")
                if "json" in ctype:
                    return await resp.json(content_type=None)
                txt = await resp.text()
                try: return json.loads(txt)
                except Exception: return txt
        except asyncio.TimeoutError as e:
            raise RuntimeError("LAN API timeout") from e
        except ClientError as e:
            raise RuntimeError(f"LAN API error: {e}") from e

    # ---------- Doors ----------
    async def list_doors(self) -> List[Dict[str, Any]]:
        """Return doors with merged config (names) + status."""
        body = build_doors_status_body(False)

        cfg = await self._request("POST", PATH_DOORS_CONFIG, body=body)
        cfg_records = _records(cfg)

        status_js = await self._request("POST", PATH_DOORS_STATUS_LIST, body=body)
        status_records = map_doors_status_response(status_js)

        status_by_id: dict[int, dict[str, Any]] = {
            int(r["id"]): r for r in (status_records or []) if r.get("id") is not None
        }

        merged: list[dict[str, Any]] = []
        seen: set[int] = set()

        for d in cfg_records:
            # Nogle varianter wrapper door objektet
            if isinstance(d, dict) and isinstance(d.get("door"), dict):
                d = d["door"]
            did = _int_id(d.get("id") or d.get("doorId") or d.get("doorID") or d.get("Id"))
            if did is None:
                continue
            cfg_name = (
                d.get("name")
                or d.get("Name")
                or d.get("doorName")
                or d.get("displayName")
                or d.get("text")
            )
            door: dict[str, Any] = {
                "id": did,
                "name": cfg_name,
                "type": d.get("type"),
                "instance_number": d.get("instanceNumber"),
                "techpoint_link": _int_id(d.get("techPointLink")),
                "elevator_link": _int_id(d.get("elevatorLink")),
            }
            st = status_by_id.get(did)
            if st:
                door.update(st)
                # Bevar navnet fra config hvis status ikke har navn
                if not door.get("name") and cfg_name:
                    door["name"] = cfg_name
            merged.append(door)
            seen.add(did)

        # status records without matching config record
        for st in status_records or []:
            sid = st.get("id")
            if sid is None:
                continue
            sid = int(sid)
            if sid in seen:
                continue
            merged.append(st)
            seen.add(sid)

        return merged

    async def set_door_status(self, door_id: Union[str, int, dict], status: Union[int, str]) -> Any:
        door_id = int(_norm_id(door_id))
        STATE_TO_INT = {
            "normal": 0,
            "close": 1,
            "secure": 1,
            "open": 2,
            "release": 2,
            "permanentrelease": 4,  # TechPoint: PermOpen = 4
            "block": 3,
        }
        if isinstance(status, int):
            new_state = status
        else:
            key = str(status).replace(" ", "").lower()
            new_state = STATE_TO_INT.get(key, 0)
        body = build_door_command([door_id], new_state)
        return await self._request("POST", PATH_DOOR_COMMAND, body=body)

    # ---------- Intrusion (AIA) ----------
    async def list_areas_status(self) -> List[Dict[str, Any]]:
        """Return intrusion areas with merged config (names) + status."""
        cfg = await self._request("POST", PATH_INTRUSION_AREAS_CONFIG, body=build_intrusion_filter(17, False))
        cfg_records = _records(cfg)

        st_js = await self._request("POST", PATH_INTRUSION_STATUS, body=build_intrusion_filter(17, True))
        st_records = map_intrusion_status_response(st_js)

        st_by_io: dict[int, dict[str, Any]] = {}
        for r in st_records or []:
            key = r.get("io_id") or r.get("id")
            if key is None:
                continue
            st_by_io[int(key)] = r

        merged: list[dict[str, Any]] = []
        seen: set[int] = set()

        for a in cfg_records:
            io_id = _int_id(a.get("ioId"))
            if io_id is None:
                continue
            rec: dict[str, Any] = {
                "id": io_id,
                "io_id": io_id,
                "io_type": int(a.get("ioType", 17)),
                "name": (a.get("name") or a.get("Name") or a.get("ioName") or a.get("displayName") or a.get("text")),
                "children_io_ids": [ _int_id(x) for x in (a.get("childrenIoIDs") or {}).get("ids", []) ] if isinstance(a.get("childrenIoIDs"), dict) else None,
            }
            st = st_by_io.get(io_id)
            if st:
                rec.update(st)
                # status mapping already has io_type/io_id etc
                if not rec.get("name"):
                    rec["name"] = (a.get("name") or a.get("Name") or a.get("ioName") or a.get("displayName") or a.get("text"))
            merged.append(rec)
            seen.add(io_id)

        for st in st_records or []:
            key = st.get("io_id") or st.get("id")
            if key is None:
                continue
            key = int(key)
            if key in seen:
                continue
            merged.append(st)
            seen.add(key)

        return merged

    async def list_zones_status(self) -> List[Dict[str, Any]]:
        """Return intrusion zones with merged config (names) + status."""
        cfg = await self._request("POST", PATH_INTRUSION_ZONES_CONFIG, body=build_intrusion_filter(16, False))
        cfg_records = _records(cfg)

        st_js = await self._request("POST", PATH_INTRUSION_STATUS, body=build_intrusion_filter(16, True))
        st_records = map_intrusion_status_response(st_js)

        st_by_io: dict[int, dict[str, Any]] = {}
        for r in st_records or []:
            key = r.get("io_id") or r.get("id")
            if key is None:
                continue
            st_by_io[int(key)] = r

        merged: list[dict[str, Any]] = []
        seen: set[int] = set()

        for z in cfg_records:
            io_id = _int_id(z.get("ioId"))
            if io_id is None:
                continue
            rec: dict[str, Any] = {
                "id": io_id,
                "io_id": io_id,
                "io_type": int(z.get("ioType", 16)),
                "name": (z.get("name") or z.get("Name") or z.get("ioName") or z.get("displayName") or z.get("text")),
                "type": z.get("type"),
            }
            st = st_by_io.get(io_id)
            if st:
                rec.update(st)
                if not rec.get("name"):
                    rec["name"] = (z.get("name") or z.get("Name") or z.get("ioName") or z.get("displayName") or z.get("text"))
            merged.append(rec)
            seen.add(io_id)

        for st in st_records or []:
            key = st.get("io_id") or st.get("id")
            if key is None:
                continue
            key = int(key)
            if key in seen:
                continue
            merged.append(st)
            seen.add(key)

        return merged

    async def _ensure_intrusion_profile_id(self) -> Optional[int]:
        """Find (and cache) a usable intrusion profile id.

        Some installations require intrusionProfileID to be specified; if omitted TechPoint may
        default to 0 which fails. We therefore try to fetch the first profile from
        /config/intrusion/profiles and cache its id.
        """
        if self._intrusion_profile_id is not None:
            return self._intrusion_profile_id
        try:
            js = await self._request("GET", PATH_INTRUSION_PROFILES)
            recs = _records(js)
            for r in recs:
                pid = _int_id(r.get("id") or r.get("Id"))
                if pid is not None:
                    self._intrusion_profile_id = int(pid)
                    return self._intrusion_profile_id
        except Exception:
            return None
        return None

    async def intrusion_command(self, io_ids: List[int], command: int, profile_id: Optional[int] = None) -> Any:
        """Send arm/disarm m.m. til intrusion.

        VIGTIGT (jf. Swagger): intrusionProfileID bør typisk udelades (eller være null),
        så profilen der er linket til API-brugeren anvendes. Feltet må kun angives hvis
        API-brugeren er systemadministrator.
        """
        cmd: Dict[str, Any] = {
            "command": int(command),
            "ioIDs": {"ids": [{"id": int(i)} for i in io_ids]},
        }
        if profile_id is None:
            profile_id = await self._ensure_intrusion_profile_id()
        if profile_id is not None:
            cmd["intrusionProfileID"] = {"id": int(profile_id)}

        body = {"intrusionCommand": cmd}
        return await self._request("POST", PATH_INTRUSION_COMMAND, body=body)

    # ---------- Access (services lige nu) ----------
    async def get_access_groups(self) -> List[Dict[str, Any]]:
        js = await self._request("GET", PATH_ACCESS_GROUPS)
        return map_access_groups_response(js)

    async def create_card_holder(self, body: Dict[str, Any]) -> Any:
        return await self._request("POST", PATH_CARD_HOLDERS, body=body)

    async def create_card(self, body: Dict[str, Any]) -> Any:
        return await self._request("POST", PATH_CARDS, body=body)

    async def list_cards(self) -> List[Dict[str, Any]]:
        try:
            js = await self._request("GET", PATH_CARDS)
        except Exception:
            js = []
        return map_card_list_response(js)


    async def list_card_holders(self) -> List[Dict[str, Any]]:
        """List cardholders (GET /access/cardHolders)."""
        js = await self._request("GET", PATH_CARD_HOLDERS)
        return _records(js)

    async def list_card_holders_filter(self, filter_body: Dict[str, Any]) -> Any:
        """Filter cardholders (POST /access/cardHolders/filter).

        Returns the raw response dict so callers can read both 'records' and 'count'.
        """
        return await self._request("POST", PATH_CARD_HOLDERS_FILTER, body=filter_body)

    async def update_card_holder(self, body: Dict[str, Any]) -> Any:
        """Update cardholder (PUT /access/cardHolders). Body must include id."""
        return await self._request("PUT", PATH_CARD_HOLDERS, body=body)

    async def delete_card_holder(self, *, id: Optional[int] = None, ext_id: Optional[str] = None) -> Any:
        """Delete cardholder (DELETE /access/cardHolders?id.id=<id> or id.extId=<extId>)."""
        params: Dict[str, Any] = {}
        if id is not None:
            params["id.id"] = int(id)
        elif ext_id:
            params["id.extId"] = str(ext_id)
        else:
            raise ValueError("delete_card_holder requires id or ext_id")
        return await self._request("DELETE", PATH_CARD_HOLDERS, params=params)

    async def get_card_option_types(self) -> Any:
        """Fetch supported card options/types (GET /access/static/types)."""
        return await self._request("GET", PATH_ACCESS_STATIC_TYPES)

    async def list_cards_filter(self, filter_body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter cards (POST /access/cards/filter)."""
        js = await self._request("POST", PATH_CARDS_FILTER, body=filter_body)
        return map_card_list_response(js)

    async def update_card(self, card_id: int, body: Dict[str, Any]) -> Any:
        """Update card (PUT /access/cards)."""
        b = dict(body or {})
        # Ensure id is present in body
        if "id" not in b:
            b["id"] = {"id": int(card_id)}
        return await self._request("PUT", PATH_CARDS, body=b)

    async def delete_card(self, card_id: int) -> Any:
        """Delete card (DELETE /access/cards?id.id=<id>)."""
        return await self._request("DELETE", PATH_CARDS, params={"id.id": int(card_id)})

    async def list_users(self) -> List[Dict[str, Any]]:
        return map_user_list_response([])  # ingen særskilt users endpoint på LAN

    async def get_api_info(self) -> Any:
        """Return API version info (GET /info/api)."""
        return await self._request("GET", "/info/api")

    # ---------- Events / WebHook (LAN) ----------
    async def get_event_types_static_config(self) -> Any:
        """Fetch static event type configuration (GET /events/static/types)."""
        return await self._request("GET", PATH_EVENTS_STATIC_TYPES)

    async def set_events_webhook(
        self,
        *,
        url: str,
        event_filter: Optional[Dict[str, Any]] = None,
        auth_type: str = "None",
        user_name: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Any:
        """Configure TechPoint to POST events to a webhook URL (POST /events/webhook)."""
        inner: Dict[str, Any] = {
            "url": str(url),
            "authType": str(auth_type),
            "eventFilter": event_filter or {},
        }
        if user_name:
            inner["userName"] = str(user_name)
        if password:
            inner["password"] = str(password)
        return await self._request("POST", PATH_EVENTS_WEBHOOK, body={"eventWebHook": inner})

    async def delete_events_webhook(self) -> Any:
        """Remove webhook configuration (DELETE /events/webhook)."""
        return await self._request("DELETE", PATH_EVENTS_WEBHOOK)

    # ---------- Global door control (v1.13.0) ----------
    async def get_global_door_control(self) -> Any:
        """Fetch current global door control state (GET /access/globalDoorControl)."""
        return await self._request("GET", PATH_GLOBAL_DOOR_CONTROL)

    async def set_global_door_control(self, active: bool) -> Any:
        """Open or close all globally-controlled doors (POST /access/globalDoorControl)."""
        return await self._request("POST", PATH_GLOBAL_DOOR_CONTROL, body={"status": {"active": bool(active)}})

    # ---------- Threat level (v1.13.0) ----------
    async def get_threat_level(self) -> Any:
        """Fetch current threat level (GET /management/threatLevel)."""
        return await self._request("GET", PATH_THREAT_LEVEL)

    async def set_threat_level(self, level: int) -> Any:
        """Set threat level 0–4 (POST /management/threatLevel).

        0=off, 1=normal, 2=level 1, 3=level 2, 4=level 3
        """
        return await self._request("POST", PATH_THREAT_LEVEL, body={"threatLevel": {"newThreatlevel": int(level)}})

    # ---------- User-defined I/O (v1.13.0) ----------
    async def get_io_userdefined(self, io_type: int) -> List[Dict[str, Any]]:
        """Fetch user-defined inputs (28) or outputs (29) with their current state.

        Per TechPoint Swagger spec v1.13.0:
          GET /config/io/userdefined?ioType=N (required query param, 28 or 29)

        Response per userDefinedIOs schema:
          {id: int, name: str, iotype: int, techpoint: int,
           state: int (0=passive, 2=active), statename: str, time: datetime}

        TP firmware also parses the request body and rejects it with
        "Expected ioFilter member" if the body is empty `{}` (the default that
        _request adds for Content-Type: application/json compliance). We send
        `{"ioFilter": {"ioType": N}}` so TP accepts it on every firmware variant.
        """
        js = await self._request(
            "GET",
            PATH_IO_USERDEFINED,
            params={"ioType": int(io_type)},
            body={"ioFilter": {"ioType": int(io_type)}},
        )
        out: List[Dict[str, Any]] = []
        for raw in _io_records(js):
            # Filter client-side too in case TP returns mixed types
            r_type = raw.get("iotype")
            if r_type is None:
                r_type = raw.get("ioType")
            try:
                r_type = int(r_type) if r_type is not None else -1
            except Exception:
                r_type = -1
            if r_type != int(io_type):
                continue
            r = dict(raw)
            # Normalize: entities use "ioType" — copy from "iotype" (per spec)
            if "ioType" not in r:
                r["ioType"] = r_type
            out.append(r)
        return out

    async def set_io_userdefined(self, body: Dict[str, Any]) -> Any:
        """Set active/passive state for user-defined I/O (POST /config/io/userdefined).

        Body: {"ids": [{"id": 0}], "status": 2}  – status at top level (0=passive, 2=active), id-only objects in ids array
        """
        return await self._request("POST", PATH_IO_USERDEFINED, body=body)

