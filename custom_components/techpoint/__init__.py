from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .api.factory import create_client
from .const import (
    CONF_BASE_URL,
    CONF_DEVICE_GROUPING,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_DEVICE_GROUPING,
    DEFAULT_NAME,
    DOMAIN,
    MANUFACTURER,
    MODEL_CONTROLLER,
    PLATFORMS,
)
from .coordinator import TechPointCoordinator
from .webhook import async_setup_realtime_events, async_unload_realtime_events, async_remove_realtime_events

_LOGGER = logging.getLogger(__name__)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_cleanup_orphan_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove legacy/orphan TechPoint devices that no longer have entities.

    This fixes the "double devices" effect when moving from per-door/per-zone
    devices to grouped devices. We only remove devices that have **zero** entities
    attached, so it's safe.
    """

    # Wait a moment so platforms have time to create entities and attach devices.
    await asyncio.sleep(2)

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    devices = dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    removed = 0

    # If older versions created grouped devices with the entry_id in the name,
    # rename them to the configured controller name.
    cfg = {**entry.data, **(entry.options or {})}
    base_name = cfg.get(CONF_NAME, DEFAULT_NAME)
    rename_map = {
        f"{entry.entry_id} - Døre": f"{base_name} - Døre",
        f"{entry.entry_id} - Zoner": f"{base_name} - Zoner",
        f"{entry.entry_id} - Områder": f"{base_name} - Områder",
        # Legacy English variants just in case
        f"{entry.entry_id} - Doors": f"{base_name} - Døre",
        f"{entry.entry_id} - Zones": f"{base_name} - Zoner",
        f"{entry.entry_id} - Areas": f"{base_name} - Områder",
    }

    for dev in devices:
        # Rename legacy grouped devices if needed.
        if dev.name in rename_map:
            try:
                device_registry.async_update_device(dev.id, name=rename_map[dev.name])
            except Exception:  # noqa: BLE001
                _LOGGER.debug("TechPoint: could not rename device %s", dev.name, exc_info=True)

        # Never touch the controller device.
        if (DOMAIN, entry.entry_id) in (dev.identifiers or set()):
            continue

        ent_entries = er.async_entries_for_device(entity_registry, dev.id)
        if ent_entries:
            continue

        try:
            device_registry.async_remove_device(dev.id)
            removed += 1
        except Exception:  # noqa: BLE001
            _LOGGER.debug("TechPoint: could not remove device %s", dev.name, exc_info=True)

    if removed:
        _LOGGER.info("TechPoint: removed %s orphan device(s)", removed)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TechPoint from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Options override data when present
    cfg = {**entry.data, **(entry.options or {})}

    client = create_client(hass, cfg[CONF_BASE_URL], cfg)
    coordinator = TechPointCoordinator(
        hass,
        entry,
        client,
        cfg.get(CONF_NAME, DEFAULT_NAME),
        int(cfg.get(CONF_SCAN_INTERVAL, 10)),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"TechPoint: initial refresh failed: {err}") from err

    # Create controller device in registry (nice 'Shelly-like' UI)
    try:
        api_info = (coordinator.data or {}).get("api_info") or {}
        sw = api_info.get("version") or api_info.get("apiVersion") or api_info.get("api_version")

        sw_version = None
        if isinstance(sw, dict):
            # Typical: {major:1, minor:12, revision:0}
            major = sw.get('major') or sw.get('Major')
            minor = sw.get('minor') or sw.get('Minor')
            rev = sw.get('revision') or sw.get('rev') or sw.get('Revision')
            if major is not None and minor is not None and rev is not None:
                sw_version = f"{major}.{minor}.{rev}"
            else:
                # Fallback if keys differ
                sw_version = '.'.join(str(x) for x in sw.values() if x is not None) or None
        elif sw is not None:
            sw_version = str(sw)

        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=cfg.get(CONF_NAME, DEFAULT_NAME),
            manufacturer=MANUFACTURER,
            model=MODEL_CONTROLLER,
            sw_version=sw_version,
            configuration_url=cfg.get(CONF_BASE_URL),
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("TechPoint: could not create controller device entry", exc_info=True)

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "controller_identifier": (DOMAIN, entry.entry_id),
        "device_grouping": cfg.get(CONF_DEVICE_GROUPING, DEFAULT_DEVICE_GROUPING),
        "manufacturer": MANUFACTURER,
        "model_controller": MODEL_CONTROLLER,
    }

    # Real-time events via TechPoint WebHook (LAN only)
    await async_setup_realtime_events(hass, entry, client, cfg)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    from .services import async_register_services

    if not hass.data[DOMAIN].get("_services_registered"):
        await async_register_services(hass)
        hass.data[DOMAIN]["_services_registered"] = True

    # Cleanup of legacy devices (old per-door/per-zone devices)
    hass.async_create_task(_async_cleanup_orphan_devices(hass, entry))

    # Automatically remove entities for doors/zones/areas/IO that have been
    # deleted on the TechPoint controller (after a few consecutive polls confirm
    # they're really gone, not just a transient fetch failure), then drop any
    # devices left empty by that removal.
    def _on_coordinator_update() -> None:
        from .services import _cleanup_orphan_devices_for_entry, _cleanup_stale_entities_for_entry

        removed = _cleanup_stale_entities_for_entry(hass, entry.entry_id, require_consecutive_misses=True)
        if removed:
            _LOGGER.info("TechPoint: removed %s stale entit(y/ies) no longer present on controller", removed)
            _cleanup_orphan_devices_for_entry(hass, entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))

    # Reload integration when options change (ensures webhook reconfigured)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called by HA when the config entry is permanently removed (not on reload)."""
    try:
        data = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
        client = data.get("client")
        if client is None:
            from .api.factory import create_client
            cfg = {**entry.data, **(entry.options or {})}
            client = create_client(hass, cfg[CONF_BASE_URL], cfg)
        await async_remove_realtime_events(hass, entry, client)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("TechPoint: error during webhook cleanup on removal", exc_info=True)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Unregister HA webhook handler only — no DELETE to TechPoint on reload/update.
    # async_remove_entry handles true removal.
    try:
        data = (hass.data.get(DOMAIN) or {}).get(entry.entry_id) or {}
        client = data.get("client")
        if client is not None:
            await async_unload_realtime_events(hass, entry, client)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("TechPoint: error during webhook handler unregister on unload", exc_info=True)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Unregister services if no entries left
    if unload_ok and not [k for k in (hass.data.get(DOMAIN) or {}).keys() if k != "_services_registered"]:
        try:
            from .services import async_unregister_services

            await async_unregister_services(hass)
            hass.data[DOMAIN].pop("_services_registered", None)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("TechPoint: error unregistering services", exc_info=True)

        try:
            hass.data.pop(DOMAIN, None)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("TechPoint: error cleaning up hass.data", exc_info=True)

    return unload_ok
