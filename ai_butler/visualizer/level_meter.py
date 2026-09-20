"""Pure audio-level/spectrum analysis for the desktop visualizer widget.

No I/O here: takes raw PCM16 mono bytes (the same format used throughout
ai_butler -- see config.REALTIME_SAMPLE_RATE) and returns plain numbers, so
this logic is fully unit-testable without any audio hardware, GUI, or
network dependency. Scaling constants below are chosen to look reasonable
for speech-level audio, not calibrated to any absolute loudness standard.
"""

from __future__ import annotations

from typing import List

import numpy as np


def _to_float_samples(pcm_bytes: bytes) -> np.ndarray:
    if not pcm_bytes:
        return np.zeros(0, dtype=np.float32)
    samples = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32)
    return samples / 32768.0


def rms_level(pcm_bytes: bytes) -> float:
    """Root-mean-square amplitude of a PCM16 chunk, roughly normalized to 0..1."""
    samples = _to_float_samples(pcm_bytes)
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples))))
    # Empirical headroom: conversational speech rarely drives RMS near 1.0.
    return min(rms * 4.0, 1.0)


def spectrum_bands(
    pcm_bytes: bytes,
    num_bands: int = 12,
    sample_rate: int = 24000,
    *,
    silence_threshold: float = 0.01,
) -> List[float]:
    """Log-spaced frequency-band magnitudes for a PCM16 chunk, each in 0..1.

    Returns all zeros for silence/near-silence or a chunk too short to FFT.
    """
    samples = _to_float_samples(pcm_bytes)
    if samples.size < 2:
        return [0.0] * num_bands

    rms = float(np.sqrt(np.mean(np.square(samples))))
    if rms < silence_threshold:
        return [0.0] * num_bands

    windowed = samples * np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)

    # Log-spaced band edges between 80Hz and just under Nyquist, roughly
    # matching how voiced speech energy spreads out perceptually.
    lo, hi = 80.0, sample_rate / 2 * 0.98
    edges = np.geomspace(lo, hi, num_bands + 1)

    # max (not mean) per band: at this FFT resolution (sample_rate/N Hz per
    # bin) a band can span well over a hundred bins, and a narrow-band
    # signal's energy sits in only one or two of them -- averaging across
    # the whole band would dilute it near to zero. max keeps a band
    # reading its loudest component, which is the usual convention for a
    # bar-style spectrum visualizer.
    bands: List[float] = []
    for i in range(num_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        magnitude = float(spectrum[mask].max()) if mask.any() else 0.0
        bands.append(magnitude)

    # Fixed (not per-chunk-peak) reference scale, so quiet backgrounds don't
    # get stretched to look as loud as real speech; intentionally approximate.
    reference = samples.size * 0.15
    return [min((b / reference) ** 0.6, 1.0) for b in bands]
