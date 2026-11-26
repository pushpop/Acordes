# ABOUTME: Tests that the Metronome's arrow keys work inside the real application screen.
# ABOUTME: Run with: uv run python -m pytest tests/test_metronome_mode.py -q
import asyncio
import os
import sys

from textual.app import App

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import MainScreen
from modes.main_menu_mode import MainMenuMode
from modes.metronome_mode import MetronomeMode


class FakeConfig:
    def __init__(self):
        self.bpm = 120

    def get_bpm(self):
        return self.bpm

    def set_bpm(self, bpm):
        self.bpm = bpm


class FakeEngine:
    def soft_all_notes_off(self):
        pass

    def play_metronome_click(self, accent=False):
        pass


def run_metronome(scenario):
    """Run scenario(pilot, mode, config) with the Metronome opened from MainScreen."""
    config, engine = FakeConfig(), FakeEngine()
    context = {
        "synth_engine": engine,
        "current_mode": "main_menu",
        "create_main_menu": lambda screen: MainMenuMode(screen),
        "create_metronome": lambda: MetronomeMode(config_manager=config, synth_engine=engine),
    }

    class ShellApp(App):
        def on_mount(self):
            self.push_screen(MainScreen(context))

    async def main():
        async with ShellApp().run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("4")
            await pilot.pause(0.5)
            await scenario(pilot, pilot.app.screen.query_one(MetronomeMode), config)

    asyncio.run(main())


def test_up_and_down_change_the_tempo():
    async def scenario(pilot, mode, config):
        await pilot.press("up", "up", "up")
        assert mode.tempo == 123 and config.bpm == 123
        await pilot.press("down")
        assert mode.tempo == 122 and config.bpm == 122

    run_metronome(scenario)


def test_left_and_right_change_the_time_signature():
    async def scenario(pilot, mode, config):
        await pilot.press("right")
        assert mode.time_signature == (2, 2)
        await pilot.press("left", "left")
        assert mode.time_signature == (3, 4)

    run_metronome(scenario)


def test_arrows_still_work_after_leaving_and_returning():
    async def scenario(pilot, mode, config):
        await pilot.press("0")
        await pilot.pause(0.3)
        await pilot.press("4")
        await pilot.pause(0.3)
        await pilot.press("up")
        assert mode.tempo == 121

    run_metronome(scenario)
