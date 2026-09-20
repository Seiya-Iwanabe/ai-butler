"""Microphone capture and speaker playback, 16-bit mono PCM at 24kHz.

Requires PortAudio via the `sounddevice` package. This module is not covered
by unit tests in this repo because it needs real audio hardware; see
docs/DESIGN.md for what was (and wasn't) verified.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Callable, Optional

import sounddevice as sd

from .config import REALTIME_SAMPLE_RATE
from .visualizer.controller import NullVisualizerController, VisualizerControllerBase

logger = logging.getLogger(__name__)

CHANNELS = 1
DTYPE = "int16"
BLOCK_SIZE = 2400  # 100ms of audio at 24kHz


class MicStream:
    """Captures mic audio and exposes it as an async generator of PCM16 chunks.

    Frames are only queued while `should_capture()` returns True at the
    moment they arrive, so callers can mute the mic (e.g. while デヴィ is
    speaking) without tearing down and restarting the underlying stream.
    """

    def __init__(
        self,
        *,
        device: Optional[str],
        should_capture: Callable[[], bool],
        visualizer: Optional[VisualizerControllerBase] = None,
    ) -> None:
        self._device = device
        self._should_capture = should_capture
        self._visualizer = visualizer if visualizer is not None else NullVisualizerController()
        self._queue: "asyncio.Queue[bytes]" = asyncio.Queue(maxsize=50)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stream: Optional[sd.RawInputStream] = None

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("mic stream status: %s", status)
        if not self._should_capture():
            return
        loop = self._loop
        if loop is None:
            return
        data = bytes(indata)
        self._visualizer.report_mic_level(data)
        try:
            loop.call_soon_threadsafe(self._put_nowait_safe, data)
        except RuntimeError:
            pass  # loop already closed during shutdown

    def _put_nowait_safe(self, data: bytes) -> None:
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            logger.debug("mic queue is full; dropping a frame")

    async def __aenter__(self) -> "MicStream":
        self._loop = asyncio.get_running_loop()
        self._stream = sd.RawInputStream(
            samplerate=REALTIME_SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=BLOCK_SIZE,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    async def frames(self) -> AsyncIterator[bytes]:
        while True:
            yield await self._queue.get()


class SpeakerPlayer:
    """Blocking PCM16 playback; wrap `write()` in `asyncio.to_thread` from async code."""

    def __init__(self, *, device: Optional[str]) -> None:
        self._device = device
        self._stream: Optional[sd.RawOutputStream] = None

    def __enter__(self) -> "SpeakerPlayer":
        self._stream = sd.RawOutputStream(
            samplerate=REALTIME_SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            device=self._device,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc_info) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def write(self, pcm_bytes: bytes) -> None:
        if self._stream is not None:
            self._stream.write(pcm_bytes)
