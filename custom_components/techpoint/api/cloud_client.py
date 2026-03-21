from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from aiohttp import ClientError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import (
    CONF_AUTH_TYPE,
    CONF_DEVICE_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_AUTH_TYPE,
    DEFAULT_VERIFY_SSL_CLOUD,
)
from .lan_client import LanApiClient


class CloudApiClient(LanApiClient):
    """TechPoint Cloud API client.

    TechPoint Cloud API is a reverse proxy that securely exposes the *regular* TechPoint Web API.
    After authenticating against /api/v1/auth and receiving a JWT, subsequent calls go through:

        <cloud_root>/api/v1/device/<device_id>/<techpoint_api_path>

    We implement this by reusing the LAN client logic and overriding request/auth.
    """

    def __init__(self, hass, cloud_root: str, entry_data: Dict[str, Any]) -> None:
        self.cloud_root = cloud_root.rstrip("/")
        self.device_id = str(entry_data.get(CONF_DEVICE_ID) or "").strip()
        if not self.device_id:
            raise ValueError("Cloud device_id is missing")

        self.username = str(entry_data.get(CONF_USERNAME) or "").strip()
        self.password = str(entry_data.get(CONF_PASSWORD) or "").strip()
        self.auth_type = int(entry_data.get(CONF_AUTH_TYPE) or DEFAULT_AUTH_TYPE)

        device_base = f"{self.cloud_root}/api/v1/device/{self.device_id}/api/v1"

        # Initialize LAN client against the device-proxy base, but we will override session/token.
        super().__init__(hass, device_base, entry_data)

        # Cloud should generally verify SSL; allow override.
        verify_ssl = bool(entry_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL_CLOUD))
        self.session = async_get_clientsession(hass, verify_ssl=verify_ssl)

        self._token: Optional[str] = None
        self._auth_lock = asyncio.Lock()

    async def _authenticate(self) -> str:
        """Authenticate and return JWT token."""
        url = f"{self.cloud_root}/api/v1/auth"
        body = {
            "userName": self.username,
            "password": self.password,
            "deviceId": self.device_id,
            "authType": self.auth_type,
        }

        async with self._auth_lock:
            # Another coroutine may have already authenticated while we waited
            if self._token:
                return self._token

            try:
                async with self.session.request(
                    "POST",
                    url,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    json=body,
                    timeout=25,
                ) as resp:
                    txt = await resp.text()
                    try:
                        js = json.loads(txt) if txt else None
                    except Exception:
                        js = None

                    if resp.status >= 400:
                        detail = js or txt
                        raise RuntimeError(f"Cloud auth error: {resp.status}, message={detail}, url='{url}'")

                    if not isinstance(js, dict):
                        raise RuntimeError(f"Cloud auth: unexpected response: {txt}")

                    token = js.get("jwtToken")
                    if not token:
                        # If device is offline, Cloud returns OK but jwtToken=null
                        is_online = js.get("isDeviceOnline")
                        raise RuntimeError(
                            f"Cloud auth: jwtToken missing (isDeviceOnline={is_online}). "
                            "Check deviceId and that the device is online."
                        )

                    self._token = str(token)
                    return self._token
            except asyncio.TimeoutError as e:
                raise RuntimeError("Cloud auth timeout") from e
            except ClientError as e:
                raise RuntimeError(f"Cloud auth error: {e}") from e

    async def _ensure_token(self) -> None:
        if self._token:
            return
        await self._authenticate()

    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
        _retry: bool = True,
    ) -> Any:
        # Ensure JWT
        await self._ensure_token()

        url = f"{self.base_url}{path}"
        headers = self._headers()

        try:
            async with self.session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=body,
                timeout=25,
            ) as resp:
                # Re-auth on 401 once
                if resp.status == 401 and _retry:
                    self._token = None
                    await self._ensure_token()
                    return await self._request(method, path, params=params, body=body, _retry=False)

                if resp.status >= 400:
                    txt = await resp.text()
                    try:
                        js_err = json.loads(txt) if txt else None
                    except Exception:
                        js_err = None
                    detail = js_err or txt
                    raise RuntimeError(
                        f"Cloud API error: {resp.status}, message={detail}, url='{url}'"
                    )

                ctype = resp.headers.get("Content-Type", "")
                if "json" in ctype:
                    return await resp.json(content_type=None)
                txt = await resp.text()
                try:
                    return json.loads(txt)
                except Exception:
                    return txt
        except asyncio.TimeoutError as e:
            raise RuntimeError("Cloud API timeout") from e
        except ClientError as e:
            raise RuntimeError(f"Cloud API error: {e}") from e

    async def get_api_info(self) -> Any:
        """Return API version info (GET /info/api)."""
        return await self._request("GET", "/info/api")
