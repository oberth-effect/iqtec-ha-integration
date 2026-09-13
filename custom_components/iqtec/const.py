"""Constants for the IQtec Smart Home integration."""

from datetime import timedelta

DOMAIN = "iqtec"

CONF_COVER_USE_SHORT_TILT = "cover_use_short_tilt"
CONF_CORRECTION_TIMEOUT = "correction_timeout"

DEFAULT_CORRECTION_TIMEOUT = 24

# How often the rooms, covers and enabled variables are read, in seconds. The
# default suits a house; the options flow lets a user trade latency for load.
DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
# Calendars only change when somebody edits them.
CALENDAR_SCAN_INTERVAL = timedelta(minutes=5)

SERVICE_SET_CALENDAR = "set_calendar"

# Per-calendar display override. data.xml types some calendars TEMPERATURE that
# are really on/off schedules; the OEM guesses from the name, we ask instead.
CONF_DISPLAY_TYPES = "calendar_display_types"

ATTR_CALENDAR_ID = "calendar_id"
ATTR_TEMPERATURES = "temperatures"
ATTR_DAYS = "days"
ATTR_TRANSITIONS = "transitions"
ATTR_AS_MONDAY = "as_monday"

# Writable variables whose switch is enabled and visible out of the box. Every
# other generic variable waits for a user to enable it.
MANUAL_SWITCHES = ["SYSTEM.SET_HEAT"]
