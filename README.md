# TechPoint Home Assistant Integration

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD%202--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-0.4.7-blue.svg)
[![HA min version](https://img.shields.io/badge/Home%20Assistant-%3E%3D2024.1-blue.svg)](https://www.home-assistant.io/)

Custom Home Assistant integration for **TechPoint Access Control Systems** (both cloud and LAN-based controllers).

## Features

- **Cloud & LAN Support**: Connects to TechPoint via cloud API or direct LAN controller
- **Real-time Events**: WebHook-based real-time event notifications for instant state updates (LAN only)
- **Device Types**: Supports doors, zones, areas, and events
- **Smart Device Grouping**: Group devices by type or per-item for flexible organization
- **Multi-language**: Danish (da), English (en), and 10+ other languages
- **Custom Services**: Door control, access management, and more
- **Sensors & State**: Monitor battery, signal strength, last activity, and system status

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
| **Binary Sensor** | Zone intrusion detection |
| **Sensor** | Battery level, signal strength, last activity, event log |

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
| `techpoint.access_create_cardholder` | Create a new cardholder |
| `techpoint.access_update_cardholder` | Update a cardholder |
| `techpoint.access_delete_cardholder` | Delete a cardholder |
| `techpoint.access_list_cards` | List access cards |
| `techpoint.access_list_cards_filter` | Filter access cards |
| `techpoint.access_create_card` | Create an access card |
| `techpoint.access_update_card` | Update an access card |
| `techpoint.access_delete_card` | Delete an access card |
| `techpoint.access_get_groups` | List access groups |
| `techpoint.events_get` | Query events with optional filters |
| `techpoint.call_api` | Call any TechPoint API endpoint directly |
| `techpoint.refresh` | Trigger an immediate data refresh |
| `techpoint.cleanup_orphan_devices` | Remove legacy orphan devices |

See `custom_components/techpoint/services.yaml` for full parameter documentation.

## Real-time Events (LAN Only)

When using LAN mode, the integration configures a WebHook on the TechPoint controller for instant event notifications. Doors, alarms, and other events are reflected in Home Assistant within seconds.

Configure which event categories to receive under **Options**:
- Door/access events
- Alarm/intrusion events
- Tamper events
- Error/fault events

The webhook URL is shown in the **Options** page for reference. The webhook is automatically cleaned up when the integration is removed.

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
