from __future__ import annotations
from typing import Any, Callable, Dict, Mapping
from datetime import timedelta
import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Backoff schedule (seconds) applied per resource key after a fetch failure, so a
# transient glitch heals itself instead of disabling that data type until the
# integration is reloaded. Capped at the last value.
_RETRY_BACKOFF_S = (10, 30, 60, 120, 300)

# Each poll group is fetched on its own interval. Most ticks therefore send only a
# single small request (the inputs) to the controller's embedded web server.
POLL_GROUPS: dict[str, tuple[str, ...]] = {
    "inputs": ("io_inputs",),
    "outputs": ("io_outputs",),
    "doors": ("doors",),
    "areas": ("areas",),
    "zones": ("zones",),
    "controller": ("global_door_control", "threat_level"),
    "info": ("api_info", "cardholders_meta"),
}
# API version and cardholder count rarely change.
_INFO_INTERVAL_S = 900

# The next tick is scheduled to whole seconds (minus HA's random sub-second
# offset), so it can fire slightly before a group's interval has fully elapsed.
_DUE_TOLERANCE_S = 1.0

# Where each fetched key ends up in coordinator.data, and its value when empty.
_DATA_DEFAULTS: dict[str, Any] = {
    "doors": [],
    "areas": [],
    "zones": [],
    "io_inputs": [],
    "io_outputs": [],
    "api_info": {},
    "cardholder_count": None,
    "global_door_control_active": None,
    "threat_level": None,
}


class TechPointCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client,
        name: str,
        intervals: Mapping[str, int],
    ) -> None:
        self._intervals: dict[str, float] = {
            group: float(max(1, int(intervals.get(group, 60)))) for group in POLL_GROUPS
        }
        self._intervals["info"] = float(_INFO_INTERVAL_S)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=timedelta(seconds=min(self._intervals.values())),
        )
        self.client = client
        self._last_fetch: dict[str, float] = {}
        self._forced_groups: set[str] = set()
        # Per-key failure bookkeeping: consecutive failure count and the monotonic
        # time before which that key isn't retried. A transient failure backs off
        # and retries on its own; it never disables a data type permanently.
        self._key_fail_count: dict[str, int] = {}
        self._key_retry_after: dict[str, float] = {}
        # Doors are always fetched (never backed off), so a doors failure means the
        # controller is unreachable, and the next doors success means it is back.
        self._controller_down = False
        # Keys whose fetch succeeded on the most recent poll. Used to gate
        # stale-entity cleanup so a failed or skipped fetch is never mistaken for
        # a door/zone/output that was actually removed on the controller.
        self.last_cycle_ok_keys: set[str] = set()

    async def async_request_refresh(self) -> None:
        """Refresh every poll group (used by the refresh service and HA's update action)."""
        self._forced_groups.update(POLL_GROUPS)
        await super().async_request_refresh()

    async def async_request_group_refresh(self, *groups: str) -> None:
        """Refresh only the given poll groups, e.g. after a door command or webhook event."""
        self._forced_groups.update(g for g in groups if g in POLL_GROUPS)
        await super().async_request_refresh()

    def _fetchers(self) -> dict[str, Callable[[], Any]]:
        c = self.client
        list_areas = getattr(c, "list_areas_status", None) or getattr(c, "list_areas", None)
        list_zones = getattr(c, "list_zones_status", None) or getattr(c, "list_zones", None)
        get_io = getattr(c, "get_io_userdefined", None)
        get_api_info = getattr(c, "get_api_info", None)
        list_cardholders = getattr(c, "list_card_holders_filter", None)
        get_gdc = getattr(c, "get_global_door_control", None)
        get_threat = getattr(c, "get_threat_level", None)
        fetchers: dict[str, Callable[[], Any]] = {"doors": c.list_doors}
        if get_io:
            fetchers["io_inputs"] = lambda: get_io(28)
            fetchers["io_outputs"] = lambda: get_io(29)
        if list_areas:
            fetchers["areas"] = list_areas
        if list_zones:
            fetchers["zones"] = list_zones
        if get_gdc:
            fetchers["global_door_control"] = get_gdc
        if get_threat:
            fetchers["threat_level"] = get_threat
        if get_api_info:
            fetchers["api_info"] = get_api_info
        if list_cardholders:
            fetchers["cardholders_meta"] = lambda: list_cardholders({"cardHolderFilter": {"doNotFetchData": True}})
        return fetchers

    def _group_due(self, group: str, now: float) -> bool:
        last = self._last_fetch.get(group)
        return (
            group in self._forced_groups
            or last is None
            or now - last >= self._intervals[group] - _DUE_TOLERANCE_S
        )

    def _record_failure(self, key: str, now: float, err: BaseException) -> None:
        count = self._key_fail_count.get(key, 0) + 1
        self._key_fail_count[key] = count
        backoff = _RETRY_BACKOFF_S[min(count, len(_RETRY_BACKOFF_S)) - 1]
        self._key_retry_after[key] = now + backoff
        _LOGGER.warning("TechPoint: %s fetch failed (retrying in %ss): %s", key, backoff, err)

    def _schedule_next(self, now: float) -> None:
        """Wake up exactly when the next poll group is due, instead of on a fixed tick."""
        waits = [
            self._last_fetch.get(group, now) + interval - now
            for group, interval in self._intervals.items()
        ]
        self.update_interval = timedelta(seconds=max(1.0, min(waits)))

    async def _async_update_data(self) -> Dict[str, Any]:
        now = time.monotonic()
        fetchers = self._fetchers()
        data: Dict[str, Any] = {**_DATA_DEFAULTS, **(self.data or {})}

        due_groups = [g for g in POLL_GROUPS if self._group_due(g, now)]
        self._forced_groups.difference_update(due_groups)
        keys = [
            key
            for group in due_groups
            for key in POLL_GROUPS[group]
            if key in fetchers and (key == "doors" or now >= self._key_retry_after.get(key, 0.0))
        ]
        for group in due_groups:
            self._last_fetch[group] = now

        # Requests are serialized in the client; inputs go first as they are time-critical.
        results = await asyncio.gather(*(fetchers[k]() for k in keys), return_exceptions=True)

        ok_keys: set[str] = set()
        for key, val in zip(keys, results):
            if isinstance(val, Exception):
                if key == "doors":
                    _LOGGER.debug("TechPoint: doors fetch failed: %s", val)
                    data["doors"] = []
                    self._controller_down = True
                else:
                    self._record_failure(key, now, val)
                    if key in data:
                        data[key] = _DATA_DEFAULTS[key]
                continue
            if key == "doors" and self._controller_down:
                # The controller is reachable again: retry everything that backed off
                # during the outage now, instead of waiting out each key's backoff.
                self._controller_down = False
                self._key_fail_count.clear()
                self._key_retry_after.clear()
            self._key_fail_count.pop(key, None)
            self._key_retry_after.pop(key, None)
            ok_keys.add(key)
            if key == "cardholders_meta":
                data["cardholder_count"] = val.get("count") if isinstance(val, dict) else None
            elif key == "global_door_control":
                data["global_door_control_active"] = (val or {}).get("status", {}).get("active")
            elif key == "threat_level":
                data["threat_level"] = (val or {}).get("currentThreatLevel", {}).get("level")
            else:
                data[key] = val or _DATA_DEFAULTS.get(key, [])

        self.last_cycle_ok_keys = ok_keys
        self._schedule_next(time.monotonic())
        return data
