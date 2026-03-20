# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
