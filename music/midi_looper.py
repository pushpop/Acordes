# ABOUTME: Sample-accurate MIDI looper that runs on the audio thread.
# ABOUTME: Records, quantizes to full bars, overdubs, and replays MIDI events in a loop.

import math


class MidiLooper:
    """MIDI looper driven from the audio callback.

    All methods that mutate state are called exclusively from the audio thread
    (via _process_midi_events and process_buffer). The UI thread only sends
    commands through the engine event queue and reads state from shared memory.

    States:
      stopped     -- no loop recorded or loop cleared
      armed       -- waiting for first note_on before starting to record
      recording   -- capturing incoming MIDI events; position advances each buffer
      playing     -- replaying recorded events; position wraps at loop end
      overdubbing -- playing back existing events AND capturing new ones
    """

    STATE_STOPPED     = "stopped"
    STATE_ARMED       = "armed"
    STATE_RECORDING   = "recording"
    STATE_PLAYING     = "playing"
    STATE_OVERDUBBING = "overdubbing"

    def __init__(self, sample_rate: int):
        self.sample_rate  = sample_rate
        self.state        = self.STATE_STOPPED

        # Recorded events: list of (sample_offset_in_loop, event_dict)
        self._events: list = []

        # Loop length in samples (0 until first recording completes)
        self.loop_length_samples: int = 0

        # Pre-set bar count cap chosen by the user before recording
        self.loop_bars: int = 2

        # Time signature numerator (beats per bar); updated from engine
        self.beats_per_bar: int = 4

        # BPM synced from arp_bpm / config each buffer
        self.bpm: float = 120.0

        # Current playback head position in samples (0..loop_length_samples-1)
        self.playback_pos: int = 0

        # Sample position where the current recording pass started
        # (relative to playback_pos at the moment REC was pressed)
        self._record_start_pos: int = 0

        # UI-readable position info written each buffer (safe to read from UI thread
        # between callbacks because these are plain Python ints — atomic under the GIL)
        self.current_bar:  int = 0
        self.current_beat: int = 0
        self.total_bars:   int = 0

    # ── Derived timing ────────────────────────────────────────────────────────

    def samples_per_bar(self) -> int:
        """Samples in one bar at current BPM and time signature."""
        return max(1, int((60.0 / max(self.bpm, 1.0)) * self.beats_per_bar * self.sample_rate))

    def max_loop_samples(self) -> int:
        """Hard cap on recording length in samples."""
        return self.samples_per_bar() * self.loop_bars

    # ── Command handlers (called from audio thread) ───────────────────────────

    def cmd_record(self):
        """Arm for recording or begin overdubbing if a loop already exists.

        From stopped: enters armed state; recording begins only when the first
        note_on arrives (so the loop starts exactly on the first played note).
        From playing: enters overdubbing immediately (loop already timed).
        """
        if self.state == self.STATE_STOPPED:
            self._events             = []
            self.loop_length_samples = 0
            self.playback_pos        = 0
            self._record_start_pos   = 0
            self.state               = self.STATE_ARMED
        elif self.state == self.STATE_PLAYING:
            self._record_start_pos = self.playback_pos
            self.state             = self.STATE_OVERDUBBING

    def cmd_stop(self):
        """Cancel arm, stop recording (quantizing to full bar), or stop playback."""
        if self.state == self.STATE_ARMED:
            self.state = self.STATE_STOPPED
            return
        if self.state == self.STATE_RECORDING:
            recorded = self.playback_pos - self._record_start_pos
            if recorded <= 0:
                self.state = self.STATE_STOPPED
                return
            spb  = self.samples_per_bar()
            bars = math.ceil(recorded / spb)
            bars = max(1, min(bars, self.loop_bars))
            self.loop_length_samples = spb * bars
            self.total_bars          = bars
            # Wrap playback head into the new loop boundary
            self.playback_pos        = self.playback_pos % self.loop_length_samples
            self.state               = self.STATE_PLAYING
        elif self.state == self.STATE_OVERDUBBING:
            self.state = self.STATE_PLAYING
        elif self.state == self.STATE_PLAYING:
            self.state = self.STATE_STOPPED

    def cmd_play(self):
        """Start playback if a loop exists and we are stopped."""
        if self.state == self.STATE_STOPPED and self.loop_length_samples > 0:
            self.state = self.STATE_PLAYING

    def cmd_go_to_start(self):
        """Reset playback head to bar 1 beat 1."""
        self.playback_pos = 0
        self._update_position()

    def cmd_clear(self):
        """Erase all events and reset to stopped state."""
        self._events             = []
        self.loop_length_samples = 0
        self.playback_pos        = 0
        self.total_bars          = 0
        self.current_bar         = 0
        self.current_beat        = 0
        self.state               = self.STATE_STOPPED

    def cmd_set_bars(self, bars: int):
        """Update the pre-set bar count cap (1, 2, 4, or 8)."""
        self.loop_bars = max(1, int(bars))

    # ── Recording input ───────────────────────────────────────────────────────

    def record_event(self, offset_in_buffer: int, event: dict):
        """Capture a MIDI event arriving during this buffer.

        offset_in_buffer: sample index within the current buffer (0-based).
        event: dict with keys 'type', 'note', 'velocity' (same format as the
               engine event queue).

        When armed, a note_on transitions the looper into active recording so
        the loop starts exactly on the first played note.
        """
        if self.state == self.STATE_ARMED:
            if event.get('type') == 'note_on':
                # First note: start recording now, time-stamp from this buffer offset.
                self.playback_pos      = 0
                self._record_start_pos = 0
                self.state             = self.STATE_RECORDING
                self._events.append((0, dict(event)))
            return

        if self.state not in (self.STATE_RECORDING, self.STATE_OVERDUBBING):
            return
        pos = self.playback_pos + offset_in_buffer
        if self.loop_length_samples > 0:
            pos = pos % self.loop_length_samples
        self._events.append((pos, dict(event)))

    # ── Per-buffer processing (called from _audio_callback) ───────────────────

    def process_buffer(self, frame_count: int, bpm: float) -> list:
        """Advance the looper by frame_count samples and return events to fire.

        bpm: current BPM from the engine (arp_bpm); kept in sync each buffer.

        Returns a list of (sample_offset_in_buffer, event_dict) pairs for events
        that fall inside [playback_pos, playback_pos + frame_count). The caller
        fires these exactly like incoming MIDI events.
        """
        self.bpm = bpm

        if self.state == self.STATE_ARMED:
            # Waiting for first note; position does not advance yet.
            return []

        if self.state == self.STATE_RECORDING:
            # During recording, advance position; auto-stop at the bar cap.
            self.playback_pos += frame_count
            if self.playback_pos >= self.max_loop_samples():
                self.cmd_stop()
            else:
                self._update_position()
            return []

        if self.state not in (self.STATE_PLAYING, self.STATE_OVERDUBBING):
            return []

        if self.loop_length_samples <= 0:
            return []

        to_fire: list = []
        pos = self.playback_pos
        end = pos + frame_count
        loop = self.loop_length_samples

        for (ev_pos, ev) in self._events:
            if pos <= ev_pos < end:
                # Event falls within this buffer without wrapping
                to_fire.append((ev_pos - pos, ev))
            elif end > loop:
                # Buffer crosses the loop boundary; check wrapped portion
                wrapped_end = end - loop
                if ev_pos < wrapped_end:
                    to_fire.append((loop - pos + ev_pos, ev))

        self.playback_pos = end % loop
        self._update_position()
        return to_fire

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _update_position(self):
        """Recompute current_bar and current_beat from playback_pos.

        During recording, loop_length_samples is 0 (finalized only when
        recording stops), so we use max_loop_samples() as the denominator
        so the playhead and bar/beat counters advance visibly while recording.
        """
        if self.state == self.STATE_RECORDING:
            spb = self.samples_per_bar()
            spp = max(1, spb // max(1, self.beats_per_bar))
            self.current_bar  = self.playback_pos // spb
            self.current_beat = (self.playback_pos % spb) // spp
            return
        if self.loop_length_samples <= 0:
            self.current_bar  = 0
            self.current_beat = 0
            return
        spb = self.samples_per_bar()
        spp = max(1, spb // max(1, self.beats_per_bar))
        self.current_bar  = self.playback_pos // spb
        self.current_beat = (self.playback_pos % spb) // spp
