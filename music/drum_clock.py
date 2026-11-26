# ABOUTME: Sample-accurate step clock for the Tambor drum machine, advanced by the audio thread.
# ABOUTME: Holds the sequence being played and reports which hits fall inside each audio buffer.

import random


class DrumClock:
    """Counts samples and fires sequencer steps at their exact position.

    A sequence is a dict:
        pattern       identifier of the pattern, so a change can drop a running fill
        steps         one list of (note, velocity, params) hits per step
        fill          alternative steps played every other cycle, or None
        step_seconds  duration of one step
        humanize      random velocity variation ratio, 0.0 for none
    """

    def __init__(self):
        self.playing = False
        self.step = 0
        self.ticks = 0          # steps fired since creation; lets readers spot a new step
        self._sequence = None
        self._next_at = 0.0     # samples from the start of the next buffer to the next step
        self._fill_queued = False
        self._in_fill = False

    def start(self, sequence: dict):
        """Play sequence from its first step, which falls on the next buffer's first sample."""
        self._sequence = sequence
        self.playing = True
        self.step = -1
        self._next_at = 0.0
        self._fill_queued = False
        self._in_fill = False

    def update(self, sequence: dict):
        """Replace the sequence without disturbing the beat."""
        if self._sequence is not None and sequence['pattern'] != self._sequence['pattern']:
            self._fill_queued = False
            self._in_fill = False
        self._sequence = sequence

    def stop(self):
        self.playing = False

    def advance(self, frame_count: int, sample_rate: float) -> list:
        """Move frame_count samples forward.

        Returns (offset, step, hits) for each step starting inside this buffer. The
        fractional part of every step position is carried over, so the tempo does not drift.
        """
        if not self.playing or not self._sequence['steps']:
            return []

        fired = []
        step_samples = max(1.0, self._sequence['step_seconds'] * sample_rate)
        # The tolerance keeps float error from pushing a step into the following buffer
        while self._next_at < frame_count - 1e-6:
            offset = max(0, min(frame_count - 1, int(self._next_at + 1e-6)))
            fired.append((offset, *self._next_step()))
            self._next_at += step_samples
        self._next_at -= frame_count
        return fired

    def _next_step(self) -> tuple:
        """Move to the following step and return (step, hits)."""
        steps = self._sequence['steps']
        fill = self._sequence['fill']
        self.step = (self.step + 1) % len(steps)
        self.ticks += 1

        # A fill queued on a cycle's last step replaces the whole following cycle
        if self.step == len(steps) - 1 and fill and not self._in_fill:
            self._fill_queued = True
        if self.step == 0:
            if self._in_fill:
                self._in_fill = False
                self._fill_queued = False
            elif self._fill_queued:
                self._in_fill = True

        playing = fill if self._in_fill and fill else steps
        hits = playing[self.step] if self.step < len(playing) else []

        amount = self._sequence['humanize']
        if amount > 0:
            hits = [(note, self._humanize(velocity, amount), params)
                    for note, velocity, params in hits]
        return self.step, hits

    @staticmethod
    def _humanize(velocity: int, amount: float) -> int:
        """Vary a velocity by up to the given ratio."""
        return max(1, min(127, int(velocity + random.uniform(-amount, amount) * velocity)))
