"""Constants for run_chicken."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "run_chicken"

DEFAULT_SCAN_INTERVAL = 300
EVENT_DEBOUNCE_TIME = 10

# Options-flow key: when set, raw inbound payloads are appended to a debug file.
CONF_RECORD_RAW_BYTES = "record_raw_bytes"

# Options-flow keys for the connection strategy. With a persistent connection
# the door pushes state changes instantly, but staying connected drains its
# batteries much faster (observed: ~3 months instead of 1-2 years). Without it,
# the integration connects briefly every CONF_POLL_INTERVAL minutes and for
# commands, then disconnects again.
CONF_PERSISTENT_CONNECTION = "persistent_connection"
DEFAULT_PERSISTENT_CONNECTION = True
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL_MINUTES = 15
MIN_POLL_INTERVAL_MINUTES = 5
MAX_POLL_INTERVAL_MINUTES = 60

# Options-flow key: without a persistent connection, poll only shortly after
# the door's scheduled opening and closing (plus on HA commands) instead of on
# a fixed interval. Every BLE connection makes the door play its tune and light
# its LED, so fewer connections save battery (and the neighbours' nerves).
CONF_POLL_ON_SCHEDULE = "poll_on_schedule"
DEFAULT_POLL_ON_SCHEDULE = True


READ_SERVICE_UUID = "0000004f-cc7a-482a-984a-7f2ed5b3e58f"
READ_CHAR_UUID = "00000001-8e22-4541-9d4c-21edae82ed19"

WRITE_SERVICE_UUID = "00000000-cc7a-482a-984a-7f2ed5b3e58f"
WRITE_CHAR_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"

MANUFACTURER_ID = 43521
