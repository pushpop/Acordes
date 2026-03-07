"""ABOUTME: Drum preset definitions for Tambor drum machine.
ABOUTME: Maps drum names to MIDI notes and synthesizer parameter configurations."""

# Standard General MIDI drum kit note assignments.
# MIDI note determines playback pitch for tonal drums (kick/toms).
# Noise-based drums (snare/hats/clap) are pitch-independent.
#
# Waveform choices:
#   "sine"       - pure tone, warm body (kick)
#   "triangle"   - odd harmonics, soft thump (toms)
#   "noise_white"- full-spectrum noise (snare, hats, clap)
#   "noise_pink" - bass-heavy noise (sub-kick texture)
#
# noise_level: 0.0-1.0 crossfade, mixing noise ON TOP of the main oscillator.
#   Sine + noise_level=0.15 → kick body with transient texture.
#   Triangle + noise_level=0.06 → tom with stick click.
#
# filter_mode: "ladder" (warm, analog) or "svf" (sharp, modern).
#   Ladder = tonal drums (kick, toms) — smooth low-pass character.
#   SVF    = noise drums (snare, hats) — precise high-frequency shaping.

DRUM_PRESETS = {
    "Kick": {
        "midi_note": 36,        # Bass Drum 1  (65.4 Hz — deep sub-bass)
        "display_name": "Kick",
        "synth_params": {
            # Pure sine wave for clean, round electronic kick
            "oscillator_type": "sine",
            "noise_level": 0.01,  # Minimal noise — pure sine tone

            # Fast attack for punch, long decay for sub-bass boom
            "attack":  0.0005,   # 0.5ms punchy onset
            "decay":   0.45,     # 450ms extended boom for low-end presence
            "sustain": 0.0,
            "release": 0.08,     # 80ms tight release

            # Clean warmth without muddiness
            "cutoff_freq": 700,
            "resonance":   0.10,
            "filter_mode": "ladder",

            "volume": 1.0,       # Full volume for punchy character
        }
    },

    "Snare": {
        "midi_note": 38,        # Acoustic Snare  (pitch irrelevant — all noise)
        "display_name": "Snare",
        "synth_params": {
            # White noise for sharp transient
            "oscillator_type": "noise_white",

            # Ultra-fast attack for crisp snap, short decay for snappy character
            "attack":  0.00001,  # 0.01ms super-sharp snap
            "decay":   0.12,     # 120ms shorter — snappier response
            "sustain": 0.0,
            "release": 0.03,     # 30ms tight tail

            # Clean, defined crack without muddiness
            "cutoff_freq": 5000,
            "resonance":   0.55,
            "filter_mode": "svf",

            "volume": 0.90,
        }
    },

    "Closed HH": {
        "midi_note": 42,        # Closed Hi-Hat  (pitch irrelevant)
        "display_name": "Closed HH",
        "synth_params": {
            "oscillator_type": "noise_white",

            # Very fast, very tight — classic electronic hihat "tick"
            "attack":  0.00002,  # 0.02ms ultra-tight snap
            "decay":   0.04,     # 40ms tight envelope
            "sustain": 0.0,
            "release": 0.004,    # 4ms snap-closed effect

            # Clean, defined shimmer without harshness
            "cutoff_freq": 15000,
            "resonance":   0.60,
            "filter_mode": "svf",

            "volume": 0.68,
        }
    },

    "Open HH": {
        "midi_note": 46,        # Open Hi-Hat  (pitch irrelevant)
        "display_name": "Open HH",
        "synth_params": {
            "oscillator_type": "noise_white",

            # Slightly slower attack for open character, sustained ring
            "attack":  0.00025,  # 0.25ms
            "decay":   0.45,     # 450ms long shimmer
            "sustain": 0.15,     # Sustained brightness for open effect
            "release": 0.18,     # 180ms tail

            # Clean, bright sustained tone
            "cutoff_freq": 12500,
            "resonance":   0.70,
            "filter_mode": "svf",

            "volume": 0.70,
        }
    },

    "Clap": {
        "midi_note": 39,        # Hand Clap  (pitch irrelevant)
        "display_name": "Clap",
        "synth_params": {
            "oscillator_type": "noise_white",

            # Fast attack for clean smack
            "attack":  0.0003,   # 0.3ms — sharp, clean transient
            "decay":   0.10,     # 100ms tight body
            "sustain": 0.0,
            "release": 0.025,    # 25ms clean release

            # Clean midrange — punchy without muddiness
            "cutoff_freq": 5500,
            "resonance":   0.45,
            "filter_mode": "svf",

            "volume": 0.88,
        }
    },

    "Tom Hi": {
        "midi_note": 50,        # Hi Tom  (196 Hz — high-pitched tom)
        "display_name": "Tom Hi",
        "synth_params": {
            # Pure sine wave for clean, round tom
            "oscillator_type": "sine",
            "noise_level": 0.01,  # Minimal noise — clean tone

            # Fast attack for punch, quick decay for definition
            "attack":  0.0003,   # 0.3ms punchy
            "decay":   0.11,     # 110ms tight — punchy tom character
            "sustain": 0.0,
            "release": 0.035,    # 35ms

            # Clean, focused high tom
            "cutoff_freq": 7200,
            "resonance":   0.35,
            "filter_mode": "ladder",

            "volume": 0.83,
        }
    },

    "Tom Mid": {
        "midi_note": 47,        # Mid Tom  (175 Hz)
        "display_name": "Tom Mid",
        "synth_params": {
            "oscillator_type": "sine",
            "noise_level": 0.01,

            # Medium attack/decay for definition
            "attack":  0.0005,   # 0.5ms
            "decay":   0.15,     # 150ms
            "sustain": 0.0,
            "release": 0.04,     # 40ms

            # Clean, balanced mid tom
            "cutoff_freq": 5200,
            "resonance":   0.30,
            "filter_mode": "ladder",

            "volume": 0.85,
        }
    },

    "Tom Low": {
        "midi_note": 43,        # Low Tom  (156 Hz)
        "display_name": "Tom Low",
        "synth_params": {
            "oscillator_type": "sine",
            "noise_level": 0.01,  # Minimal noise for clean low tom

            # Slower attack for deep thump, longer decay
            "attack":  0.0008,   # 0.8ms
            "decay":   0.20,     # 200ms for bass presence
            "sustain": 0.0,
            "release": 0.06,     # 60ms

            # Lower cutoff for deep, clean tom body
            "cutoff_freq": 3600,
            "resonance":   0.25,
            "filter_mode": "ladder",

            "volume": 0.86,
        }
    },
}


def get_preset(drum_name: str) -> dict:
    """Get preset configuration for a drum by name.

    Args:
        drum_name: Name of the drum (e.g., "Kick", "Snare")

    Returns:
        Dictionary containing midi_note and synth_params, or None if not found
    """
    return DRUM_PRESETS.get(drum_name)


def get_all_drum_names() -> list:
    """Get list of all available drum names in order."""
    return list(DRUM_PRESETS.keys())


def get_midi_note(drum_name: str) -> int:
    """Get MIDI note number for a drum."""
    preset = get_preset(drum_name)
    return preset["midi_note"] if preset else None


def get_synth_params(drum_name: str) -> dict:
    """Get synth parameters for a drum."""
    preset = get_preset(drum_name)
    return preset["synth_params"].copy() if preset else None
