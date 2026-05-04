# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.4] - 2026-05-04

### Added
- **User-defined Inputs** as `binary_sensor` entities (ioType 28) — active when state=2
- **User-defined Outputs** as `switch` entities (ioType 29) — toggle active/passive via HA
- **Cardholder count** sensor on the controller device
- **I/O and System control** view in example dashboard (4-view multi-tab layout)
- **Cardholder management** and **Create access** views in example dashboard
- Card numbers shown in cardholder dropdown (e.g. `Name (12345, 67890)`)
- New scripts: `techpoint_apply_threat_level`, `techpoint_global_door_open`, `techpoint_global_door_release`
- Threat level dropdown (`input_select`) with options 0–4 in access package
- Event categories default to `true` for new LAN installations
- Webhook `registered_at` timestamp and `event_filter` exposed as sensor attributes
- I/O state change events added to webhook event filter (keyword: output/input/relay/digital)

### Fixed
- Webhook POST body now correctly wrapped in `{"eventWebHook": {...}}` — previously returned 400
- User-defined I/O fetch changed from `GET ?ioType=` to `POST /filter` with body — fixes 400 errors flooding TechPoint event log every poll cycle
- Webhook no longer deleted on integration reload/update — only removed on true uninstall (`async_remove_entry`)
- HACS zip structure fixed: files now at zip root, resolving "Integration not found" after update
- Removed non-existent `email`/`phone` fields from cardholder create/update package scripts

### Changed
- `Platform.SWITCH` added to `PLATFORMS` list
- Coordinator uses `asyncio.gather(return_exceptions=True)` for resilient multi-fetch
- `device.py` extended with `input`/`output` kind branches for `build_device_info()`
- Release workflow (`release.yml`): zip built with `cd custom_components/techpoint && zip -r ../../techpoint.zip .`

## [0.5.2] - 2026-03-21

### Added
- Faroese (fo), Ukrainian (uk) and Kalaallisut/Greenlandic (kl) translations

### Fixed
- Danish (da) translation: replaced English words with proper Danish equivalents (Auth type → Godkendelsestype, Device ID → Enheds-ID, Devices → Enheder, Realtime → Realtid, Eventlog → Hændelseslog, copy/paste → kopiér/indsæt)
- Completed all previously partial translations (de, el, es, fi, is, it, nl, no, pl, sv) — only door mode states were translated before; all config flow, options and sensor strings are now fully translated

## [0.5.0] - 2026-03-21

### Changed
- Version bump to 0.5.0 for first public HACS release
- Added `hacs.json` for HACS integration store compatibility
- Updated `manifest.json` documentation URL to GitHub repository

### Fixed
- Removed duplicate `add_update_listener` registration in `async_setup_entry`
- Translated all Danish error messages in API clients to English
- Cloud mode diagnostics now reports configuration correctly without webhook setup
- Silent `except: pass` blocks in unload path now emit debug log entries

## [0.4.7] - 2025-03-01

### Fixed
- Removed duplicate `add_update_listener` registration in `async_setup_entry`
- Translated Danish error messages in API clients to English for international compatibility
- Cloud mode diagnostics now correctly reports configuration even without webhook setup
- Silent `except: pass` blocks in unload path now emit debug log entries

### Changed
- `manifest.json` documentation URL updated to GitHub repository
- Added `hacs.json` for HACS integration store compatibility

## [0.4.6] - 2025-02-15

### Fixed
- Cloud auth error messages now show device online status when `jwtToken` is missing
- LAN and Cloud API error messages unified to English

## [0.4.5] - 2025-02-01

### Added
- Real-time WebHook support for LAN mode (instant event updates)
- Device grouping options: group by type or per-item
- Full Danish translation (da) support
- Support for multiple TechPoint instances in Home Assistant
- Controller device in device registry (like Shelly devices)
- Automatic cleanup of orphan devices from legacy versions

### Changed
- Refactored API client factory to support both cloud and LAN cleanly
- Improved device naming and organization
- Enhanced error handling for SSL verification failures

### Fixed
- Device name conflicts when using grouped devices
- Service registration on multiple integration instances
- WebHook cleanup on integration unload

## [0.4.0] - 2024-12-15

### Added
- Basic cloud and LAN mode support
- Lock, Select, Button, Alarm Control Panel, Binary Sensor, Sensor platforms
- Config flow for easy setup
- Custom services (lock/unlock, call relay, clear alarm, set mode)
- Sensor data: battery, signal strength, last activity

### Fixed
- Initial API connection errors

## [0.3.0] - Earlier versions

- Development versions, not released publicly
