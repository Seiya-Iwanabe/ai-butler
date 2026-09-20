import math
import struct

from ai_butler.visualizer import level_meter

SAMPLE_RATE = 24000


def _pcm16(samples):
    samples = list(samples)
    return struct.pack(f"<{len(samples)}h", *(int(max(-32768, min(32767, s))) for s in samples))


def _silence(num_samples: int) -> bytes:
    return _pcm16([0] * num_samples)


def _sine_wave(freq_hz: float, num_samples: int, amplitude: float = 0.8) -> bytes:
    return _pcm16(
        32767 * amplitude * math.sin(2 * math.pi * freq_hz * i / SAMPLE_RATE)
        for i in range(num_samples)
    )


def test_rms_level_silence_is_zero():
    assert level_meter.rms_level(_silence(2400)) == 0.0


def test_rms_level_empty_bytes_is_zero():
    assert level_meter.rms_level(b"") == 0.0


def test_rms_level_loud_tone_is_near_max():
    loud = _sine_wave(1000, 2400, amplitude=0.95)
    assert level_meter.rms_level(loud) > 0.9


def test_rms_level_quiet_tone_is_lower_than_loud_tone():
    quiet = _sine_wave(1000, 2400, amplitude=0.05)
    loud = _sine_wave(1000, 2400, amplitude=0.95)
    assert level_meter.rms_level(quiet) < level_meter.rms_level(loud)


def test_spectrum_bands_silence_is_all_zero():
    bands = level_meter.spectrum_bands(_silence(2400), num_bands=12)
    assert bands == [0.0] * 12


def test_spectrum_bands_short_input_is_all_zero():
    bands = level_meter.spectrum_bands(_pcm16([100]), num_bands=8)
    assert bands == [0.0] * 8


def test_spectrum_bands_peaks_near_the_tone_frequency():
    # A clean 3kHz tone should show up as a clear peak in the band that
    # actually contains 3kHz, not in a band far away from it (near-DC or
    # near-Nyquist), given the log-spaced 80Hz..~11.76kHz band edges.
    tone = _sine_wave(3000, 4800, amplitude=0.9)
    bands = level_meter.spectrum_bands(tone, num_bands=12, sample_rate=SAMPLE_RATE)

    edges = [80.0 * (SAMPLE_RATE / 2 * 0.98 / 80.0) ** (i / 12) for i in range(13)]
    target_band = next(i for i in range(12) if edges[i] <= 3000 < edges[i + 1])

    assert bands[target_band] > 0.3
    far_band = 0 if target_band > 1 else 11
    assert bands[target_band] > bands[far_band]


def test_spectrum_bands_respects_num_bands():
    tone = _sine_wave(500, 2400)
    assert len(level_meter.spectrum_bands(tone, num_bands=6)) == 6
    assert len(level_meter.spectrum_bands(tone, num_bands=20)) == 20


def test_spectrum_bands_values_stay_in_unit_range():
    tone = _sine_wave(440, 2400, amplitude=1.0)
    for b in level_meter.spectrum_bands(tone, num_bands=12):
        assert 0.0 <= b <= 1.0
