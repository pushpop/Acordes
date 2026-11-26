# ABOUTME: Generates 909-style drum sounds from code: oscillators, envelopes and seeded noise.
# ABOUTME: Write audition files with: uv run python -m music.drum_synth tools

import sys
import wave
import zlib
from pathlib import Path
from typing import List

import numpy as np
from scipy.signal import butter, sosfilt

from music.sample_player import SamplePlayer

SAMPLE_RATE = 48000
PEAK = 0.9
_END_FADE_SECONDS = 0.005
_AUDITION_BPM = 120
_AUDITION_BEATS = 4

# Kick alternatives as (label, settings); the first one is the default.
#   length       seconds
#   start, end   pitch in Hz at the start of the sweep and where it settles
#   sweep        seconds for the pitch to cover most of the drop
#   hold, decay  seconds at full level, then the time constant of the fall
#   drive        how far the sine is pushed into saturation
#   click        level of the beater click
_KICKS = [
    ("Punch", dict(length=0.65, start=230.0, end=52.0, sweep=0.022,
                   hold=0.025, decay=0.11, drive=1.6, click=0.35)),
    ("Long", dict(length=1.7, start=170.0, end=48.0, sweep=0.030,
                  hold=0.040, decay=0.32, drive=1.2, click=0.20)),
    ("Hard", dict(length=0.8, start=300.0, end=55.0, sweep=0.018,
                  hold=0.030, decay=0.14, drive=3.5, click=0.55)),
]


# Snare alternatives.
#   low, high    pitches in Hz of the two body oscillators
#   body         time constant of the body
#   noise        level of the noise
#   tail, snap   time constants of the darker and the brighter noise
#   brightness   cutoff in Hz of the brighter noise
_SNARES = [
    ("Tight", dict(length=0.45, low=190.0, high=340.0, body=0.045, noise=0.8,
                   tail=0.065, snap=0.045, brightness=3000.0)),
    ("Fat", dict(length=0.8, low=160.0, high=285.0, body=0.085, noise=0.7,
                 tail=0.130, snap=0.070, brightness=2200.0)),
]

# Tom pitches in Hz, with the time constant of the standard length
_TOM_PITCHES = {"Tom Hi": (165.0, 0.10), "Tom Mid": (125.0, 0.12), "Tom Low": (92.0, 0.14)}
_LONG_TOM = 2.4  # how much longer the long toms ring

# Clap alternatives.
#   tail   time constant of the noise after the bursts
#   wide   different noise on each side
_CLAPS = [
    ("Standard", dict(length=0.6, tail=0.085, wide=False)),
    ("Wide", dict(length=0.9, tail=0.140, wide=True)),
]
_CLAP_SPACING = 0.011  # seconds between bursts


# Hi-hat and ride alternatives.
#   low, high    range in Hz of the metal partials
#   cutoff       high-pass frequency in Hz
#   decay        time constant of the fall
_CLOSED_HATS = [
    ("Dark", dict(length=0.22, low=3500.0, high=11000.0, cutoff=5500.0, decay=0.022)),
    ("Bright", dict(length=0.22, low=6000.0, high=16000.0, cutoff=8500.0, decay=0.022)),
]
_OPEN_HATS = [
    ("Dark", dict(length=1.1, low=3500.0, high=11000.0, cutoff=5500.0, decay=0.19)),
    ("Bright", dict(length=1.1, low=6000.0, high=16000.0, cutoff=8500.0, decay=0.19)),
]


def _times(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE


def _noise(name: str, length: int) -> np.ndarray:
    """White noise that is the same every time for a given name."""
    return np.random.default_rng(zlib.crc32(name.encode())).uniform(-1.0, 1.0, length)


def _filtered(data: np.ndarray, kind: str, cutoff, order: int = 2) -> np.ndarray:
    """Butterworth filter; cutoff is a frequency, or a pair for a band."""
    sos = butter(order, cutoff, btype=kind, fs=SAMPLE_RATE, output="sos")
    return sosfilt(sos, data)


def _kick(name: str, length, start, end, sweep, hold, decay, drive, click) -> np.ndarray:
    """A sine that drops quickly in pitch, lightly saturated, with a short click."""
    t = _times(length)
    frequency = end + (start - end) * np.exp(-t / sweep)
    phase = 2.0 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    # The sine starts at zero, so the body needs no fade-in
    body = np.tanh(drive * np.sin(phase - phase[0])) / np.tanh(drive)
    body *= np.exp(-np.maximum(t - hold, 0.0) / decay)

    tick = _filtered(_noise(name, len(t)), "bandpass", (900.0, 6000.0))
    tick *= np.exp(-t / 0.0025) * np.minimum(t / 0.0003, 1.0)
    return body + click * tick


def _sweep(t: np.ndarray, start: float, end: float, seconds: float) -> np.ndarray:
    """Phase of an oscillator whose pitch falls from start to end, beginning at zero."""
    frequency = end + (start - end) * np.exp(-t / seconds)
    phase = 2.0 * np.pi * np.cumsum(frequency) / SAMPLE_RATE
    return phase - phase[0]


def _onset(t: np.ndarray, seconds: float = 0.0003) -> np.ndarray:
    """A very short fade-in that keeps noise from starting with a jump."""
    return np.minimum(t / seconds, 1.0)


def _snare(name: str, length, low, high, body, noise, tail, snap, brightness) -> np.ndarray:
    """Two falling oscillators for the shell and two bands of noise for the wires."""
    t = _times(length)
    shell = np.sin(_sweep(t, low * 1.6, low, 0.012)) * np.exp(-t / body)
    shell += 0.5 * np.sin(_sweep(t, high * 1.4, high, 0.010)) * np.exp(-t / (body * 0.7))

    hiss = _noise(name, len(t))
    wires = _filtered(hiss, "bandpass", (700.0, 7000.0)) * np.exp(-t / tail)
    wires += _filtered(hiss, "highpass", brightness) * np.exp(-t / snap)
    return np.tanh(1.3 * (shell + noise * wires * _onset(t)))


def _tom(name: str, length, pitch, decay) -> np.ndarray:
    """Three falling oscillators, the higher ones dying sooner, with a breath of noise."""
    t = _times(length)
    tone = np.zeros(len(t))
    for ratio, level, shortening in ((1.0, 1.0, 1.0), (1.5, 0.35, 0.55), (2.2, 0.15, 0.35)):
        phase = _sweep(t, pitch * ratio * 1.5, pitch * ratio, 0.025)
        tone += level * np.sin(phase) * np.exp(-t / (decay * shortening))
    stick = _filtered(_noise(name, len(t)), "bandpass", (500.0, 5000.0))
    stick *= np.exp(-t / 0.012) * _onset(t)
    return np.tanh(tone + 0.2 * stick)


def _rim(name: str, length) -> np.ndarray:
    """Three very short resonances, clipped and thinned."""
    t = _times(length)
    ring = np.zeros(len(t))
    for pitch, level, decay in ((480.0, 0.7, 0.006), (1050.0, 1.0, 0.005), (1750.0, 0.6, 0.003)):
        ring += level * np.sin(2.0 * np.pi * pitch * t) * np.exp(-t / decay)
    ring += 0.3 * _noise(name, len(t)) * np.exp(-t / 0.001)
    return _filtered(np.tanh(2.5 * ring * _onset(t, 0.0002)), "highpass", 300.0)


def _metallic_rim(name: str, length) -> np.ndarray:
    """Clashing high resonances that ring, with a sharp strike."""
    t = _times(length)
    ring = np.zeros(len(t))
    for pitch, level, decay in ((845.0, 0.8, 0.030), (1370.0, 1.0, 0.038), (2215.0, 0.8, 0.032),
                                (3170.0, 0.55, 0.022), (4620.0, 0.35, 0.014)):
        ring += level * np.sin(2.0 * np.pi * pitch * t) * np.exp(-t / decay)
    ring += 0.8 * _noise(name, len(t)) * np.exp(-t / 0.0006)
    return _filtered(np.tanh(0.9 * ring * _onset(t, 0.0001)), "highpass", 600.0)


def _six_bit(data: np.ndarray) -> np.ndarray:
    """Scale to full range and keep six bits, the grain of early digital cymbals."""
    return np.round(data / np.abs(data).max() * 31.0) / 31.0


def _metal(name: str, t: np.ndarray, low: float, high: float, count: int) -> np.ndarray:
    """Many unrelated tones, which together sound like struck metal."""
    random = np.random.default_rng(zlib.crc32(f"{name} metal".encode()))
    pitches = np.exp(random.uniform(np.log(low), np.log(high), count))
    phases = random.uniform(0.0, 2.0 * np.pi, count)
    total = np.zeros(len(t))
    for pitch, phase in zip(pitches, phases):
        total += np.sin(2.0 * np.pi * pitch * t + phase)
    return total / np.sqrt(count)


def _hat(name: str, length, low, high, cutoff, decay) -> np.ndarray:
    """Metal tones and noise in six bits, shaped by a falling envelope."""
    t = _times(length)
    source = _six_bit(_metal(name, t, low, high, 40) + 0.5 * _noise(name, len(t)))
    envelope = (0.8 * np.exp(-t / decay) + 0.2 * np.exp(-t / (decay * 0.3))) * _onset(t)
    return _filtered(source, "highpass", cutoff, order=4) * envelope


def _ride(name: str, length, decay) -> np.ndarray:
    """A clear ping over a long wash of metal."""
    t = _times(length)
    wash = _metal(name, t, 2500.0, 12000.0, 70) + 0.25 * _noise(name, len(t))
    wash = _filtered(_six_bit(wash), "highpass", 3000.0)
    wash *= 0.7 * np.exp(-t / decay) + 0.3 * np.exp(-t / 0.05)
    ping = np.zeros(len(t))
    for pitch, level in ((3140.0, 1.0), (4220.0, 0.7), (5370.0, 0.5)):
        ping += level * np.sin(2.0 * np.pi * pitch * t)
    ping *= 0.22 * np.exp(-t / (decay * 0.7))
    return (wash + ping) * _onset(t)


def _clap_side(name: str, t: np.ndarray, tail: float) -> np.ndarray:
    """Three quick noise bursts and a fourth that rings on."""
    envelope = np.zeros(len(t))
    for n in range(4):
        since = t - n * _CLAP_SPACING
        fall = tail if n == 3 else 0.0025
        envelope += np.where(since >= 0.0, np.exp(-np.maximum(since, 0.0) / fall)
                             * _onset(since), 0.0) * (0.6 if n == 3 else 1.0)
    return _filtered(_noise(name, len(t)), "bandpass", (850.0, 2600.0)) * envelope


def _clap(name: str, length, tail, wide) -> np.ndarray:
    t = _times(length)
    if not wide:
        return _clap_side(name, t, tail)
    return np.stack([_clap_side(f"{name} {side}", t, tail) for side in ("left", "right")], axis=1)


_SOUNDS = {
    "Kick": [(label, _kick, settings) for label, settings in _KICKS],
    "Snare": [(label, _snare, settings) for label, settings in _SNARES],
    "Closed HH": [(label, _hat, settings) for label, settings in _CLOSED_HATS],
    "Open HH": [(label, _hat, settings) for label, settings in _OPEN_HATS],
    "Clap": [(label, _clap, settings) for label, settings in _CLAPS],
    **{
        slot: [
            ("Standard", _tom, dict(length=decay * 6, pitch=pitch, decay=decay)),
            ("Long", _tom, dict(length=decay * _LONG_TOM * 6, pitch=pitch,
                                decay=decay * _LONG_TOM)),
        ]
        for slot, (pitch, decay) in _TOM_PITCHES.items()
    },
    "Rim": [
        ("Standard", _rim, dict(length=0.08)),
        ("Metallic", _metallic_rim, dict(length=0.25)),
    ],
    "Ride": [("Standard", _ride, dict(length=2.8, decay=0.50))],
}


def _finish(sound: np.ndarray) -> np.ndarray:
    """Fade the end to silence, set the peak level and return stereo float32.

    sound is one channel, or two channels side by side.
    """
    if sound.ndim == 1:
        sound = np.repeat(sound[:, np.newaxis], 2, axis=1)
    fade = int(_END_FADE_SECONDS * SAMPLE_RATE)
    sound[-fade:] *= np.linspace(1.0, 0.0, fade)[:, np.newaxis]
    sound *= PEAK / np.abs(sound).max()
    return sound.astype(np.float32)


def slots() -> List[str]:
    """Names of the drum rows that have sounds."""
    return list(_SOUNDS)


def labels(slot: str) -> List[str]:
    """Names of the alternatives for a drum row."""
    return [label for label, _, _ in _SOUNDS[slot]]


def render(slot: str, index: int = 0) -> np.ndarray:
    """Stereo samples of one alternative; the index wraps around."""
    entries = _SOUNDS[slot]
    label, build, settings = entries[index % len(entries)]
    return _finish(build(f"{slot} {label}", **settings))


def _audition(data: np.ndarray) -> np.ndarray:
    """Four beats of one sound, each hit cutting off the previous one as in Tambor."""
    beat = SAMPLE_RATE * 60 // _AUDITION_BPM
    left = np.zeros(beat * _AUDITION_BEATS, dtype=np.float32)
    right = np.zeros_like(left)
    player = SamplePlayer(SAMPLE_RATE)
    for n in range(_AUDITION_BEATS):
        player.trigger(data, 1.0, group="audition")
        part = slice(n * beat, (n + 1) * beat)
        player.mix(left[part], right[part])
    return np.stack((left, right), axis=1)


def write_auditions(folder) -> List[Path]:
    """Write one WAV per sound into folder, for listening."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for slot in _SOUNDS:
        for index, label in enumerate(labels(slot)):
            path = folder / f"audition_{slot}_{label}.wav".lower().replace(" ", "_")
            pcm = (np.clip(_audition(render(slot, index)), -1.0, 1.0) * 32767).astype("<i2")
            with wave.open(str(path), "wb") as f:
                f.setnchannels(2)
                f.setsampwidth(2)
                f.setframerate(SAMPLE_RATE)
                f.writeframes(pcm.tobytes())
            written.append(path)
    return written


def main(argv: list) -> int:
    for path in write_auditions(argv[0] if argv else "tools"):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
