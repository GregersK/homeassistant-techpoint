from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "techpoint"

# Device metadata (used for device registry entries)
MANUFACTURER = "TechSolutions"
MODEL_CONTROLLER = "TechPoint"

PLATFORMS: list[Platform] = [
    Platform.LOCK,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

# Mode
CONF_MODE = "mode"
MODE_CLOUD = "cloud"
MODE_LAN = "lan"
MODES = [MODE_CLOUD, MODE_LAN]

# Common
CONF_BASE_URL = "base_url"  # Cloud root URL OR LAN host/IP
CONF_NAME = "name"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"

# Options / UI
CONF_DEVICE_GROUPING = "device_grouping"
GROUP_BY_TYPE = "type"
GROUP_BY_ITEM = "item"
DEVICE_GROUPINGS = [GROUP_BY_TYPE, GROUP_BY_ITEM]
DEFAULT_DEVICE_GROUPING = GROUP_BY_TYPE

DEFAULT_NAME = "TechPoint"
DEFAULT_SCAN_INTERVAL = 10

# Default SSL settings:
# - LAN controllers are often using self-signed certificates
# - Cloud is hosted with a public certificate
DEFAULT_VERIFY_SSL_LAN = False
DEFAULT_VERIFY_SSL_CLOUD = True

# Cloud (TechPoint Cloud API reverse proxy)
CONF_DEVICE_ID = "device_id"
CONF_AUTH_TYPE = "auth_type"  # typically 2
DEFAULT_AUTH_TYPE = 2
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# LAN auth
CONF_LAN_USERNAME = "lan_username"
CONF_LAN_PASSWORD = "lan_password"
CONF_LAN_TOKEN = "lan_token"

# --- Real-time events via TechPoint WebHook (LAN only) ---
CONF_EVENTS_DOOR = "events_door"
CONF_EVENTS_ALARM = "events_alarm"
CONF_EVENTS_TAMPER = "events_tamper"
CONF_EVENTS_ERROR = "events_error"

# Realtime event log (keeps last N events in a sensor attribute)
CONF_EVENT_LOG_MAX = "event_log_max"
DEFAULT_EVENT_LOG_MAX = 200
SIGNAL_EVENT_LOG_UPDATED = "techpoint_event_log_updated"

EVENT_BUS_NAME = "techpoint_event"