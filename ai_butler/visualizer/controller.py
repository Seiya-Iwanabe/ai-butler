"""Bridges audio callbacks (on arbitrary threads) to the GUI window.

Audio-thread-sensitive work (`report_mic_level`/`report_output_level`) only
computes numbers and stores them under a lock; a dedicated pump thread is
the only thing that actually calls into the GUI (`window.evaluate_js`), at
a fixed ~30fps. That way a slow or blocked GUI/IPC call can never add
latency to the realtime audio path.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional, Protocol

from . import level_meter

logger = logging.getLogger(__name__)

PUMP_INTERVAL_SEC = 1 / 30
LISTENING_IDLE_TIMEOUT_SEC = 0.35
NUM_BANDS = 12

# How much each new spectrum reading counts vs. the previous smoothed
# value (0..1; higher = more reactive, lower = smoother/laggier). This is
# a first smoothing pass over raw per-chunk FFT noise; orb.html applies a
# second, separate attack/release smoothing on top for the actual
# frame-to-frame animation.
BAND_SMOOTHING = 0.5


def _blend(old: List[float], new: List[float], factor: float) -> List[float]:
    return [o + (n - o) * factor for o, n in zip(old, new)]


class VisualizerControllerBase(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def report_mic_level(self, pcm_bytes: bytes) -> None: ...
    def report_output_level(self, pcm_bytes: bytes) -> None: ...
    def mark_output_done(self) -> None: ...
    def run_blocking(self) -> None: ...
    def on_closed(self, callback) -> None: ...
    def close_window_if_open(self) -> None: ...

    @property
    def is_active(self) -> bool: ...


class NullVisualizerController:
    """No-op stand-in used when the visualizer is disabled or unavailable."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def report_mic_level(self, pcm_bytes: bytes) -> None:
        return None

    def report_output_level(self, pcm_bytes: bytes) -> None:
        return None

    def mark_output_done(self) -> None:
        return None

    def run_blocking(self) -> None:
        return None

    def on_closed(self, callback) -> None:
        return None

    def close_window_if_open(self) -> None:
        return None

    @property
    def is_active(self) -> bool:
        return False


class VisualizerController:
    def __init__(self, window) -> None:
        self._window = window
        self._lock = threading.Lock()
        self._mode = "idle"
        self._bands: List[float] = [0.0] * NUM_BANDS
        self._last_mic_activity = 0.0
        self._pushed_mode: Optional[str] = None
        self._stop = threading.Event()
        self._pump_thread: Optional[threading.Thread] = None

    @property
    def is_active(self) -> bool:
        return True

    def start(self) -> None:
        self._stop.clear()
        self._pump_thread = threading.Thread(
            target=self._pump_loop, name="ai-butler-visualizer-pump", daemon=True
        )
        self._pump_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._pump_thread is not None:
            self._pump_thread.join(timeout=1.0)

    def report_mic_level(self, pcm_bytes: bytes) -> None:
        bands = level_meter.spectrum_bands(pcm_bytes, num_bands=NUM_BANDS)
        now = time.monotonic()
        with self._lock:
            self._last_mic_activity = now
            if self._mode != "speaking":
                self._mode = "listening"
                self._bands = _blend(self._bands, bands, BAND_SMOOTHING)

    def report_output_level(self, pcm_bytes: bytes) -> None:
        bands = level_meter.spectrum_bands(pcm_bytes, num_bands=NUM_BANDS)
        with self._lock:
            self._mode = "speaking"
            self._bands = _blend(self._bands, bands, BAND_SMOOTHING)

    def mark_output_done(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._mode != "speaking":
                return
            if now - self._last_mic_activity <= LISTENING_IDLE_TIMEOUT_SEC:
                self._mode = "listening"
            else:
                self._mode = "idle"
            self._bands = [0.0] * NUM_BANDS

    def run_blocking(self) -> None:
        self._window.run()

    def on_closed(self, callback) -> None:
        self._window.on_closed(callback)

    def close_window_if_open(self) -> None:
        try:
            self._window.close()
        except Exception:
            logger.debug("visualizer window close failed", exc_info=True)

    def _pump_loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            with self._lock:
                if (
                    self._mode == "listening"
                    and now - self._last_mic_activity > LISTENING_IDLE_TIMEOUT_SEC
                ):
                    self._mode = "idle"
                mode = self._mode
                bands = list(self._bands)

            if mode != self._pushed_mode:
                self._window.push_state(mode)
                self._pushed_mode = mode
            if mode != "idle":
                self._window.push_spectrum(bands)

            time.sleep(PUMP_INTERVAL_SEC)
