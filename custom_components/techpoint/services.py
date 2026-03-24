from __future__ import annotations

from typing import Any, Dict, Iterable

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


def _get_entry(hass: HomeAssistant, entry_id: str | None) -> Dict[str, Any]:
    dom = hass.data.get(DOMAIN) or {}
    entry_ids = [k for k in dom if k != "_services_registered"]
    if not entry_id:
        if len(entry_ids) == 1:
            return dom[entry_ids[0]]
        if not entry_ids:
            raise ValueError("No TechPoint integration found")
        raise ValueError(
            f"Multiple TechPoint entries found – please specify entry_id. Available: {entry_ids}"
        )
    if entry_id not in dom:
        raise ValueError(f"Unknown entry_id: {entry_id!r}")
    return dom[entry_id]


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
            records = await client.list_card_holders_filter(filter_body)
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
            # /access/cardHolders (GET) expects a single parameter on many TechPoint versions.
            # Use the filter endpoint to list all cardholders.
            res = await client.list_card_holders_filter({"cardHolderFilter": {"limitCount": 1000, "skipCount": 0}})
            _fire(hass, f"{DOMAIN}_access_list_cardholders_result", {"result": res})
            return {"cardholders": res}
        except Exception as e:
            raise HomeAssistantError(str(e))

    async def access_list_cardholders_filter(call: ServiceCall):
        try:
            client = _get_client(hass, call.data.get("entry_id"))
            flt = call.data["filter"]
            if isinstance(flt, dict) and "cardHolderFilter" not in flt:
                flt = {"cardHolderFilter": flt}
            res = await client.list_card_holders_filter(flt)
            _fire(hass, f"{DOMAIN}_access_list_cardholders_filter_result", {"result": res})
            return {"cardholders": res}
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


async def async_unregister_services(hass: HomeAssistant) -> None:
    for name in [
        "call_api",
        "get_cache",
        "management_set_door_status",
        "door_set_status_by_entity",
        "refresh",
        "cleanup_orphan_devices",
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
    ]:
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
