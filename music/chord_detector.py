"""Chord recognition using unified ChordLibrary."""
from typing import Set, List, Optional
from music.chord_library import ChordLibrary


class ChordDetector:
    """Detects chords from MIDI note numbers using the unified ChordLibrary.

    Uses ChordLibrary as the authoritative source of chord definitions,
    ensuring consistent chord detection across all modes (Piano, Compendium, etc).
    """

    # MIDI note 60 = C4 (middle C)
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    def __init__(self, chord_library: Optional[ChordLibrary] = None):
        """Initialize ChordDetector with optional ChordLibrary.

        Args:
            chord_library: Optional ChordLibrary instance. If not provided,
                          a new one will be created.
        """
        self.chord_library = chord_library or ChordLibrary()

    def midi_to_note_name(self, midi_note: int) -> str:
        """Convert MIDI note number to note name with octave.

        Args:
            midi_note: MIDI note number (0-127).

        Returns:
            Note name with octave (e.g., "C4", "D#5").
        """
        octave = (midi_note // 12) - 1
        note_index = midi_note % 12
        note_name = self.NOTE_NAMES[note_index]
        return f"{note_name}{octave}"

    def midi_to_note_name_no_octave(self, midi_note: int) -> str:
        """Convert MIDI note number to note name without octave.

        Args:
            midi_note: MIDI note number (0-127).

        Returns:
            Note name without octave (e.g., "C", "D#").
        """
        note_index = midi_note % 12
        return self.NOTE_NAMES[note_index]

    def detect_chord(self, midi_notes: Set[int]) -> Optional[str]:
        """Detect chord from set of MIDI note numbers.

        Supports all chord types including:
        - Triads (major, minor, diminished, augmented)
        - 7th chords (maj7, min7, dom7, dim7, etc.)
        - Extended chords (9th, 11th, 13th)
        - All inversions (1st, 2nd, 3rd, etc.)

        Uses the unified ChordLibrary as the authoritative source of chord definitions.

        Args:
            midi_notes: Set of MIDI note numbers currently pressed.

        Returns:
            Chord name if detected, None if no valid chord or <2 notes.
            Format: "C Major", "Am7", "G Major/B" (with inversion slash notation).
        """
        if len(midi_notes) < 2:
            return None

        # Convert MIDI notes to note names (without octave)
        note_names_list = [self.midi_to_note_name_no_octave(n) for n in sorted(midi_notes)]

        # Remove duplicates while preserving order
        unique_notes = []
        seen = set()
        for note in note_names_list:
            if note not in seen:
                unique_notes.append(note)
                seen.add(note)

        if len(unique_notes) < 2:
            return None

        # Use ChordLibrary to detect the chord
        # Pass as list to preserve bass note (first element = lowest MIDI note)
        # This returns the authoritative chord name from the library with inversion notation
        chord_name = self.chord_library.detect_chord_from_notes(unique_notes)

        return chord_name if chord_name else None

    def get_note_names(self, midi_notes: Set[int]) -> List[str]:
        """Get list of note names with octaves from MIDI notes.

        Args:
            midi_notes: Set of MIDI note numbers.

        Returns:
            List of note names with octaves, sorted by pitch.
        """
        return [self.midi_to_note_name(n) for n in sorted(midi_notes)]
