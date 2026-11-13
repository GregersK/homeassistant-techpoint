from __future__ import annotations
from typing import Any, Dict
from datetime import timedelta
import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Backoff schedule (seconds) applied per optional resource key after a fetch
# failure, so a transient glitch heals itself instead of disabling that data
# type until the integration is reloaded. Capped at the last value.
_RETRY_BACKOFF_S = (30, 60, 120, 300)

# Data that rarely changes is fetched at most this often; in between, the last
# value is reused, so each poll only asks the controller for live status.
_SLOW_KEYS = {"api_info": "api_info", "cardholders_meta": "cardholder_count"}
_SLOW_INTERVAL_S = 900


class TechPointCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client,
        name: str,
        update_interval_s: int,
        input_interval_s: int,
    ) -> None:
        # The coordinator ticks at the (fast) input interval. Most ticks fetch only
        # the user-defined inputs; everything else is fetched every update_interval_s.
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=timedelta(seconds=max(1, min(input_interval_s, update_interval_s))),
        )
        self.client = client
        self._full_interval_s = max(1, update_interval_s)
        self._last_full: float | None = None
        self._force_full = False
        # Per-key failure bookkeeping for optional resources: consecutive failure
        # count and the monotonic time before which we won't retry that key.
        # A transient failure backs off and retries on its own — it never
        # permanently disables a data type the way an unconditional "skip
        # forever" flag would (that previously required a full integration
        # reload to recover from a single blip).
        self._key_fail_count: dict[str, int] = {}
        self._key_retry_after: dict[str, float] = {}
        # Keys whose fetch succeeded on the most recent poll cycle. Used to gate
        # stale-entity cleanup so a single transient API failure (which leaves
        # that key's data empty for the cycle) can never be mistaken for a
        # door/zone/output that was actually removed on the controller.
        self.last_cycle_ok_keys: set[str] = set()
        self._slow_fetched_at: dict[str, float] = {}

    def _due_for_retry(self, key: str, now: float) -> bool:
        if now < self._key_retry_after.get(key, 0.0):
            return False
        if key in _SLOW_KEYS and key in self._slow_fetched_at:
            return now - self._slow_fetched_at[key] >= _SLOW_INTERVAL_S
        return True

    async def async_request_refresh(self) -> None:
        # Requested refreshes (after an entity command or a webhook event) should
        # pick up everything, not just the inputs.
        self._force_full = True
        await super().async_request_refresh()

    async def _async_update_data(self) -> Dict[str, Any]:
        now = time.monotonic()
        full_due = (
            self._force_full
            or self.data is None
            or self._last_full is None
            # Small tolerance so tick jitter doesn't push a full update one tick late.
            or now - self._last_full >= self._full_interval_s - 0.5
        )
        if full_due:
            self._force_full = False
            data = await self._async_full_update()
            self._last_full = now
            return data
        return await self._async_inputs_update(now)

    async def _async_inputs_update(self, now: float) -> Dict[str, Any]:
        """Refresh only the user-defined inputs, reusing everything else from the last poll."""
        data = dict(self.data or {})
        get_io = getattr(self.client, "get_io_userdefined", None)
        ok_keys: set[str] = set()
        if get_io and self._due_for_retry("io_inputs", now):
            try:
                data["io_inputs"] = await get_io(28) or []
            except Exception as err:  # noqa: BLE001
                self._record_failure("io_inputs", now, err)
            else:
                self._key_fail_count.pop("io_inputs", None)
                self._key_retry_after.pop("io_inputs", None)
                ok_keys.add("io_inputs")
        self.last_cycle_ok_keys = ok_keys
        return data

    def _record_failure(self, key: str, now: float, err: BaseException) -> None:
        count = self._key_fail_count.get(key, 0) + 1
        self._key_fail_count[key] = count
        backoff = _RETRY_BACKOFF_S[min(count, len(_RETRY_BACKOFF_S)) - 1]
        self._key_retry_after[key] = now + backoff
        _LOGGER.warning("TechPoint: %s fetch failed (retrying in %ss): %s", key, backoff, err)

    async def _async_full_update(self) -> Dict[str, Any]:
        """Fetch doors, AIA area/zone status, user-defined I/O, cardholder count, and controller state."""
        try:
            list_areas = getattr(self.client, "list_areas_status", None) or getattr(self.client, "list_areas", None)
            list_zones = getattr(self.client, "list_zones_status", None) or getattr(self.client, "list_zones", None)
            get_api_info = getattr(self.client, "get_api_info", None)
            get_io = getattr(self.client, "get_io_userdefined", None)
            list_cardholders_filter = getattr(self.client, "list_card_holders_filter", None)
            get_global_door_control = getattr(self.client, "get_global_door_control", None)
            get_threat_level = getattr(self.client, "get_threat_level", None)

            now = time.monotonic()
            tasks: list = [self.client.list_doors()]
            task_keys = ["doors"]

            if list_areas and self._due_for_retry("areas", now):
                tasks.append(list_areas())
                task_keys.append("areas")
            if list_zones and self._due_for_retry("zones", now):
                tasks.append(list_zones())
                task_keys.append("zones")
            if get_api_info and self._due_for_retry("api_info", now):
                tasks.append(get_api_info())
                task_keys.append("api_info")
            if get_io and self._due_for_retry("io_inputs", now):
                tasks.append(get_io(28))
                task_keys.append("io_inputs")
            if get_io and self._due_for_retry("io_outputs", now):
                tasks.append(get_io(29))
                task_keys.append("io_outputs")
            if list_cardholders_filter and self._due_for_retry("cardholders_meta", now):
                tasks.append(list_cardholders_filter({"cardHolderFilter": {"doNotFetchData": True}}))
                task_keys.append("cardholders_meta")
            if get_global_door_control and self._due_for_retry("global_door_control", now):
                tasks.append(get_global_door_control())
                task_keys.append("global_door_control")
            if get_threat_level and self._due_for_retry("threat_level", now):
                tasks.append(get_threat_level())
                task_keys.append("threat_level")

            results = await asyncio.gather(*tasks, return_exceptions=True)

            data: Dict[str, Any] = {
                "doors": [], "areas": [], "zones": [], "api_info": {},
                "io_inputs": [], "io_outputs": [], "cardholder_count": None,
                "global_door_control_active": None, "threat_level": None,
            }
            # Carry over slow data that isn't refetched this cycle.
            prev = self.data or {}
            for data_key in _SLOW_KEYS.values():
                if prev.get(data_key) is not None:
                    data[data_key] = prev[data_key]
            ok_keys: set[str] = set()
            for key, val in zip(task_keys, results):
                if isinstance(val, Exception):
                    if key != "doors":
                        self._record_failure(key, now, val)
                    else:
                        _LOGGER.debug("TechPoint: %s fetch failed: %s", key, val)
                    continue
                if key != "doors":
                    self._key_fail_count.pop(key, None)
                    self._key_retry_after.pop(key, None)
                if key in _SLOW_KEYS:
                    self._slow_fetched_at[key] = now
                ok_keys.add(key)
                if key == "cardholders_meta":
                    data["cardholder_count"] = (val or {}).get("count") if isinstance(val, dict) else None
                elif key == "global_door_control":
                    data["global_door_control_active"] = (val or {}).get("status", {}).get("active")
                elif key == "threat_level":
                    data["threat_level"] = (val or {}).get("currentThreatLevel", {}).get("level")
                else:
                    data[key] = val or data.get(key, [])

            self.last_cycle_ok_keys = ok_keys
            return data
        except Exception as e:
            _LOGGER.warning("TechPoint update failed: %s", e)
            raise
