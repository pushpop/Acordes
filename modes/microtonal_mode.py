# ABOUTME: μTonalidade mode — microtonal scale explorer with EDO (Equal Division of Octave) systems.
# ABOUTME: Provides real-time pitch exploration, scale browsing, MLT detection, and strum chords.
import math
import random
from typing import TYPE_CHECKING, List, Tuple, Optional

from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal

from components.header_widget import HeaderWidget
from gamepad.actions import GP

if TYPE_CHECKING:
    from music.engine_proxy import SynthEngineProxy
    from midi.input_handler import MIDIInputHandler


# ── EDO definitions ──────────────────────────────────────────────────────────
# Supported EDOs (Equal Divisions of the Octave), cycled with e/E.
_EDO_CYCLE = [18, 24, 36, 48, 72, 96]

# Mode catalog: dict[EDO, list[(name, [step_intervals])]]
# Each interval list must sum exactly to the EDO value.
_MODE_CATALOG: dict = {
    18: [
        ("Whole-Tone",    [3, 3, 3, 3, 3, 3]),          # all tones, 6 notes
        ("Augmented",     [2, 4, 2, 4, 2, 4]),           # symmetric aug triad
        ("Diminished 18", [4, 2, 4, 2, 4, 2]),           # symmetric dim triad
        ("Pentatonic 18", [4, 4, 2, 4, 4]),              # 5 notes
        ("Chromatic 18",  [1] * 18),                     # all steps
    ],
    24: [
        ("Rast",          [4, 3, 3, 4, 4, 3, 3]),        # Arabic maqam rast
        ("Bayati",        [3, 4, 3, 4, 4, 3, 3]),        # maqam bayati
        ("Hijaz",         [2, 6, 2, 4, 2, 4, 4]),        # maqam hijaz
        ("Whole-Tone 24", [4, 4, 4, 4, 4, 4]),           # whole-tone hexatonic
        ("Chromatic 24",  [2] * 12),                     # 12 quartertone semitones
    ],
    36: [
        ("Diatonic 36",   [6, 6, 3, 6, 6, 6, 3]),       # major in 36-EDO
        ("Chromatic 36",  [3] * 12),                     # 12 semitones × 3
        ("Whole-Tone 36", [6, 6, 6, 6, 6, 6]),           # whole-tone
        ("BP-like 36",    [5, 4, 5, 4, 5, 4, 4, 5]),    # Bohlen-Pierce inspired
        ("Thirds 36",     [4] * 9),                      # symmetrical thirds
    ],
    48: [
        ("Diatonic 48",   [8, 8, 4, 8, 8, 8, 4]),       # major in 48-EDO
        ("Rast 48",       [8, 6, 6, 8, 8, 6, 6]),        # rast with quarter-tones
        ("Chromatic 48",  [4] * 12),                     # standard chromatic
        ("Whole-Tone 48", [8, 8, 8, 8, 8, 8]),           # whole-tone
        ("Pentatonic 48", [8, 8, 12, 8, 12]),            # major pentatonic
    ],
    72: [
        ("Diatonic 72",   [12, 12, 6, 12, 12, 12, 6]),  # major, very precise
        ("Chromatic 72",  [6] * 12),                     # standard chromatic
        ("Rast 72",       [12, 9, 9, 12, 12, 9, 9]),     # rast (9 = 3/4 tone)
        ("Whole-Tone 72", [12, 12, 12, 12, 12, 12]),     # whole-tone
        ("Secor 9",       [8] * 9),                      # 9-equal sub-temperament
    ],
    96: [
        ("Diatonic 96",   [16, 16, 8, 16, 16, 16, 8]),  # major, finest resolution
        ("Chromatic 96",  [8] * 12),                     # standard chromatic
        ("Rast 96",       [16, 12, 12, 16, 16, 12, 12]), # rast at 96-EDO
        ("Whole-Tone 96", [16, 16, 16, 16, 16, 16]),     # whole-tone
        ("Commas 96",     [4] * 24),                     # 24-equal sub-lattice
    ],
}

# Reference middle-C frequency for EDO calculations.
_MIDDLE_C_HZ = 261.626
# MIDI note for middle C.
_MIDDLE_C_MIDI = 60
# Pitch bend range in semitones (must match synth engine — engine uses ±2).
_BEND_RANGE_SEMITONES = 2.0

# Strum parameters: velocity range, base stagger, timing jitter, gate.
_STRUM_VEL_MIN   = 62
_STRUM_VEL_MAX   = 96
_STRUM_BASE_MS   = 110    # base gap between notes (ms)
_STRUM_JITTER_MS = 35     # max random ±deviation per gap (ms)
_STRUM_GATE_S    = 1.1    # how long notes ring before gate-off


def _is_mlt(steps: List[int]) -> bool:
    """Return True if the scale step pattern is a Mode of Limited Transposition.

    A scale is MLT when its step pattern is periodic, meaning transposing by
    a fraction of the octave produces the same set of pitch classes.
    """
    n = len(steps)
    for period in range(1, n):
        if n % period == 0:
            k = n // period
            if steps[:period] * k == steps:
                return True
    return False


def _scale_cumulative(steps: List[int]) -> List[int]:
    """Return cumulative step offsets from tonic (including tonic=0)."""
    result = [0]
    acc = 0
    for s in steps[:-1]:  # last step wraps back to octave, not included as a distinct degree
        acc += s
        result.append(acc)
    return result


def _edo_step_to_midi_and_bend(total_edo_steps: int, edo: int) -> Tuple[int, int]:
    """Convert an absolute EDO step number to (midi_note, pitch_bend_14bit).

    pitch_bend_14bit is in the range [0, 16383], centered at 8192 (no bend).
    The engine's pitch_bend_change() formula: ((value - 8192) / 8192) * 2.0 semitones.
    """
    freq = _MIDDLE_C_HZ * (2.0 ** (total_edo_steps / edo))
    # MIDI note number as float
    midi_float = _MIDDLE_C_MIDI + 12.0 * math.log2(freq / _MIDDLE_C_HZ)
    midi_note = int(round(midi_float))
    midi_note = max(0, min(127, midi_note))
    # Deviation from nearest semitone in semitones
    deviation_semitones = midi_float - midi_note
    # Map to 14-bit pitch bend centered at 8192
    bend_value = int(8192 + (deviation_semitones / _BEND_RANGE_SEMITONES) * 8192)
    bend_value = max(0, min(16383, bend_value))
    return midi_note, bend_value


class MicrotonalMode(Widget):
    """μTonalidade — microtonal scale explorer using EDO systems."""

    # Width of panel interior (excluding │ borders).
    # 5 panels × (W+2) chars must fit the terminal; 20 = 110 chars total, comfortable at 130+.
    _W = 20

    CSS = """
    MicrotonalMode {
        layout: vertical;
        height: 100%;
        width: 100%;
        background: #111111;
    }
    #utonal-panels {
        layout: horizontal;
        width: 100%;
        height: 13;
        padding: 0;
        margin: 0;
    }
    #utonal-edo-panel {
        width: 1fr;
        height: 100%;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }
    #utonal-scale-panel {
        width: 1fr;
        height: 100%;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }
    #utonal-tonic-panel {
        width: 1fr;
        height: 100%;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }
    #utonal-step-panel {
        width: 1fr;
        height: 100%;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }
    #utonal-status-panel {
        width: 1fr;
        height: 100%;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }
    #utonal-ring-panel {
        width: 100%;
        height: 1fr;
        background: #0d0d0d;
        padding: 0;
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("j",      "prev_mode",    "◄ Mode",   show=False),
        Binding("k",      "next_mode",    "Mode ►",   show=False),
        Binding("up",     "step_up",      "Step ▲",   show=False, priority=True),
        Binding("down",   "step_down",    "Step ▼",   show=False, priority=True),
        Binding("left",   "tonic_flat",   "Tonic ♭",  show=False, priority=True),
        Binding("right",  "tonic_sharp",  "Tonic ♯",  show=False, priority=True),
        Binding("o",      "octave_down",  "Oct ▼",    show=False),
        Binding("O",      "octave_up",    "Oct ▲",    show=False),
        Binding("space",  "play_step",    "Play",     show=False, priority=True),
        Binding("enter",  "toggle_hold",  "Hold",     show=False),
        Binding("e",      "next_edo",     "EDO ►",    show=False),
        Binding("E",      "prev_edo",     "EDO ◄",    show=False),
        Binding("g",      "step_gen_fwd", "Gen ►",    show=False),
        Binding("G",      "step_gen_bwd", "Gen ◄",    show=False),
        Binding("z",      "strum",        "Strum",    show=False, priority=True),
        Binding("m",      "toggle_mlt",   "MLT",      show=False),
        Binding("r",      "toggle_reverse", "Rev",    show=False),
    ]

    can_focus = True

    def __init__(self, synth_engine: 'SynthEngineProxy',
                 midi_handler: 'MIDIInputHandler' = None,
                 gamepad_handler=None):
        super().__init__()
        self.synth_engine = synth_engine
        self.midi_handler = midi_handler
        self.gamepad_handler = gamepad_handler

        # EDO state
        self._edo_index: int = 1              # default: 24-EDO
        self._mode_index: int = 0             # index into mode catalog for current EDO
        self._tonic_step: int = 0             # tonic position in EDO (0 to EDO-1)
        self._scale_step: int = 0             # current selected degree in the scale
        self._octave: int = 0                 # octave offset (-2 to +2)
        self._hold_on: bool = False           # whether hold is active
        self._mlt_filter: bool = False        # show only MLT modes
        self._reversed: bool = False          # flip keyboard direction (high keys → low pitch)

        # Keyboard playback state
        # Maps original incoming MIDI note -> actual MIDI note played (after EDO mapping).
        # Needed so note_off can release the right pitch.
        self._active_midi_notes: dict = {}
        self._poll_timer = None

        # Track held note (keyboard actions) so we can release it
        self._held_note: Optional[int] = None
        self._held_bend: int = 8192

        # Strum state: track which notes are pending release.
        # _strum_fire_timers holds every set_timer() handle for pending note-on
        # events so they can all be cancelled when a new strum fires or the mode
        # is paused.  Without this, orphaned timers fire note-ons that never
        # receive a matching note-off, filling all voices with stuck notes.
        self._strum_notes: List[int] = []
        self._strum_gate_timer = None
        self._strum_fire_timers: List = []

        # Panel widget references (set in on_mount after compose)
        self._panel_edo:    Optional[Static] = None
        self._panel_scale:  Optional[Static] = None
        self._panel_tonic:  Optional[Static] = None
        self._panel_step:   Optional[Static] = None
        self._panel_status: Optional[Static] = None
        self._panel_ring:   Optional[Static] = None

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def _current_edo(self) -> int:
        return _EDO_CYCLE[self._edo_index]

    @property
    def _catalog(self) -> List[Tuple[str, List[int]]]:
        """Return the mode catalog for the current EDO, filtered if MLT-only."""
        catalog = _MODE_CATALOG[self._current_edo]
        if self._mlt_filter:
            filtered = [(name, steps) for name, steps in catalog if _is_mlt(steps)]
            return filtered if filtered else catalog  # fall back if none match
        return catalog

    @property
    def _current_mode_name(self) -> str:
        return self._catalog[self._mode_index][0]

    @property
    def _current_steps(self) -> List[int]:
        return self._catalog[self._mode_index][1]

    @property
    def _scale_degrees(self) -> List[int]:
        """Cumulative EDO offsets for the current mode, relative to tonic."""
        return _scale_cumulative(self._current_steps)

    @property
    def _num_scale_notes(self) -> int:
        return len(self._current_steps)

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self):
        """Build the μTonalidade layout: 5 info panels on top, large ring below."""
        yield HeaderWidget(
            title="μ T O N A L I D A D E",
            subtitle=self._get_subtitle(),
            is_big=False,
            id="utonal-header",
        )
        with Horizontal(id="utonal-panels"):
            yield Static("", id="utonal-edo-panel")
            yield Static("", id="utonal-scale-panel")
            yield Static("", id="utonal-tonic-panel")
            yield Static("", id="utonal-step-panel")
            yield Static("", id="utonal-status-panel")
        yield Static("", id="utonal-ring-panel")

    def on_mount(self):
        """Initialise display, wire MIDI, and register gamepad callbacks."""
        self._panel_edo    = self.query_one("#utonal-edo-panel",    Static)
        self._panel_scale  = self.query_one("#utonal-scale-panel",  Static)
        self._panel_tonic  = self.query_one("#utonal-tonic-panel",  Static)
        self._panel_step   = self.query_one("#utonal-step-panel",   Static)
        self._panel_status = self.query_one("#utonal-status-panel", Static)
        self._panel_ring   = self.query_one("#utonal-ring-panel",   Static)
        self._refresh_display()
        self.focus()
        self._register_midi_callbacks()
        # Only start MIDI polling when a handler is present; no handler = no timer overhead.
        if self.midi_handler is not None:
            self._poll_timer = self.set_interval(0.01, self._poll_midi)
        self._register_gamepad_callbacks()

    def on_unmount(self):
        """Release held notes and cancel pending timers."""
        self._release_all_midi()
        self._release_held()
        self._cancel_strum_gate()
        self._stop_poll_timer()
        if self.midi_handler is not None:
            self.midi_handler.set_callbacks(note_on=None, note_off=None)
        gp = self.gamepad_handler
        if gp is not None:
            gp.clear_callbacks()

    def on_mode_pause(self):
        """Called when switching away from this mode (widget caching)."""
        self._release_all_midi()
        self._release_held()
        self._cancel_strum_gate()
        self._stop_poll_timer()
        if self.midi_handler is not None:
            self.midi_handler.set_callbacks(note_on=None, note_off=None)
        gp = self.gamepad_handler
        if gp is not None:
            gp.clear_callbacks()

    def on_mode_resume(self):
        """Called when returning to this cached mode."""
        self._refresh_display()
        self.focus()
        self._register_midi_callbacks()
        if self.midi_handler is not None:
            # Guard against duplicate timers (config push_screen skips on_mode_pause).
            if self._poll_timer is not None:
                self._poll_timer.stop()
                self._poll_timer = None
            self._poll_timer = self.set_interval(0.01, self._poll_midi)
        self._register_gamepad_callbacks()

    # ── MIDI ──────────────────────────────────────────────────────────────────

    def _register_midi_callbacks(self):
        """Wire note-on / note-off callbacks to the MIDI handler."""
        if self.midi_handler is None:
            return
        self.midi_handler.set_callbacks(
            note_on=self._on_midi_note_on,
            note_off=self._on_midi_note_off,
        )

    def _poll_midi(self):
        """Drain pending MIDI messages (called every 10 ms)."""
        if self.midi_handler is not None and self.midi_handler.is_device_open():
            self.midi_handler.poll_messages()

    def _on_midi_note_on(self, midi_note: int, velocity: int):
        """Map incoming MIDI note to an EDO scale degree, apply pitch bend, and play.

        The piano keyboard is treated as a linear scale keyboard: each semitone
        above/below MIDI 60 (C4 = tonic) advances one scale degree. The octave
        wraps naturally every N degrees (N = number of notes in the current scale).
        """
        degrees = self._scale_degrees
        n = self._num_scale_notes
        if n == 0:
            return

        # Distance in semitones from the tonic reference key (C4 = 60).
        # When reversed, the keyboard is flipped: high keys produce low pitches.
        distance = -(midi_note - 60) if self._reversed else (midi_note - 60)
        degree_index = distance % n
        octave_shift = distance // n

        abs_step = (self._tonic_step + degrees[degree_index]
                    + (self._octave + octave_shift) * self._current_edo)
        actual_note, bend = _edo_step_to_midi_and_bend(abs_step, self._current_edo)

        self.synth_engine.pitch_bend_change(bend)
        self.synth_engine.note_on(actual_note, velocity)
        # Remember mapping so note_off can release the right pitch.
        self._active_midi_notes[midi_note] = actual_note

    def _on_midi_note_off(self, midi_note: int, velocity: int = 0):
        """Release the EDO-mapped note that was started for this MIDI key."""
        actual_note = self._active_midi_notes.pop(midi_note, None)
        if actual_note is not None:
            self.synth_engine.note_off(actual_note, velocity)

    def _release_all_midi(self):
        """Release every active MIDI-triggered note immediately."""
        for actual_note in self._active_midi_notes.values():
            self.synth_engine.note_off(actual_note, 0)
        self._active_midi_notes.clear()

    def _stop_poll_timer(self):
        """Stop the MIDI poll timer if running."""
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None

    # ── Gamepad ───────────────────────────────────────────────────────────────

    def _register_gamepad_callbacks(self):
        gp = self.gamepad_handler
        if gp is None:
            return
        gp.clear_callbacks()
        gp.set_button_callback(GP.DPAD_UP,    lambda: self.action_step_up())
        gp.set_button_callback(GP.DPAD_DOWN,  lambda: self.action_step_down())
        gp.set_button_callback(GP.DPAD_LEFT,  lambda: self.action_prev_mode())
        gp.set_button_callback(GP.DPAD_RIGHT, lambda: self.action_next_mode())
        gp.set_button_callback(GP.CONFIRM,    lambda: self.action_play_step())
        gp.set_button_callback(GP.ACTION_2,   lambda: self.action_strum())
        gp.set_button_callback(GP.LB,         lambda: self.action_prev_edo())
        gp.set_button_callback(GP.RB,         lambda: self.action_next_edo())

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_next_mode(self):
        """Advance to the next mode in the catalog."""
        self._release_held()
        self._mode_index = (self._mode_index + 1) % len(self._catalog)
        self._scale_step = 0
        self._refresh_display()

    def action_prev_mode(self):
        """Retreat to the previous mode in the catalog."""
        self._release_held()
        self._mode_index = (self._mode_index - 1) % len(self._catalog)
        self._scale_step = 0
        self._refresh_display()

    def action_step_up(self):
        """Move one scale degree up."""
        self._scale_step = (self._scale_step + 1) % self._num_scale_notes
        if self._hold_on:
            self._play_current_step()
        self._refresh_display()

    def action_step_down(self):
        """Move one scale degree down."""
        self._scale_step = (self._scale_step - 1) % self._num_scale_notes
        if self._hold_on:
            self._play_current_step()
        self._refresh_display()

    def action_tonic_sharp(self):
        """Transpose tonic one EDO step up."""
        self._release_held()
        self._tonic_step = (self._tonic_step + 1) % self._current_edo
        self._refresh_display()

    def action_tonic_flat(self):
        """Transpose tonic one EDO step down."""
        self._release_held()
        self._tonic_step = (self._tonic_step - 1) % self._current_edo
        self._refresh_display()

    def action_octave_up(self):
        """Shift octave up."""
        self._release_held()
        self._octave = min(2, self._octave + 1)
        self._refresh_display()

    def action_octave_down(self):
        """Shift octave down."""
        self._release_held()
        self._octave = max(-2, self._octave - 1)
        self._refresh_display()

    def action_play_step(self):
        """Play the current scale step (single note, short gate)."""
        self._play_current_step(hold=self._hold_on)
        self._refresh_display()

    def action_toggle_hold(self):
        """Toggle sustain hold — held note continues until next note or release."""
        self._hold_on = not self._hold_on
        if not self._hold_on:
            self._release_held()
        self._refresh_display()

    def action_next_edo(self):
        """Cycle to the next EDO."""
        self._release_held()
        self._edo_index = (self._edo_index + 1) % len(_EDO_CYCLE)
        self._clamp_mode_index()
        self._tonic_step = 0
        self._scale_step = 0
        self._refresh_display()

    def action_prev_edo(self):
        """Cycle to the previous EDO."""
        self._release_held()
        self._edo_index = (self._edo_index - 1) % len(_EDO_CYCLE)
        self._clamp_mode_index()
        self._tonic_step = 0
        self._scale_step = 0
        self._refresh_display()

    def action_step_gen_fwd(self):
        """Advance by the generating interval (first step of current mode) forward."""
        self._release_held()
        gen = self._current_steps[0]
        self._tonic_step = (self._tonic_step + gen) % self._current_edo
        self._refresh_display()

    def action_step_gen_bwd(self):
        """Advance by the generating interval backward."""
        self._release_held()
        gen = self._current_steps[0]
        self._tonic_step = (self._tonic_step - gen) % self._current_edo
        self._refresh_display()

    def action_strum(self):
        """Strum scale notes with randomised order and humanised timing each press.

        Note order is chosen from musically meaningful patterns each time:
          - ascending  (root → top, most common)
          - descending (top → root)
          - inside-out (root, top, 2nd, 2nd-from-top, …)
          - skip-step  (every other degree then fill gaps — thirds-like motion)
          - cascade    (root, 5th-ish, 2nd, 6th-ish, 3rd, 7th-ish, 4th — wide leaps)

        Timing between each note varies by ±_STRUM_JITTER_MS so no two strums
        sound metronomic.  Velocity follows the position in the chosen order
        (low to high) regardless of pitch direction.
        """
        self._release_held()
        self._cancel_strum_gate()

        degrees = self._scale_degrees
        n = min(len(degrees), 7)
        if n == 0:
            return

        indices = list(range(n))

        # Build candidate orderings and pick one with weighted randomness.
        def _inside_out(idx_list):
            lo, hi = 0, len(idx_list) - 1
            result = []
            toggle = True
            while lo <= hi:
                result.append(idx_list[lo] if toggle else idx_list[hi])
                if toggle: lo += 1
                else: hi -= 1
                toggle = not toggle
            return result

        def _skip_step(idx_list):
            evens = idx_list[::2]
            odds  = idx_list[1::2]
            return evens + odds

        def _cascade(idx_list):
            # Interleave low and high halves: 0, mid, 1, mid+1, 2, …
            mid = len(idx_list) // 2
            lo, hi = idx_list[:mid], idx_list[mid:]
            result = []
            for a, b in zip(lo, hi):
                result += [a, b]
            if len(lo) > len(hi):
                result.append(lo[-1])
            return result

        patterns = [
            ("asc",       indices),
            ("asc",       indices),          # weighted 2× — most natural feel
            ("desc",      list(reversed(indices))),
            ("inside",    _inside_out(indices)),
            ("skip",      _skip_step(indices)),
            ("cascade",   _cascade(indices)),
        ]
        _, order = random.choice(patterns)

        # Build per-gap timings with jitter.
        gaps_ms = [
            _STRUM_BASE_MS + random.randint(-_STRUM_JITTER_MS, _STRUM_JITTER_MS)
            for _ in range(n - 1)
        ]

        # Cumulative delay for each note position in the chosen order.
        cumulative_ms = [0.0]
        for gap in gaps_ms:
            cumulative_ms.append(cumulative_ms[-1] + max(40, gap))  # floor at 40ms

        self._strum_notes = []
        self._strum_fire_timers = []

        for pos, deg_idx in enumerate(order):
            abs_step = self._tonic_step + degrees[deg_idx] + self._octave * self._current_edo
            midi_note, bend = _edo_step_to_midi_and_bend(abs_step, self._current_edo)
            # Velocity climbs with position in firing order (not pitch order).
            velocity = _STRUM_VEL_MIN + int(
                (_STRUM_VEL_MAX - _STRUM_VEL_MIN) * pos / max(1, n - 1)
            )
            delay_s = cumulative_ms[pos] / 1000.0

            self._strum_notes.append(midi_note)

            def _fire_note(mn=midi_note, bv=bend, vel=velocity):
                self.synth_engine.pitch_bend_change(bv)
                self.synth_engine.note_on(mn, vel)

            if pos == 0:
                _fire_note()
            else:
                # Store the timer handle so _cancel_strum_gate() can stop it
                # before it fires if a new strum or a mode switch arrives.
                timer_handle = self.set_timer(delay_s, _fire_note)
                self._strum_fire_timers.append(timer_handle)

        # Gate-off fires after the last note has had time to ring.
        total_delay_s = cumulative_ms[-1] / 1000.0 + _STRUM_GATE_S
        self._strum_gate_timer = self.set_timer(total_delay_s, self._release_strum)
        self._refresh_display()

    def action_toggle_mlt(self):
        """Toggle MLT-only filter for the mode catalog."""
        self._release_held()
        self._mlt_filter = not self._mlt_filter
        self._clamp_mode_index()
        self._scale_step = 0
        self._refresh_display()

    def action_toggle_reverse(self):
        """Flip keyboard direction: high keys play low pitches and vice versa."""
        self._release_all_midi()
        self._reversed = not self._reversed
        self._refresh_display()

    # ── Playback helpers ─────────────────────────────────────────────────────

    def _play_current_step(self, hold: bool = False):
        """Compute pitch for current scale step, set bend, trigger note."""
        if not hold:
            self._release_held()

        degrees = self._scale_degrees
        if not degrees or self._scale_step >= len(degrees):
            return

        abs_step = self._tonic_step + degrees[self._scale_step] + self._octave * self._current_edo
        midi_note, bend = _edo_step_to_midi_and_bend(abs_step, self._current_edo)

        self.synth_engine.pitch_bend_change(bend)
        self.synth_engine.note_on(midi_note, 85)
        self._held_note = midi_note
        self._held_bend = bend

        if not hold:
            # Short gate: 0.35 s
            self.set_timer(0.35, lambda: self._release_note(midi_note))

    def _release_held(self):
        """Release the currently held note, if any."""
        if self._held_note is not None:
            self.synth_engine.note_off(self._held_note, 0)
            self._held_note = None

    def _release_note(self, midi_note: int):
        """Release a specific note (only if it's still the held note)."""
        if self._held_note == midi_note:
            self._release_held()

    def _release_strum(self):
        """Release all strum notes (called by the gate-off timer on normal expiry)."""
        for mn in self._strum_notes:
            self.synth_engine.note_off(mn, 0)
        self._strum_notes = []
        self._strum_gate_timer = None
        self._strum_fire_timers = []  # all fire timers have already elapsed by now

    def _cancel_strum_gate(self):
        """Cancel all pending strum timers and release any strum notes immediately.

        Cancels both the gate-off timer AND every pending note-on fire timer.
        Cancelling only the gate-off timer leaves orphaned fire timers that
        trigger note-ons without a matching note-off, causing stuck voices.
        """
        # Cancel pending note-on fire timers first so no new notes are triggered.
        for t in self._strum_fire_timers:
            try:
                t.stop()
            except Exception:
                pass
        self._strum_fire_timers = []

        if self._strum_gate_timer is not None:
            self._strum_gate_timer.stop()
            self._strum_gate_timer = None

        for mn in self._strum_notes:
            self.synth_engine.note_off(mn, 0)
        self._strum_notes = []

    def _clamp_mode_index(self):
        """Keep mode index within the current catalog bounds."""
        catalog = self._catalog
        if self._mode_index >= len(catalog):
            self._mode_index = 0

    # ── Display rendering ────────────────────────────────────────────────────

    def _get_subtitle(self) -> str:
        return f"EDO-{self._current_edo}  |  {self._current_mode_name}"

    # -- Synth-style panel box helpers --

    def _sec_top(self, title: str) -> str:
        """Top border: ╭─ TITLE ──╮  matching synth mode visual language."""
        t = f" {title} "
        W = self._W + 2
        dashes = max(0, W - len(t))
        lp = max(1, dashes // 2)
        rp = max(1, dashes - lp)
        return f"[bold #a06000]╭{'─'*lp}{t}{'─'*rp}╮[/]"

    def _sec_bot(self) -> str:
        """Bottom border: ╰──╯"""
        return f"[bold #a06000]╰{'─'*(self._W+2)}╯[/]"

    def _sec_line(self, text: str, color: str = "#888888") -> str:
        """One interior row, content padded to _W visible chars."""
        W = self._W
        # Truncate to _W visible chars (text is plain, no embedded markup).
        display = text[:W].ljust(W)
        return f"[bold #a06000]│[/][{color}] {display} [/][bold #a06000]│[/]"

    def _sec_big(self, text: str, color: str = "#00ffff") -> str:
        """Two-line large value: spaced chars on one line + blank line below.

        Produces two rendered lines so callers count 2 rows from this call.
        """
        W = self._W
        spaced = " ".join(text)     # e.g. "24" → "2 4", "Rast" → "R a s t"
        spaced = spaced[:W].ljust(W)
        value_row = f"[bold #a06000]│[/][bold {color}] {spaced} [/][bold #a06000]│[/]"
        blank_row = self._sec_line("")
        return value_row + "\n" + blank_row

    def _sec_tag(self, label: str, active: bool) -> str:
        """Inline status tag: active = bright amber reverse, inactive = dim."""
        if active:
            return f"[bold #d79b00 reverse] {label} [/]"
        return f"[dim #444444] {label} [/]"

    def _sec_divider(self) -> str:
        """Thin horizontal divider row inside a panel."""
        return f"[bold #a06000]│{'─'*(self._W+2)}│[/]"

    # -- Top panel renderers (each produces exactly 13 lines: 1 top + 11 content + 1 bot) --

    def _render_edo_panel(self) -> str:
        """EDO selector panel — large EDO number, step size, nav hints."""
        edo = self._current_edo
        idx = self._edo_index
        step_cents = int(round(1200.0 / edo))
        lines = [
            self._sec_top("E D O"),
            self._sec_line(""),
            self._sec_big(str(edo), "#00ffff"),   # 2 rows (value + blank)
            self._sec_line(f"equal divisions", "#555555"),
            self._sec_divider(),
            self._sec_line(f"{idx+1} / {len(_EDO_CYCLE)}", "#888888"),
            self._sec_line(f"1 step = {step_cents}¢", "#666666"),
            self._sec_line(""),
            self._sec_line("[e] next  [E] prev", "#444444"),
            self._sec_line(""),
            self._sec_line(""),
            self._sec_bot(),
        ]
        return "\n".join(lines)

    def _render_scale_panel(self) -> str:
        """Scale / mode selector panel — scale name large, degree count, MLT badge."""
        catalog = self._catalog
        name = self._current_mode_name
        mlt = _is_mlt(self._current_steps)
        mlt_c = "#d79b00" if mlt else "#555555"
        mlt_label = "★ M L T" if mlt else "· · ·"
        # Shorten name to _W if long before spacing
        short = name[:self._W]
        lines = [
            self._sec_top("S C A L E"),
            self._sec_line(""),
            self._sec_big(short, "#00ffff"),       # 2 rows (value + blank)
            self._sec_line(f"{self._num_scale_notes} notes", "#888888"),
            self._sec_divider(),
            self._sec_line(f"{self._mode_index+1} / {len(catalog)} modes", "#666666"),
            self._sec_line(mlt_label, mlt_c),
            self._sec_line(""),
            self._sec_line("[j] prev  [k] next", "#444444"),
            self._sec_line(""),
            self._sec_line(""),
            self._sec_bot(),
        ]
        return "\n".join(lines)

    def _render_tonic_panel(self) -> str:
        """Tonic transposition panel — note name large, cents, nav hints."""
        edo = self._current_edo
        tonic_cents = int(round(1200.0 * self._tonic_step / edo))
        note_names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        semitone = int(round(tonic_cents / 100)) % 12
        tonic_name = note_names[semitone]
        lines = [
            self._sec_top("T O N I C"),
            self._sec_line(""),
            self._sec_big(tonic_name, "#00ffff"),  # 2 rows (value + blank)
            self._sec_line(f"{tonic_cents}¢  from C", "#888888"),
            self._sec_divider(),
            self._sec_line(f"step {self._tonic_step} / {edo}", "#666666"),
            self._sec_line(f"gen: [g/G]", "#555555"),
            self._sec_line(""),
            self._sec_line("[◄] flat  [►] sharp", "#444444"),
            self._sec_line(""),
            self._sec_line(""),
            self._sec_bot(),
        ]
        return "\n".join(lines)

    def _render_step_panel(self) -> str:
        """Current degree / cursor panel — degree number large, cents, octave."""
        degrees = self._scale_degrees
        step = self._scale_step
        n = self._num_scale_notes
        cents = int(round(1200.0 * degrees[step] / self._current_edo)) if degrees else 0
        oct_str = f"{self._octave:+d}" if self._octave != 0 else " 0"
        lines = [
            self._sec_top("D E G R E E"),
            self._sec_line(""),
            self._sec_big(f"{step+1}/{n}", "#00ffff"),  # 2 rows (value + blank)
            self._sec_line(f"{cents}¢ above tonic", "#888888"),
            self._sec_divider(),
            self._sec_line(f"octave: {oct_str}", "#666666"),
            self._sec_line("[o] down  [O] up", "#555555"),
            self._sec_line(""),
            self._sec_line("[▲] up  [▼] down", "#444444"),
            self._sec_line(""),
            self._sec_line(""),
            self._sec_bot(),
        ]
        return "\n".join(lines)

    def _render_status_panel(self) -> str:
        """Hold / MLT / Reverse / strum controls panel — flags as large toggle tags."""
        hold_c  = "#d79b00" if self._hold_on    else "#333333"
        mlt_c   = "#d79b00" if self._mlt_filter else "#333333"
        rev_c   = "#d79b00" if self._reversed   else "#333333"
        hold_label = "H O L D" if self._hold_on    else "h o l d"
        mlt_label  = "M L T"   if self._mlt_filter else "m l t"
        rev_label  = "R E V"   if self._reversed   else "r e v"
        lines = [
            self._sec_top("S T A T U S"),
            self._sec_line(""),
            self._sec_line(hold_label, hold_c),
            self._sec_line(mlt_label,  mlt_c),
            self._sec_line(rev_label,  rev_c),
            self._sec_divider(),
            self._sec_line("[spc] play note", "#555555"),
            self._sec_line("[↵] toggle hold", "#555555"),
            self._sec_line("[z] strum  [r] rev", "#444444"),
            self._sec_line("[m] MLT filter", "#444444"),
            self._sec_line(""),
            self._sec_bot(),
        ]
        return "\n".join(lines)

    # -- Ring / bottom panel renderer --

    def _render_ring_panel(self) -> str:
        """Large bottom panel: pitch ring visualization + degree table + intervals."""
        edo = self._current_edo
        degrees_set = set(self._scale_degrees)
        selected_abs = self._scale_degrees[self._scale_step] if self._scale_degrees else 0
        note_names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

        # ── Pitch ring ────────────────────────────────────────────────────
        # Small EDOs: each step is one symbol + space.
        # Large EDOs (>48): group by semitone boundaries with │ dividers.
        use_spaces = edo <= 48
        sep_every  = 12 if edo > 48 else 0

        ring_parts = []
        for i in range(edo):
            step_rel = (i - self._tonic_step) % edo
            if step_rel == 0:
                ch = "[bold #00ffff]◉[/]"
            elif step_rel == selected_abs:
                ch = "[bold #d79b00]♦[/]"
            elif step_rel in degrees_set:
                ch = "[bold #00cc44]●[/]"
            else:
                ch = "[#2a2a2a]·[/]"
            if sep_every and i > 0 and i % sep_every == 0:
                ring_parts.append("[#444444] │ [/]")
            ring_parts.append(ch)
            if use_spaces:
                ring_parts.append(" ")
        ring_str = "".join(ring_parts).rstrip()

        # ── Degree name table ─────────────────────────────────────────────
        degrees_list = self._scale_degrees
        note_parts = []
        for i, deg in enumerate(degrees_list):
            abs_step = self._tonic_step + deg + self._octave * self._current_edo
            midi_note, bend = _edo_step_to_midi_and_bend(abs_step, self._current_edo)
            name = note_names[midi_note % 12]
            oct_num = (midi_note // 12) - 1
            bend_cents = int(round((bend - 8192) / 8192.0 * _BEND_RANGE_SEMITONES * 100))
            bend_tag = f"{bend_cents:+d}¢" if abs(bend_cents) > 2 else ""
            label = f"{name}{oct_num}{bend_tag}"
            if i == self._scale_step:
                note_parts.append(f"[bold #d79b00 reverse] {label} [/]")
            elif i == 0:
                note_parts.append(f"[bold #00ffff]{label}[/]")
            else:
                note_parts.append(f"[#777777]{label}[/]")
        notes_str = "  ".join(note_parts)

        # ── Interval steps row ────────────────────────────────────────────
        steps = self._current_steps
        intervals = []
        for i, s in enumerate(steps):
            cents_val = int(round(1200.0 * s / edo))
            if i == self._scale_step:
                intervals.append(f"[bold #d79b00]{cents_val}¢[/]")
            else:
                intervals.append(f"[#555555]{cents_val}¢[/]")
        intervals_str = "  ·  ".join(intervals)

        # ── Absolute position indicator ───────────────────────────────────
        tonic_cents = int(round(1200.0 * self._tonic_step / edo))
        semitone = int(round(tonic_cents / 100)) % 12
        tonic_name = note_names[semitone]
        step_cents = int(round(1200.0 * (degrees_list[self._scale_step] if degrees_list else 0) / edo))
        mlt_badge = "  [bold #d79b00]★ MLT[/]" if _is_mlt(self._current_steps) else ""

        divider_a = f"[#3a3a3a]{'─' * 80}[/]"
        divider_b = f"[#2a2a2a]{'─' * 80}[/]"

        lines = [
            "",
            f"  [bold #a06000]╔{'═'*74}╗[/]",
            (f"  [bold #a06000]║[/]  [bold #a06000]P I T C H   R I N G[/]"
             f"   [#555555]EDO-{edo}[/]"
             f"   [#888888]{self._current_mode_name}[/]"
             f"{mlt_badge}"
             f"   [#555555]tonic: {tonic_name} ({tonic_cents}¢)[/]"
             f"  [bold #a06000]║[/]"),
            f"  [bold #a06000]╚{'═'*74}╝[/]",
            "",
            f"  {ring_str}",
            "",
            divider_a,
            "",
            f"  [#444444]degrees:[/]   {notes_str}",
            "",
            f"  [#444444]intervals:[/] {intervals_str}",
            "",
            f"  [#333333]deg {self._scale_step+1}  ·  {step_cents}¢ above tonic[/]",
        ]
        return "\n".join(lines)

    def _refresh_display(self):
        """Update all panel widgets to reflect current state."""
        if self._panel_edo:
            self._panel_edo.update(self._render_edo_panel())
        if self._panel_scale:
            self._panel_scale.update(self._render_scale_panel())
        if self._panel_tonic:
            self._panel_tonic.update(self._render_tonic_panel())
        if self._panel_step:
            self._panel_step.update(self._render_step_panel())
        if self._panel_status:
            self._panel_status.update(self._render_status_panel())
        if self._panel_ring:
            self._panel_ring.update(self._render_ring_panel())
