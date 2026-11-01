"""Pure audio builders: arrays are non-empty, finite and mixer-free."""

from __future__ import annotations

import numpy as np

from slg.audio import (
    SAMPLE_RATE,
    make_drone,
    make_glass_drone,
    make_tink,
    make_well_drone,
)


def _check(buf: np.ndarray) -> None:
    assert isinstance(buf, np.ndarray)
    assert buf.size > SAMPLE_RATE // 4
    assert np.all(np.isfinite(buf))
    assert float(np.max(np.abs(buf))) > 0.0


def test_glass_drone_is_a_valid_loop():
    _check(make_glass_drone())


def test_tink_is_a_short_chime():
    buf = make_tink()
    _check(buf)
    assert buf.size <= SAMPLE_RATE


def test_swamp_drone_is_a_valid_loop():
    _check(make_drone())


def test_glass_drone_is_soft_not_harsh():
    """The ambience must stay dark: no sustained high-frequency energy."""
    buf = make_glass_drone()
    mono = buf.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1.0 / SAMPLE_RATE)
    centroid = float((spectrum * freqs).sum() / spectrum.sum())
    high_ratio = float(spectrum[freqs > 3000.0].sum() / spectrum.sum())
    assert centroid < 800.0, centroid
    assert high_ratio < 0.05, high_ratio


def test_well_drone_is_a_valid_loop():
    _check(make_well_drone())


def test_well_drone_is_subterranean():
    """The well ambience is heavier and darker than the glass desert."""
    buf = make_well_drone()
    mono = buf.mean(axis=1)
    spectrum = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1.0 / SAMPLE_RATE)
    centroid = float((spectrum * freqs).sum() / spectrum.sum())
    high_ratio = float(spectrum[freqs > 3000.0].sum() / spectrum.sum())
    assert centroid < 600.0, centroid
    assert high_ratio < 0.05, high_ratio
