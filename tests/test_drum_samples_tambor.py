# ABOUTME: Tests for sampled drums inside the engine and the Tambor screen.
# ABOUTME: Run with: uv run python -m pytest tests/test_drum_samples_tambor.py -q
import json

import numpy as np
import pytest

from music import drum_synth
from music.drum_kit import DrumKit
from modes.tambor.tambor_mode import TamborMode
from modes.tambor.music.drum_presets import DRUM_PRESETS
from modes.tambor.music.drum_voice_manager import DrumVoiceManager
from tests.test_tambor_mode import isolated_cwd, run_tambor, write_pattern  # noqa: F401
from tests.test_voice_regression import make_engine, run_buffers, BUFFER_SIZE, SAMPLE_RATE

ROWS = ["Kick", "Snare", "Closed HH", "Open HH", "Clap",
        "Tom Hi", "Tom Mid", "Tom Low", "Ride", "Rim"]
KICK, SNARE, CLOSED_HH, OPEN_HH, RIDE, RIM = 0, 1, 2, 3, 8, 9


def every_sound():
    return [(slot, index) for slot in ROWS for index in range(len(drum_synth.labels(slot)))]


def fake_kit(seconds=0.2):
    """Kit whose samples are constant, with a different level for every sound."""
    return DrumKit({
        key: np.full((int(seconds * SAMPLE_RATE), 2), 0.05 * (i + 1) / 2, dtype=np.float32)
        for i, key in enumerate(every_sound())
    })


def sample_engine(seconds=0.2, **params):
    engine = make_engine(**params)
    engine.drum_kit = fake_kit(seconds)
    return engine


def level_of(slot):
    """Output level expected for a full-velocity hit of a fake sample."""
    return fake_kit().sample(slot)[0, 0] * sample_engine().DRUM_BUS_GAIN


def hit(engine, drum_idx, velocity=127):
    note, params = DrumVoiceManager(engine).hit_params(drum_idx)
    return (note, velocity, params)


def sequence(steps, fill=None, step_seconds=0.5):
    return {"pattern": 1, "steps": steps, "fill": fill,
            "step_seconds": step_seconds, "humanize": 0.0}


def live_voices(engine):
    return [v for v in engine.voices if v.note_active or v.is_releasing]


# ── Kit rows ─────────────────────────────────────────────────────

def test_every_row_has_generated_sounds():
    assert all(drum_synth.labels(slot) for slot in ROWS)


def test_every_row_has_a_synth_stand_in_with_its_own_note():
    assert list(DRUM_PRESETS) == ROWS
    assert len({preset["midi_note"] for preset in DRUM_PRESETS.values()}) == len(ROWS)


def test_hit_params_name_the_sample_and_keep_the_synth_sound():
    note, params = DrumVoiceManager(None).hit_params(RIDE)
    assert note == DRUM_PRESETS["Ride"]["midi_note"]
    assert params["sample"] == {"slot": "Ride", "index": 0, "controls": {}}
    assert "waveform" in params


def test_voice_manager_without_samples_sends_synth_parameters_only():
    manager = DrumVoiceManager(None, use_samples=False)
    assert "sample" not in manager.hit_params(KICK)[1]


def test_engine_has_every_sound_ready_before_playing(generated_kit, monkeypatch):
    kit = make_engine().drum_kit

    def late(slot, index=0):
        raise AssertionError("a sound was generated after the engine started")

    monkeypatch.setattr(drum_synth, "render", late)
    for slot, index in every_sound():
        assert len(kit.sample(slot, index))


@pytest.mark.parametrize("drum_idx", range(len(ROWS)))
def test_engine_plays_every_generated_alternative(generated_kit, drum_idx):
    engine = make_engine()
    manager = DrumVoiceManager(engine)
    for index in range(len(drum_synth.labels(ROWS[drum_idx]))):
        note, params = manager.hit_params(drum_idx, {"sample": {"index": index, "controls": {}}})
        engine.all_notes_off()
        run_buffers(engine, 4)
        engine.drum_trigger(note, 127, params)
        audio = run_buffers(engine, 4)
        assert 0.1 < np.abs(audio).max() <= 1.0
        assert live_voices(engine) == []


# ── Engine ───────────────────────────────────────────────────────

def test_hit_plays_the_sample_and_uses_no_synth_voice():
    engine = sample_engine()
    note, velocity, params = hit(engine, KICK)
    engine.drum_trigger(note, velocity, params)
    audio = run_buffers(engine, 4)
    assert live_voices(engine) == []
    assert audio[100, 0] == pytest.approx(level_of("Kick"), abs=1e-3)


def test_without_a_kit_the_synth_drum_plays():
    engine = make_engine()
    note, velocity, params = hit(engine, KICK)
    engine.drum_trigger(note, velocity, params)
    assert np.abs(run_buffers(engine, 4)).max() > 0.01
    assert live_voices(engine)


def test_clock_places_samples_on_their_exact_position():
    engine = sample_engine(seconds=0.01)
    engine.drum_clock_start(sequence([[hit(engine, KICK)]], step_seconds=0.1055))  # 5064 samples
    audio = run_buffers(engine, 14)[:, 0]
    assert np.abs(audio[600:5064]).max() < 0.001
    assert audio[5064] == pytest.approx(level_of("Kick"), abs=1e-3)


def test_sample_keeps_playing_when_no_synth_voice_is_active():
    engine = sample_engine(seconds=0.5)
    engine.drum_trigger(*hit(engine, KICK))
    audio = run_buffers(engine, 60)[:, 0]
    assert audio[int(0.45 * SAMPLE_RATE)] == pytest.approx(level_of("Kick"), abs=1e-3)
    assert np.abs(audio[int(0.55 * SAMPLE_RATE):]).max() < 0.001


def test_velocity_changes_the_volume():
    engine = sample_engine()
    engine.drum_trigger(*hit(engine, KICK, velocity=64))
    audio = run_buffers(engine, 2)
    assert audio[100, 0] == pytest.approx(level_of("Kick") * (64 / 127) ** 1.5, abs=1e-3)


def test_closed_hat_cuts_off_the_open_hat():
    engine = sample_engine(seconds=0.5)
    engine.drum_trigger(*hit(engine, OPEN_HH))
    run_buffers(engine, 5)
    engine.drum_trigger(*hit(engine, CLOSED_HH))
    audio = run_buffers(engine, 5)[:, 0]
    assert audio[1000] == pytest.approx(level_of("Closed HH"), abs=1e-3)


def test_one_drum_does_not_lower_another():
    engine = sample_engine()
    engine.drum_trigger(*hit(engine, KICK))
    engine.drum_trigger(*hit(engine, SNARE))
    audio = run_buffers(engine, 2)
    assert audio[100, 0] == pytest.approx(level_of("Kick") + level_of("Snare"), abs=1e-3)


def test_synth_effects_and_amp_level_leave_the_drums_alone():
    engine = sample_engine(seconds=0.05, delay_mix=1.0, delay_feedback=0.8,
                           chorus_mix=1.0, amp_level=0.1)
    engine.drum_trigger(*hit(engine, KICK))
    audio = run_buffers(engine, 100)[:, 0]
    assert audio[100] == pytest.approx(level_of("Kick"), abs=1e-3)
    assert np.abs(audio[int(0.07 * SAMPLE_RATE):]).max() < 0.001


def test_master_volume_applies_to_the_drums():
    engine = sample_engine()
    engine.update_parameters(master_volume=0.5)
    run_buffers(engine, 100)
    engine.drum_trigger(*hit(engine, KICK))
    audio = run_buffers(engine, 2)
    assert audio[100, 0] == pytest.approx(level_of("Kick") * 0.5, abs=1e-3)


def test_many_loud_drums_stay_inside_full_scale():
    engine = sample_engine()
    engine.drum_kit = DrumKit({
        key: np.ones((4800, 2), dtype=np.float32) for key in every_sound()
    })
    for drum_idx in range(len(ROWS)):
        engine.drum_trigger(*hit(engine, drum_idx))
    audio = run_buffers(engine, 4)
    assert 0.8 < np.abs(audio).max() <= 1.0


@pytest.mark.parametrize("silence", ["all_notes_off", "soft_all_notes_off"])
def test_silencing_the_engine_stops_the_samples(silence):
    engine = sample_engine(seconds=1.0)
    engine.drum_trigger(*hit(engine, KICK))
    run_buffers(engine, 5)
    getattr(engine, silence)()
    run_buffers(engine, 3)
    assert np.abs(run_buffers(engine, 10)).max() < 0.001


def test_arm_engine_does_not_play_samples():
    engine = sample_engine()
    engine._IS_ARM = True
    engine.drum_trigger(*hit(engine, KICK))
    engine._process_midi_events()
    assert not engine._sample_player.active


# ── Screen ───────────────────────────────────────────────────────

def test_desktop_grid_has_ten_rows():
    async def scenario(pilot, mode, engine):
        assert [row.drum_name for row in mode.drum_rows] == ROWS
        await pilot.press(*["down"] * 9)
        await pilot.press("enter")
        assert mode.patterns[1][RIM][0]["active"]

    run_tambor(scenario)


def test_eight_row_pattern_files_load_and_gain_two_empty_rows(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 4})

    async def scenario(pilot, mode, engine):
        assert [s["active"] for s in mode.patterns[1][KICK]].count(True) == 2
        assert len(mode.patterns[1]) == 10
        assert not any(s["active"] for row in mode.patterns[1][8:] for s in row)
        mode._auto_save_current_pattern()

    run_tambor(scenario)
    saved = json.loads((isolated_cwd / "presets" / "tambor" / "pattern_01.json").read_text())
    assert [drum["name"] for drum in saved["drums"]] == ROWS


def test_ride_keeps_playing_during_a_fill():
    async def scenario(pilot, mode, engine):
        mode.patterns[1][RIDE][0]["active"] = True
        mode._on_fill_selected(1)
        fill = mode._build_sequence()["fill"]
        ride_note = DRUM_PRESETS["Ride"]["midi_note"]
        assert ride_note in [note for note, _, _ in fill[0]]

    run_tambor(scenario)


def test_arm_keeps_eight_rows_and_synth_drums(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine):
        assert [row.drum_name for row in mode.drum_rows] == ROWS[:8]
        await pilot.press("enter", "space")
        await pilot.pause(0.2)
        assert engine.hits and "sample" not in engine.hits[0][2]

    run_tambor(scenario)
