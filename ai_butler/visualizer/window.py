"""Floating, always-on-top, transparent desktop visualizer window.

Built with pywebview + a plain HTML/Canvas page (orb.html) rather than
drawing directly with PyObjC/Quartz -- specifically so the visual itself
could be rendered and screenshotted with a headless browser during
development (see docs/DESIGN.md). This module could only be syntax- and
import-checked in the sandbox this was written in (no macOS available);
the actual floating-window behavior on a real Mac is unverified -- see
README.md.

Threading contract: `webview.start()` blocks and must run on the process's
main thread on macOS (a Cocoa requirement). The window itself is created
in `__init__` (safe to call from the main thread before `start()`), so
callers can register `on_closed` before the blocking `run()` call -- see
app.py, which runs the rest of ai_butler's asyncio pipeline on a
background thread while this blocks the main thread.
`push_state`/`push_spectrum` internally call pywebview's `evaluate_js`,
which pywebview documents as safe to call from any thread.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, List, Tuple

import webview

logger = logging.getLogger(__name__)

ORB_HTML = Path(__file__).parent / "orb.html"

DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 720
DEFAULT_MARGIN = 24


class VisualizerWindow:
    def __init__(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        corner: str = "center",
        margin: int = DEFAULT_MARGIN,
    ) -> None:
        self._width = width
        self._height = height
        self._corner = corner
        self._margin = margin
        self._started = False
        self._window = webview.create_window(
            "デヴィ",
            url=ORB_HTML.as_uri(),
            width=width,
            height=height,
            frameless=True,
            easy_drag=True,
            on_top=True,
            transparent=True,
            # Shown only for the instant before orb.html loads; actual
            # transparency comes from `transparent=True` above (pywebview
            # validates this as a plain #RRGGBB hex triplet, no alpha).
            background_color="#000000",
        )

    def _initial_geometry(self) -> Tuple[int, int]:
        try:
            screens = webview.screens
            screen = screens[0] if screens else None
            if screen is None:
                return (self._margin, self._margin)
            sw, sh = screen.width, screen.height
        except Exception:
            logger.debug(
                "could not read screen size; leaving window at its default position",
                exc_info=True,
            )
            return (self._margin, self._margin)

        if self._corner == "center":
            return ((sw - self._width) // 2, (sh - self._height) // 2)

        x, y = self._margin, self._margin
        if "right" in self._corner:
            x = sw - self._width - self._margin
        if "bottom" in self._corner:
            y = sh - self._height - self._margin
        return (x, y)

    def _place_window(self) -> None:
        x, y = self._initial_geometry()
        try:
            self._window.move(x, y)
        except Exception:
            logger.debug("window.move failed", exc_info=True)

    def run(self) -> None:
        """Blocking. Call from the process's main thread only."""
        # Confirmed in testing: if webview.start() never gets a GUI backend
        # going (e.g. raises because no GTK/Qt is available at all), a
        # later window.destroy() call hangs forever waiting on a backend
        # loop that never started. Track whether start() actually got
        # underway so close() below knows not to attempt it in that case.
        self._started = True
        try:
            webview.start(self._place_window, debug=False)
        except Exception:
            self._started = False
            raise

    def push_state(self, state: str) -> None:
        self._eval(f"window.setVisualizerState({json.dumps(state)})")

    def push_spectrum(self, bands: List[float]) -> None:
        self._eval(f"window.setVisualizerSpectrum({json.dumps(bands)})")

    def on_closed(self, callback: Callable[[], None]) -> None:
        self._window.events.closed += callback

    def close(self) -> None:
        if not self._started:
            return
        self._window.destroy()

    def _eval(self, js: str) -> None:
        try:
            self._window.evaluate_js(js)
        except Exception:
            logger.debug("evaluate_js failed", exc_info=True)
