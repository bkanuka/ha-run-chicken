"""Optional raw-payload recorder for debugging Run-Chicken doors."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class RawByteRecorder:
    """
    Append every raw message exchanged with the door to a text file for debugging.

    Each line is ``<ISO-8601 UTC timestamp> <RX|TX> <base64 payload>``, where RX
    is a payload received from the door and TX is one sent to it. Writes run on
    the executor (off the event loop) and are serialised through a lock so
    concurrent reads and writes never interleave a line. This is an opt-in
    debugging aid enabled from the integration options; the file is meant to be
    handed to a maintainer when reporting an issue.
    """

    def __init__(self, hass: HomeAssistant, path: str | Path) -> None:
        """Initialise a recorder that appends to ``path``."""
        self._hass = hass
        self._path = Path(path)
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        """Return the file the recorder appends to."""
        return self._path

    def record(self, direction: str, payload: bytes | bytearray) -> None:
        """
        Queue a message to be appended. Safe to call from the event loop.

        ``direction`` is a short marker (``"RX"`` for received, ``"TX"`` for sent)
        written verbatim before the base64 payload.
        """
        encoded = base64.b64encode(payload).decode("ascii")
        line = f"{dt.datetime.now(dt.UTC).isoformat()} {direction} {encoded}\n"
        self._hass.async_create_task(self._async_append(line), "run_chicken_raw_record")

    async def _async_append(self, line: str) -> None:
        """Append a single line, serialised against any other in-flight write."""
        async with self._lock:
            await self._hass.async_add_executor_job(self._append, line)

    def _append(self, line: str) -> None:
        """Blocking append; runs on the executor."""
        try:
            with self._path.open("a", encoding="utf-8") as file:
                file.write(line)
        except OSError:
            _LOGGER.exception("Failed to write raw-byte recording to %s", self._path)
