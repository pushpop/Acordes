# ABOUTME: Tests for Tambor's gamepad controls: triggers, dialog navigation and the Start button.
# ABOUTME: Run with: uv run python -m pytest tests/test_tambor_gamepad.py -q
import asyncio

import pytest
from textual.app import App

from components.confirmation_dialog import ConfirmationDialog
from gamepad.actions import GP
from gamepad.input_handler import GamepadHandler
from main import MainScreen
from modes.main_menu_mode import MainMenuMode
from modes.tambor import tambor_mode
from modes.tambor.tambor_mode import TamborMode
from modes.tambor.components.drum_editor import DrumEditorScreen, SampleDrumEditorScreen
from modes.tambor.components.fill_selector import FillSelectorScreen
from modes.tambor.components.pattern_selector import PatternSelectorScreen
from tests.test_tambor_mode import FakeEngine, FakeConfig, isolated_cwd  # noqa: F401


class Pad:
    """Presses buttons on the application's gamepad handler as a controller would."""

    def __init__(self, handler, pilot):
        self.handler, self.pilot = handler, pilot

    async def press(self, *actions):
        for action in actions:
            self.handler._on_button_down(action)
            self.handler._on_button_up(action)
            await self.pilot.pause(0.15)

    async def trigger(self, axis, *values):
        for value in values:
            self.handler._on_axis(axis, value)
        await self.pilot.pause(0.15)


PULL = [v / 10 for v in range(1, 11)]
RELEASE = [v / 10 for v in range(9, -1, -1)]


def run_with_pad(scenario):
    """Run scenario(pilot, pad, mode, context) with Tambor opened from the main screen."""
    handler = GamepadHandler()
    engine = FakeEngine()
    engine.soft_all_notes_off = lambda: None
    context = {
        "synth_engine": engine, "current_mode": "main_menu", "gamepad_handler": handler,
        "create_main_menu": lambda screen: MainMenuMode(screen),
        "create_tambor": lambda: TamborMode(config_manager=FakeConfig(), synth_engine=engine,
                                            gamepad_handler=handler),
    }

    class Shell(App):
        def on_mount(self):
            self.push_screen(MainScreen(context))

    async def main():
        async with Shell().run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("5")
            await pilot.pause(0.5)
            mode = pilot.app.screen.query_one(TamborMode)
            await scenario(pilot, Pad(handler, pilot), mode, context)

    asyncio.run(main())


def top(pilot):
    return type(pilot.app.screen)


def steps_on(mode, drum=0):
    return [i for i, step in enumerate(mode.patterns[mode.current_pattern][drum]) if step["active"]]


# -- Triggers ------------------------------------------------------

def count_calls(mode, name):
    """Record every call of a mode action, keeping what it does."""
    calls = []
    original = getattr(mode, name)
    setattr(mode, name, lambda: (calls.append(1), original()))
    return calls


@pytest.mark.parametrize("axis,action", [(GP.LT, "action_toggle_mute"), (GP.RT, "action_toggle_solo")])
def test_one_pull_toggles_once(axis, action):
    async def scenario(pilot, pad, mode, context):
        calls = count_calls(mode, action)
        await pad.trigger(axis, *PULL)
        assert len(calls) == 1
        await pad.trigger(axis, *RELEASE)
        assert len(calls) == 1
        await pad.trigger(axis, *PULL, *RELEASE)
        assert len(calls) == 2

    run_with_pad(scenario)


def test_a_trigger_hovering_near_halfway_toggles_once():
    async def scenario(pilot, pad, mode, context):
        calls = count_calls(mode, "action_toggle_mute")
        await pad.trigger(GP.LT, 0.6, 0.45, 0.62, 0.4, 0.7, 0.65)
        assert len(calls) == 1

    run_with_pad(scenario)


def test_a_trigger_released_inside_a_dialog_works_on_the_next_pull():
    async def scenario(pilot, pad, mode, context):
        calls = count_calls(mode, "action_toggle_mute")
        await pad.trigger(GP.LT, 1.0)
        await pad.press(GP.L3)
        await pad.trigger(GP.LT, 0.0)
        await pad.press(GP.BACK)
        await pad.trigger(GP.LT, 1.0)
        assert len(calls) == 2

    run_with_pad(scenario)


# -- Pattern selector ----------------------------------------------

def test_pattern_selector_is_driven_by_the_pad():
    async def scenario(pilot, pad, mode, context):
        await pad.press(GP.L3)
        await pad.press(GP.DPAD_RIGHT, GP.DPAD_DOWN, GP.DPAD_DOWN, GP.DPAD_UP, GP.DPAD_RIGHT, GP.DPAD_LEFT)
        await pad.press(GP.CONFIRM)
        assert top(pilot) is MainScreen
        assert mode.current_pattern == 10
        assert mode.cursor_drum == 0 and mode.cursor_step == 0
        assert steps_on(mode) == []

    run_with_pad(scenario)


@pytest.mark.parametrize("button", [GP.BACK, GP.BACK_BTN])
def test_back_closes_the_pattern_selector_without_choosing(button):
    async def scenario(pilot, pad, mode, context):
        await pad.press(GP.L3, GP.DPAD_RIGHT, button)
        assert top(pilot) is MainScreen and context["current_mode"] == "tambor"
        assert mode.current_pattern == 1
        # The grid has the controller again
        await pad.press(GP.DPAD_RIGHT, GP.CONFIRM)
        assert steps_on(mode) == [1]

    run_with_pad(scenario)


def test_x_erases_a_pattern_after_asking():
    async def scenario(pilot, pad, mode, context):
        await pad.press(GP.CONFIRM, GP.L3, GP.ACTION_1)
        assert top(pilot) is ConfirmationDialog
        selector = pilot.app.screen_stack[-2]
        # Nothing but the answer is accepted while asking
        await pad.press(GP.DPAD_RIGHT, GP.ACTION_1, GP.ACTION_2)
        assert top(pilot) is ConfirmationDialog and selector.selected_col == 0
        await pad.press(GP.BACK)
        assert top(pilot) is PatternSelectorScreen and steps_on(mode) == [0]
        await pad.press(GP.ACTION_1, GP.CONFIRM)
        assert top(pilot) is PatternSelectorScreen and steps_on(mode) == []
        await pad.press(GP.DPAD_RIGHT)
        assert selector.selected_col == 1
        await pad.press(GP.BACK, GP.CONFIRM)
        assert steps_on(mode) == [0]

    run_with_pad(scenario)


# -- Fill selector -------------------------------------------------

def test_fill_selector_is_driven_by_the_pad():
    async def scenario(pilot, pad, mode, context):
        await pilot.press("f")
        await pilot.pause(0.3)
        screen = pilot.app.screen
        await pad.press(GP.DPAD_DOWN, GP.DPAD_DOWN, GP.DPAD_UP, GP.CONFIRM)
        assert top(pilot) is MainScreen
        assert mode.pattern_fill_patterns[1] == screen.fill_ids[1]
        assert mode.cursor_drum == 0 and steps_on(mode) == []

    run_with_pad(scenario)


def test_back_closes_the_fill_selector_without_choosing():
    async def scenario(pilot, pad, mode, context):
        await pilot.press("f")
        await pilot.pause(0.3)
        await pad.press(GP.DPAD_DOWN, GP.BACK)
        assert top(pilot) is MainScreen
        assert mode.pattern_fill_patterns.get(1) is None

    run_with_pad(scenario)


# -- Drum editor ---------------------------------------------------

@pytest.mark.parametrize("with_kit", [True, False])
def test_drum_editor_adjusts_previews_and_applies(request, with_kit):
    if with_kit:
        request.getfixturevalue("generated_kit")

    async def scenario(pilot, pad, mode, context):
        engine = context["synth_engine"]
        await pad.press(GP.R3)
        screen = pilot.app.screen
        assert type(screen) is (SampleDrumEditorScreen if with_kit else DrumEditorScreen)
        name = screen.PARAMETERS[1][0]
        before = dict(screen.synth_params)
        await pad.press(GP.DPAD_DOWN, GP.DPAD_RIGHT)
        assert screen.synth_params[name] > before[name]
        await pad.press(GP.DPAD_LEFT, GP.DPAD_LEFT, GP.DPAD_UP)
        assert screen.synth_params[name] < before[name] or screen.synth_params[name] == screen.PARAMETERS[1][1]
        assert screen.selected_idx == 0
        engine.hits.clear()
        await pad.press(GP.ACTION_1)
        assert len(engine.hits) == 1
        await pad.press(GP.ACTION_2)
        assert len(engine.hits) == 2
        assert mode.playback_state == "STOPPED" and mode.cursor_drum == 0
        edited = dict(screen.synth_params)
        await pad.press(GP.CONFIRM)
        assert top(pilot) is MainScreen
        saved = mode.pattern_drum_overrides[1]["Kick"]
        if with_kit:
            assert saved["sample"] == SampleDrumEditorScreen.to_choice(edited)
        else:
            assert saved[name] == edited[name]

    run_with_pad(scenario)


@pytest.mark.parametrize("button", [GP.BACK, GP.BACK_BTN])
def test_back_cancels_the_drum_editor(generated_kit, button):
    async def scenario(pilot, pad, mode, context):
        await pad.press(GP.R3, GP.DPAD_RIGHT, button)
        assert top(pilot) is MainScreen and context["current_mode"] == "tambor"
        assert mode._sample_choice("Kick") == {}
        await pad.press(GP.DPAD_DOWN)
        assert mode.cursor_drum == 1

    run_with_pad(scenario)


def test_closing_with_the_keyboard_hands_the_pad_back():
    async def scenario(pilot, pad, mode, context):
        for opener in (GP.L3, GP.R3):
            await pad.press(opener)
            await pilot.press("escape")
            await pilot.pause(0.3)
            before = mode.cursor_drum
            await pad.press(GP.DPAD_DOWN)
            assert mode.cursor_drum == before + 1

    run_with_pad(scenario)


# -- Start ---------------------------------------------------------

async def assert_left_for_the_main_menu(pilot, pad, mode, context):
    assert top(pilot) is MainScreen
    assert context["current_mode"] == "main_menu"
    # Tambor no longer listens to the controller
    cursor = mode.cursor_drum
    await pad.press(GP.DPAD_DOWN, GP.ACTION_1)
    assert mode.cursor_drum == cursor and mode.playback_state == "STOPPED"
    # and takes it again when reopened
    await pilot.press("5")
    await pilot.pause(0.5)
    await pad.press(GP.DPAD_DOWN)
    assert mode.cursor_drum == cursor + 1
    await pad.press(GP.L3)
    assert top(pilot) is PatternSelectorScreen


@pytest.mark.parametrize("opener", [
    (GP.L3,), (GP.R3,), ("f",), (GP.L3, GP.ACTION_1),
], ids=["patterns", "editor", "fills", "erase question"])
def test_start_closes_dialogs_and_shows_the_main_menu(opener):
    async def scenario(pilot, pad, mode, context):
        for action in opener:
            if action == "f":
                await pilot.press("f")
                await pilot.pause(0.3)
            else:
                await pad.press(action)
        assert top(pilot) is not MainScreen
        await pad.press(GP.START)
        await pilot.pause(0.5)
        await assert_left_for_the_main_menu(pilot, pad, mode, context)

    run_with_pad(scenario)


# -- Raspberry Pi --------------------------------------------------

def test_arm_keeps_its_trigger_and_dialog_behaviour(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, pad, mode, context):
        toggles = []
        original = mode.action_toggle_mute
        mode.action_toggle_mute = lambda: (toggles.append(1), original())
        await pad.trigger(GP.LT, 0.6, 0.8, 1.0)
        assert len(toggles) == 3
        await pad.press(GP.L3, GP.DPAD_DOWN)
        assert mode.cursor_drum == 1  # the grid still listens behind the dialog

    run_with_pad(scenario)


# -- Grid: undo and right stick ------------------------------------

async def flick(pilot, pad, x=0.0, y=0.0):
    """Push the right stick, then let it return to the centre. Positive y is up."""
    up = tambor_mode.STICK_UP
    pad.handler._on_axis(GP.AXIS_RX, x)
    pad.handler._on_axis(GP.AXIS_RY, y * up)
    await pilot.pause(0.25)
    pad.handler._on_axis(GP.AXIS_RX, 0.0)
    pad.handler._on_axis(GP.AXIS_RY, 0.0)
    await pilot.pause(0.1)


def test_b_undoes_a_randomized_row():
    async def scenario(pilot, pad, mode, context):
        await pad.press(GP.CONFIRM, GP.ACTION_2)
        assert steps_on(mode) != [0]
        await pad.press(GP.BACK)
        assert steps_on(mode) == [0]
        await pad.press(GP.BACK)  # nothing left to undo
        assert steps_on(mode) == [0] and context["current_mode"] == "tambor"

    run_with_pad(scenario)


def test_right_stick_changes_the_drum_sound_once_per_push(generated_kit):
    async def scenario(pilot, pad, mode, context):
        pad.handler._on_axis(GP.AXIS_RX, 0.8)
        await pilot.pause(0.1)
        for value in (0.9, 1.0, 0.75, 0.95):
            pad.handler._on_axis(GP.AXIS_RX, value)
        await pilot.pause(0.25)
        assert mode._sample_choice("Kick")["index"] == 1
        await flick(pilot, pad)
        await flick(pilot, pad, x=1.0)
        assert mode._sample_choice("Kick")["index"] == 2
        await flick(pilot, pad, x=-1.0)
        assert mode._sample_choice("Kick")["index"] == 1
        assert top(pilot) is MainScreen

    run_with_pad(scenario)


def test_a_small_push_of_the_right_stick_does_nothing(generated_kit):
    async def scenario(pilot, pad, mode, context):
        await flick(pilot, pad, x=0.6)
        await flick(pilot, pad, y=0.6)
        await flick(pilot, pad, y=-1.0)  # down has no function
        assert mode._sample_choice("Kick") == {} and top(pilot) is MainScreen

    run_with_pad(scenario)


@pytest.mark.parametrize("stick_up", [1, -1])
def test_right_stick_up_opens_the_fill_selector(monkeypatch, stick_up):
    monkeypatch.setattr(tambor_mode, "STICK_UP", stick_up)

    async def scenario(pilot, pad, mode, context):
        await flick(pilot, pad, y=1.0)
        assert top(pilot) is FillSelectorScreen
        screen = pilot.app.screen
        await pad.press(GP.DPAD_DOWN, GP.CONFIRM)
        assert mode.pattern_fill_patterns[1] == screen.fill_ids[1]
        await flick(pilot, pad, y=1.0)
        assert top(pilot) is FillSelectorScreen

    run_with_pad(scenario)


@pytest.mark.parametrize("x,y,opens_fills", [(0.75, 0.95, True), (0.95, 0.75, False)])
def test_a_diagonal_push_follows_the_stronger_direction(generated_kit, x, y, opens_fills):
    async def scenario(pilot, pad, mode, context):
        await flick(pilot, pad, x=x, y=y)
        assert (top(pilot) is FillSelectorScreen) == opens_fills
        assert (mode._sample_choice("Kick") == {}) == opens_fills

    run_with_pad(scenario)


def test_arm_has_no_undo_or_right_stick_controls(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, pad, mode, context):
        assert pad.handler.get_button_callback(GP.BACK) is None
        await flick(pilot, pad, y=1.0)
        assert top(pilot) is MainScreen

    run_with_pad(scenario)
