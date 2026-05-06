from __future__ import annotations
from typing import Any, Dict, List


# ------- Door status enums (from TechPoint API schema doorStatus) -------
_DOOR_POSITION_TX = {
    0: "Ukendt",
    1: "Sikret",
    2: "Normal",
    3: "Frigivet",
    4: "Åben",
}

_DOOR_POSITION_CAUSE_TX = {
    0: "Ingen årsag",
    1: "Frigivet med kort",
    2: "Frigivet med udgangsknap",
    3: "Frigivet fjernstyret",
    4: "Frigivet via ugeprogram",
    5: "Frigivet via funktion",
    6: "Blokeret (styring)",
    7: "Blokeret (ugeprogram)",
    8: "Blokeret (funktion)",
}

_DOOR_EXCEPTION_TX = {
    0: "Ingen",
    1: "Blokeret",
    2: "Perm. frigivet",
    3: "Advarsel",
    4: "Holdt åben",
    5: "Brudt op",
    6: "Offline",
}

_DOOR_INTRUSION_TX = {
    0: "Ingen intrusion",
    1: "Intrusion tilkoblet",
    2: "Intrusion frakoblet",
}


def _build_door_status_text(position: Any, exception: Any) -> str:
    """Make a human friendly door status string.

    Focus: what you want to see in HA quickly: held open, forced, offline, etc.
    """
    try:
        exc = int(exception) if exception is not None else 0
    except Exception:  # noqa: BLE001
        exc = 0
    try:
        pos = int(position) if position is not None else 0
    except Exception:  # noqa: BLE001
        pos = 0

    if exc in (4, 5, 6, 3, 1, 2):
        return _DOOR_EXCEPTION_TX.get(exc, "Ukendt")

    # No exception: show current physical position
    return _DOOR_POSITION_TX.get(pos, "Ukendt")

# ------- Paths (LAN API v1.x) -------
# Doors
PATH_DOORS_STATUS_LIST = "/management/doors/status"   # POST
PATH_DOOR_COMMAND      = "/management/doors"          # POST
PATH_DOORS_CONFIG      = "/config/doors/filter"         # POST

# Intrusion (AIA) status/commands
PATH_INTRUSION_STATUS  = "/management/intrusion/status"  # POST
PATH_INTRUSION_COMMAND = "/management/intrusion"         # POST
PATH_INTRUSION_AREAS_CONFIG = "/config/intrusion/areas/filter"   # POST
PATH_INTRUSION_ZONES_CONFIG = "/config/intrusion/zones/filter"   # POST
PATH_INTRUSION_PROFILES = "/config/intrusion/profiles"           # GET

# Access (we eksponerer stadig via services; beholder stierne til senere entiteter)
PATH_ACCESS_GROUPS   = "/access/accessGroups"
PATH_ACCESS_STATIC_TYPES = "/access/static/types"
PATH_CARD_HOLDERS    = "/access/cardHolders"
PATH_CARD_HOLDERS_FILTER = "/access/cardHolders/filter"
PATH_CARDS           = "/access/cards"
PATH_CARDS_FILTER    = "/access/cards/filter"

# Events / WebHook
PATH_EVENTS_WEBHOOK = "/events/webhook"               # POST/DELETE
PATH_EVENTS_STATIC_TYPES = "/events/static/types"     # GET

# Global door control (v1.13.0)
PATH_GLOBAL_DOOR_CONTROL = "/access/globalDoorControl"   # GET/POST

# Threat level (v1.13.0)
PATH_THREAT_LEVEL = "/management/threatLevel"             # GET/POST

# User-defined I/O (v1.13.0) – ioType 28=inputs, 29=outputs
PATH_IO_USERDEFINED = "/config/io/userdefined"            # GET/POST

# ------- Builders -------
def build_doors_status_body(include_access_rights: bool = False) -> Dict[str, Any]:
    return {"doorFilter": {"includeAccessRights": bool(include_access_rights)}}

def build_intrusion_filter(io_type: int, include_status_text: bool = True) -> Dict[str, Any]:
    # ioType: 16=Zone, 17=Area, 18=Wired zone, 19=Area group
    return {"intrusionFilter": {"ioType": io_type, "includeStatusText": bool(include_status_text)}}

def build_door_command(door_ids: List[int], new_state: int) -> Dict[str, Any]:
    # new_state: 0 Normal, 1 Close(Secured), 2 Open(Release), 3 Block, 4 PermOpen
    return {
        "doorCommand": {
            "doorIDs": {"ids": [{"id": int(d)} for d in door_ids]},
            "newDoorState": int(new_state),
        }
    }

# ------- Mappers -------
def _extract_id(obj: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get("id") or obj.get("Id")
    return obj

def map_doors_status_response(js: Any) -> List[Dict[str, Any]]:
    records = (js or {}).get("records") or []
    out: List[Dict[str, Any]] = []
    for r in records:
        # Nogle firmware-versioner bruger "id", andre "doorId"/"doorID"
        did = _extract_id(
            r.get("id")
            or r.get("doorId")
            or r.get("doorID")
            or r.get("door_id")
        )
        pos = r.get("position")
        cause = r.get("positionCause")
        exception = r.get("exception")
        intrusion_state = r.get("intrusionState")

        # IMPORTANT: door-status indeholder typisk IKKE dørnavn. Hvis vi sætter name=None her,
        # kan vi komme til at overskrive navnet fra /config/doors/filter under merge.
        name = (
            r.get("name")
            or r.get("doorName")
            or r.get("displayName")
            or r.get("text")
        )

        rec: Dict[str, Any] = {
            "id": did,
            "position": pos,          # 1 Secured, 2 Unsecure, 3 Released, 4 Open
            "positionCause": cause,   # per API
            "exception": exception,   # 0 none, 1 block, 2 permOpen (if supported)
            "intrusionState": intrusion_state,
            "issabotage": r.get("issabotage"),  # bool, added in API v1.13.0
            "position_text": _DOOR_POSITION_TX.get(int(pos), "Ukendt") if pos is not None else "Ukendt",
            "position_cause_text": _DOOR_POSITION_CAUSE_TX.get(int(cause), "Ukendt") if cause is not None else None,
            "exception_text": _DOOR_EXCEPTION_TX.get(int(exception), "Ukendt") if exception is not None else None,
            "intrusion_state_text": _DOOR_INTRUSION_TX.get(int(intrusion_state), "Ukendt") if intrusion_state is not None else None,
            "status_text": _build_door_status_text(pos, exception),
            "raw": r,
        }
        if name:
            rec["name"] = name

        out.append(rec)
    return out

def map_intrusion_status_response(js: Any) -> List[Dict[str, Any]]:
    records = (js or {}).get("records") or []
    out: List[Dict[str, Any]] = []
    for r in records:
        rid = _extract_id(r.get("id"))  # tabel-id objekt -> int
        io_id = _extract_id(r.get("ioId") or r.get("ioID") or r.get("io_id"))
        io_type = r.get("ioType")
        state = r.get("state")
        flags = r.get("stateFlags") or []
        state_tx = r.get("stateText")
        name = (
            r.get("name")
            or r.get("ioName")
            or r.get("displayName")
            or r.get("text")
        )
        out.append(
            {
                "id": rid,
                "name": name,
                "io_id": io_id,
                "io_type": io_type,     # 16 zone, 17 area, ...
                "state": state,         # 0..6
                "state_flags": flags,
                "state_text": state_tx,
                "raw": r,
            }
        )
    return out

# Simple pass-through mappers for future access entities
def map_access_groups_response(js: Any) -> List[Dict[str, Any]]:
    return ((js or {}).get("records")) or []

def map_card_list_response(js: Any) -> List[Dict[str, Any]]:
    return ((js or {}).get("records")) or []

def map_user_list_response(js: Any) -> List[Dict[str, Any]]:
    return ((js or {}).get("records")) or []
