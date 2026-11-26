# ABOUTME: Tests for Tambor timing: the audio-thread drum clock, its engine wiring and the UI link.
# ABOUTME: Run with: uv run python -m pytest tests/test_tambor_timing.py -q
import asyncio
import os
import random
import struct
import sys
from multiprocessing.shared_memory import SharedMemory

import numpy as np
import pytest
from textual.app import App

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from music.drum_clock import DrumClock
from music.engine_proxy import SynthEngineProxy
from modes.tambor.tambor_mode import TamborMode
from modes.tambor.music.drum_voice_manager import DrumVoiceManager
from tests.test_voice_regression import make_engine, run_buffers, BUFFER_SIZE, SAMPLE_RATE

STEP_SECONDS_120 = 0.125
STEP_SAMPLES_120 = 6000
CLOSED_HH = 2


def sequence(steps, fill=None, step_seconds=STEP_SECONDS_120, humanize=0.0, pattern=1):
    return {"pattern": pattern, "steps": steps, "fill": fill,
            "step_seconds": step_seconds, "humanize": humanize}


def numbered_steps(count, base=0):
    """Each step carries one hit whose note identifies the step."""
    return [[(base + i, 100, {})] for i in range(count)]


def run_clock(clock, samples, buffer_size=BUFFER_SIZE):
    """Return (absolute_sample, step, hits) for every step fired within the given time."""
    fired = []
    for start in range(0, samples, buffer_size):
        for offset, step, hits in clock.advance(buffer_size, SAMPLE_RATE):
            assert 0 <= offset < buffer_size
            fired.append((start + offset, step, hits))
    return fired


# ── Clock ────────────────────────────────────────────────────────

def test_clock_is_silent_until_started():
    clock = DrumClock()
    assert clock.advance(BUFFER_SIZE, SAMPLE_RATE) == []


def test_clock_places_steps_on_exact_samples_without_drift():
    clock = DrumClock()
    clock.start(sequence(numbered_steps(16)))
    fired = run_clock(clock, STEP_SAMPLES_120 * 64)
    assert [f[0] for f in fired] == [i * STEP_SAMPLES_120 for i in range(64)]
    assert [f[1] for f in fired] == [i % 16 for i in range(64)]


def test_clock_keeps_tempo_when_the_step_length_is_not_a_whole_number_of_samples():
    clock = DrumClock()
    step_seconds = 60.0 / (137 * 4)
    clock.start(sequence(numbered_steps(16), step_seconds=step_seconds))
    fired = run_clock(clock, SAMPLE_RATE * 30, buffer_size=256)
    for i, (position, _, _) in enumerate(fired):
        assert abs(position - i * step_seconds * SAMPLE_RATE) <= 1.0


def test_clock_applies_a_tempo_change_while_playing():
    clock = DrumClock()
    clock.start(sequence(numbered_steps(16)))
    run_clock(clock, STEP_SAMPLES_120)
    clock.update(sequence(numbered_steps(16), step_seconds=0.25))
    fired = run_clock(clock, 48000)
    gaps = np.diff([f[0] for f in fired])
    assert all(gap == 12000 for gap in gaps)


def test_clock_follows_a_shorter_pattern():
    clock = DrumClock()
    clock.start(sequence(numbered_steps(16)))
    run_clock(clock, STEP_SAMPLES_120 * 12)
    clock.update(sequence(numbered_steps(8)))
    fired = run_clock(clock, STEP_SAMPLES_120 * 10)
    assert all(step < 8 for _, step, _ in fired)


def test_clock_stops():
    clock = DrumClock()
    clock.start(sequence(numbered_steps(4)))
    run_clock(clock, STEP_SAMPLES_120)
    clock.stop()
    assert run_clock(clock, STEP_SAMPLES_120 * 4) == []


def test_clock_plays_the_fill_every_other_cycle():
    clock = DrumClock()
    clock.start(sequence(numbered_steps(4), fill=numbered_steps(4, base=100)))
    fired = run_clock(clock, STEP_SAMPLES_120 * 16)
    first_notes = [hits[0][0] for _, step, hits in fired if step == 0]
    assert first_notes == [0, 100, 0, 100]


def test_clock_drops_a_fill_when_the_pattern_changes():
    clock = DrumClock()
    clock.start(sequence(numbered_steps(4), fill=numbered_steps(4, base=100)))
    run_clock(clock, STEP_SAMPLES_120 * 5)  # inside the fill
    clock.update(sequence(numbered_steps(4, base=50), pattern=2))
    fired = run_clock(clock, STEP_SAMPLES_120 * 3)
    assert all(hits[0][0] >= 50 and hits[0][0] < 100 for _, _, hits in fired)


@pytest.mark.parametrize("velocity", [60, 100, 127])
def test_clock_humanizes_velocity_within_the_chosen_amount(velocity):
    random.seed(1)
    clock = DrumClock()
    clock.start(sequence([[(36, velocity, {})]], humanize=0.15))
    velocities = [hits[0][1] for _, _, hits in run_clock(clock, STEP_SAMPLES_120 * 200)]
    low, high = int(velocity * 0.85), min(127, int(velocity * 1.15))
    assert len(set(velocities)) > 5
    assert all(low <= v <= high for v in velocities)
    # The variation uses the whole range around the programmed velocity
    assert min(velocities) < velocity * 0.9
    if velocity < 127:
        assert max(velocities) > velocity * 1.1


def test_clock_leaves_velocity_alone_without_humanize():
    clock = DrumClock()
    clock.start(sequence([[(36, 90, {})]]))
    assert run_clock(clock, STEP_SAMPLES_120)[0][2][0][1] == 90


# ── Engine ───────────────────────────────────────────────────────

def hat_hit():
    note, params = DrumVoiceManager(None).hit_params(CLOSED_HH)
    return (note, 100, params)


def onsets(audio, threshold=0.002, quiet=480):
    """Sample positions where sound starts after at least `quiet` silent samples."""
    loud = np.nonzero(np.abs(audio[:, 0]) > threshold)[0]
    return [int(s) for i, s in enumerate(loud) if i == 0 or s - loud[i - 1] > quiet]


@pytest.mark.parametrize("bpm", [120, 137])
def test_engine_places_hits_on_the_beat(bpm):
    engine = make_engine()
    step_seconds = 60.0 / (bpm * 4)
    engine.drum_clock_start(sequence([[hat_hit()]], step_seconds=step_seconds))
    audio = run_buffers(engine, 300)  # 3 seconds
    found = onsets(audio)
    assert len(found) >= int(3 / step_seconds) - 1
    expected = step_seconds * SAMPLE_RATE
    for i, position in enumerate(found):
        assert abs((position - found[0]) - i * expected) <= 24  # half a millisecond


def test_engine_hit_inside_a_buffer_is_silent_before_its_time():
    engine = make_engine()
    engine.drum_clock_start(sequence([[hat_hit()]], step_seconds=0.1055))  # 5064 samples
    audio = run_buffers(engine, 12)
    assert np.abs(audio[4000:5064, 0]).max() < 0.001
    assert np.abs(audio[5064:5400, 0]).max() > 0.01


def test_engine_stop_ends_playback():
    engine = make_engine()
    engine.drum_clock_start(sequence([[hat_hit()]]))
    run_buffers(engine, 30)
    engine.drum_clock_stop()
    run_buffers(engine, 20)
    assert np.abs(run_buffers(engine, 40)).max() < 0.001


def test_engine_reports_the_playing_step():
    engine = make_engine()
    engine.drum_clock_start(sequence([[]] * 4))
    run_buffers(engine, 1)
    first = engine.get_drum_clock_position()
    run_buffers(engine, 26)  # past two more steps
    later = engine.get_drum_clock_position()
    assert first[1] == 0 and later[1] == 2
    assert later[0] - first[0] == 2


def test_retriggered_drum_fades_the_previous_hit_without_a_jump():
    engine = make_engine()
    manager = DrumVoiceManager(engine)
    note, params = manager.hit_params(0, {"noise_level": 0.0})
    engine.drum_clock_start(sequence([[(note, 100, params)]], step_seconds=0.1))
    audio = run_buffers(engine, 40)[:, 0]
    steady = np.abs(np.diff(audio[1500:4500])).max()
    around_retrigger = np.abs(np.diff(audio[4500:6500])).max()
    assert around_retrigger < max(steady * 3, 0.05)


RESONANT_KICK = {"cutoff_freq": 500, "resonance": 1.0}


@pytest.mark.parametrize("step_seconds, edits", [
    (0.5, {}), (0.4937, {}), (0.4937, RESONANT_KICK),
])
def test_every_hit_of_a_drum_sounds_the_same(step_seconds, edits):
    engine = make_engine()
    note, params = DrumVoiceManager(engine).hit_params(0, {"noise_level": 0.0, "decay": 0.17, **edits})
    engine.drum_clock_start(sequence([[(note, 100, params)]], step_seconds=step_seconds))
    audio = run_buffers(engine, int(8.5 * step_seconds * SAMPLE_RATE / BUFFER_SIZE))[:, 0]
    length = int(0.15 * SAMPLE_RATE)
    starts = [int(i * step_seconds * SAMPLE_RATE + 1e-6) for i in range(8)]
    first = audio[:length]
    for start in starts[1:]:
        difference = audio[start:start + length] - first
        assert np.sqrt(np.mean(difference ** 2)) < 0.05 * np.sqrt(np.mean(first ** 2))


def test_arm_engine_ignores_the_drum_clock():
    engine = make_engine()
    engine._IS_ARM = True
    engine.drum_clock_start(sequence([[hat_hit()]]))
    engine._process_midi_events()
    assert not engine._drum_clock.playing


def test_proxy_reads_the_position_the_engine_writes():
    shm = SharedMemory(create=True, size=SynthEngineProxy.SHM_SIZE)
    try:
        engine = make_engine()
        engine._level_shm = shm
        engine.drum_clock_start(sequence([[]] * 4))
        run_buffers(engine, 14)
        proxy = SynthEngineProxy.__new__(SynthEngineProxy)
        proxy._level_shm = shm
        assert proxy.get_drum_clock_position() == engine.get_drum_clock_position()
        assert proxy.get_drum_clock_position()[1] == 1
    finally:
        engine._level_shm = None
        shm.close()
        shm.unlink()


def test_proxy_sends_clock_commands():
    proxy = SynthEngineProxy.__new__(SynthEngineProxy)
    sent = []
    proxy._cmd_queue = type("Q", (), {"put": lambda self, msg: sent.append(msg)})()
    proxy.drum_clock_start({"a": 1})
    proxy.drum_clock_update({"a": 2})
    proxy.drum_clock_stop()
    assert [m["type"] for m in sent] == ["drum_clock_start", "drum_clock_update", "drum_clock_stop"]


# ── Screen ───────────────────────────────────────────────────────

class ClockEngine:
    """Records clock commands instead of producing audio."""

    def __init__(self):
        self.commands = []
        self.hits = []
        self.position = (0, 0)

    def drum_clock_start(self, seq):
        self.commands.append(("start", seq))

    def drum_clock_update(self, seq):
        self.commands.append(("update", seq))

    def drum_clock_stop(self):
        self.commands.append(("stop", None))

    def get_drum_clock_position(self):
        return self.position

    def drum_trigger(self, note, velocity, params):
        self.hits.append(note)

    def update_parameters(self, **kwargs):
        pass

    def all_notes_off(self):
        pass


class Config:
    def __init__(self):
        self.bpm = 120

    def get_bpm(self):
        return self.bpm

    def set_bpm(self, bpm):
        self.bpm = bpm


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TamborMode, "_IS_ARM", False)


def run_screen(scenario, engine=None):
    engine = engine or ClockEngine()
    config = Config()

    class TamborApp(App):
        def compose(self):
            yield TamborMode(config_manager=config, synth_engine=engine)

        def on_mount(self):
            self.query_one(TamborMode).focus()

    async def main():
        async with TamborApp().run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.2)
            await scenario(pilot, pilot.app.query_one(TamborMode), engine, config)

    asyncio.run(main())


def test_space_hands_the_pattern_to_the_engine_clock():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("enter", "space")
        await pilot.pause(0.3)
        kind, seq = engine.commands[0]
        assert kind == "start"
        assert seq["step_seconds"] == pytest.approx(STEP_SECONDS_120)
        assert len(seq["steps"]) == 16
        assert [hit[0] for hit in seq["steps"][0]] == [36]
        assert seq["fill"] is None
        assert engine.hits == []  # the screen itself triggers nothing
        await pilot.press("space")
        assert engine.commands[-1][0] == "stop"

    run_screen(scenario)


def test_edits_during_playback_are_sent_once():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("space")
        await pilot.pause(0.2)
        assert [c[0] for c in engine.commands] == ["start"]
        await pilot.press("enter")
        await pilot.pause(0.2)
        assert [c[0] for c in engine.commands] == ["start", "update"]
        assert engine.commands[-1][1]["steps"][0]
        await pilot.press("m")
        await pilot.pause(0.2)
        assert engine.commands[-1][1]["steps"][0] == []
        config.bpm = 90
        await pilot.pause(0.2)
        assert engine.commands[-1][1]["step_seconds"] == pytest.approx(60 / 360)
        await pilot.press("space")

    run_screen(scenario)


def test_sequence_carries_fill_humanize_and_drum_edits():
    async def scenario(pilot, mode, engine, config):
        mode._on_drum_editor_applied("Kick", {"decay": 0.2})
        mode._on_fill_selected(1)
        await pilot.press("enter", "h", "space")
        seq = engine.commands[0][1]
        assert seq["steps"][0][0][2]["decay"] == 0.2
        assert len(seq["fill"]) == 16 and any(seq["fill"])
        assert seq["humanize"] == pytest.approx(0.15)
        await pilot.press("space")

    run_screen(scenario)


def test_playhead_follows_the_engine():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("space")
        engine.position = (6, 5)
        await pilot.pause(0.2)
        assert mode.playhead_step == 5
        assert mode.drum_rows[0].cells[5].has_class("playing")
        await pilot.press("space")
        assert mode.playhead_step == -1

    run_screen(scenario)


def test_arm_screen_keeps_triggering_drums_itself(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine, config):
        await pilot.press("enter", "space")
        await pilot.pause(0.1)
        await pilot.press("space")
        assert engine.commands == []
        assert engine.hits == [36]

    run_screen(scenario)


def test_space_plays_audio_through_a_real_engine():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("enter", "space")
        await pilot.pause(0.1)
        audio = run_buffers(engine, 60)
        await pilot.pause(0.1)
        assert np.abs(audio).max() > 0.05
        assert mode.playhead_step == engine.get_drum_clock_position()[1]
        await pilot.press("space")

    run_screen(scenario, engine=make_engine())
