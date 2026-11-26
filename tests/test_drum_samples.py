# ABOUTME: Tests for the sampled drum kit: WAV conversion, sound shaping and playback.
# ABOUTME: Run with: uv run python -m pytest tests/test_drum_samples.py -q
import os
import subprocess
import sys
import wave

import numpy as np
import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from music.drum_kit import DrumKit, SLOT_SAMPLES, build_kit
from music.sample_player import SamplePlayer, shape_sample

RATE = 48000
SOURCE_RATE = 44100


def write_wav(path, samples, rate=SOURCE_RATE):
    """Write a 16-bit WAV from a (frames,) or (frames, channels) float array."""
    data = np.atleast_2d(samples.T).T
    with wave.open(str(path), "wb") as f:
        f.setnchannels(data.shape[1])
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((data * 32767).astype("<i2").tobytes())


def tone(freq, seconds, rate=SOURCE_RATE, level=0.8):
    t = np.arange(int(seconds * rate)) / rate
    return level * np.sin(2 * np.pi * freq * t) * np.exp(-t * 4)


def source_files():
    return sorted({name for entries in SLOT_SAMPLES.values() for _, name in entries})


@pytest.fixture
def source_dir(tmp_path):
    folder = tmp_path / "wavs"
    folder.mkdir()
    for i, name in enumerate(source_files()):
        mono = tone(100 + 50 * i, 0.3)
        write_wav(folder / name, np.column_stack((mono, mono * 0.5)) if i % 2 else mono)
    return folder


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

def test_every_drum_row_has_alternatives_mapped():
    assert all(SLOT_SAMPLES.values())
    assert len(source_files()) == 16


def test_build_and_load_round_trip(source_dir, tmp_path):
    target = tmp_path / "kit" / "909.npz"
    build_kit(source_dir, target)
    kit = DrumKit.load(target)
    assert kit.sample_rate == RATE
    for slot, entries in SLOT_SAMPLES.items():
        assert kit.labels(slot) == [label for label, _ in entries]
        for index in range(len(entries)):
            data = kit.sample(slot, index)
            assert data.dtype == np.float32 and data.ndim == 2 and data.shape[1] == 2
            assert abs(len(data) - int(0.3 * RATE)) <= 2
            assert np.abs(data[-1]).max() < 0.001  # ends without a step


def test_conversion_keeps_pitch_and_stereo(source_dir, tmp_path):
    build_kit(source_dir, tmp_path / "909.npz")
    kit = DrumKit.load(tmp_path / "909.npz")
    name = SLOT_SAMPLES["Kick"][0][1]
    index = source_files().index(name)
    data = kit.sample("Kick", 0)
    assert abs(dominant_frequency(data) - (100 + 50 * index)) < 5
    expected_ratio = 0.5 if index % 2 else 1.0
    assert np.abs(data[:, 1]).max() / np.abs(data[:, 0]).max() == pytest.approx(expected_ratio, rel=0.01)


def test_alternative_index_wraps_around(source_dir, tmp_path):
    build_kit(source_dir, tmp_path / "909.npz")
    kit = DrumKit.load(tmp_path / "909.npz")
    count = len(kit.labels("Kick"))
    assert np.array_equal(kit.sample("Kick", count), kit.sample("Kick", 0))


def test_missing_source_file_is_reported(source_dir, tmp_path):
    os.remove(source_dir / source_files()[0])
    with pytest.raises(FileNotFoundError, match=source_files()[0].split(".")[0]):
        build_kit(source_dir, tmp_path / "909.npz")


def test_loading_without_a_kit_returns_none(tmp_path):
    assert DrumKit.load(tmp_path / "absent.npz") is None


def test_command_line_builds_the_kit(source_dir, tmp_path):
    target = tmp_path / "out.npz"
    result = subprocess.run(
        [sys.executable, "-m", "music.drum_kit", str(source_dir), str(target)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert DrumKit.load(target) is not None


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
