# ABOUTME: Tests for the drum kit and for sample shaping and playback.
# ABOUTME: Run with: uv run python -m pytest tests/test_drum_samples.py -q
import os
import sys

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from music import drum_synth
from music.drum_kit import DrumKit
from music.sample_player import SamplePlayer, shape_sample

RATE = 48000


def tone(freq, seconds, rate=RATE, level=0.8):
    t = np.arange(int(seconds * rate)) / rate
    return level * np.sin(2 * np.pi * freq * t) * np.exp(-t * 4)


def noise(seconds=0.5, channels=2):
    rng = np.random.default_rng(1)
    data = rng.uniform(-0.5, 0.5, (int(seconds * RATE), channels)).astype(np.float32)
    return data


def dominant_frequency(audio):
    spectrum = np.abs(np.fft.rfft(audio[:, 0]))
    return np.fft.rfftfreq(len(audio), 1 / RATE)[np.argmax(spectrum)]


def brightness(audio):
    spectrum = np.abs(np.fft.rfft(audio[:, 0]))
    freqs = np.fft.rfftfreq(len(audio), 1 / RATE)
    return spectrum[freqs > 6000].sum() / spectrum.sum()


# ── Kit ──────────────────────────────────────────────────────────

ROWS = ["Kick", "Snare", "Closed HH", "Open HH", "Clap",
        "Tom Hi", "Tom Mid", "Tom Low", "Ride", "Rim"]


@pytest.fixture
def renders(monkeypatch):
    """Record which sounds are generated."""
    made = []
    render = drum_synth.render

    def recording(slot, index=0):
        made.append((slot, index))
        return render(slot, index)

    monkeypatch.setattr(drum_synth, "render", recording)
    return made


def test_loading_the_kit_needs_no_files(generated_kit, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    kit = DrumKit.load()
    assert kit.sample_rate == RATE
    for slot in ROWS:
        assert kit.labels(slot) == drum_synth.labels(slot)
        for index in range(len(kit.labels(slot))):
            assert np.array_equal(kit.sample(slot, index), drum_synth.render(slot, index))


def test_sounds_are_generated_when_first_needed_and_kept(generated_kit, renders):
    kit = DrumKit.load()
    kit.labels("Kick")
    assert renders == []
    first = kit.sample("Kick", 1)
    assert kit.sample("Kick", 1) is first
    assert renders == [("Kick", 1)]


def test_preparing_the_kit_generates_every_sound_once(generated_kit, renders):
    kit = DrumKit.load()
    kit.prepare()
    total = sum(len(kit.labels(slot)) for slot in ROWS)
    assert len(renders) == len(set(renders)) == total
    for slot in ROWS:
        for index in range(len(kit.labels(slot))):
            kit.sample(slot, index)
    assert len(renders) == total


def test_alternative_index_wraps_around(generated_kit):
    kit = DrumKit.load()
    count = len(kit.labels("Kick"))
    assert kit.sample("Kick", count) is kit.sample("Kick", 0)


# ── Shaping ──────────────────────────────────────────────────────

def test_default_controls_leave_the_sample_untouched():
    data = noise()
    assert np.array_equal(shape_sample(data, RATE, RATE, {}), data)


def test_shaping_does_not_modify_the_source():
    data = noise()
    original = data.copy()
    shape_sample(data, RATE, RATE, {"level": 0.5, "attack": 0.01, "decay": 0.5, "drive": 1.0})
    assert np.array_equal(data, original)


@pytest.mark.parametrize("semitones, factor", [(12, 2.0), (-12, 0.5), (0, 1.0)])
def test_tune_changes_pitch_and_length(semitones, factor):
    data = np.column_stack([tone(200, 0.5, RATE)] * 2).astype(np.float32)
    out = shape_sample(data, RATE, RATE, {"tune": semitones})
    assert abs(dominant_frequency(out) - 200 * factor) < 5
    assert len(out) == pytest.approx(len(data) / factor, abs=2)


def test_output_rate_keeps_pitch_and_duration():
    data = np.column_stack([tone(200, 0.5, RATE)] * 2).astype(np.float32)
    out = shape_sample(data, RATE, 44100, {})
    assert len(out) == pytest.approx(0.5 * 44100, abs=2)


def test_attack_fades_the_front_in():
    out = shape_sample(noise(), RATE, RATE, {"attack": 0.02})
    assert np.abs(out[:48]).max() < 0.05
    assert np.array_equal(out[2000:], noise()[2000:])


def test_decay_shortens_the_tail_and_ends_silently():
    data = noise()
    out = shape_sample(data, RATE, RATE, {"decay": 0.3})
    assert len(out) < 0.6 * len(data)
    assert np.array_equal(out[:400], data[:400])
    assert np.abs(out[-48:]).max() < 0.002


def test_tone_darkens_and_brightens():
    data = noise()
    plain = brightness(data)
    assert brightness(shape_sample(data, RATE, RATE, {"tone": -1.0})) < plain * 0.4
    assert brightness(shape_sample(data, RATE, RATE, {"tone": 1.0})) > plain * 1.05


def test_drive_adds_density_without_raising_the_peak():
    data = np.column_stack([tone(100, 0.5, RATE, level=0.9)] * 2).astype(np.float32)
    out = shape_sample(data, RATE, RATE, {"drive": 1.0})
    assert np.abs(out).max() <= 1.0
    assert np.sqrt(np.mean(out ** 2)) > np.sqrt(np.mean(data ** 2)) * 1.3


def test_level_scales_the_sound():
    data = noise()
    assert np.allclose(shape_sample(data, RATE, RATE, {"level": 0.5}), data * 0.5)


# ── Playback ─────────────────────────────────────────────────────

def play(player, frames, block=480):
    out = np.zeros((frames, 2), dtype=np.float32)
    for start in range(0, frames, block):
        player.mix(out[start:start + block, 0], out[start:start + block, 1])
    return out


def constant(frames, value=0.5):
    return np.full((frames, 2), value, dtype=np.float32)


def test_hit_plays_across_buffers_from_its_offset():
    player = SamplePlayer(RATE)
    data = noise(0.05)
    player.trigger(data, gain=1.0, offset=700)
    out = play(player, 4800)
    assert np.all(out[:700] == 0)
    assert np.array_equal(out[700:700 + len(data)], data)
    assert np.all(out[700 + len(data):] == 0)
    assert not player.active


def test_mix_adds_to_what_is_already_there():
    player = SamplePlayer(RATE)
    player.trigger(constant(100, 0.25), gain=1.0)
    left = np.full(200, 0.1, dtype=np.float32)
    right = left.copy()
    player.mix(left, right)
    assert left[0] == pytest.approx(0.35) and left[150] == pytest.approx(0.1)


def test_choke_group_fades_the_ringing_sound_without_a_step():
    player = SamplePlayer(RATE)
    player.trigger(constant(48000), gain=1.0, group="hat")
    player.trigger(constant(100, 0.0), gain=1.0, offset=1000, group="hat")
    out = play(player, 4800)[:, 0]
    assert np.all(out[:1000] == 0.5)
    assert np.abs(np.diff(out[900:1500])).max() < 0.01
    assert np.all(out[1000 + int(0.006 * RATE):] == 0)


def test_different_groups_ring_together():
    player = SamplePlayer(RATE)
    player.trigger(constant(48000, 0.2), gain=1.0, group="kick")
    player.trigger(constant(48000, 0.2), gain=1.0, group="snare")
    assert np.allclose(play(player, 4800), 0.4)


def test_stop_all_silences_playback():
    player = SamplePlayer(RATE)
    player.trigger(constant(48000), gain=1.0)
    play(player, 480)
    player.stop_all()
    out = play(player, 4800)[:, 0]
    assert np.abs(np.diff(out)).max() < 0.01
    assert np.all(out[int(0.006 * RATE):] == 0)
