# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
