from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

try:
    # HA 2025+ (incl. 2026.1)
    from homeassistant.helpers.network import get_url
except Exception:  # pragma: no cover
    get_url = None  # type: ignore

from homeassistant.components.webhook import async_register, async_unregister
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_EVENTS_ALARM,
    CONF_EVENTS_DOOR,
    CONF_EVENTS_ERROR,
    CONF_EVENTS_TAMPER,
    CONF_EVENT_LOG_MAX,
    DEFAULT_EVENT_LOG_MAX,
    DOMAIN,
    EVENT_BUS_NAME,
    MODE_LAN,
    SIGNAL_EVENT_LOG_UPDATED,
    CONF_MODE,
)

_LOGGER = logging.getLogger(__name__)


def get_webhook_url(hass: HomeAssistant, entry_id: str) -> str:
    """Return the Home Assistant webhook URL TechPoint should POST to.

    Exposed for UI/help-text and diagnostics.
    """
    return _build_webhook_url(hass, entry_id)


def _webhook_id(entry_id: str) -> str:
    # Stable per config entry
    return f"{DOMAIN}_{entry_id}"


def _build_webhook_url(hass: HomeAssistant, entry_id: str) -> str:
    wid = _webhook_id(entry_id)
    base = None
    if get_url is not None:
        try:
            base = get_url(hass, prefer_external=False, allow_internal=True, allow_external=False)
        except Exception:  # noqa: BLE001
            base = None
    if not base:
        # Fallback: typical local URL
        base = "http://homeassistant.local:8123"
    return f"{base.rstrip('/')}/api/webhook/{wid}"


def _enabled_categories(cfg: Dict[str, Any]) -> Tuple[bool, bool, bool, bool]:
    return (
        bool(cfg.get(CONF_EVENTS_DOOR)),
        bool(cfg.get(CONF_EVENTS_ALARM)),
        bool(cfg.get(CONF_EVENTS_TAMPER)),
        bool(cfg.get(CONF_EVENTS_ERROR)),
    )


def _any_enabled(enabled: Tuple[bool, bool, bool, bool]) -> bool:
    return any(enabled)


def _iter_events(payload: Any) -> Iterable[Dict[str, Any]]:
    """Normalize TechPoint webhook payload to iterable of event dicts."""
    if payload is None:
        return []

    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]

    if not isinstance(payload, dict):
        return []

    # Swagger types: eventFilterResult { records: [event], count: n }
    if "eventFilterResult" in payload and isinstance(payload.get("eventFilterResult"), dict):
        recs = payload["eventFilterResult"].get("records")
        if isinstance(recs, list):
            return [x for x in recs if isinstance(x, dict)]

    recs = payload.get("records")
    if isinstance(recs, list):
        return [x for x in recs if isinstance(x, dict)]

    # Sometimes wrapped as {event:{...}}
    ev = payload.get("event")
    if isinstance(ev, dict):
        return [ev]

    return []


def _details_values(details: Any) -> List[str]:
    out: List[str] = []
    if not isinstance(details, list):
        return out
    for d in details:
        if not isinstance(d, dict):
            continue
        v = d.get("value")
        if v is None:
            continue
        out.append(str(v))
    return out


def _detail_value(details: Any, detail_type: int) -> Optional[str]:
    if not isinstance(details, list):
        return None
    for d in details:
        if not isinstance(d, dict):
            continue
        if d.get("type") == detail_type:
            v = d.get("value")
            return str(v) if v is not None else None
    return None


def _format_hhmm(iso_ts: Any) -> Optional[str]:
    """Return local HH:MM from an ISO timestamp (usually UTC '...Z')."""
    if iso_ts is None:
        return None
    try:
        dt_utc = dt_util.parse_datetime(str(iso_ts))
        if dt_utc is None:
            return None
        dt_local = dt_util.as_local(dt_utc)
        return dt_local.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        # Fallback: simple string slice (may be UTC)
        s = str(iso_ts)
        if len(s) >= 16 and "T" in s:
            try:
                return s.split("T", 1)[1][:5]
            except Exception:  # noqa: BLE001
                return None
        return None

    s = str(iso_ts)
    # Expected: 2026-02-01T07:51:25Z
    if len(s) >= 16 and "T" in s:
        try:
            return s.split("T", 1)[1][:5]
        except Exception:  # noqa: BLE001
            return None
    return None




def _to_local_iso(iso_ts: Any) -> Optional[str]:
    """Convert an ISO timestamp to local ISO string."""
    if iso_ts is None:
        return None
    try:
        dt_utc = dt_util.parse_datetime(str(iso_ts))
        if dt_utc is None:
            return None
        return dt_util.as_local(dt_utc).isoformat()
    except Exception:  # noqa: BLE001
        return None

def _normalize_action(type_name: Optional[str]) -> str:
    """Return a stable action identifier derived from the TechPoint event type name."""
    if not type_name:
        return "event"
    n = str(type_name).strip().lower()

    # Door / access
    if n == "access granted":
        return "access_granted"
    if n == "access denied":
        return "access_denied"
    if n == "door opened":
        return "door_opened"
    if n == "door closed":
        return "door_closed"
    if n == "door normal":
        return "door_normal"
    if "door management" in n:
        return "door_management"
    if "permanent" in n and "release" in n:
        return "door_permanent_release"
    if "release" in n:
        return "door_release"

    # Alarm
    if any(k in n for k in ("arm", "set")) and not any(k in n for k in ("disarm", "unset")):
        return "alarm_armed"
    if any(k in n for k in ("disarm", "unset")):
        return "alarm_disarmed"

    # Tamper / error
    if "tamper" in n or "sabotage" in n:
        return "tamper"
    if "offline" in n:
        return "offline"
    if "online" in n:
        return "online"
    if "error" in n or "fault" in n:
        return "error"

    return n.replace(" ", "_")


def _parse_event_for_ui(category: str, type_id: Optional[int], type_name: Optional[str], ev: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a TechPoint event into a compact, automation-friendly dict.

    Keeps raw details, but also extracts common fields like door/reader/area/who and normalizes
    an `action` + optional `source` for stable automations/Node-RED.
    """
    details = ev.get("details")

    # Common fields (door/access)
    door = _detail_value(details, 1500)
    reader = _detail_value(details, 1501)

    # Alarm / intrusion fields
    area = _detail_value(details, 14008)
    alarm_mode = _detail_value(details, 14014)

    # Who can be an operator (Web UI/API), a card holder, or an intrusion user.
    who = (
        _detail_value(details, 3503)  # operator username (door management events)
        or _detail_value(details, 14001)  # intrusion/alarm user (area set/unset/login)
        or _detail_value(details, 1502)  # card holder / credential name
    )
    if who:
        who = str(who).strip()

    # Badge/serial (access events)
    card_badge = _detail_value(details, 1503) or _detail_value(details, 1506)
    chip_serial = _detail_value(details, 1504)

    # Access denied reason/message
    reason = _detail_value(details, 1507)

    # Descriptive text, often present on management actions
    action_msg = _detail_value(details, 504)
    action_msg_l = (action_msg or "").lower()

    # Normalized action defaults from type_name, then refined by known type_id patterns.
    action = _normalize_action(type_name)

    # Determine source for management actions / keypad actions.
    source: Optional[str] = None
    if "web api" in action_msg_l:
        source = "web_api"
    elif "web ui" in action_msg_l:
        source = "web_ui"

    # Fine-grained overrides by known type_id.
    if type_id == 1057:
        # Door management action (often release via UI/API)
        if "release" in action_msg_l:
            action = "door_release"
        else:
            action = "door_management"
    elif type_id == 1003:
        action = "door_permanent_release"
    elif type_id == 1022:
        action = "door_normal"
    elif type_id == 1053:
        action = "door_normal"
        source = source or "keypad"
    elif type_id == 1011:
        action = "access_granted"
    elif type_id == 1010:
        action = "access_denied"
    elif type_id == 1016:
        action = "card_not_created"
    elif type_id == 16000:
        action = "alarm_disarmed"
    elif type_id == 16010:
        action = "alarm_armed"
    elif type_id == 19001:
        action = "intrusion_login"

    # A short summary string (prefer a concrete message if present)
    base_summary = (type_name or "Event").strip()
    if type_id == 1057 and action_msg:
        # "Door release executed from Web API/UI"
        summary = str(action_msg).strip()
    elif reason and action in ("access_denied", "card_not_created"):
        summary = f"{base_summary} ({reason})"
    else:
        summary = base_summary

    hhmm = _format_hhmm(ev.get("eventTime"))

    # Choose a primary target label for the line
    target = door or area or reader or ""

    # Build a human-friendly line:
    # 15:08 – Skur Forhaven – Door release (Web API) – APISync2026
    parts: List[str] = []
    if hhmm:
        parts.append(hhmm)
    if target:
        parts.append(str(target).strip())

    line_summary = summary
    if type_id in (16000, 16010) and area:
        line_summary = "Alarm armed" if action == "alarm_armed" else "Alarm disarmed"
    elif type_id == 19001:
        line_summary = "Intrusion login"

    if source and action in ("door_release", "door_management", "door_normal"):
        src_txt = source.replace("_", " ").title()
        line_summary = f"{line_summary} ({src_txt})"

    parts.append(line_summary)

    if who:
        parts.append(who)

    line = " – ".join([p for p in parts if p])

    return {
        "id": (ev.get("id") or {}).get("id") if isinstance(ev.get("id"), dict) else ev.get("id"),
        "category": category,
        "type_id": type_id,
        "type_name": type_name,
        "event_time": _to_local_iso(ev.get("eventTime")),
        "event_time_utc": ev.get("eventTime"),
        "time": hhmm,
        "door": door,
        "reader": reader,
        "area": area,
        "who": who,
        "action": action,
        "source": source,
        "alarm_mode": alarm_mode,
        "reason": reason,
        "card_badge": card_badge,
        "chip_serial": chip_serial,
        "summary": summary,
        "line": line,
        "details_values": _details_values(details),
        "details": details,
    }

def _classify_event(type_name: Optional[str], details_values: List[str]) -> str:
    """Best-effort classification for toggles."""
    hay = " ".join([type_name or ""] + details_values).lower()

    # Door / access
    if any(k in hay for k in ("door", "dør", "access", "adgang", "reader", "læser", "card", "kort")):
        return "door"

    # Alarm / intrusion
    if any(k in hay for k in ("intrusion", "alarm", "tilkob", "frakob", "armed", "disarmed", "set", "unset")):
        return "alarm"

    # Tamper / sabotage
    if any(k in hay for k in ("tamper", "sabotage", "sab", "cover")):
        return "tamper"

    # User-defined I/O state changes
    if any(k in hay for k in ("i/o", "io state", "output", "input", "userdefined", "relay", "digital")):
        return "io"

    # Error
    if any(k in hay for k in ("error", "fault", "fejl", "offline", "power", "battery", "communication")):
        return "error"

    return "other"


def _is_enabled(category: str, enabled: Tuple[bool, bool, bool, bool]) -> bool:
    door_on, alarm_on, tamper_on, error_on = enabled
    if category == "door":
        return door_on
    if category == "alarm":
        return alarm_on
    if category == "tamper":
        return tamper_on
    if category == "error":
        return error_on
    # I/O events follow door toggle (they are action/control events).
    if category == "io":
        return door_on
    # If unknown, only forward when at least one category is enabled.
    return any(enabled)


async def _handle_webhook(hass: HomeAssistant, webhook_id: str, request) -> None:
    # NOTE: signature is HA webhook handler signature
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = None

    entry_id = webhook_id.replace(f"{DOMAIN}_", "", 1)
    entry_data = (hass.data.get(DOMAIN) or {}).get(entry_id) or {}

    cfg = entry_data.get("cfg") or {}
    enabled = _enabled_categories(cfg)

    type_names: Dict[int, str] = entry_data.get("event_type_names") or {}

    forwarded = 0
    for ev in _iter_events(payload):
        type_id = ev.get("type")
        try:
            type_id_i = int(type_id) if type_id is not None else None
        except Exception:  # noqa: BLE001
            type_id_i = None

        type_name = type_names.get(type_id_i) if type_id_i is not None else None
        details_vals = _details_values(ev.get("details"))
        category = _classify_event(type_name, details_vals)

        if not _is_enabled(category, enabled):
            continue

        data = {
            "entry_id": entry_id,
            "category": category,
            "type_id": type_id_i,
            "type_name": type_name,
            "event_time": _to_local_iso(ev.get("eventTime")),
        "event_time_utc": ev.get("eventTime"),
            "clear_time": ev.get("clearTime"),
            "techpoint_id": ev.get("techPointId"),
            "details": ev.get("details"),
            "details_values": details_vals,
            "raw": ev,
        }
        hass.bus.async_fire(EVENT_BUS_NAME, data)
        hass.bus.async_fire(f"{DOMAIN}_event", data)
        forwarded += 1

        # Keep a rolling in-memory log for UI/dashboard usage
        try:
            log = entry_data.setdefault("event_log", [])
            log_max = int(
                (cfg or {}).get(CONF_EVENT_LOG_MAX, DEFAULT_EVENT_LOG_MAX) or DEFAULT_EVENT_LOG_MAX
            )
            parsed = _parse_event_for_ui(category, type_id_i, type_name, ev)
            # Store latest parsed event for user-friendly sensors
            entry_data["last_event_parsed"] = parsed
            log.insert(0, parsed)
            if log_max > 0 and len(log) > log_max:
                del log[log_max:]
            async_dispatcher_send(hass, f"{SIGNAL_EVENT_LOG_UPDATED}_{entry_id}")
        except Exception:  # noqa: BLE001
            pass

    if forwarded:
        _LOGGER.debug("TechPoint webhook: forwarded %s event(s)", forwarded)


def _build_event_filter(
    enabled: Tuple[bool, bool, bool, bool],
    event_type_names: Dict[int, str],
    event_tags: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build eventFilter for TechPoint webhook.

    We try to be smart by selecting eventTypes based on keywords in the static
    event type list. If we can't build a good filter, we return an empty filter
    which typically means "all events".
    """
    door_on, alarm_on, tamper_on, error_on = enabled

    if not any(enabled):
        return {}

    def want(name: str) -> Optional[str]:
        n = (name or "").lower()
        if door_on and any(k in n for k in ("access", "door", "reader", "card", "credential")):
            return "door"
        if door_on and any(k in n for k in ("i/o", "io state", "output", "input", "userdefined", "relay", "digital")):
            return "io"
        if alarm_on and any(k in n for k in ("intrusion", "alarm", "arm", "disarm", "set", "unset")):
            return "alarm"
        if tamper_on and any(k in n for k in ("tamper", "sabotage", "sab")):
            return "tamper"
        if error_on and any(k in n for k in ("error", "fault", "offline", "power", "battery", "communication")):
            return "error"
        return None

    selected: List[int] = []
    for tid, tname in event_type_names.items():
        if want(tname):
            selected.append(int(tid))

    # If we selected too little, fallback to tags if present (best-effort).
    # Tags schema: {id,name,linkedEventTypeIDs,...}
    if len(selected) < 3 and event_tags:
        tag_ids: List[int] = []
        for tag in event_tags:
            try:
                nm = str(tag.get("name") or "")
            except Exception:
                nm = ""
            cat = want(nm)
            if cat:
                try:
                    tag_ids.append(int(tag.get("id")))
                except Exception:
                    pass
        if tag_ids:
            return {"eventTypeTags": tag_ids}

    if selected:
        return {"eventTypes": selected}
    return {}


async def async_setup_realtime_events(hass: HomeAssistant, entry, client, cfg: Dict[str, Any]) -> None:
    """Register HA webhook and configure TechPoint to push events (LAN only)."""
    if cfg.get(CONF_MODE) != MODE_LAN:
        return

    enabled = _enabled_categories(cfg)

    # Always store the resolved config (used by handler)
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["cfg"] = cfg

    # If nothing is enabled: disable on TechPoint and unregister HA webhook.
    if not any(enabled):
        try:
            if hasattr(client, "delete_events_webhook"):
                await client.delete_events_webhook()
        except Exception:  # noqa: BLE001
            pass

        try:
            async_unregister(hass, _webhook_id(entry.entry_id))
        except Exception:  # noqa: BLE001
            pass
        return

    # Register HA webhook (idempotent)
    wid = _webhook_id(entry.entry_id)
    try:
        async_register(hass, DOMAIN, "TechPoint", wid, _handle_webhook)
    except Exception:  # noqa: BLE001
        # If already registered, ignore
        _LOGGER.debug("TechPoint: webhook already registered", exc_info=True)

    # Build filter using static types, if available.
    type_names: Dict[int, str] = {}
    event_tags: Optional[List[Dict[str, Any]]] = None
    try:
        if hasattr(client, "get_event_types_static_config"):
            js = await client.get_event_types_static_config()
            cfg2 = (js or {}).get("eventTypesStaticConfig") or {}
            for t in (cfg2.get("eventTypes") or []):
                if isinstance(t, dict) and "id" in t and "name" in t:
                    try:
                        type_names[int(t["id"])] = str(t["name"])
                    except Exception:
                        pass
            event_tags = cfg2.get("eventTags") if isinstance(cfg2.get("eventTags"), list) else None
    except Exception:  # noqa: BLE001
        _LOGGER.debug("TechPoint: could not fetch static event types", exc_info=True)

    # Store type names for handler
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["event_type_names"] = type_names

    event_filter = _build_event_filter(enabled, type_names, event_tags)
    webhook_url = _build_webhook_url(hass, entry.entry_id)

    # Expose for diagnostics/UI (copy/paste into TechPoint)
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["webhook_id"] = wid
        hass.data[DOMAIN][entry.entry_id]["webhook_url"] = webhook_url
        hass.data[DOMAIN][entry.entry_id]["webhook_filter"] = event_filter

    try:
        if hasattr(client, "set_events_webhook"):
            await client.set_events_webhook(url=webhook_url, event_filter=event_filter, auth_type="None")
            registered_at = dt_util.now().isoformat()
            _LOGGER.info(
                "TechPoint: webhook POST sent to /events/webhook at %s | url=%s | filter=%s",
                registered_at,
                webhook_url,
                event_filter,
            )
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                hass.data[DOMAIN][entry.entry_id]["webhook_registered_at"] = registered_at
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("TechPoint: could not configure TechPoint webhook: %s", err)


async def async_unload_realtime_events(hass: HomeAssistant, entry, client) -> None:
    """Unregister HA webhook handler on unload.

    We intentionally do NOT send DELETE to TechPoint here — the webhook URL
    is stable (based on entry_id) and the next async_setup_entry will POST
    an updated registration. Sending DELETE during every reload/update would
    leave TechPoint with no webhook until the new setup completes (or fails).
    """
    try:
        async_unregister(hass, _webhook_id(entry.entry_id))
    except Exception:  # noqa: BLE001
        pass


async def async_remove_realtime_events(hass: HomeAssistant, entry, client) -> None:
    """Full cleanup — send DELETE to TechPoint and unregister HA handler.

    Call this only on true removal/uninstall of the integration, not on reload.
    """
    try:
        if hasattr(client, "delete_events_webhook"):
            await client.delete_events_webhook()
            _LOGGER.info("TechPoint: webhook DELETE sent to /events/webhook (integration removed)")
    except Exception:  # noqa: BLE001
        pass

    try:
        async_unregister(hass, _webhook_id(entry.entry_id))
    except Exception:  # noqa: BLE001
        pass
