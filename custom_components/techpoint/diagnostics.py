"""Diagnostics support for TechPoint.

This is used by Home Assistant when the user clicks "Download diagnostics" on
the integration. Keep it free of secrets.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


REDACT_KEYS = {
    "password",
    "token",
    "api_key",
    "access_token",
    "refresh_token",
    "lan_password",
    "lan_token",
    "lan_username",
    "username",
    "device_id",
    "webhook_id",
    "webhook_url",
}

# Only non-personal fields of the latest event: no cardholder/operator name,
# credential numbers or raw details.
_EVENT_SUMMARY_KEYS = ("category", "type_id", "type_name", "action", "source", "event_time_utc")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    data = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}

    # "cfg" is stored by webhook setup (LAN mode); fall back to entry data for cloud mode.
    cfg = (data.get("cfg") or {**entry.data, **(entry.options or {})}).copy()
    cfg = async_redact_data(cfg, REDACT_KEYS)

    event_log = data.get("event_log") or []
    last_event = event_log[0] if isinstance(event_log, list) and event_log else None
    if isinstance(last_event, dict):
        last_event = {k: last_event.get(k) for k in _EVENT_SUMMARY_KEYS}

    diag: dict[str, Any] = {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
        },
        "config": cfg,
        "realtime": async_redact_data(
            {
                "webhook_id": data.get("webhook_id"),
                "webhook_url": data.get("webhook_url"),
                "webhook_filter": data.get("webhook_filter"),
                "allowed_sources": len(data.get("webhook_allowed_ips") or ()),
            },
            REDACT_KEYS,
        ),
        "event_log": {
            "count": len(event_log) if isinstance(event_log, list) else 0,
            "last": last_event,
        },
    }

    # Optional: coordinator snapshot sizes (avoid dumping full datasets)
    try:
        coordinator = data.get("coordinator")
        snap = getattr(coordinator, "data", None) or {}
        if isinstance(snap, dict):
            diag["snapshot_counts"] = {
                "doors": len(snap.get("doors") or []),
                "zones": len(snap.get("zones") or []),
                "areas": len(snap.get("areas") or []),
            }
    except Exception:  # noqa: BLE001
        pass

    return diag
