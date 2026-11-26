# ABOUTME: Tests for drum output levels: how loud the kit is and how the drums sit against the kick.
# ABOUTME: Run with: uv run python -m pytest tests/test_drum_levels.py -q
import numpy as np
import pytest
from scipy.signal import lfilter

from music import drum_synth
from modes.tambor.music.drum_voice_manager import DrumVoiceManager
from tests.test_voice_regression import make_engine, run_buffers, BUFFER_SIZE, SAMPLE_RATE

ROWS = ["Kick", "Snare", "Closed HH", "Open HH", "Clap",
        "Tom Hi", "Tom Mid", "Tom Low", "Ride", "Rim"]
SOUNDS = [(slot, label) for slot in ROWS for label in drum_synth.labels(slot)]

# Loudness in dB relative to the average kick
TARGETS = {"Kick": 0.0, "Snare": -2.5, "Closed HH": -11.0, "Open HH": -9.0, "Clap": -3.0,
           "Tom Hi": -2.5, "Tom Mid": -2.5, "Tom Low": -2.5, "Rim": -6.0, "Ride": -9.0}
# Short, spiky sounds that cannot reach their target without peaking far above the kick
PEAK_LIMITED = [("Clap", "Standard"), ("Clap", "Wide"), ("Rim", "Standard")]
PEAK_LIMIT_DB = 2.0  # how far above the kick their peaks may go


def db(value):
    return 20 * np.log10(value)


def play(slot, label, velocity=100, master=1.0, controls=None):
    """Output of the engine for one hit."""
    engine = make_engine()
    engine.update_parameters(master_volume=master)
    run_buffers(engine, 200)
    index = drum_synth.labels(slot).index(label)
    note, params = DrumVoiceManager(engine).hit_params(
        ROWS.index(slot), {"sample": {"index": index, "controls": controls or {}}})
    engine.drum_trigger(note, velocity, params)
    return run_buffers(engine, SAMPLE_RATE // BUFFER_SIZE)


def peak_db(audio):
    return db(np.abs(audio).max())


def loudness(audio):
    """Perceived loudness of a hit: BS.1770 weighting, loudest tenth of a second."""
    out = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285],
                  [1.0, -1.69065929318241, 0.73248077421585], audio, axis=0)
    out = lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], out, axis=0)
    window = SAMPLE_RATE // 10
    power = np.convolve(out.mean(axis=1) ** 2, np.ones(window) / window, mode="valid")
    return 10 * np.log10(power.max())


def kick_loudness():
    return np.mean([loudness(play("Kick", label)) for label in drum_synth.labels("Kick")])


@pytest.mark.parametrize("label", drum_synth.labels("Kick"))
def test_a_single_kick_peaks_at_minus_six(generated_kit, label):
    assert peak_db(play("Kick", label)) == pytest.approx(-6.0, abs=0.5)


def test_master_volume_still_scales_the_drums(generated_kit):
    full, half = play("Kick", "Punch"), play("Kick", "Punch", master=0.5)
    assert peak_db(full) - peak_db(half) == pytest.approx(6.0, abs=0.2)


@pytest.mark.parametrize("slot,label", [s for s in SOUNDS if s not in PEAK_LIMITED])
def test_each_drum_sits_at_its_level_under_the_kick(generated_kit, slot, label):
    relative = loudness(play(slot, label)) - kick_loudness()
    expected = TARGETS[slot]
    assert relative == pytest.approx(expected, abs=1.0)


@pytest.mark.parametrize("slot,label", PEAK_LIMITED)
def test_spiky_drums_are_raised_as_far_as_their_peaks_allow(generated_kit, slot, label):
    above = peak_db(play(slot, label)) - peak_db(play("Kick", "Punch"))
    assert above == pytest.approx(PEAK_LIMIT_DB, abs=0.2)


@pytest.mark.parametrize("slot,label", SOUNDS)
def test_no_single_hit_reaches_full_scale(generated_kit, slot, label):
    assert peak_db(play(slot, label, velocity=127)) < -0.5


def test_drive_does_not_undo_a_drums_level(generated_kit):
    plain = play("Closed HH", "Dark")
    driven = play("Closed HH", "Dark", controls={"drive": 1.0})
    assert abs(peak_db(driven) - peak_db(plain)) < 1.0
