# ABOUTME: Sampled drum kit: maps drum rows to sample alternatives and converts WAVs to one data file.
# ABOUTME: Build the kit with: uv run python -m music.drum_kit tools/909 kits/909.npz

import sys
import wave
from math import gcd
from pathlib import Path
from typing import List, Optional

import numpy as np
from scipy.signal import resample_poly

KIT_SAMPLE_RATE = 48000
DEFAULT_SOURCE = "tools/909"
DEFAULT_KIT = str(Path(__file__).resolve().parent.parent / "kits" / "909.npz")
END_FADE_SECONDS = 0.002

# Alternatives for each drum row as (label, source file); the first one is the default.
_TOM_LOW = ("Tom 01", "Tom 909 Standard Vinyl 01.wav")
_TOM_MID = ("Tom 02", "Tom 909 Standard Vinyl 02.wav")
_TOM_HIGH = ("Tom 03", "Tom 909 Standard Vinyl 03.wav")

SLOT_SAMPLES = {
    "Kick": [
        ("Drive 02", "BD 909 Drive Vinyl 02.wav"),
        ("Drive 04", "BD 909 Drive Vinyl 04.wav"),
        ("Tape", "BD 909 Tape Vinyl.wav"),
    ],
    "Snare": [
        ("Standard 01", "SD 909 Standard Vinyl 01.wav"),
        ("Standard 04", "SD 909 Standard Vinyl 04.wav"),
    ],
    "Closed HH": [
        ("Dark", "HH 909 Dark CH Vinyl.wav"),
        ("Dust", "HH 909 Dust CH Vinyl.wav"),
        ("Sharp", "HH 909 Sharp CH Vinyl.wav"),
    ],
    "Open HH": [
        ("Dark", "HH 909 Dark OH Vinyl.wav"),
        ("Short", "HH 909 Short OH Vinyl.wav"),
    ],
    "Clap": [
        ("Snappy", "Clap 909 Snappy Vinyl.wav"),
    ],
    "Tom Hi": [_TOM_HIGH, _TOM_MID, _TOM_LOW],
    "Tom Mid": [_TOM_MID, _TOM_HIGH, _TOM_LOW],
    "Tom Low": [_TOM_LOW, _TOM_MID, _TOM_HIGH],
    "Ride": [("Ride 01", "Ride 909 Standard Vinyl 01.wav")],
    "Rim": [("Rim 02", "Rim 909 Standard Vinyl 02.wav")],
}


def _read_wav(path: Path) -> tuple:
    """Return (stereo float32 samples, sample rate) of a 16 or 24-bit PCM WAV."""
    with wave.open(str(path), "rb") as f:
        channels, width, rate = f.getnchannels(), f.getsampwidth(), f.getframerate()
        raw = f.readframes(f.getnframes())
    if width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 3:
        parts = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        values = parts[:, 0] | (parts[:, 1] << 8) | (parts[:, 2] << 16)
        values[values >= 1 << 23] -= 1 << 24
        data = values.astype(np.float32) / float(1 << 23)
    else:
        raise ValueError(f"{path.name}: only 16 and 24-bit WAV files are supported")
    data = data.reshape(-1, channels)
    if channels == 1:
        data = np.repeat(data, 2, axis=1)
    return data[:, :2], rate


def _convert(path: Path) -> np.ndarray:
    """Read one WAV and return it at the kit sample rate with a click-free end."""
    data, rate = _read_wav(path)
    if rate != KIT_SAMPLE_RATE:
        common = gcd(KIT_SAMPLE_RATE, rate)
        data = resample_poly(data, KIT_SAMPLE_RATE // common, rate // common, axis=0)
    data = np.array(data, dtype=np.float32)
    fade = min(len(data), int(END_FADE_SECONDS * KIT_SAMPLE_RATE))
    data[len(data) - fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, np.newaxis]
    return data


def build_kit(source_dir, kit_path):
    """Convert the WAV files in source_dir into one kit data file."""
    source_dir, kit_path = Path(source_dir), Path(kit_path)
    names = sorted({name for entries in SLOT_SAMPLES.values() for _, name in entries})
    missing = [name for name in names if not (source_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing in {source_dir}: {', '.join(missing)}")
    kit_path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {name: _convert(source_dir / name) for name in names}
    with open(kit_path, "wb") as f:
        np.savez(f, **arrays)


class DrumKit:
    """Samples of a converted kit, held in memory."""

    sample_rate = KIT_SAMPLE_RATE

    def __init__(self, arrays: dict):
        self._arrays = arrays

    @classmethod
    def load(cls, kit_path=None) -> Optional["DrumKit"]:
        """Return the kit, or None if the file is absent or incomplete."""
        try:
            with np.load(kit_path or DEFAULT_KIT) as stored:
                arrays = {name: stored[name] for name in stored.files}
        except (OSError, ValueError):
            return None
        needed = {name for entries in SLOT_SAMPLES.values() for _, name in entries}
        return cls(arrays) if needed <= set(arrays) else None

    def labels(self, slot: str) -> List[str]:
        """Names of the alternatives for a drum row."""
        return [label for label, _ in SLOT_SAMPLES[slot]]

    def sample(self, slot: str, index: int = 0) -> np.ndarray:
        """Stereo samples of one alternative; the index wraps around."""
        entries = SLOT_SAMPLES[slot]
        return self._arrays[entries[index % len(entries)][1]]


def main(argv: list) -> int:
    source = argv[0] if argv else DEFAULT_SOURCE
    target = argv[1] if len(argv) > 1 else DEFAULT_KIT
    try:
        build_kit(source, target)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Kit written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
