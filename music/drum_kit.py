# ABOUTME: The drum kit: the sound alternatives of every drum row, held in memory once generated.
# ABOUTME: The sounds come from music/drum_synth.py, so the kit needs no files.

from typing import List, Optional

import numpy as np

from music import drum_synth


class DrumKit:
    """Drum sounds, each generated when first needed and then kept."""

    sample_rate = drum_synth.SAMPLE_RATE

    def __init__(self, sounds: Optional[dict] = None):
        """sounds maps (row name, alternative index) to stereo samples already made."""
        self._sounds = dict(sounds or {})

    @classmethod
    def load(cls) -> "DrumKit":
        """Return the kit without generating any sound yet."""
        return cls()

    def prepare(self):
        """Generate every sound now, so playing never has to wait for one."""
        for slot in drum_synth.slots():
            for index in range(len(self.labels(slot))):
                self.sample(slot, index)

    def labels(self, slot: str) -> List[str]:
        """Names of the alternatives for a drum row."""
        return drum_synth.labels(slot)

    def level(self, slot: str, index: int = 0) -> float:
        """Playback gain of one alternative, applied after shaping so drive cannot undo it."""
        return drum_synth.level(slot, index)

    def sample(self, slot: str, index: int = 0) -> np.ndarray:
        """Stereo samples of one alternative; the index wraps around."""
        key = (slot, index % len(self.labels(slot)))
        if key not in self._sounds:
            self._sounds[key] = drum_synth.render(*key)
        return self._sounds[key]
