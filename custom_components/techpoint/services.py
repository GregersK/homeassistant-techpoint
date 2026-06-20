from __future__ import annotations

from typing import Any, Dict, Iterable

import yaml

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .util import find_by_id, normalize_id, parse_techpoint_unique_id, UID_KIND_TO_DATA_KEY


def _resolve_entry_id(hass: HomeAssistant, entry_id: str | None) -> str:
    dom = hass.data.get(DOMAIN) or {}
    entry_ids = [k for k in dom if k != "_services_registered"]
    if entry_id:
        if entry_id not in dom:
            raise ValueError(f"Unknown entry_id: {entry_id!r}")
        return entry_id
    if len(entry_ids) == 1:
        return entry_ids[0]
    if not entry_ids:
        raise ValueError("No TechPoint integration found")
    raise ValueError(
        f"Multiple TechPoint entries found – please specify entry_id. Available: {entry_ids}"
    )


def _get_entry(hass: HomeAssistant, entry_id: str | None) -> Dict[str, Any]:
    return (hass.data.get(DOMAIN) or {})[_resolve_entry_id(hass, entry_id)]


def _get_client(hass: HomeAssistant, entry_id: str | None):
    return _get_entry(hass, entry_id)["client"]


def _get_coordinator(hass: HomeAssistant, entry_id: str | None):
    return _get_entry(hass, entry_id)["coordinator"]


def _fire(hass: HomeAssistant, event: str, payload: Dict[str, Any]) -> None:
    hass.bus.async_fire(event, payload)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _cleanup_orphan_devices_for_entry(hass: HomeAssistant, entry_id: str) -> int:
    """Remove devices for a config entry that have zero entities."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    removed = 0
    for dev in dr.async_entries_for_config_entry(dev_reg, entry_id):
        # Never remove the controller device
        if (DOMAIN, entry_id) in (dev.identifiers or set()):
            continue

        ents = er.async_entries_for_device(ent_reg, dev.id)
        if ents:
            continue

        dev_reg.async_remove_device(dev.id)
        removed += 1

    return removed


STALE_MISSING_THRESHOLD = 3


def _valid_ids_for_key(snapshot: Dict[str, Any], data_key: str) -> set[str]:
    """Return the set of current TechPoint object ids (as strings) for a data key."""
    ids: set[str] = set()
    for item in snapshot.get(data_key) or []:
        rid = normalize_id((item or {}).get("id"))
        if rid is not None:
            ids.add(str(rid))
    return ids


def _stale_entity_ids_for_entry(
    hass: HomeAssistant, entry_id: str, *, require_consecutive_misses: bool
) -> list[str]:
    """Return entity_ids whose underlying door/zone/area/IO no longer exists on the controller.

    Only considers resource kinds whose most recent poll succeeded (coordinator.last_cycle_ok_keys),
    so a single transient API failure can never be mistaken for a removed door/output. When
    require_consecutive_misses is True (the automatic background pass), an entity must be reported
    missing on STALE_MISSING_THRESHOLD consecutive checks before it's returned, to ride out brief
    glitches. The manual service passes False to act immediately on the user's explicit request.
    """
    entry_data = (hass.data.get(DOMAIN) or {}).get(entry_id) or {}
    coordinator = entry_data.get("coordinator")
    if coordinator is None or not coordinator.last_update_success:
        return []

    snapshot = coordinator.data or {}
    ok_keys = getattr(coordinator, "last_cycle_ok_keys", set())
    ent_reg = er.async_get(hass)
    missing_counts: dict[str, int] = entry_data.setdefault("_stale_missing_counts", {})

    stale: list[str] = []
    seen: set[str] = set()

    for ent in er.async_entries_for_config_entry(ent_reg, entry_id):
        if ent.platform != DOMAIN or not ent.unique_id:
            continue
        parsed = parse_techpoint_unique_id(entry_id, ent.unique_id)
        if parsed is None:
            continue
        kind, obj_id, _sub = parsed
        data_key = UID_KIND_TO_DATA_KEY[kind]
        if data_key not in ok_keys:
            # Last poll for this resource type failed/disabled — don't trust absence.
            continue
        if obj_id in _valid_ids_for_key(snapshot, data_key):
            missing_counts.pop(ent.unique_id, None)
            continue
        seen.add(ent.unique_id)
        count = missing_counts.get(ent.unique_id, 0) + 1
        missing_counts[ent.unique_id] = count
        if not require_consecutive_misses or count >= STALE_MISSING_THRESHOLD:
            stale.append(ent.entity_id)

    for uid in [u for u in missing_counts if u not in seen]:
        missing_counts.pop(uid, None)

    return stale


def _cleanup_stale_entities_for_entry(
    hass: HomeAssistant, entry_id: str, *, require_consecutive_misses: bool
) -> int:
    """Remove entities returned by _stale_entity_ids_for_entry. Returns count removed."""
    stale_ids = _stale_entity_ids_for_entry(hass, entry_id, require_consecutive_misses=require_consecutive_misses)
    if not stale_ids:
        return 0
    ent_reg = er.async_get(hass)
    for entity_id in stale_ids:
        ent_reg.async_remove(entity_id)
    entry_data = (hass.data.get(DOMAIN) or {}).get(entry_id) or {}
    entry_data.get("_stale_missing_counts", {}).clear()
    return len(stale_ids)


_DOOR_SUB_ORDER = ["lock", "open", "sabotage", "status", "mode", "pulse"]


def _build_dashboard_view(hass: HomeAssistant, entry_id: str) -> Dict[str, Any]:
    """Build a Lovelace view (dict) with ready-made cards for this entry's doors,
    outputs, inputs, zones and areas, grouped from the current entity registry +
    coordinator snapshot (for friendly door names)."""
    entry_data = (hass.data.get(DOMAIN) or {})[entry_id]
    coordinator = entry_data["coordinator"]
    snapshot = coordinator.data or {}
    ent_reg = er.async_get(hass)

    doors: dict[str, dict[str, str]] = {}
    outputs: list[str] = []
    inputs: list[str] = []
    zones: list[str] = []
    areas: list[str] = []
    controller: list[str] = []

    for ent in er.async_entries_for_config_entry(ent_reg, entry_id):
        if ent.platform != DOMAIN or not ent.unique_id or ent.disabled:
            continue
        parsed = parse_techpoint_unique_id(entry_id, ent.unique_id)
        if parsed is None:
            controller.append(ent.entity_id)
            continue
        kind, obj_id, sub = parsed
        if kind == "door":
            doors.setdefault(obj_id, {})[sub or ""] = ent.entity_id
        elif kind == "io_output":
            outputs.append(ent.entity_id)
        elif kind == "io_input":
            inputs.append(ent.entity_id)
        elif kind == "zone":
            zones.append(ent.entity_id)
        elif kind == "area":
            areas.append(ent.entity_id)

    cards: list[dict[str, Any]] = []

    for door_id, by_sub in sorted(doors.items(), key=lambda kv: int(kv[0])):
        door_data = find_by_id(snapshot.get("doors"), int(door_id)) or {}
        name = door_data.get("name") or f"Dør {door_id}"
        entities = [by_sub[s] for s in _DOOR_SUB_ORDER if s in by_sub]
        if entities:
            cards.append({"type": "entities", "title": name, "entities": entities})

    if outputs:
        cards.append({"type": "entities", "title": "Udgange", "entities": sorted(outputs)})
    if inputs:
        cards.append({"type": "entities", "title": "Indgange", "entities": sorted(inputs)})
    if zones:
        cards.append({"type": "entities", "title": "Zoner", "entities": sorted(zones)})
    for area_entity in sorted(areas):
        cards.append({"type": "alarm-panel", "entity": area_entity, "states": ["arm_away", "arm_home"]})
    if controller:
        cards.append({"type": "entities", "title": "Controller", "entities": sorted(controller)})

    return {"title": "TechPoint", "path": "techpoint", "cards": cards}


def _int_id_local(v: Any):
    """Try to extract integer id from TechPoint crossId-ish structures."""
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
        return _int_id_local(inner)
    try:
        return int(v)
    except Exception:
        return None


async def _fetch_max_id_via_filter(client, filter_key: str, limit: int = 1000, max_pages: int = 50):
    """Fetch records via TechPoint filter endpoints and return current max numeric id."""
    max_id = 0
    skip = 0
    for _ in range(max_pages):
        filter_body = {filter_key: {"limitCount": limit, "skipCount": skip}}
        if filter_key == "cardHolderFilter":
            raw = await client.list_card_holders_filter(filter_body)
            records = raw.get("records", []) if isinstance(raw, dict) else (raw or [])
        else:
            records = await client.list_cards_filter(filter_body)
        if not records:
            break
        for r in records:
            rid = _int_id_local((r or {}).get("id"))
            if rid and rid > max_id:
                max_id = rid
        if len(records) < limit:
            break
        skip += limit
    return max_id


async def _ensure_cross_id_has_numeric_id(client, kind: str, body: dict):
    """Ensure body['id'] exists and contains a numeric id; auto-assign next free id if missing."""
    id_obj = body.get("id")
    # Accept shorthand forms
    if id_obj is None or not isinstance(id_obj, dict):
        id_obj = {} if id_obj is None else {"id": id_obj}
    numeric = _int_id_local(id_obj.get("id"))
    if numeric is None:
        filter_key = "cardHolderFilter" if kind == "cardholder" else "cardFilter"
        max_existing = await _fetch_max_id_via_filter(client, filter_key)
        id_obj["id"] = max_existing + 1
    body["id"] = id_obj
    return body


async def async_register_services(hass: HomeAssistant) -> None:
    """Register TechPoint services."""

    # ---------- GENERIC ----------
    async def call_api(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.call_api(
            call.data["method"],
            call.data["path"],
            call.data.get("params"),
            call.data.get("body"),
        )
        _fire(hass, f"{DOMAIN}_call_api_result", {"result": res})
        return {"result": res}

    async def get_cache(call: ServiceCall):
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        snap = coord.data or {}
        _fire(hass, f"{DOMAIN}_cache", {"entry_id": call.data.get("entry_id"), **snap})
        return {"cache": snap}

    # ---------- DOORS ----------
    async def management_set_door_status(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.set_door_status(call.data["door_id"], call.data["status"])
        _fire(hass, f"{DOMAIN}_management_set_door_status_result", {"result": res})
        return {"result": res}

    async def door_set_status_by_entity(call: ServiceCall):
        entity_ids = _as_list(call.data.get("entity_id"))
        status = call.data["status"]
        handled: list[dict[str, Any]] = []

        for eid in entity_ids:
            st = hass.states.get(eid)
            if st is None:
                handled.append({"entity_id": eid, "ok": False, "error": "entity_not_found"})
                continue

            entry_id = st.attributes.get("entry_id")
            door_id = st.attributes.get("door_id")
            if not entry_id or door_id is None:
                handled.append({"entity_id": eid, "ok": False, "error": "missing_entry_or_door_id"})
                continue

            client = _get_client(hass, entry_id)
            await client.set_door_status(door_id, status)
            handled.append({"entity_id": eid, "ok": True, "entry_id": entry_id, "door_id": door_id})

        # Refresh only once per unique entry id
        for entry_id in sorted({h.get("entry_id") for h in handled if h.get("ok") and h.get("entry_id")}) :
            coord = _get_coordinator(hass, entry_id)
            await coord.async_request_refresh()

        return {"handled": handled}

    async def refresh(call: ServiceCall):
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        await coord.async_request_refresh()
        return {"ok": True}

    async def cleanup_orphan_devices(call: ServiceCall):
        # If entry_id is given, clean that one; otherwise clean all TechPoint entries
        entry_id = call.data.get("entry_id")
        removed_total = 0
        if entry_id:
            removed_total = _cleanup_orphan_devices_for_entry(hass, entry_id)
        else:
            for eid in [k for k in (hass.data.get(DOMAIN) or {}).keys() if k != "_services_registered"]:
                removed_total += _cleanup_orphan_devices_for_entry(hass, eid)
        return {"removed": removed_total}

    async def cleanup_stale_entities(call: ServiceCall):
        # Remove entities whose door/zone/area/IO no longer exists on the controller
        # (e.g. a door was deleted in TechPoint), then drop any devices left empty by that.
        entry_id = call.data.get("entry_id")
        entry_ids = (
            [entry_id]
            if entry_id
            else [k for k in (hass.data.get(DOMAIN) or {}).keys() if k != "_services_registered"]
        )
        removed_entities = 0
        removed_devices = 0
        for eid in entry_ids:
            removed_entities += _cleanup_stale_entities_for_entry(hass, eid, require_consecutive_misses=False)
            removed_devices += _cleanup_orphan_devices_for_entry(hass, eid)
        return {"removed_entities": removed_entities, "removed_devices": removed_devices}

    async def generate_dashboard_yaml(call: ServiceCall):
        try:
            entry_id = _resolve_entry_id(hass, call.data.get("entry_id"))
            view = _build_dashboard_view(hass, entry_id)
            yaml_text = yaml.safe_dump({"views": [view]}, sort_keys=False, allow_unicode=True)
            _fire(hass, f"{DOMAIN}_generate_dashboard_yaml_result", {"entry_id": entry_id, "yaml": yaml_text})
            return {"yaml": yaml_text, "view": view}
        except Exception as e:
            raise HomeAssistantError(str(e))

    # ---------- AIA ----------
    async def aia_update_zone(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.update_zone(call.data["zone_id"], call.data["body"])
        _fire(hass, f"{DOMAIN}_aia_update_zone_result", {"result": res})
        return {"result": res}

    async def aia_update_area(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.update_area(call.data["area_id"], call.data["body"])
        _fire(hass, f"{DOMAIN}_aia_update_area_result", {"result": res})
        return {"result": res}

    # ---------- ACCESS ----------
    async def access_get_groups(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.get_access_groups()
            _fire(hass, f"{DOMAIN}_access_get_groups_result", {"result": res})
            return {"access_groups": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_get_static_types(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.get_card_option_types()
        _fire(hass, f"{DOMAIN}_access_get_static_types_result", {"result": res})
        return {"types": res}

    async def access_list_cardholders(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            raw = await client.list_card_holders_filter({"cardHolderFilter": {"limitCount": 1000, "skipCount": 0}})
            records = raw.get("records", []) if isinstance(raw, dict) else (raw or [])
            _fire(hass, f"{DOMAIN}_access_list_cardholders_result", {"result": records})
            return {"cardholders": records}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_list_cardholders_filter(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            flt = call.data["filter"]
            if isinstance(flt, dict) and "cardHolderFilter" not in flt:
                flt = {"cardHolderFilter": flt}
            raw = await client.list_card_holders_filter(flt)
            records = raw.get("records", []) if isinstance(raw, dict) else (raw or [])
            _fire(hass, f"{DOMAIN}_access_list_cardholders_filter_result", {"result": records})
            return {"cardholders": records}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_create_cardholder(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            body = dict(call.data["body"] or {})
            body = await _ensure_cross_id_has_numeric_id(client, "cardholder", body)
            res = await client.create_card_holder(body)
            # Normalisér ID: prøv svaret først, fall back til det vi sendte
            ch_id = _int_id_local(res) or _int_id_local(body)
            _fire(hass, f"{DOMAIN}_access_create_cardholder_result", {"result": res})
            return {"result": res, "cardholder_id": ch_id}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_update_cardholder(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.update_card_holder(call.data["body"])
        _fire(hass, f"{DOMAIN}_access_update_cardholder_result", {"result": res})
        return {"result": res}

    async def access_delete_cardholder(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.delete_card_holder(id=call.data.get("id"), ext_id=call.data.get("ext_id"))
        _fire(hass, f"{DOMAIN}_access_delete_cardholder_result", {"result": res})
        return {"result": res}

    async def access_list_cards(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.list_cards()
        _fire(hass, f"{DOMAIN}_access_list_cards_result", {"result": res})
        return {"cards": res}

    async def access_list_cards_filter(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            flt = call.data["filter"]
            if isinstance(flt, dict) and "cardFilter" not in flt:
                flt = {"cardFilter": flt}
            res = await client.list_cards_filter(flt)
            _fire(hass, f"{DOMAIN}_access_list_cards_filter_result", {"result": res})
            return {"cards": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_create_card(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            body = dict(call.data["body"] or {})
            # TechPoint expects number as string; HA template engine may coerce
            # pure-digit values to int via parse_result=True
            if "number" in body and body["number"] is not None:
                body["number"] = str(body["number"])
            body = await _ensure_cross_id_has_numeric_id(client, "card", body)
            res = await client.create_card(body)
            card_id = _int_id_local(res) or _int_id_local(body)
            _fire(hass, f"{DOMAIN}_access_create_card_result", {"result": res})
            return {"result": res, "card_id": card_id}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_update_card(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            body = dict(call.data.get("body") or {})
            if "number" in body and body["number"] is not None:
                body["number"] = str(body["number"])
            res = await client.update_card(call.data["card_id"], body)
            _fire(hass, f"{DOMAIN}_access_update_card_result", {"result": res})
            return {"result": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_delete_card(call: ServiceCall):
        client = _get_client(hass, call.data.get("entry_id"))
        res = await client.delete_card(call.data["card_id"])
        _fire(hass, f"{DOMAIN}_access_delete_card_result", {"result": res})
        return {"result": res}

    # ---------- GLOBAL DOOR CONTROL (v1.13.0) ----------
    async def management_get_global_door_control(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.get_global_door_control()
            active = (res or {}).get("status", {}).get("active")
            return {"result": res, "active": active}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def management_set_global_door_control(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.set_global_door_control(bool(call.data["active"]))
            return {"result": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    # ---------- THREAT LEVEL (v1.13.0) ----------
    async def management_get_threat_level(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.get_threat_level()
            level = (res or {}).get("currentThreatLevel", {}).get("level")
            return {"result": res, "level": level}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def management_set_threat_level(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.set_threat_level(int(call.data["level"]))
            return {"result": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    # ---------- USER-DEFINED I/O (v1.13.0) ----------
    async def config_get_io_inputs(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.get_io_userdefined(28)
            return {"inputs": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def config_get_io_outputs(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.get_io_userdefined(29)
            return {"outputs": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def config_set_io_userdefined(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            res = await client.set_io_userdefined(
                int(call.data["output_id"]),
                int(call.data["status"]),
                int(call.data.get("io_type", 29)),
            )
            return {"result": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    # ---------- EVENTS ----------
    async def events_get(call: ServiceCall):
        entry_id = call.data.get("entry_id")
        client = _get_client(hass, entry_id)
        res = await client.get_events(
            {
                k: v
                for k, v in {
                    "since": call.data.get("since"),
                    "until": call.data.get("until"),
                    "limit": call.data.get("limit"),
                    **(call.data.get("filters") or {}),
                }.items()
                if v not in (None, "")
            }
        )
        coord = _get_coordinator(hass, entry_id)
        if coord.data is None:
            coord.data = {}
        coord.data["events_recent"] = res or []
        _fire(hass, f"{DOMAIN}_events", {"entry_id": entry_id, "events": res})
        return {"events": res}

    # Register (with responses where useful)
    hass.services.async_register(DOMAIN, "call_api", call_api, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "get_cache", get_cache, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "management_set_door_status", management_set_door_status, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "door_set_status_by_entity", door_set_status_by_entity, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "refresh", refresh, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "cleanup_orphan_devices", cleanup_orphan_devices, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "cleanup_stale_entities", cleanup_stale_entities, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "generate_dashboard_yaml", generate_dashboard_yaml, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "aia_update_zone", aia_update_zone, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "aia_update_area", aia_update_area, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "access_get_groups", access_get_groups, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_get_static_types", access_get_static_types, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_list_cardholders", access_list_cardholders, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_list_cardholders_filter", access_list_cardholders_filter, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "access_create_cardholder", access_create_cardholder, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_update_cardholder", access_update_cardholder, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_delete_cardholder", access_delete_cardholder, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "access_list_cards", access_list_cards, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_list_cards_filter", access_list_cards_filter, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "access_create_card", access_create_card, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_update_card", access_update_card, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "access_delete_card", access_delete_card, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "events_get", events_get, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "management_get_global_door_control", management_get_global_door_control, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "management_set_global_door_control", management_set_global_door_control, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "management_get_threat_level", management_get_threat_level, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "management_set_threat_level", management_set_threat_level, supports_response=SupportsResponse.ONLY)

    hass.services.async_register(DOMAIN, "config_get_io_inputs", config_get_io_inputs, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "config_get_io_outputs", config_get_io_outputs, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "config_set_io_userdefined", config_set_io_userdefined, supports_response=SupportsResponse.ONLY)


async def async_unregister_services(hass: HomeAssistant) -> None:
    for name in [
        "call_api",
        "get_cache",
        "management_set_door_status",
        "door_set_status_by_entity",
        "refresh",
        "cleanup_orphan_devices",
        "cleanup_stale_entities",
        "generate_dashboard_yaml",
        "aia_update_zone",
        "aia_update_area",
        "access_get_groups",
        "access_get_static_types",
        "access_list_cardholders",
        "access_list_cardholders_filter",
        "access_create_cardholder",
        "access_update_cardholder",
        "access_delete_cardholder",
        "access_list_cards",
        "access_list_cards_filter",
        "access_create_card",
        "access_update_card",
        "access_delete_card",
        "events_get",
        "management_get_global_door_control",
        "management_set_global_door_control",
        "management_get_threat_level",
        "management_set_threat_level",
        "config_get_io_inputs",
        "config_get_io_outputs",
        "config_set_io_userdefined",
    ]:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
