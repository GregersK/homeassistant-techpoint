"""
TechPoint Cloud endpoints og mappere
Base URL: fx https://<tenant>/api/v1

Selvstændig fil (ingen import fra LAN), indeholder ALLE map_* funktioner
for at undgå import-fejl og cirkulære imports.
"""

from __future__ import annotations
from typing import Any, Dict, List

# ----------------------------
# Management / Doors (Cloud)
# ----------------------------
PATH_DOORS_LIST   = "/management/doors"         # GET
PATH_DOOR_STATUS  = "/management/doors/status"  # POST  {doorId, status}

# ----------------------------
# AIA (Cloud)
# ----------------------------
PATH_AREAS_LIST    = "/aia/areas"               # GET
PATH_AREAS_COMMAND = "/aia/areas/command"       # POST {areaId, command}

PATH_ZONES_LIST    = "/aia/zones"               # GET
PATH_ZONE_UPDATE   = "/aia/zones/{zoneId}"      # PUT

# ----------------------------
# Access (Cloud)
# ----------------------------
PATH_USERS_LIST   = "/access/users"             # GET
PATH_USER_CREATE  = "/access/users"             # POST
PATH_USER_UPDATE  = "/access/users/{userId}"    # PUT
PATH_USER_DELETE  = "/access/users/{userId}"    # DELETE
PATH_USER_GROUPS  = "/access/users/{userId}/access-groups"  # PUT

PATH_CARDS_LIST   = "/access/cards"             # GET
PATH_USER_CARDS   = "/access/users/{userId}/cards"          # GET/POST
PATH_CARD_UPDATE  = "/access/cards/{cardId}"                # PUT
PATH_CARD_DELETE  = "/access/cards/{cardId}"                # DELETE

# ----------------------------
# Events (Cloud)
# ----------------------------
PATH_EVENTS       = "/events"                   # GET

# =====================================================================
# Map-funktioner (Cloud)
# =====================================================================

def map_door_list_response(js: Any) -> List[Dict[str, Any]]:
    if isinstance(js, dict):
        itr = js.get("items") or js.get("doors") or []
    elif isinstance(js, list):
        itr = js
    else:
        itr = []
    out: List[Dict[str, Any]] = []
    for d in itr:
        out.append({
            "id":    d.get("id") or d.get("doorId"),
            "name":  d.get("name") or d.get("doorName"),
            "state": d.get("state") or d.get("status") or "Normal",
            "raw":   d,
        })
    return out

def map_area_list_response(js: Any) -> List[Dict[str, Any]]:
    if isinstance(js, dict):
        itr = js.get("items") or js.get("areas") or []
    elif isinstance(js, list):
        itr = js
    else:
        itr = []
    out: List[Dict[str, Any]] = []
    for a in itr:
        out.append({
            "id":    a.get("id") or a.get("areaId"),
            "name":  a.get("name") or a.get("areaName"),
            "state": a.get("state") or a.get("status") or "disarmed",
            "raw":   a,
        })
    return out

def map_user_list_response(js: Any) -> List[Dict[str, Any]]:
    if isinstance(js, dict):
        itr = js.get("items") or js.get("users") or []
    elif isinstance(js, list):
        itr = js
    else:
        itr = []
    out: List[Dict[str, Any]] = []
    for u in itr:
        uid = u.get("id") or u.get("userId") or (isinstance(u.get("id"), dict) and u["id"].get("id"))
        out.append({
            "id":     uid,
            "name":   u.get("name") or u.get("displayName") or (u.get("firstName") and f"{u.get('firstName')} {u.get('lastName') or ''}".strip()) or f"User {uid}",
            "email":  u.get("email"),
            "phone":  u.get("phone"),
            "active": u.get("active", True),
            "raw":    u,
        })
    return out

def map_card_list_response(js: Any) -> List[Dict[str, Any]]:
    if isinstance(js, dict):
        itr = js.get("items") or js.get("cards") or []
    elif isinstance(js, list):
        itr = js
    else:
        itr = []
    out: List[Dict[str, Any]] = []
    for c in itr:
        cid = c.get("id") or c.get("cardId") or (isinstance(c.get("id"), dict) and c["id"].get("id"))
        ch_id = None
        if isinstance(c.get("cardHolderID"), dict):
            ch_id = c["cardHolderID"].get("id")
        else:
            ch_id = c.get("userId")
        out.append({
            "id":         cid,
            "number":     c.get("number") or c.get("cardNumber"),
            "cardholder": ch_id,
            "valid_from": c.get("validFrom"),
            "valid_to":   c.get("validTo"),
            "isBlocked":  c.get("isBlocked", False),
            "active":     c.get("active", True),
            "raw":        c,
        })
    return out

def map_zone_list_response(js: Any) -> List[Dict[str, Any]]:
    if isinstance(js, dict):
        itr = js.get("items") or js.get("zones") or []
    elif isinstance(js, list):
        itr = js
    else:
        itr = []
    out: List[Dict[str, Any]] = []
    for z in itr:
        out.append({
            "id":       z.get("id") or z.get("zoneId"),
            "name":     z.get("name") or z.get("zoneName"),
            "state":    z.get("state") or z.get("status"),
            "alarm":    z.get("alarm") or z.get("inAlarm"),
            "bypassed": z.get("bypassed"),
            "area_id":  z.get("areaId"),
            "raw":      z,
        })
    return out

def map_events_response(js: Any) -> List[Dict[str, Any]]:
    if isinstance(js, dict):
        return js.get("items") or js.get("records") or js.get("events") or []
    return js or []
