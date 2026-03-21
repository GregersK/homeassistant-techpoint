from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

from ..const import CONF_MODE, MODE_CLOUD, MODE_LAN
from .cloud_client import CloudApiClient
from .lan_client import LanApiClient


def _ensure_scheme(url: str) -> str:
    """Ensure the URL has a scheme; default to https."""
    u = (url or "").strip()
    if not u:
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return f"https://{u}"


def _normalize_lan_base_url(base_url: str) -> str:
    """Normalize LAN base URL.

    Users typically input only IP/host (e.g. 10.0.0.5) or https://10.0.0.5.
    TechPoint LAN API lives under /api/v1.

    If base_url already contains /api/v*, keep it.
    Otherwise append /api/v1.
    """
    b = _ensure_scheme(base_url).rstrip("/")
    lb = b.lower()
    if "/api/v" in lb:
        return b
    return b + "/api/v1"


def _normalize_cloud_root(base_url: str) -> str:
    """Normalize Cloud root URL.

    Cloud API base URL is typically something like:
      https://<site>.azurewebsites.net
    Some examples/docs show /api or /api/v1. We strip those so we can build
    /api/v1/auth and /api/v1/device/<id>/... reliably.
    """
    b = _ensure_scheme(base_url).rstrip("/")
    lb = b.lower()
    for suffix in ("/api/v1", "/api"):
        if lb.endswith(suffix):
            b = b[: -len(suffix)]
            break
    return b.rstrip("/")


def create_client(hass: HomeAssistant, base_url: str, entry_data: Dict[str, Any]):
    mode = (entry_data.get(CONF_MODE) or MODE_CLOUD).lower()
    if mode == MODE_LAN:
        return LanApiClient(hass, _normalize_lan_base_url(base_url), entry_data)
    return CloudApiClient(hass, _normalize_cloud_root(base_url), entry_data)
