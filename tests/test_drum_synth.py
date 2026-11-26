# ABOUTME: Tests for the drum sounds generated in code: shape, pitch, tone and audition files.
# ABOUTME: Run with: uv run python -m pytest tests/test_drum_synth.py -q
import os
import subprocess
import sys
import wave

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from music import drum_synth
from music.sample_player import shape_sample

RATE = drum_synth.SAMPLE_RATE
KICKS = ["Punch", "Long", "Hard"]
TOMS = ["Tom Low", "Tom Mid", "Tom Hi"]
SOUNDS = {
    "Kick": KICKS,
    "Snare": ["Tight", "Fat"],
    "Clap": ["Standard", "Wide"],
    "Tom Hi": ["Standard", "Long"],
    "Tom Mid": ["Standard", "Long"],
    "Tom Low": ["Standard", "Long"],
    "Rim": ["Standard", "Metallic"],
}
EVERY_SOUND = [(slot, label) for slot, names in SOUNDS.items() for label in names]


def sound(slot, label):
    return drum_synth.render(slot, SOUNDS[slot].index(label))


def kick(label):
    return sound("Kick", label)


def energy_between(data, low, high):
    return energy_above(data, low) - energy_above(data, high)


def peak_frequency(data, start, end, low=40, high=1000):
    """Strongest frequency in Hz between two times."""
    part = data[int(start * RATE):int(end * RATE), 0]
    size = 1 << 17
    spectrum = np.abs(np.fft.rfft(part * np.hanning(len(part)), size))
    frequencies = np.fft.rfftfreq(size, 1.0 / RATE)
    wanted = (frequencies >= low) & (frequencies <= high)
    return frequencies[wanted][np.argmax(spectrum[wanted])]


def loudness(data, start, end):
    """RMS level between two times."""
    return np.sqrt(np.mean(data[int(start * RATE):int(end * RATE), 0] ** 2))


def pitch(data, start, end):
    """Frequency in Hz between two times, from the spacing of rising zero crossings."""
    mono = data[:, 0]
    # A gentle low-pass keeps the click out of the measurement
    width = RATE // 1000
    mono = np.convolve(mono, np.ones(width) / width, mode="same")
    part = mono[int(start * RATE):int(end * RATE)]
    rising = np.flatnonzero((part[:-1] < 0) & (part[1:] >= 0))
    assert len(rising) >= 2, "not enough cycles to measure"
    return RATE * (len(rising) - 1) / (rising[-1] - rising[0])


def energy_above(data, hertz):
    """Share of the energy above a frequency."""
    power = np.abs(np.fft.rfft(data[:, 0])) ** 2
    frequencies = np.fft.rfftfreq(len(data), 1.0 / RATE)
    return power[frequencies > hertz].sum() / power.sum()


def seconds_until_quiet(data, level=0.05):
    loud = np.flatnonzero(np.abs(data[:, 0]) > level)
    return loud[-1] / RATE


def test_kick_offers_three_alternatives():
    assert drum_synth.labels("Kick") == KICKS


@pytest.mark.parametrize("slot", SOUNDS)
def test_every_row_offers_its_alternatives(slot):
    assert drum_synth.labels(slot) == SOUNDS[slot]


@pytest.mark.parametrize("slot,label", EVERY_SOUND)
def test_sound_is_clean_stereo(slot, label):
    data = sound(slot, label)
    assert data.dtype == np.float32 and data.ndim == 2 and data.shape[1] == 2
    assert np.isfinite(data).all()
    assert np.array_equal(data[:, 0], data[:, 1]) != ((slot, label) == ("Clap", "Wide"))
    assert np.abs(data).max() == pytest.approx(drum_synth.PEAK, abs=1e-4)
    assert np.abs(data[0]).max() < 0.1  # no jump at the start
    assert np.all(data[-1] == 0.0)
    assert np.abs(data[-RATE // 200:]).max() < 0.01  # fades out before the end
    assert abs(data.mean()) < 0.005  # no constant offset


@pytest.mark.parametrize("slot,label", EVERY_SOUND)
def test_sound_is_the_same_every_time(slot, label):
    np.random.seed(1)
    first = sound(slot, label)
    np.random.seed(2)
    assert np.array_equal(first, sound(slot, label))


@pytest.mark.parametrize("label", KICKS)
def test_kick_pitch_drops_to_a_low_note(label):
    data = kick(label)
    early, late = pitch(data, 0.0, 0.04), pitch(data, 0.15, 0.30)
    assert early > late * 1.8
    assert 40 <= late <= 65


@pytest.mark.parametrize("label", KICKS)
def test_kick_energy_is_mostly_low(label):
    assert energy_above(kick(label), 250) < 0.3


def test_long_kick_rings_longest():
    assert seconds_until_quiet(kick("Long")) > 1.8 * seconds_until_quiet(kick("Punch"))


def test_hard_kick_is_brightest():
    hard = energy_above(kick("Hard"), 250)
    assert hard > energy_above(kick("Punch"), 250) > energy_above(kick("Long"), 250)


# ── Snare ────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", SOUNDS["Snare"])
def test_snare_has_a_tuned_body_and_noise(label):
    data = sound("Snare", label)
    assert energy_between(data, 120, 450) > 0.2
    assert energy_above(data, 2000) > 0.15


def test_fat_snare_is_lower_and_longer_than_tight():
    tight, fat = sound("Snare", "Tight"), sound("Snare", "Fat")
    assert peak_frequency(fat, 0.02, 0.08, 120, 450) < peak_frequency(tight, 0.02, 0.08, 120, 450)
    assert seconds_until_quiet(fat) > 1.3 * seconds_until_quiet(tight)


# ── Toms ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", ["Standard", "Long"])
def test_toms_are_pitched_low_to_high(label):
    low, mid, high = (peak_frequency(sound(slot, label), 0.05, 0.15) for slot in TOMS)
    assert 70 < low < mid < high < 220
    assert mid > low * 1.2 and high > mid * 1.2


@pytest.mark.parametrize("slot", TOMS)
def test_tom_pitch_drops_and_energy_is_low(slot):
    data = sound(slot, "Standard")
    assert peak_frequency(data, 0.0, 0.03) > 1.15 * peak_frequency(data, 0.08, 0.2)
    assert energy_above(data, 1000) < 0.15


@pytest.mark.parametrize("slot", TOMS)
def test_long_tom_rings_longer(slot):
    long, standard = sound(slot, "Long"), sound(slot, "Standard")
    assert seconds_until_quiet(long) > 1.6 * seconds_until_quiet(standard)


# ── Rim ──────────────────────────────────────────────────────────

def test_rim_is_a_short_mid_range_click():
    data = sound("Rim", "Standard")
    assert seconds_until_quiet(data) < 0.04
    assert energy_between(data, 300, 4000) > 0.75


def flatness(data):
    """Near 1 for noise, near 0 for a few clear tones."""
    power = np.abs(np.fft.rfft(data[:int(0.03 * RATE), 0], 4096)) ** 2
    frequencies = np.fft.rfftfreq(4096, 1.0 / RATE)
    power = power[(frequencies > 500) & (frequencies < 8000)] + 1e-20
    return np.exp(np.mean(np.log(power))) / np.mean(power)


def test_metallic_rim_rings_with_clear_high_tones():
    metallic, standard = sound("Rim", "Metallic"), sound("Rim", "Standard")
    assert 0.06 < seconds_until_quiet(metallic) < 0.2
    assert energy_above(metallic, 700) > 0.85
    assert flatness(metallic) < 0.1
    assert energy_above(metallic, 1200) > 1.2 * energy_above(standard, 1200)
    assert seconds_until_quiet(metallic) > 2 * seconds_until_quiet(standard)


# ── Clap ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("label", SOUNDS["Clap"])
def test_clap_starts_with_separate_bursts(label):
    data = sound("Clap", label)
    for n in range(3):
        burst = n * 0.011
        assert loudness(data, burst, burst + 0.003) > 2.5 * loudness(data, burst + 0.008, burst + 0.0108)
    assert loudness(data, 0.05, 0.08) > 0.02  # followed by a tail


@pytest.mark.parametrize("label", SOUNDS["Clap"])
def test_clap_sits_in_the_mid_range(label):
    assert energy_between(sound("Clap", label), 600, 4000) > 0.7


def test_wide_clap_differs_between_the_sides():
    data = sound("Clap", "Wide")
    assert abs(np.corrcoef(data[:, 0], data[:, 1])[0, 1]) < 0.5


def test_index_wraps_around():
    assert np.array_equal(drum_synth.render("Kick", 3), kick("Punch"))
    assert np.array_equal(drum_synth.render("Kick", -1), kick("Hard"))


def test_generated_sound_can_be_shaped():
    data = kick("Punch")
    shaped = shape_sample(data, RATE, 44100, {"tune": -2.0, "decay": 0.5, "drive": 0.3})
    assert np.isfinite(shaped).all() and len(shaped) > 0


def test_command_writes_audition_files(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "music.drum_synth", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0 and result.stderr == ""
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == sorted(
        f"audition_{slot}_{label}.wav".lower().replace(" ", "_") for slot, label in EVERY_SOUND
    )
    with wave.open(str(tmp_path / "audition_kick_punch.wav"), "rb") as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (2, 2, RATE)
        frames = np.frombuffer(f.readframes(f.getnframes()), "<i2").reshape(-1, 2)
    # Four beats at 120 BPM, each one audible
    beat = RATE // 2
    assert len(frames) >= 4 * beat
    for n in range(4):
        assert np.abs(frames[n * beat:n * beat + beat // 4]).max() > 10000
