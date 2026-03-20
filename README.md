# TechPoint Home Assistant Integration

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD%202--Clause-orange.svg)](https://opensource.org/licenses/BSD-2-Clause)
![Version](https://img.shields.io/badge/version-0.4.5-blue.svg)

Custom Home Assistant integration for **TechPoint Access Control Systems** (both cloud and LAN-based controllers).

## Features

- 🔐 **Cloud & LAN Support**: Connects to TechPoint via cloud API or direct LAN controller
- ⚡ **Real-time Events**: WebHook-based real-time event polling for instant state updates
- 🚪 **Device Types**: Supports doors, zones, areas, and events
- 🎛️ **Smart Device Grouping**: Group devices by type or per-item for flexible organization
- 🌍 **Multi-language**: Danish (da), English (en), and 10+ other language support
- 🔧 **Custom Services**: Lock/unlock, call relay, clear alarm, and more
- 📊 **Sensors & State**: Monitor battery, signal strength, last activity, and system status

## Installation

### Prerequisites
- Home Assistant 2024.1 or later
- TechPoint API access (cloud or LAN)
- Network connectivity to TechPoint controller

### Steps

1. **Copy the integration** to your Home Assistant `custom_components` directory:
   ```bash
   git clone https://github.com/GregersK/homeassistant-techpoint.git
   cp -r homeassistant-techpoint/custom_components/techpoint ~/.homeassistant/custom_components/
   ```

2. **Restart Home Assistant**

3. **Add via UI**:
   - Go to **Settings → Devices & Services → Create Integration**
   - Search for **TechPoint**
   - Choose **Cloud** or **LAN** mode
   - Enter your credentials and controller details

## Configuration

### Cloud Mode
```yaml
TechPoint:
  Mode: Cloud
  Base URL: https://api.techpoint.cloud (or your endpoint)
  Device ID: your-device-id
  Username: your-username
  Password: your-password
  Auth Type: 2
```

### LAN Mode
```yaml
TechPoint:
  Mode: LAN
  Base URL: https://192.168.1.100:8080 (or your controller IP)
  Username: admin
  Password: controller-password
  Verify SSL: No (for self-signed certificates)
```

## Supported Platforms

- **Lock**: Door locks and relay control
- **Select**: Device modes and configurations
- **Button**: Trigger actions (call relay, clear alarm, etc.)
- **Alarm Control Panel**: Zone and area alarms
- **Binary Sensor**: Motion, door status, alarm states
- **Sensor**: Battery level, signal strength, last activity

## Device Grouping

By default, devices are grouped by **type** (Doors, Zones, Areas). You can also group **per-item** for a flatter structure.

Change grouping in **Options** after installation.

## Services

The integration provides several custom services:

- `techpoint.lock_doors`: Lock specific doors
- `techpoint.unlock_doors`: Unlock specific doors
- `techpoint.call_relay`: Trigger relay output
- `techpoint.clear_alarm`: Clear zone/area alarm
- `techpoint.set_mode`: Change device mode

See `services.yaml` for full documentation.

## Real-time Events (LAN Only)

When using LAN mode, the integration sets up a WebHook on your TechPoint controller for instant event notifications. This means doors, alarms, and other events are reflected in Home Assistant within seconds.

The webhook is automatically configured and removed when the integration is unloaded.

## Troubleshooting

### "Device not found" in cloud mode
- Verify the device ID is correct
- Check that API credentials are valid
- Ensure multi-domain lookup is enabled in TechPoint Web API configuration

### Connection fails in LAN mode
- Verify the controller IP and port are reachable from Home Assistant
- If using self-signed SSL: disable SSL verification in options
- Check firewall rules allow HTTPS traffic

### WebHook not being called
- Confirm the Home Assistant instance is reachable from the TechPoint controller
- Check that outbound HTTPS (to HA) is not blocked on the LAN
- Review Home Assistant logs for webhook registration errors

## Development

### Structure
```
custom_components/techpoint/
├── api/              # API clients (cloud, LAN)
├── __init__.py       # Setup & platform loading
├── config_flow.py    # Configuration UI
├── coordinator.py    # Data coordinator
├── services.py       # Custom service handlers
├── webhook.py        # Real-time event handler
└── *.py              # Platform implementations
```

### Running Tests
```bash
python -m pytest tests/
```

## API Documentation

See the official TechPoint API docs:
https://app.swaggerhub.com/apis-docs/techsolutions.dk/tech-point-api/1

## License

[BSD 2-Clause License](LICENSE)

## Support

For issues and feature requests: https://github.com/GregersK/homeassistant-techpoint/issues

---

**Author**: [@GregersK](https://github.com/GregersK)
