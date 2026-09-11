"""Constants for the IQtec Smart Home integration."""

from datetime import timedelta

DOMAIN = "iqtec"

CONF_COVER_USE_SHORT_TILT = "cover_use_short_tilt"
CONF_CORRECTION_TIMEOUT = "correction_timeout"

DEFAULT_CORRECTION_TIMEOUT = 24
DEFAULT_SCAN_INTERVAL = timedelta(seconds=15)

# System variables worth exposing even though they are not discovered as devices.
MANUAL_SWITCHES = ["SYSTEM.SET_HEAT"]
