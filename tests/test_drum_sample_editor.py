# ABOUTME: Tests for choosing and shaping drum samples: editor, bracket keys and saved settings.
# ABOUTME: Run with: uv run python -m pytest tests/test_drum_sample_editor.py -q
import json

import numpy as np
import pytest

import music.drum_kit
from music.drum_kit import SLOT_SAMPLES
from modes.tambor.tambor_mode import TamborMode
from modes.tambor.components.drum_editor import DrumEditorScreen, SampleDrumEditorScreen
from modes.tambor.music.drum_voice_manager import DrumVoiceManager
from tests.test_tambor_mode import (  # noqa: F401
    isolated_cwd, run_tambor, run_in_main_screen, panel_text,
)

KICK, CLAP, RIDE = 0, 4, 8
LEFT, RIGHT = "left_square_bracket", "right_square_bracket"


@pytest.fixture
def kit():
    """Build a silent kit where the app looks for one."""
    names = {name for entries in SLOT_SAMPLES.values() for _, name in entries}
    with open(music.drum_kit.DEFAULT_KIT, "wb") as f:
        np.savez(f, **{name: np.zeros((10, 2), dtype=np.float32) for name in names})


def saved(root):
    return json.loads((root / "presets" / "tambor" / "pattern_01.json").read_text())


def sample_sent(engine):
    """Sample reference of the most recent drum hit sent to the engine."""
    return engine.hits[-1][2]["sample"]


def clock_sample(mode, drum_idx=KICK):
    return mode._build_sequence()["steps"][0][0][2]["sample"]


async def open_editor(pilot):
    await pilot.press("e")
    await pilot.pause(0.2)
    return pilot.app.screen


# ── Voice manager ────────────────────────────────────────────────

def test_chosen_sample_and_controls_reach_the_hit():
    overrides = {"sample": {"index": 2, "controls": {"tune": -3.0}}, "decay": 0.1}
    _, params = DrumVoiceManager(None).hit_params(KICK, overrides)
    assert params["sample"] == {"slot": "Kick", "index": 2, "controls": {"tune": -3.0}}
    assert params["decay"] == 0.1  # synth edits stay for when there is no kit


# ── Bracket keys ─────────────────────────────────────────────────

def test_brackets_step_through_the_alternatives_and_wrap(kit):
    async def scenario(pilot, mode, engine):
        assert "(Drive 02)" in panel_text(mode, "focus-label")
        await pilot.press(RIGHT)
        assert sample_sent(engine)["index"] == 1
        assert "(Drive 04)" in panel_text(mode, "focus-label")
        await pilot.press(LEFT, LEFT)
        assert sample_sent(engine)["index"] == 2
        assert "(Tape)" in panel_text(mode, "focus-label")
        await pilot.press(RIGHT)
        assert sample_sent(engine)["index"] == 0

    run_tambor(scenario)


def test_chosen_sample_is_saved_with_the_pattern(kit, isolated_cwd):
    async def choose(pilot, mode, engine):
        await pilot.press("enter", RIGHT, RIGHT)
        assert clock_sample(mode)["index"] == 2

    async def reopen(pilot, mode, engine):
        assert clock_sample(mode)["index"] == 2
        assert "(Tape)" in panel_text(mode, "focus-label")

    run_tambor(choose)
    assert saved(isolated_cwd)["drum_overrides"]["Kick"]["sample"]["index"] == 2
    run_tambor(reopen)


def test_sample_choice_belongs_to_one_pattern(kit):
    async def scenario(pilot, mode, engine):
        await pilot.press(RIGHT)
        mode._select_pattern(2)
        await pilot.pause(0.2)
        assert "(Drive 02)" in panel_text(mode, "focus-label")
        mode._select_pattern(1)
        await pilot.pause(0.2)
        assert "(Drive 04)" in panel_text(mode, "focus-label")

    run_tambor(scenario)


def test_returning_to_the_default_leaves_no_override(kit, isolated_cwd):
    async def scenario(pilot, mode, engine):
        await pilot.press(RIGHT, LEFT)

    run_tambor(scenario)
    assert "drum_overrides" not in saved(isolated_cwd)


def test_brackets_do_not_play_over_a_running_pattern(kit):
    async def scenario(pilot, mode, engine):
        await pilot.press("space")
        await pilot.pause(0.1)
        engine.hits.clear()
        await pilot.press(RIGHT)
        assert engine.hits == []

    run_tambor(scenario)


def test_brackets_do_nothing_without_a_kit():
    async def scenario(pilot, mode, engine):
        await pilot.press(RIGHT)
        assert engine.hits == []
        assert "(" not in panel_text(mode, "focus-label")

    run_tambor(scenario)


def test_brackets_work_inside_the_app(kit):
    async def scenario(pilot, mode):
        await pilot.press(RIGHT)
        assert "(Drive 04)" in panel_text(mode, "focus-label")

    run_in_main_screen(scenario)


# ── Editor ───────────────────────────────────────────────────────

def test_editor_shows_sample_controls_with_a_kit(kit):
    async def scenario(pilot, mode, engine):
        screen = await open_editor(pilot)
        assert isinstance(screen, SampleDrumEditorScreen)
        names = [p[0] for p in screen.PARAMETERS]
        assert names == ["index", "tune", "attack", "decay", "tone", "drive", "level"]
        shown = [str(label.render()) for label in screen.query(".param-val")]
        assert shown == ["Drive 02", "0.0st", "0ms", "100%", "0.00", "0.00", "100%"]
        titles = [str(label.render()) for label in screen.query(".param-name")]
        assert titles[0] == "Sample" and titles[-1] == "Level"

    run_tambor(scenario)


def test_editor_keeps_synth_controls_without_a_kit():
    async def scenario(pilot, mode, engine):
        screen = await open_editor(pilot)
        assert type(screen) is DrumEditorScreen

    run_tambor(scenario)


def test_choosing_a_sample_in_the_editor_plays_it(kit):
    async def scenario(pilot, mode, engine):
        screen = await open_editor(pilot)
        await pilot.press("right")
        assert sample_sent(engine)["index"] == 1
        assert str(screen.query(".param-val").first().render()) == "Drive 04"
        await pilot.press("right", "right")
        assert sample_sent(engine)["index"] == 0  # wraps around

    run_tambor(scenario)


def test_preview_plays_the_edited_controls(kit):
    async def scenario(pilot, mode, engine):
        await open_editor(pilot)
        await pilot.press("down", "left", "left", "space")
        assert sample_sent(engine)["controls"] == {"tune": -2.0}

    run_tambor(scenario)


def test_applied_controls_are_used_and_saved(kit, isolated_cwd):
    async def scenario(pilot, mode, engine):
        await pilot.press("enter")
        await open_editor(pilot)
        await pilot.press("down", "down", "down", "left", "down", "left", "left", "enter")
        await pilot.pause(0.2)
        assert clock_sample(mode)["controls"] == {"decay": 0.95, "tone": -0.2}

    run_tambor(scenario)
    stored = saved(isolated_cwd)["drum_overrides"]["Kick"]["sample"]
    assert stored == {"index": 0, "controls": {"decay": 0.95, "tone": -0.2}}


def test_cancel_discards_the_edit(kit):
    async def scenario(pilot, mode, engine):
        await pilot.press("enter")
        await open_editor(pilot)
        await pilot.press("right", "down", "right", "escape")
        await pilot.pause(0.2)
        assert clock_sample(mode) == {"slot": "Kick", "index": 0, "controls": {}}

    run_tambor(scenario)


def test_editor_starts_from_the_saved_settings(kit):
    async def scenario(pilot, mode, engine):
        await pilot.press(RIGHT)
        screen = await open_editor(pilot)
        assert str(screen.query(".param-val").first().render()) == "Drive 04"

    run_tambor(scenario)


def test_fine_steps_and_limits(kit):
    async def scenario(pilot, mode, engine):
        screen = await open_editor(pilot)
        await pilot.press("down", *["right"] * 20)
        assert screen.synth_params["tune"] == 12.0
        await pilot.press("shift+left")
        assert screen.synth_params["tune"] == pytest.approx(11.9)

    run_tambor(scenario)


def test_randomize_keeps_the_level_and_stays_in_range(kit):
    async def scenario(pilot, mode, engine):
        screen = await open_editor(pilot)
        for _ in range(20):
            await pilot.press("r")
            values = screen.synth_params
            assert values["level"] == 1.0
            for name, low, high, *_ in screen.PARAMETERS:
                assert low <= values[name] <= high

    run_tambor(scenario)


def test_arm_keeps_the_synth_editor_and_ignores_brackets(kit, monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine):
        await pilot.press(RIGHT)
        assert engine.hits == []
        screen = await open_editor(pilot)
        assert type(screen) is DrumEditorScreen

    run_tambor(scenario)
