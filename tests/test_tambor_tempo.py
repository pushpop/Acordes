# ABOUTME: Tests for changing the shared tempo from Tambor: keys, limits, playback and other modes.
# ABOUTME: Run with: uv run python -m pytest tests/test_tambor_tempo.py -q
import asyncio

import numpy as np
import pytest
from textual.app import App

from main import MainScreen, TamborHelpBar
from modes.main_menu_mode import MainMenuMode
from modes.metronome_mode import MetronomeMode
from modes.tambor import tambor_mode
from modes.tambor.tambor_mode import TamborMode
from tests.test_tambor_timing import (
    ClockEngine, Config, isolated_cwd, onsets, run_screen,  # noqa: F401
)
from tests.test_voice_regression import make_engine, run_buffers, SAMPLE_RATE


def bpm_label(mode):
    return str(mode.control_panel.query_one("#bpm-label").render())


@pytest.mark.parametrize("key, expected", [
    ("full_stop", 121),
    ("comma", 119),
    ("greater_than_sign", 130),
    ("less_than_sign", 110),
])
def test_key_changes_the_shared_tempo(key, expected):
    async def scenario(pilot, mode, engine, config):
        await pilot.press(key)
        assert config.bpm == expected
        assert bpm_label(mode) == f"BPM: {expected}"

    run_screen(scenario)


@pytest.mark.parametrize("start, key, expected", [
    (300, "full_stop", 300),
    (295, "greater_than_sign", 300),
    (50, "comma", 50),
    (55, "less_than_sign", 50),
])
def test_tempo_stays_within_the_metronome_range(start, key, expected):
    async def scenario(pilot, mode, engine, config):
        config.bpm = start
        await pilot.press(key)
        assert config.bpm == expected
        assert bpm_label(mode) == f"BPM: {expected}"

    run_screen(scenario)


def test_tempo_change_is_not_an_unsaved_pattern_edit():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("full_stop")
        assert mode.current_pattern not in mode.pattern_dirty

    run_screen(scenario)


def test_tempo_survives_a_pattern_change():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("greater_than_sign")
        mode._select_pattern(2)
        mode._select_pattern(1)
        await pilot.pause(0.2)
        assert config.bpm == 130
        assert bpm_label(mode) == "BPM: 130"

    run_screen(scenario)


def test_tempo_change_reaches_the_running_clock():
    async def scenario(pilot, mode, engine, config):
        await pilot.press("space")
        await pilot.pause(0.2)
        await pilot.press("greater_than_sign")
        await pilot.pause(0.2)
        kind, sequence = engine.commands[-1]
        assert kind == "update"
        assert sequence["step_seconds"] == pytest.approx(60 / (130 * 4))
        await pilot.press("space")

    run_screen(scenario)


def test_playing_audio_follows_the_new_tempo():
    async def scenario(pilot, mode, engine, config):
        # Closed hat on every other step, so each hit is separated by silence
        for step in range(0, 16, 2):
            mode.patterns[mode.current_pattern][2][step]["active"] = True
        await pilot.press("greater_than_sign", "greater_than_sign", "greater_than_sign")
        await pilot.press("space")
        await pilot.pause(0.2)
        found = onsets(run_buffers(engine, 150))
        await pilot.press("space")
        gap = 2 * 60 / (150 * 4) * SAMPLE_RATE
        assert len(found) > 4
        assert np.median(np.diff(found)) == pytest.approx(gap, abs=48)

    run_screen(scenario, engine=make_engine())


def test_arm_tambor_leaves_the_tempo_alone(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine, config):
        await pilot.press("full_stop", "comma", "comma", "greater_than_sign")
        assert config.bpm == 120

    run_screen(scenario)


@pytest.mark.parametrize("is_arm, listed", [(False, True), (True, False)])
def test_help_bar_lists_the_tempo_keys_on_the_desktop(monkeypatch, is_arm, listed):
    monkeypatch.setattr(tambor_mode, "IS_ARM", is_arm)
    assert (",/.: Tempo" in TamborHelpBar().render()) is listed


def test_tempo_set_in_tambor_shows_in_the_metronome():
    config = Config()
    engine = ClockEngine()
    engine.soft_all_notes_off = lambda: None
    context = {
        "synth_engine": engine, "current_mode": "main_menu",
        "create_main_menu": lambda screen: MainMenuMode(screen),
        "create_tambor": lambda: TamborMode(config_manager=config, synth_engine=engine),
        "create_metronome": lambda: MetronomeMode(config, engine),
    }

    class Shell(App):
        def on_mount(self):
            self.push_screen(MainScreen(context))

    async def main():
        async with Shell().run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("5")
            await pilot.pause(0.5)
            await pilot.press("greater_than_sign", "full_stop")
            await pilot.press("4")
            await pilot.pause(0.5)
            assert pilot.app.screen.query_one(MetronomeMode).tempo == 131
            await pilot.press("up", "5")
            await pilot.pause(0.5)
            mode = pilot.app.screen.query_one(TamborMode)
            assert bpm_label(mode) == "BPM: 132"

    asyncio.run(main())
