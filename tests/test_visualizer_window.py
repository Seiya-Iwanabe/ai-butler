"""Tests for the pure geometry math in VisualizerWindow._initial_geometry().

`webview.create_window()` itself works fine even without a real GUI backend
(confirmed: it just builds a Window object), so VisualizerWindow can be
instantiated here -- only the actual `webview.start()` GUI loop needs a
real macOS/GTK/Qt backend this sandbox doesn't have. `webview.screens` is
monkeypatched below since normally it lazily triggers backend detection
too (and raises without one), which _initial_geometry already has to
tolerate in production (e.g. before webview.start() has picked a backend).
"""

from types import SimpleNamespace

import pytest
import webview

from ai_butler.visualizer.window import VisualizerWindow

SCREEN_1920x1080 = SimpleNamespace(width=1920, height=1080)


@pytest.fixture
def fake_screen(monkeypatch):
    monkeypatch.setattr(webview, "screens", [SCREEN_1920x1080])


def test_center_placement(fake_screen):
    win = VisualizerWindow(width=720, height=720, corner="center")
    assert win._initial_geometry() == ((1920 - 720) // 2, (1080 - 720) // 2)


@pytest.mark.parametrize(
    "corner,expected",
    [
        ("top-left", (24, 24)),
        ("top-right", (1920 - 720 - 24, 24)),
        ("bottom-left", (24, 1080 - 720 - 24)),
        ("bottom-right", (1920 - 720 - 24, 1080 - 720 - 24)),
    ],
)
def test_corner_placement(fake_screen, corner, expected):
    win = VisualizerWindow(width=720, height=720, corner=corner, margin=24)
    assert win._initial_geometry() == expected


class _RaisingScreens:
    """Stands in for webview.screens when no GUI backend is available.

    In production, `webview.screens` is a lazily-evaluated proxy that
    triggers backend detection on first use and raises WebViewException if
    none is found (confirmed in this sandbox: no GTK/Qt installed). This
    mimics that -- raising as soon as it's interacted with, not on lookup.
    """

    def __bool__(self):
        raise RuntimeError("no GUI backend")

    def __getitem__(self, index):
        raise RuntimeError("no GUI backend")


def test_falls_back_to_margin_when_screens_unavailable(monkeypatch):
    monkeypatch.setattr(webview, "screens", _RaisingScreens())
    win = VisualizerWindow(width=720, height=720, corner="center", margin=10)
    assert win._initial_geometry() == (10, 10)
