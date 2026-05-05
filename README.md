# TechPoint Home Assistant Integration

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD%202--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.7.7-blue.svg)
[![HA min version](https://img.shields.io/badge/Home%20Assistant-%3E%3D2024.1-blue.svg)](https://www.home-assistant.io/)

Custom Home Assistant integration for **TechPoint Access Control Systems** (both cloud and LAN-based controllers).

## Features

- **Cloud & LAN Support**: Connects to TechPoint via cloud API or direct LAN controller
- **Real-time Events**: WebHook-based real-time event notifications for instant state updates (LAN only)
- **Device Types**: Supports doors, zones, areas, user-defined I/O, and events
- **Smart Device Grouping**: Group devices by type or per-item for flexible organization
- **Multi-language**: Danish (da), English (en), and 10+ other languages
- **Custom Services**: Door control, access management, threat level, global door control, and more
- **Sensors & State**: Monitor battery, signal strength, last activity, cardholder count, and system status
- **Access Management**: Full cardholder and card management with example dashboard

## Installation

### Via HACS (recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click the three-dot menu → **Custom repositories**
4. Add `https://github.com/GregersK/homeassistant-techpoint` as an **Integration**
5. Click **TechPoint** → **Download**
6. Restart Home Assistant

### Manual

```bash
git clone https://github.com/GregersK/homeassistant-techpoint.git
cp -r homeassistant-techpoint/custom_components/techpoint ~/.homeassistant/custom_components/
```

Restart Home Assistant.

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **TechPoint**
3. Choose **Cloud** or **LAN** mode and enter your credentials

### Prerequisites

- Home Assistant 2024.1 or later
- TechPoint API access — requires an API LAN or Cloud license on the TechPoint / Siedle Secure SC-600
- Network connectivity to the TechPoint controller

## Configuration

### Cloud Mode

| Field | Example |
|---|---|
| Base URL | `https://api.techpoint.cloud` |
| Device ID | `your-device-id` |
| Username | `your-username` |
| Password | `your-password` |
| Auth Type | `2` |

### LAN Mode

| Field | Example |
|---|---|
| Base URL | `https://192.168.1.100:8080` |
| Username | `admin` |
| Password | `controller-password` |
| Verify SSL | No (for self-signed certificates) |

## Supported Platforms

| Platform | Description |
|---|---|
| **Lock** | Door locks — open, release, secure, block |
| **Select** | Door mode selection (Normal, Release, PermanentRelease, Secure, Block) |
| **Button** | Momentary pulse actions |
| **Alarm Control Panel** | Area intrusion arm/disarm |
| **Binary Sensor** | Zone intrusion detection + user-defined inputs (ioType 28) |
| **Switch** | User-defined outputs (ioType 29) — toggle active/passive |
| **Sensor** | Door status, cardholder count, event log, webhook URL |

## Device Grouping

By default, devices are grouped **by type** (Doors, Zones, Areas). You can also group **per-item** for a flatter structure.

Change the grouping in **Options** after installation.

## Services

The integration provides the following custom services:

| Service | Description |
|---|---|
| `techpoint.management_set_door_status` | Set door status by door ID (Normal, Release, PermanentRelease, Secure, Block) |
| `techpoint.door_set_status_by_entity` | Set door status by selecting a TechPoint door entity |
| `techpoint.aia_update_zone` | Update an intrusion zone |
| `techpoint.aia_update_area` | Update an intrusion area |
| `techpoint.access_list_cardholders` | List access cardholders |
| `techpoint.access_list_cardholders_filter` | Filter cardholders |
| `techpoint.access_create_cardholder` | Create a new cardholder — returns `cardholder_id` |
| `techpoint.access_update_cardholder` | Update a cardholder |
| `techpoint.access_delete_cardholder` | Delete a cardholder |
| `techpoint.access_list_cards` | List access cards |
| `techpoint.access_list_cards_filter` | Filter access cards |
| `techpoint.access_create_card` | Create an access card — returns `card_id` |
| `techpoint.access_update_card` | Update an access card (use `accessGroupLinks` to assign access groups) |
| `techpoint.access_delete_card` | Delete an access card |
| `techpoint.access_get_groups` | List access groups — returns `access_groups` list |
| `techpoint.management_get_global_door_control` | Get global door control state — returns `active` (bool) |
| `techpoint.management_set_global_door_control` | Open or close all globally-controlled doors (`active: true/false`) |
| `techpoint.management_get_threat_level` | Get current threat level — returns `level` (0–4) |
| `techpoint.management_set_threat_level` | Set threat level (0=off, 1=normal, 2–4=level 1–3) |
| `techpoint.config_get_io_inputs` | List user-defined inputs with state — returns `inputs` list |
| `techpoint.config_get_io_outputs` | List user-defined outputs with state — returns `outputs` list |
| `techpoint.config_set_io_userdefined` | Set active (2) or passive (0) state on user-defined I/O |
| `techpoint.events_get` | Query events with optional filters |
| `techpoint.call_api` | Call any TechPoint API endpoint directly |
| `techpoint.refresh` | Trigger an immediate data refresh |
| `techpoint.cleanup_orphan_devices` | Remove legacy orphan devices |

See `custom_components/techpoint/services.yaml` for full parameter documentation.

> **Note:** The `entry_id` parameter is optional for all services. When only one TechPoint integration instance is configured, it is detected automatically.

## Access Management Package

The `examples/` directory contains a ready-to-use HA package for full cardholder and access management via the UI.

### Setup

1. Copy `examples/techpoint_access_package.yaml` to `config/packages/techpoint_access.yaml`
2. Enable packages in `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
3. Restart Home Assistant
4. Copy the dashboard from `examples/techpoint_access_dashboard.yaml` into a new Lovelace dashboard (Settings → Dashboards → Add → raw config editor)

### Creating a cardholder with access

1. Fill in the **Cardholder** fields (first name, last name, optional external ID)
2. Enter a **Card number**
3. Set **Valid from** and **Valid to** dates
4. Click **Load access groups** to populate the dropdowns
5. Select up to 3 **Access groups**
6. Click **Create cardholder, card & assign access**

A persistent notification confirms success.

### Managing existing cardholders

1. Click **Load cardholders** in the "Manage cardholder" section
2. Select a cardholder from the dropdown
3. Set a new **Valid to** date and/or change the **Access groups**
4. Click **Update** to save, or **Delete** to remove the cardholder and their linked card

### Scripts provided

| Script | Description |
|---|---|
| `script.techpoint_load_access_groups` | Fetch access groups from TechPoint and populate the three dropdowns |
| `script.techpoint_load_cardholders` | Fetch all cardholders (with card numbers) and populate the management dropdown |
| `script.techpoint_full_flow` | Create cardholder + card and assign access groups in one step |
| `script.techpoint_update_selected` | Update expiry date and access groups for the selected cardholder |
| `script.techpoint_delete_selected` | Delete the selected cardholder and their linked card |
| `script.techpoint_apply_threat_level` | Apply the selected threat level to TechPoint |
| `script.techpoint_global_door_open` | Open all globally-controlled doors |
| `script.techpoint_global_door_release` | Release global door control (return to normal) |

## Real-time Events (LAN Only)

When using LAN mode, the integration automatically registers a WebHook on the TechPoint controller for instant event notifications. Doors, alarms, and other events are reflected in Home Assistant within seconds.

Configure which event categories to receive under **Options** (all enabled by default for LAN):
- Door/access events
- Alarm/intrusion events
- Tamper/sabotage events
- Error/fault events

The webhook URL is shown in the **Options** page for easy reference. On integration reload or update, the webhook registration is preserved — no manual reconfiguration in TechPoint is needed. The webhook is only removed when the integration is fully uninstalled.

> **Note:** Real-time events are not supported in Cloud mode.

## Troubleshooting

### "Device not found" in cloud mode

- Verify the device ID is correct
- Check that API credentials are valid
- Ensure the device is online (check `isDeviceOnline` in the log)

### Connection fails in LAN mode

- Verify the controller IP and port are reachable from Home Assistant
- If using a self-signed SSL certificate: disable SSL verification in **Options**
- Check firewall rules allow HTTPS traffic

### WebHook not being called

- Confirm the Home Assistant instance is reachable from the TechPoint controller
- Check that outbound HTTPS to Home Assistant is not blocked on the LAN
- Review Home Assistant logs for webhook registration errors

## Development

### Structure

```
custom_components/techpoint/
├── api/              # API clients (cloud, LAN, factory)
├── __init__.py       # Setup & platform loading
├── config_flow.py    # Configuration UI
├── coordinator.py    # Data coordinator
├── services.py       # Custom service handlers
├── webhook.py        # Real-time event handler
└── *.py              # Platform implementations (lock, select, button, ...)
```

### API Documentation

See the official TechPoint API docs:
https://app.swaggerhub.com/apis-docs/techsolutions.dk/tech-point-api/1

## License

[BSD 2-Clause License](LICENSE)

## Support

For issues and feature requests: https://github.com/GregersK/homeassistant-techpoint/issues

---

**Author**: [@GregersK](https://github.com/GregersK)
