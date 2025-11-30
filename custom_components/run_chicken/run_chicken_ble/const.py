"""Constants for run_chicken."""

from logging import Logger, getLogger

from run_chicken.run_chicken_ble.models import RunChickenDevice

LOGGER: Logger = getLogger(__package__)

DOMAIN = "run_chicken"

READ_SERVICE_UUID = "0000004f-cc7a-482a-984a-7f2ed5b3e58f"
READ_CHAR_UUID = "00000001-8e22-4541-9d4c-21edae82ed19"

WRITE_SERVICE_UUID = "00000000-cc7a-482a-984a-7f2ed5b3e58f"
WRITE_CHAR_UUID = "00000000-8e22-4541-9d4c-21edae82ed19"
