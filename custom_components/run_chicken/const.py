"""Constants for run_chicken."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "run_chicken"

DEFAULT_SCAN_INTERVAL = 300
EVENT_DEBOUNCE_TIME = 10

READ_SERVICE_UUID = "0000004f-cc7a-482a-984a-7f2ed5b3e58f"
READ_CHAR_UUID = "00000001-8e22-4541-9d4c-21edae82ed19"

WRITE_SERVICE_UUID = "00000000-cc7a-482a-984a-7f2ed5b3e58f"
WRITE_CHAR_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"

MANUFACTURER_ID = 43521