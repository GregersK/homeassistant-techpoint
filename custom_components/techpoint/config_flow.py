from __future__ import annotations

import re
from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTH_TYPE,
    CONF_BASE_URL,
    CONF_BRAND,
    CONF_DEVICE_ID,
    CONF_LAN_PASSWORD,
    CONF_LAN_TOKEN,
    CONF_LAN_USERNAME,
    CONF_MODE,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_AUTH_TYPE,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL_CLOUD,
    DEFAULT_VERIFY_SSL_LAN,
    CONF_DEVICE_GROUPING,
    DEVICE_GROUPINGS,
    DEFAULT_DEVICE_GROUPING,
    CONF_EVENTS_DOOR,
    CONF_EVENTS_ALARM,
    CONF_EVENTS_TAMPER,
    CONF_EVENTS_ERROR,
    DOMAIN,
    BRAND_TECHPOINT,
    BRAND_META,
    MODE_CLOUD,
    MODE_LAN,
    MODES,
    CONF_EVENT_LOG_MAX,
    DEFAULT_EVENT_LOG_MAX,
)
from .webhook import get_webhook_url
from .api.factory import create_client


def _ensure_scheme(url: str, default_scheme: str = "https") -> str:
    u = (url or "").strip()
    if not u:
        return u
    if re.match(r"^https?://", u, re.I):
        return u
    return f"{default_scheme}://{u}"


def _normalize_lan_input(host_or_url: str) -> str:
    # factory will append /api/v1; we only ensure scheme for unique id
    return _ensure_scheme(host_or_url).rstrip("/")


def _normalize_cloud_input(url: str) -> str:
    u = _ensure_scheme(url).rstrip("/")
    low = u.lower()
    for suffix in ("/api/v1", "/api"):
        if low.endswith(suffix):
            u = u[: -len(suffix)]
            break
    return u.rstrip("/")


def _is_auth_error(err: Exception) -> bool:
    s = str(err)
    return (" 401" in s) or ("Unauthorized" in s) or ("auth" in s.lower())


async def _probe(hass: HomeAssistant, base_url: str, data: Dict[str, Any]) -> None:
    client = create_client(hass, base_url, data)
    # Prefer fast /info/api probe
    if hasattr(client, "get_api_info"):
        await client.get_api_info()
    else:
        await client.list_doors()


class TechPointConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._brand: str = BRAND_TECHPOINT

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "TechPointOptionsFlowHandler":
        return TechPointOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: Dict[str, Any] | None = None):
        """First step: select brand (TechPoint or Siedle SC-600)."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_BRAND, default=BRAND_TECHPOINT): vol.In({
                        "techpoint": "TechPoint",
                        "siedle": "Siedle Secure SC-600",
                    }),
                }),
            )

        self._brand = user_input[CONF_BRAND]
        return await self.async_step_mode()

    async def async_step_mode(self, user_input: Dict[str, Any] | None = None):
        """Second step: select connection mode (LAN or Cloud)."""
        if user_input is None:
            return self.async_show_form(
                step_id="mode",
                data_schema=vol.Schema({
                    vol.Required(CONF_MODE, default=MODE_LAN): vol.In(MODES)
                }),
            )

        mode = user_input[CONF_MODE]
        if mode == MODE_CLOUD:
            return await self.async_step_cloud()
        return await self.async_step_lan()

    async def async_step_lan(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}
        brand_default_name = BRAND_META.get(self._brand, BRAND_META["techpoint"])["default_name"]

        if user_input is not None:
            base_url_raw = user_input[CONF_BASE_URL]
            unique_base = _normalize_lan_input(base_url_raw)
            unique_id = f"{MODE_LAN}:{unique_base}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            data = dict(user_input)
            data[CONF_MODE] = MODE_LAN
            data[CONF_BRAND] = self._brand

            try:
                await _probe(self.hass, base_url_raw, data)
            except Exception as err:  # noqa: BLE001
                errors["base"] = "auth" if _is_auth_error(err) else "cannot_connect"
            else:
                title = data.get(CONF_NAME) or brand_default_name
                return self.async_create_entry(title=title, data=data)

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL): str,
            vol.Optional(CONF_NAME, default=brand_default_name): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(int),
            vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL_LAN): bool,
            vol.Optional(CONF_LAN_USERNAME): str,
            vol.Optional(CONF_LAN_PASSWORD): str,
            vol.Optional(CONF_LAN_TOKEN): str,
        })

        return self.async_show_form(step_id="lan", data_schema=schema, errors=errors)

    async def async_step_cloud(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}
        brand_default_name = BRAND_META.get(self._brand, BRAND_META["techpoint"])["default_name"]

        if user_input is not None:
            cloud_root = _normalize_cloud_input(user_input[CONF_BASE_URL])
            device_id = str(user_input.get(CONF_DEVICE_ID) or "").strip()
            unique_id = f"{MODE_CLOUD}:{cloud_root}:{device_id}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            data = dict(user_input)
            data[CONF_MODE] = MODE_CLOUD
            data[CONF_BASE_URL] = cloud_root
            data[CONF_BRAND] = self._brand

            try:
                await _probe(self.hass, cloud_root, data)
            except Exception as err:  # noqa: BLE001
                errors["base"] = "auth" if _is_auth_error(err) else "cannot_connect"
            else:
                title = data.get(CONF_NAME) or brand_default_name
                return self.async_create_entry(title=title, data=data)

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL): str,
            vol.Required(CONF_DEVICE_ID): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_AUTH_TYPE, default=DEFAULT_AUTH_TYPE): vol.Coerce(int),
            vol.Optional(CONF_NAME, default=brand_default_name): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.Coerce(int),
            vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL_CLOUD): bool,
        })

        return self.async_show_form(step_id="cloud", data_schema=schema, errors=errors)


class TechPointOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle TechPoint options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        cur = {**self._config_entry.data, **(self._config_entry.options or {})}

        schema = vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=cur.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.Coerce(int),
            vol.Optional(CONF_VERIFY_SSL, default=cur.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL_LAN if cur.get(CONF_MODE) == MODE_LAN else DEFAULT_VERIFY_SSL_CLOUD)): bool,
            vol.Optional(CONF_DEVICE_GROUPING, default=cur.get(CONF_DEVICE_GROUPING, DEFAULT_DEVICE_GROUPING)): vol.In(DEVICE_GROUPINGS),
            # Realtime events (LAN only). These are safe to show for cloud too; they will simply be ignored.
            vol.Optional(CONF_EVENTS_DOOR, default=cur.get(CONF_EVENTS_DOOR, False)): bool,
            vol.Optional(CONF_EVENTS_ALARM, default=cur.get(CONF_EVENTS_ALARM, False)): bool,
            vol.Optional(CONF_EVENTS_TAMPER, default=cur.get(CONF_EVENTS_TAMPER, False)): bool,
            vol.Optional(CONF_EVENTS_ERROR, default=cur.get(CONF_EVENTS_ERROR, False)): bool,
            vol.Optional(CONF_EVENT_LOG_MAX, default=cur.get(CONF_EVENT_LOG_MAX, DEFAULT_EVENT_LOG_MAX)): vol.Coerce(int),
        })

        webhook_url = get_webhook_url(self.hass, self._config_entry.entry_id)

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "webhook_url": webhook_url,
                "tp_endpoint": "/events/webhook",
                "auth_type": "None",
            },
        )

