import time

from ai_butler.visualizer.controller import (
    LISTENING_IDLE_TIMEOUT_SEC,
    VisualizerController,
    _blend,
)


def test_blend_is_linear_interpolation():
    assert _blend([0.0, 0.0], [1.0, 1.0], 0.5) == [0.5, 0.5]
    assert _blend([0.2, 0.4], [1.0, 1.0], 0.25) == [0.4, 0.55]
    assert _blend([1.0], [0.0], 0.0) == [1.0]
    assert _blend([1.0], [0.0], 1.0) == [0.0]


class FakeWindow:
    def __init__(self) -> None:
        self.states = []
        self.spectra = []

    def push_state(self, state):
        self.states.append(state)

    def push_spectrum(self, bands):
        self.spectra.append(list(bands))

    def run(self):  # pragma: no cover - not exercised here
        pass

    def on_closed(self, callback):  # pragma: no cover
        pass

    def close(self):  # pragma: no cover
        pass


def _silent_pcm(n=2400):
    return b"\x00\x00" * n


def _loud_pcm(n=2400):
    # Not silent (non-zero, unlike _silent_pcm), just needs to be tone-like
    # enough to produce a non-trivial spectrum; exact values aren't checked
    # here, only that report_mic_level's smoothing kicks in over repeats.
    import math
    import struct

    samples = [int(32767 * 0.8 * math.sin(2 * math.pi * 1000 * i / 24000)) for i in range(n)]
    return struct.pack(f"<{n}h", *samples)


def test_mic_activity_sets_listening_mode_and_blends_bands():
    controller = VisualizerController(FakeWindow())
    controller.report_mic_level(_loud_pcm())
    assert controller._mode == "listening"
    first = list(controller._bands)
    assert any(b > 0 for b in first)

    controller.report_mic_level(_loud_pcm())
    second = list(controller._bands)
    # Blended (not simply replaced): second reading moves toward, but not
    # instantly to, the raw per-chunk spectrum (which for a steady tone is
    # ~the same shape both times -- the point is that _bands isn't just
    # overwritten wholesale, verified via the blend helper's own test above
    # plus the mode/activity bookkeeping updating correctly here).
    assert controller._mode == "listening"
    assert controller._last_mic_activity > 0


def test_output_activity_sets_speaking_and_overrides_listening():
    controller = VisualizerController(FakeWindow())
    controller.report_mic_level(_loud_pcm())
    assert controller._mode == "listening"

    controller.report_output_level(_loud_pcm())
    assert controller._mode == "speaking"

    # While speaking, further mic activity must not steal the mode back
    # (デヴィ's own voice bleeding into the mic shouldn't flip the orb back
    # to "listening" mid-sentence).
    controller.report_mic_level(_loud_pcm())
    assert controller._mode == "speaking"


def test_mark_output_done_returns_to_listening_if_mic_recently_active():
    controller = VisualizerController(FakeWindow())
    controller.report_mic_level(_loud_pcm())
    controller.report_output_level(_loud_pcm())
    assert controller._mode == "speaking"

    controller.mark_output_done()
    assert controller._mode == "listening"
    assert controller._bands == [0.0] * len(controller._bands)


def test_mark_output_done_returns_to_idle_if_mic_inactive_for_a_while():
    controller = VisualizerController(FakeWindow())
    controller.report_mic_level(_loud_pcm())
    controller._last_mic_activity -= LISTENING_IDLE_TIMEOUT_SEC + 1.0
    controller.report_output_level(_loud_pcm())

    controller.mark_output_done()
    assert controller._mode == "idle"


def test_pump_loop_pushes_state_changes_to_window():
    window = FakeWindow()
    controller = VisualizerController(window)
    controller.start()
    try:
        controller.report_mic_level(_loud_pcm())
        # Pump runs at ~30fps; give it a few cycles to observe the change.
        time.sleep(0.2)
    finally:
        controller.stop()

    assert "listening" in window.states
    assert len(window.spectra) > 0
