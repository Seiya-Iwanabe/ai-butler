"""Global hotkey listener (default: Option+Space) bridged into asyncio.

pynput's listener runs on its own OS thread, so the callback hops back onto
the asyncio loop via `call_soon_threadsafe` rather than touching asyncio
state directly from that thread.

On macOS this requires granting the terminal/app running ai-butler
Accessibility permission (System Settings -> Privacy & Security ->
Accessibility), otherwise pynput cannot observe global key events.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyListener:
    def __init__(self, combo: str, on_trigger: Callable[[], None]) -> None:
        self._combo = combo
        self._on_trigger = on_trigger
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listener: Optional[keyboard.GlobalHotKeys] = None

    def _fire(self) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._on_trigger)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._listener = keyboard.GlobalHotKeys({self._combo: self._fire})
        self._listener.start()
        logger.info("グローバルホットキー %s を監視開始しました", self._combo)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
