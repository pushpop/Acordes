# ABOUTME: Tests for Tambor drum machine interaction: per-pattern state, drum editor, step count.
# ABOUTME: Run with: uv run python -m pytest tests/test_tambor_mode.py -q
import asyncio
import json
import os
import sys

import numpy as np
import pytest
from textual.app import App

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modes.tambor.tambor_mode import TamborMode
from modes.tambor.music.drum_presets import DRUM_PRESETS
from modes.tambor.music.drum_voice_manager import DrumVoiceManager

KICK = 0
FACTORY_KICK_DECAY = DRUM_PRESETS["Kick"]["synth_params"]["decay"]


class FakeEngine:
    """Records drum triggers instead of producing audio."""

    def __init__(self):
        self.hits = []

    def drum_trigger(self, note, velocity, params):
        self.hits.append((note, velocity, params))

    def update_parameters(self, **kwargs):
        pass

    def note_on(self, *args):
        pass

    def note_off(self, *args, **kwargs):
        pass

    def all_notes_off(self):
        pass


class FakeConfig:
    def get_bpm(self):
        return 120

    def set_bpm(self, bpm):
        pass


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Pattern files are written relative to the working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(TamborMode, "_IS_ARM", False, raising=False)
    return tmp_path


def run_tambor(scenario):
    """Run an async scenario(pilot, mode, engine) against a mounted TamborMode."""
    engine = FakeEngine()

    class TamborApp(App):
        def compose(self):
            yield TamborMode(config_manager=FakeConfig(), synth_engine=engine)

        def on_mount(self):
            self.query_one(TamborMode).focus()

    async def main():
        async with TamborApp().run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.2)
            await scenario(pilot, pilot.app.query_one(TamborMode), engine)

    asyncio.run(main())


async def select(pilot, mode, pattern_num):
    mode._select_pattern(pattern_num)
    await pilot.pause(0.1)


def write_pattern(root, pattern_num, active_kick_steps, num_steps=16):
    """Write a pattern file with the given kick steps switched on."""
    drums = []
    for drum_idx, name in enumerate(TamborMode.DRUM_SOUNDS):
        steps = [
            {
                "active": drum_idx == KICK and step in active_kick_steps,
                "velocity": 100,
                "note_length": 0.5,
            }
            for step in range(num_steps)
        ]
        drums.append({"name": name, "steps": steps})
    folder = root / "presets" / "tambor"
    folder.mkdir(parents=True, exist_ok=True)
    data = {"metadata": {"bpm": 120, "num_steps": num_steps, "pre_scale": "4"}, "drums": drums}
    (folder / f"pattern_{pattern_num:02d}.json").write_text(json.dumps(data))


def mute_light(mode, drum_idx):
    return mode.drum_rows[drum_idx].query_one("#mute-button").has_class("muted")


def panel_text(mode, label_id):
    return str(mode.control_panel.query_one(f"#{label_id}").render())


# ── Per-pattern state ────────────────────────────────────────────

def test_mute_and_solo_stay_with_their_pattern():
    async def scenario(pilot, mode, engine):
        await select(pilot, mode, 2)
        await select(pilot, mode, 1)
        await pilot.press("m", "down", "s")
        await select(pilot, mode, 2)
        assert mode.drum_mute_toggle == set()
        assert mode.drum_solo_toggle == set()
        assert not mute_light(mode, KICK)
        assert not mode.sequencer.is_drum_muted(36)

        await select(pilot, mode, 1)
        assert mode.drum_mute_toggle == {0}
        assert mode.drum_solo_toggle == {1}
        assert mute_light(mode, KICK)
        assert mode.sequencer.is_drum_muted(36)

    run_tambor(scenario)


def test_humanize_fill_and_prescale_labels_follow_the_pattern():
    async def scenario(pilot, mode, engine):
        await select(pilot, mode, 2)
        await select(pilot, mode, 1)
        await pilot.press("h", "t")
        mode._on_fill_selected(3)
        humanize = panel_text(mode, "humanize-label")
        pre_scale = panel_text(mode, "pre-scale-label")

        await select(pilot, mode, 2)
        assert panel_text(mode, "humanize-label") == "Humanize: OFF"
        assert panel_text(mode, "fill-label") == "Fill: None"
        assert "4 steps/beat" in panel_text(mode, "pre-scale-label")

        await select(pilot, mode, 1)
        assert panel_text(mode, "humanize-label") == humanize
        assert panel_text(mode, "fill-label") == "Fill: 3"
        assert panel_text(mode, "pre-scale-label") == pre_scale

    run_tambor(scenario)


def test_pattern_one_on_disk_survives_when_another_pattern_was_last_open(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 4, 8})
    (isolated_cwd / "patterns").mkdir()
    (isolated_cwd / "patterns" / ".last_pattern").write_text('{"last_pattern": 2}')

    async def scenario(pilot, mode, engine):
        await select(pilot, mode, 1)
        active = [i for i, step in enumerate(mode.patterns[1][KICK]) if step["active"]]
        assert active == [0, 4, 8]

    run_tambor(scenario)


def test_empty_pattern_keeps_its_step_count():
    async def scenario(pilot, mode, engine):
        await select(pilot, mode, 3)
        await pilot.press("plus", "plus", "plus", "plus")
        await select(pilot, mode, 4)
        assert mode.current_step_count == 16
        assert len(mode.drum_rows[KICK].cells) == 16
        assert mode.sequencer.num_steps == 16

        await select(pilot, mode, 3)
        assert mode.current_step_count == 20
        assert len(mode.drum_rows[KICK].cells) == 20
        assert mode.sequencer.num_steps == 20

    run_tambor(scenario)


def test_switching_pattern_drops_a_queued_fill():
    async def scenario(pilot, mode, engine):
        mode._on_fill_selected(3)
        mode._trigger_active_drums_for_step(mode.current_step_count - 1)
        assert mode._current_fill_id == 3

        await select(pilot, mode, 2)
        assert mode._current_fill_id is None
        assert not mode._fill_in_progress

    run_tambor(scenario)


# ── Step count changes ───────────────────────────────────────────

def test_step_count_change_keeps_playback_mute_light_and_cursor():
    async def scenario(pilot, mode, engine):
        await pilot.press("m", "right", "right", "space")
        await pilot.press("plus")
        await pilot.pause(0.2)

        assert mode.playback_state == "PLAYING"
        assert mode.sequencer.is_playing
        assert len(mode.drum_rows[KICK].cells) == 17
        assert len(mode.drum_rows[KICK].query("GridCell")) == 17
        assert mute_light(mode, KICK)
        assert mode.drum_rows[KICK].cells[2].has_class("focused")

        await pilot.press("minus", "minus")
        await pilot.pause(0.2)
        assert mode.playback_state == "PLAYING"
        assert len(mode.drum_rows[KICK].query("GridCell")) == 15
        await pilot.press("space")

    run_tambor(scenario)


def test_shrinking_below_cursor_moves_cursor_to_last_step():
    async def scenario(pilot, mode, engine):
        for _ in range(15):
            await pilot.press("right")
        await pilot.press("minus")
        await pilot.pause(0.1)
        assert mode.cursor_step == 14
        assert mode.drum_rows[KICK].cells[14].has_class("focused")

    run_tambor(scenario)


# ── Drum editor ──────────────────────────────────────────────────

def test_applied_drum_edit_is_used_by_playback():
    async def scenario(pilot, mode, engine):
        await pilot.press("enter", "e")
        await pilot.pause(0.1)
        await pilot.press("down", "right", "right", "enter")
        await pilot.pause(0.1)
        engine.hits.clear()
        mode._trigger_active_drums_for_step(0)
        assert engine.hits[0][2]["decay"] == pytest.approx(FACTORY_KICK_DECAY + 0.02)

    run_tambor(scenario)


def test_drum_edit_applies_only_to_its_pattern():
    async def scenario(pilot, mode, engine):
        mode._on_drum_editor_applied("Kick", {"decay": 0.2})
        await select(pilot, mode, 2)
        await pilot.press("enter")
        engine.hits.clear()
        mode._trigger_active_drums_for_step(0)
        assert engine.hits[0][2]["decay"] == FACTORY_KICK_DECAY

    run_tambor(scenario)


def test_editor_preview_plays_the_edited_sound():
    async def scenario(pilot, mode, engine):
        await pilot.press("e")
        await pilot.pause(0.1)
        await pilot.press("down", "right", "space")
        await pilot.pause(0.1)
        assert len(engine.hits) == 1
        note, velocity, params = engine.hits[0]
        assert note == 36
        assert params["decay"] == pytest.approx(FACTORY_KICK_DECAY + 0.01)

    run_tambor(scenario)


def test_cancelled_drum_edit_leaves_playback_unchanged():
    async def scenario(pilot, mode, engine):
        await pilot.press("enter", "e")
        await pilot.pause(0.1)
        await pilot.press("down", "right", "escape")
        await pilot.pause(0.1)
        engine.hits.clear()
        mode._trigger_active_drums_for_step(0)
        assert engine.hits[0][2]["decay"] == FACTORY_KICK_DECAY

    run_tambor(scenario)


def test_voice_manager_merges_overrides_without_touching_presets():
    engine = FakeEngine()
    DrumVoiceManager(engine).trigger_drum(KICK, 100, overrides={"decay": 0.2, "cutoff_freq": 900})
    params = engine.hits[0][2]
    assert params["decay"] == 0.2
    assert params["cutoff"] == 900
    assert params["attack"] == DRUM_PRESETS["Kick"]["synth_params"]["attack"]
    assert DRUM_PRESETS["Kick"]["synth_params"]["decay"] == FACTORY_KICK_DECAY


def test_override_reaches_the_synth_engine():
    from tests.test_voice_regression import make_engine, run_buffers

    engine = make_engine()
    DrumVoiceManager(engine).trigger_drum(KICK, 100, overrides={"cutoff_freq": 900})
    run_buffers(engine, 1)
    assert sounding_voices(engine, 36)[0].drum_sound["cutoff_current"] == 900


# ── Drum envelopes in the synth engine ───────────────────────────

SYNTH_NOTE = 60


def drum_engine():
    """Engine whose synth envelope sustains, so only a drum envelope can end a hit."""
    from tests.test_voice_regression import make_engine

    return make_engine(attack=0.1, decay=0.25, sustain=0.7, release=0.3)


def render(engine, seconds):
    from tests.test_voice_regression import run_buffers, BUFFER_SIZE, SAMPLE_RATE

    return run_buffers(engine, max(1, round(seconds * SAMPLE_RATE / BUFFER_SIZE)))


def sounding_voices(engine, note):
    return [v for v in engine.voices
            if v.midi_note == note and (v.note_active or v.is_releasing)]


def test_drum_hit_ends_after_its_own_decay():
    engine = drum_engine()
    DrumVoiceManager(engine).trigger_drum(KICK, 100)
    assert np.abs(render(engine, 0.1)).max() > 0.01
    render(engine, 0.5)
    assert sounding_voices(engine, 36) == []
    assert np.abs(render(engine, 0.1)).max() < 0.001


def test_edited_decay_changes_how_long_the_drum_sounds():
    engine = drum_engine()
    DrumVoiceManager(engine).trigger_drum(KICK, 100, overrides={"decay": 0.1})
    render(engine, 0.2)
    assert sounding_voices(engine, 36) == []


def test_simultaneous_drums_keep_their_own_envelopes():
    engine = drum_engine()
    manager = DrumVoiceManager(engine)
    manager.trigger_drum(KICK, 100)
    manager.trigger_drum(2, 100)  # Closed HH, 40 ms decay, same step
    render(engine, 0.2)
    assert len(sounding_voices(engine, 36)) == 1
    assert sounding_voices(engine, 42) == []


def test_drum_with_sustain_releases_and_ends_by_itself():
    engine = drum_engine()
    DrumVoiceManager(engine).trigger_drum(3, 100)  # Open HH, sustain 0.15
    render(engine, 0.55)
    voices = sounding_voices(engine, 46)
    assert voices and voices[0].is_releasing
    render(engine, 2.0)
    assert sounding_voices(engine, 46) == []


def test_retriggered_drum_starts_a_fresh_envelope():
    engine = drum_engine()
    manager = DrumVoiceManager(engine)
    manager.trigger_drum(KICK, 100)
    render(engine, 0.3)
    manager.trigger_drum(KICK, 100)
    render(engine, 0.3)
    assert len(sounding_voices(engine, 36)) == 1


@pytest.mark.parametrize("voice_type", ["poly", "mono", "unison"])
def test_synth_notes_after_drums_use_the_synth_envelope(voice_type):
    engine = drum_engine()
    DrumVoiceManager(engine).trigger_drum(KICK, 100)
    render(engine, 0.05)
    engine.update_parameters(voice_type=voice_type, attack=0.01, sustain=0.7)
    engine.note_on(SYNTH_NOTE, 100 / 127)
    render(engine, 1.5)
    assert sounding_voices(engine, SYNTH_NOTE)
    assert all(v.drum_env is None for v in sounding_voices(engine, SYNTH_NOTE))
    assert all(v.drum_sound is None for v in sounding_voices(engine, SYNTH_NOTE))
    assert np.abs(render(engine, 0.1)).max() > 0.01


def test_arm_engine_ignores_per_drum_envelopes():
    engine = drum_engine()
    engine._IS_ARM = True
    DrumVoiceManager(engine).trigger_drum(KICK, 100)
    engine._process_midi_events()
    assert all(v.drum_env is None for v in engine.voices)


# ── Drum sound settings in the synth engine ──────────────────────

def low_band_db(audio):
    """Energy below 150 Hz in the first 200 ms of the left channel."""
    spectrum = np.abs(np.fft.rfft(audio[:9600, 0])) ** 2
    freqs = np.fft.rfftfreq(9600, 1 / 48000)
    return 10 * np.log10(spectrum[freqs < 150].sum() + 1e-12)


def test_kick_keeps_its_low_end_with_a_hat_on_the_same_step():
    alone = drum_engine()
    DrumVoiceManager(alone).trigger_drum(KICK, 100)
    together = drum_engine()
    manager = DrumVoiceManager(together)
    manager.trigger_drum(KICK, 100)
    manager.trigger_drum(2, 100)
    # Two voices share the mix, which lowers each by about 3 dB
    assert low_band_db(render(together, 0.2)) > low_band_db(render(alone, 0.2)) - 6.0


def test_drum_hits_leave_the_synth_sound_untouched():
    engine = drum_engine()
    render(engine, 3.0)  # let smoothed synth parameters settle
    names = ("waveform", "cutoff_target", "cutoff_current", "resonance_target",
             "noise_level_target", "amp_level_target", "amp_level_current")
    before = {name: getattr(engine, name) for name in names}
    manager = DrumVoiceManager(engine)
    for drum_idx in range(8):
        manager.trigger_drum(drum_idx, 100)
    render(engine, 0.2)
    assert {name: getattr(engine, name) for name in names} == before


def test_synth_settings_do_not_colour_the_drums():
    def kick(**synth):
        engine = drum_engine()
        engine.update_parameters(**synth)
        render(engine, 3.0)  # let smoothed synth parameters settle
        DrumVoiceManager(engine).trigger_drum(KICK, 100, overrides={"noise_level": 0.0})
        return render(engine, 0.3)

    plain = kick()
    coloured = kick(octave=1, octave_enabled=True, sine_mix=0.5, rank2_enabled=True,
                    feg_amount=1.0, hpf_cutoff=2000.0, key_tracking=1.0,
                    lfo_depth=1.0, lfo_target="all", lfo_freq=8.0)
    assert np.abs(plain).max() > 0.01
    np.testing.assert_allclose(coloured, plain, atol=1e-3)


def test_each_drum_has_its_own_volume():
    def peak(volume):
        engine = drum_engine()
        DrumVoiceManager(engine).trigger_drum(5, 100, overrides={"volume": volume})
        return np.abs(render(engine, 0.1)).max()

    assert peak(0.3) == pytest.approx(peak(0.9) / 3, rel=0.15)


def test_arm_engine_keeps_global_drum_parameters():
    engine = drum_engine()
    engine._IS_ARM = True
    DrumVoiceManager(engine).trigger_drum(KICK, 100)
    engine._process_midi_events()
    assert engine.cutoff_target == DRUM_PRESETS["Kick"]["synth_params"]["cutoff_freq"]
    assert all(v.drum_sound is None for v in engine.voices)


# ── Navigation inside the application ────────────────────────────

def run_in_main_screen(scenario):
    """Run scenario(pilot, mode) with Tambor opened from the real MainScreen."""
    from main import MainScreen
    from modes.main_menu_mode import MainMenuMode

    engine = FakeEngine()
    engine.soft_all_notes_off = lambda: None
    context = {
        "synth_engine": engine,
        "current_mode": "main_menu",
        "create_main_menu": lambda screen: MainMenuMode(screen),
        "create_tambor": lambda: TamborMode(config_manager=FakeConfig(), synth_engine=engine),
    }

    class ShellApp(App):
        def on_mount(self):
            self.push_screen(MainScreen(context))

    async def main():
        async with ShellApp().run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.3)
            await pilot.press("5")
            await pilot.pause(0.5)
            await scenario(pilot, pilot.app.screen.query_one(TamborMode))

    asyncio.run(main())


def test_arrow_keys_move_the_cursor_inside_the_app():
    async def scenario(pilot, mode):
        await pilot.press("right", "right", "right", "down", "down", "left")
        assert (mode.cursor_drum, mode.cursor_step) == (2, 2)
        assert mode.drum_rows[2].cells[2].has_class("focused")
        await pilot.press("up")
        assert mode.cursor_drum == 1

    run_in_main_screen(scenario)


def test_arrow_keys_still_work_after_dialogs_and_mode_changes():
    async def scenario(pilot, mode):
        await pilot.press("e")
        await pilot.pause(0.1)
        await pilot.press("down", "right", "escape")
        await pilot.pause(0.1)
        assert (mode.cursor_drum, mode.cursor_step) == (0, 0)
        await pilot.press("0")
        await pilot.pause(0.3)
        await pilot.press("5")
        await pilot.pause(0.3)
        await pilot.press("right")
        assert mode.cursor_step == 1

    run_in_main_screen(scenario)


# ── ARM behaviour is frozen ──────────────────────────────────────

def test_arm_keeps_stopping_playback_on_step_count_change(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine):
        await pilot.press("space", "plus")
        await pilot.pause(0.2)
        assert mode.playback_state == "STOPPED"

    run_tambor(scenario)


def test_arm_keeps_factory_sound_and_silent_preview(monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)

    async def scenario(pilot, mode, engine):
        mode._on_drum_editor_applied("Kick", {"decay": 0.2})
        await pilot.press("e")
        await pilot.pause(0.1)
        await pilot.press("space", "escape")
        await pilot.pause(0.1)
        assert engine.hits == []
        await pilot.press("enter")
        mode._trigger_active_drums_for_step(0)
        assert engine.hits[0][2]["decay"] == FACTORY_KICK_DECAY

    run_tambor(scenario)


# ── Safety: undo, erase confirmation, hidden steps ───────────────

def active(mode, pattern_num=1, drum_idx=KICK):
    return [i for i, s in enumerate(mode.patterns[pattern_num][drum_idx]) if s["active"]]


def saved_pattern(root, pattern_num=1):
    path = root / "presets" / "tambor" / f"pattern_{pattern_num:02d}.json"
    return json.loads(path.read_text())


def saved_active(root, pattern_num=1, drum_idx=KICK):
    steps = saved_pattern(root, pattern_num)["drums"][drum_idx]["steps"]
    return [i for i, s in enumerate(steps) if s["active"]]


async def erase_selected(pilot, answer="y"):
    """Open the pattern selector, ask to erase the highlighted pattern and answer."""
    await pilot.press("n")
    await pilot.pause(0.2)
    await pilot.press("c")
    await pilot.pause(0.2)
    await pilot.press(answer)
    await pilot.pause(0.2)
    await pilot.press("escape")
    await pilot.pause(0.2)


def decorate(mode):
    """Give the current pattern every kind of per-pattern setting."""
    mode._on_drum_editor_applied("Kick", {"decay": 0.1})
    mode._on_fill_selected(3)
    mode.action_toggle_humanize()
    mode.action_toggle_mute()


def assert_decorated(mode, root):
    saved = saved_pattern(root)
    assert saved["drum_overrides"] == {"Kick": {"decay": 0.1}}
    assert saved["metadata"]["fill_pattern_id"] == 3
    assert saved["metadata"]["humanize_enabled"] is True
    assert saved["mute_state"][KICK] is True
    assert mode.pattern_drum_overrides[1] == {"Kick": {"decay": 0.1}}
    assert panel_text(mode, "fill-label") == "Fill: 3"
    assert "ON" in panel_text(mode, "humanize-label")
    assert mute_light(mode, KICK)


def test_cleared_row_comes_back_with_undo(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 4})

    async def scenario(pilot, mode, engine):
        await pilot.press("c")
        assert active(mode) == []
        await pilot.press("ctrl+z")
        await pilot.pause(0.2)
        assert active(mode) == [0, 4]
        assert mode.drum_rows[KICK].cells[4].is_active
        assert saved_active(isolated_cwd) == [0, 4]

    run_tambor(scenario)


def test_randomized_row_comes_back_with_undo(isolated_cwd):
    write_pattern(isolated_cwd, 1, {1, 2, 3})

    async def scenario(pilot, mode, engine):
        await pilot.press("r")
        await pilot.press("ctrl+z")
        await pilot.pause(0.2)
        assert active(mode) == [1, 2, 3]

    run_tambor(scenario)


def test_clearing_an_empty_row_adds_nothing_to_undo(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 4})

    async def scenario(pilot, mode, engine):
        await pilot.press("c", "down", "c", "ctrl+z")
        await pilot.pause(0.2)
        assert active(mode) == [0, 4]

    run_tambor(scenario)


def test_undo_keeps_the_last_twenty_actions(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0})

    async def scenario(pilot, mode, engine):
        for _ in range(25):
            mode.action_randomize_drum()
        assert len(mode.undo_stack) == 20

    run_tambor(scenario)


@pytest.mark.parametrize("answer", ["n", "escape"])
def test_erase_can_be_declined(isolated_cwd, answer):
    write_pattern(isolated_cwd, 1, {0, 4})

    async def scenario(pilot, mode, engine):
        await erase_selected(pilot, answer)
        assert active(mode) == [0, 4]
        assert saved_active(isolated_cwd) == [0, 4]

    run_tambor(scenario)


def test_erase_resets_every_pattern_setting(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 20}, num_steps=32)

    async def scenario(pilot, mode, engine):
        decorate(mode)
        mode._auto_save_periodic()
        await erase_selected(pilot)
        saved = saved_pattern(isolated_cwd)
        assert saved["metadata"]["num_steps"] == 16
        assert saved["metadata"]["fill_pattern_id"] is None
        assert saved["metadata"]["humanize_enabled"] is False
        assert "drum_overrides" not in saved and "mute_state" not in saved
        assert saved_active(isolated_cwd) == []
        assert mode.current_step_count == 16 and active(mode) == []
        assert len(mode.drum_rows[KICK].cells) == 16
        assert 1 not in mode.pattern_drum_overrides
        assert panel_text(mode, "fill-label") == "Fill: None"
        assert "OFF" in panel_text(mode, "humanize-label")
        assert not mute_light(mode, KICK)

    run_tambor(scenario)


def test_undo_restores_the_whole_erased_pattern(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 20}, num_steps=32)

    async def scenario(pilot, mode, engine):
        decorate(mode)
        mode._auto_save_periodic()
        await erase_selected(pilot)
        await pilot.press("ctrl+z")
        await pilot.pause(0.3)
        assert mode.current_step_count == 32
        assert len(mode.drum_rows[KICK].cells) == 32
        assert active(mode) == [0, 20]
        assert_decorated(mode, isolated_cwd)

    run_tambor(scenario)


def test_erasing_another_pattern_leaves_the_current_one_and_undo_shows_it(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0})
    write_pattern(isolated_cwd, 2, {5})

    async def scenario(pilot, mode, engine):
        await pilot.press("n")
        await pilot.pause(0.2)
        await pilot.press("right", "c")
        await pilot.pause(0.2)
        await pilot.press("y")
        await pilot.pause(0.2)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert mode.current_pattern == 1 and active(mode) == [0]
        assert saved_active(isolated_cwd, 2) == []
        await pilot.press("ctrl+z")
        await pilot.pause(0.3)
        assert mode.current_pattern == 2 and active(mode, 2) == [5]
        assert saved_active(isolated_cwd, 2) == [5]

    run_tambor(scenario)


def test_shortening_a_pattern_keeps_the_hidden_notes(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 15})

    async def shorten(pilot, mode, engine):
        await pilot.press("minus", "minus")
        await pilot.pause(0.2)
        assert mode.current_step_count == 14
        assert len(mode.drum_rows[KICK].cells) == 14
        assert len(mode._build_sequence()["steps"]) == 14
        await pilot.press("r", "ctrl+z")
        await pilot.pause(0.2)
        mode._auto_save_current_pattern()

    async def lengthen(pilot, mode, engine):
        assert mode.current_step_count == 14
        await pilot.press("plus", "plus")
        await pilot.pause(0.2)
        assert active(mode) == [0, 15]
        assert mode.drum_rows[KICK].cells[15].is_active

    run_tambor(shorten)
    assert saved_pattern(isolated_cwd)["metadata"]["num_steps"] == 14
    assert saved_active(isolated_cwd) == [0, 15]
    run_tambor(lengthen)


def test_randomize_leaves_hidden_notes_alone(isolated_cwd):
    write_pattern(isolated_cwd, 1, {0, 15})

    async def scenario(pilot, mode, engine):
        await pilot.press("minus", "r", "plus")
        await pilot.pause(0.2)
        assert 15 in active(mode)

    run_tambor(scenario)


def test_periodic_save_writes_to_disk_straight_away(isolated_cwd):
    write_pattern(isolated_cwd, 1, set())

    async def scenario(pilot, mode, engine):
        await pilot.press("enter")
        mode._auto_save_periodic()
        mode._pattern_saver.wait_for_saves()
        assert saved_active(isolated_cwd) == [0]

    run_tambor(scenario)


def test_undo_works_inside_the_app(isolated_cwd):
    async def scenario(pilot, mode):
        await pilot.press("enter", "c")
        assert active(mode) == []
        await pilot.press("ctrl+z")
        await pilot.pause(0.2)
        assert active(mode) == [0]

    run_in_main_screen(scenario)


def test_arm_keeps_immediate_erase_and_truncating_step_count(isolated_cwd, monkeypatch):
    monkeypatch.setattr(TamborMode, "_IS_ARM", True)
    write_pattern(isolated_cwd, 1, {0, 15})

    async def scenario(pilot, mode, engine):
        await pilot.press("minus", "plus")
        await pilot.pause(0.3)
        assert active(mode) == [0]
        await pilot.press("n")
        await pilot.pause(0.2)
        await pilot.press("c")
        await pilot.pause(0.2)
        assert active(mode) == []

    run_tambor(scenario)


# -- Humanize ------------------------------------------------------

@pytest.mark.parametrize("arm", [False, True])
def test_screen_playback_humanizes_once_on_desktop_only(monkeypatch, arm):
    monkeypatch.setattr(TamborMode, "_IS_ARM", arm)

    async def scenario(pilot, mode, engine):
        mode.humanizer.humanize_velocity = lambda amount, velocity: 110
        await pilot.press("enter", "h")
        mode._trigger_active_drums_for_step(0)
        assert engine.hits[-1][1] == (121 if arm else 110)

    run_tambor(scenario)
