# ABOUTME: Tests for Tambor's PRE-SCALE: step length, playback, saving and each pattern keeping its own.
# ABOUTME: Run with: uv run python -m pytest tests/test_tambor_prescale.py -q
import numpy as np
import pytest

from modes.tambor.music.pre_scale import PreScale
from modes.tambor.music.sequencer_engine import SequencerEngine
from modes.tambor.tambor_mode import TamborMode
from tests.test_tambor_timing import (
    Config, isolated_cwd, onsets, run_screen,  # noqa: F401
)
from tests.test_voice_regression import make_engine, run_buffers, SAMPLE_RATE


def label(mode):
    return str(mode.control_panel.query_one("#pre-scale-label").render())


def beat_fraction(bpm, steps_per_beat):
    return 60.0 / (bpm * steps_per_beat)


@pytest.mark.parametrize("steps_per_beat", [1, 2, 4, 8, 16])
def test_step_duration_divides_the_beat(steps_per_beat):
    sequencer = SequencerEngine(None, Config())
    assert sequencer.get_step_duration(steps_per_beat) == pytest.approx(0.5 / steps_per_beat)


def test_step_duration_defaults_to_four_steps_per_beat():
    assert SequencerEngine(None, Config()).get_step_duration() == pytest.approx(0.125)


def test_each_press_changes_the_playing_step_length():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("space")
        await pilot.pause(0.2)
        for steps_per_beat in (8, 16, 1, 2, 4):
            await pilot.press("t")
            await pilot.pause(0.2)
            kind, sequence = engine.commands[-1]
            assert kind == "update"
            assert sequence["step_seconds"] == pytest.approx(beat_fraction(120, steps_per_beat))
            assert label(mode) == f"PRE-SCALE: {steps_per_beat} steps/beat"
        await pilot.press("space")

    run_screen(scenario)


def test_pre_scale_and_tempo_work_together():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("t", "greater_than_sign", "space")
        await pilot.pause(0.1)
        assert engine.commands[0][1]["step_seconds"] == pytest.approx(beat_fraction(130, 8))
        await pilot.press("space")

    run_screen(scenario)


@pytest.mark.parametrize("presses, steps_per_beat", [(1, 8), (4, 2)])
def test_playing_audio_follows_the_pre_scale(presses, steps_per_beat):
    async def scenario(pilot, mode, engine, config):
        # Closed hat on every other step, so each hit is separated by silence
        for step in range(0, 16, 2):
            mode.patterns[mode.current_pattern][2][step]["active"] = True
        await pilot.press(*["t"] * presses, "space")
        await pilot.pause(0.2)
        found = onsets(run_buffers(engine, 300))
        await pilot.press("space")
        gap = 2 * beat_fraction(120, steps_per_beat) * SAMPLE_RATE
        assert len(found) >= 3
        assert np.median(np.diff(found)) == pytest.approx(gap, abs=48)

    run_screen(scenario, engine=make_engine())


def test_changing_it_is_an_unsaved_pattern_edit():
    async def scenario(pilot, mode, engine, config):
        assert mode.current_pattern not in mode.pattern_dirty
        await pilot.press("t")
        assert mode.current_pattern in mode.pattern_dirty

    run_screen(scenario)


def test_each_pattern_keeps_its_own_pre_scale():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("t")  # pattern 1 at 8
        mode._select_pattern(2)
        await pilot.pause(0.2)
        assert mode.current_pre_scale == PreScale.SCALE_4
        await pilot.press("t", "t")  # pattern 2 at 16
        mode._select_pattern(1)
        await pilot.pause(0.2)
        assert mode.current_pre_scale == PreScale.SCALE_8
        assert label(mode) == "PRE-SCALE: 8 steps/beat"
        mode._select_pattern(2)
        await pilot.pause(0.2)
        assert mode.current_pre_scale == PreScale.SCALE_16

    run_screen(scenario)


def test_a_new_pattern_starts_at_four_steps_per_beat():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("t")
        mode._select_pattern(40)  # never used
        await pilot.pause(0.2)
        assert mode.current_pre_scale == PreScale.SCALE_4
        assert mode.pre_scale_values[mode.pre_scale_index] == PreScale.SCALE_4
        assert label(mode) == "PRE-SCALE: 4 steps/beat"

    run_screen(scenario)


def test_pre_scale_is_still_there_after_leaving_tambor():
    async def change(pilot, mode, engine, config):
        await pilot.press("t")

    async def check(pilot, mode, engine, config):
        assert mode.current_pre_scale == PreScale.SCALE_8
        assert label(mode) == "PRE-SCALE: 8 steps/beat"
        assert mode.current_pattern not in mode.pattern_dirty
        await pilot.press("space")
        await pilot.pause(0.1)
        assert engine.commands[0][1]["step_seconds"] == pytest.approx(beat_fraction(120, 8))
        await pilot.press("space")

    run_screen(change)
    run_screen(check)


def test_arm_tambor_keeps_its_timing(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine, config):
        await pilot.press("t")
        assert label(mode) == "PRE-SCALE: 8 steps/beat"
        assert mode.current_pattern not in mode.pattern_dirty
        assert mode.sequencer.get_step_duration() == pytest.approx(0.125)

    run_screen(scenario)
