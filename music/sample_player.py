# ABOUTME: Shapes drum samples with tune, attack, decay, tone, drive and level controls.
# ABOUTME: SamplePlayer mixes triggered hits into audio buffers at exact positions, with choke groups.

from typing import Optional

import numpy as np
from scipy.signal import lfilter

CHOKE_SECONDS = 0.005
_DECAY_HOLD_SECONDS = 0.01
_DARKEST_HZ = 500.0
_BRIGHTEST_HZ = 18000.0
_PRESENCE_HZ = 3000.0


def _resample(data: np.ndarray, step: float) -> np.ndarray:
    """Read data every `step` input samples using Catmull-Rom interpolation."""
    length = max(1, int(round(len(data) / step)))
    positions = np.arange(length) * step
    base = np.minimum(positions.astype(np.int64), len(data) - 1)
    t = (positions - base).astype(np.float32)[:, np.newaxis]
    padded = np.concatenate((data[:1], data, np.zeros((2, data.shape[1]), dtype=data.dtype)))
    p0, p1, p2, p3 = (padded[base + k] for k in range(4))
    return p1 + 0.5 * t * (
        (p2 - p0)
        + t * ((2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) + t * (3.0 * (p1 - p2) + p3 - p0))
    )


def _lowpass(data: np.ndarray, cutoff: float, rate: float) -> np.ndarray:
    """One-pole low-pass filter along time."""
    alpha = 1.0 - np.exp(-2.0 * np.pi * min(cutoff, rate * 0.45) / rate)
    return lfilter([alpha], [1.0, alpha - 1.0], data, axis=0).astype(np.float32)


def shape_sample(data: np.ndarray, source_rate: float, output_rate: float, controls: dict) -> np.ndarray:
    """Return a stereo sample ready to play at output_rate; data itself is not modified.

    Controls, each optional and neutral by default:
        tune    semitones, -12 to 12
        attack  fade-in time in seconds
        decay   fraction of the sample that rings, 0.05 to 1.0
        tone    -1.0 darkest to 1.0 brightest
        drive   0.0 to 1.0 saturation
        level   0.0 to 1.0 volume
    """
    tune = float(controls.get("tune", 0.0))
    step = (source_rate / output_rate) * 2.0 ** (tune / 12.0)
    out = np.array(data, dtype=np.float32) if step == 1.0 else _resample(data, step).astype(np.float32)

    tone = float(controls.get("tone", 0.0))
    if tone < 0.0:
        cutoff = _BRIGHTEST_HZ * (_DARKEST_HZ / _BRIGHTEST_HZ) ** min(1.0, -tone)
        # Two poles give a clearly audible darkening
        out = _lowpass(_lowpass(out, cutoff, output_rate), cutoff, output_rate)
    elif tone > 0.0:
        highs = out - _lowpass(out, _PRESENCE_HZ, output_rate)
        out = out + np.float32(1.5 * min(1.0, tone)) * highs

    drive = float(controls.get("drive", 0.0))
    if drive > 0.0:
        gain = np.float32(1.0 + 5.0 * min(1.0, drive))
        out = np.tanh(out * gain) / np.tanh(gain)

    attack = int(float(controls.get("attack", 0.0)) * output_rate)
    if attack > 0:
        n = min(attack, len(out))
        out[:n] *= (np.arange(n, dtype=np.float32) / attack)[:, np.newaxis]

    decay = float(controls.get("decay", 1.0))
    if decay < 1.0:
        ringing = max(0.05, decay) * len(out)
        hold = int(_DECAY_HOLD_SECONDS * output_rate)
        tau = max(1.0, (ringing - hold) / 6.0)
        length = min(len(out), int(max(ringing, hold + tau)))
        out = out[:length]
        after = np.maximum(np.arange(length, dtype=np.float32) - hold, 0.0)
        envelope = np.exp(-after / np.float32(tau))
        # The last part reaches exact silence so the cut cannot click
        end = min(length, int(0.002 * output_rate))
        envelope[length - end:] *= np.linspace(1.0, 0.0, end, dtype=np.float32)
        out = out * envelope[:, np.newaxis]

    level = float(controls.get("level", 1.0))
    if level != 1.0:
        out = out * np.float32(level)
    return out


class _Hit:
    def __init__(self, data: np.ndarray, gain: float, offset: int, group):
        self.data = data
        self.gain = np.float32(gain)
        self.delay = offset                   # samples before the sound starts
        self.position = 0
        self.group = group
        self.fade_delay: Optional[int] = None  # samples before a choke starts
        self.fade_done = 0


class SamplePlayer:
    """Plays shaped samples; hits sharing a choke group cut each other off."""

    def __init__(self, sample_rate: float):
        self.fade_length = max(1, int(CHOKE_SECONDS * sample_rate))
        self._hits = []

    @property
    def active(self) -> bool:
        return bool(self._hits)

    def trigger(self, data: np.ndarray, gain: float, offset: int = 0, group=None):
        """Start data `offset` samples into the next mixed buffer."""
        if group is not None:
            for hit in self._hits:
                if hit.group == group:
                    self._choke(hit, offset)
        self._hits.append(_Hit(data, gain, offset, group))

    def stop_all(self):
        """Fade out everything that is sounding and drop hits that have not started."""
        self._hits = [hit for hit in self._hits if hit.delay == 0]
        for hit in self._hits:
            self._choke(hit, 0)

    def _choke(self, hit: _Hit, offset: int):
        if hit.fade_delay is None or offset < hit.fade_delay:
            hit.fade_delay = offset

    def mix(self, left: np.ndarray, right: np.ndarray):
        """Add the sounding hits to a pair of buffers and advance them by one buffer."""
        frames = len(left)
        still_playing = []
        for hit in self._hits:
            if self._mix_hit(hit, left, right, frames):
                still_playing.append(hit)
        self._hits = still_playing

    def _mix_hit(self, hit: _Hit, left: np.ndarray, right: np.ndarray, frames: int) -> bool:
        """Mix one hit and return True while it has more to play."""
        start = min(hit.delay, frames)
        hit.delay -= start
        count = min(frames - start, len(hit.data) - hit.position)
        end = start + max(0, count)
        block = hit.data[hit.position:hit.position + end - start] * hit.gain
        hit.position += end - start
        finished = hit.position >= len(hit.data)

        if hit.fade_delay is not None:
            fade_from = max(0, hit.fade_delay - start)      # index inside block
            hit.fade_delay = max(0, hit.fade_delay - frames)
            if fade_from < len(block):
                steps = hit.fade_done + np.arange(1, len(block) - fade_from + 1, dtype=np.float32)
                ramp = np.clip(1.0 - steps / self.fade_length, 0.0, 1.0)
                block[fade_from:] *= ramp[:, np.newaxis]
                hit.fade_done += len(block) - fade_from
                finished = finished or hit.fade_done >= self.fade_length

        left[start:end] += block[:, 0]
        right[start:end] += block[:, 1]
        return not finished
