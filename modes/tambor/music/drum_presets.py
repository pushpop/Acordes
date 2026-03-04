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
            # Sine body + 15% noise texture for the "thud" transient
            "oscillator_type": "sine",
            "noise_level": 0.15,

            # Long decay sustains the sub-bass boom
            "attack":  0.001,    # 1ms fast onset
            "decay":   0.38,     # 380ms boom tail
            "sustain": 0.0,
            "release": 0.07,     # 70ms release

            # Low-pass keeps sub-bass, cuts mud
            "cutoff_freq": 550,
            "resonance":   0.1,
            "filter_mode": "ladder",  # warm, analog low-pass

            "volume": 0.95,
        }
    },

    "Snare": {
        "midi_note": 38,        # Acoustic Snare  (pitch irrelevant — all noise)
        "display_name": "Snare",
        "synth_params": {
            # White noise for crack and buzz
            "oscillator_type": "noise_white",

            "attack":  0.0002,   # 0.2ms ultra-fast snap
            "decay":   0.18,     # 180ms for body + crack
            "sustain": 0.0,
            "release": 0.04,     # 40ms

            # Mid-high cutoff gives the sharp crack character
            "cutoff_freq": 3500,
            "resonance":   0.55,
            "filter_mode": "svf",     # sharp, modern crack

            "volume": 0.88,
        }
    },

    "Closed HH": {
        "midi_note": 42,        # Closed Hi-Hat  (pitch irrelevant)
        "display_name": "Closed HH",
        "synth_params": {
            "oscillator_type": "noise_white",

            # Very tight — defines the "tick" character
            "attack":  0.0001,   # 0.1ms
            "decay":   0.04,     # 40ms tight choke
            "sustain": 0.0,
            "release": 0.007,    # 7ms

            # Ultra-high cutoff for metallic shimmer
            "cutoff_freq": 14000,
            "resonance":   0.70,
            "filter_mode": "svf",

            "volume": 0.65,
        }
    },

    "Open HH": {
        "midi_note": 46,        # Open Hi-Hat  (pitch irrelevant)
        "display_name": "Open HH",
        "synth_params": {
            "oscillator_type": "noise_white",

            # Long sustained shimmer
            "attack":  0.0002,   # 0.2ms
            "decay":   0.38,     # 380ms open ring
            "sustain": 0.12,     # Sustained brightness
            "release": 0.15,     # 150ms tail

            "cutoff_freq": 12000,
            "resonance":   0.80,  # high resonance = metallic shimmer
            "filter_mode": "svf",

            "volume": 0.70,
        }
    },

    "Clap": {
        "midi_note": 39,        # Hand Clap  (pitch irrelevant)
        "display_name": "Clap",
        "synth_params": {
            "oscillator_type": "noise_white",

            # 3ms attack delay gives the clap its characteristic "smack" shape
            "attack":  0.003,    # 3ms — mimics hand-clap transient
            "decay":   0.09,     # 90ms
            "sustain": 0.0,
            "release": 0.025,    # 25ms

            "cutoff_freq": 5000,
            "resonance":   0.45,
            "filter_mode": "svf",

            "volume": 0.87,
        }
    },

    "Tom Hi": {
        "midi_note": 50,        # Hi Tom  (196 Hz — high-pitched tom)
        "display_name": "Tom Hi",
        "synth_params": {
            # Triangle wave: odd harmonics give a softer "thonk" vs sine
            # Small noise_level adds the stick-on-head click transient
            "oscillator_type": "triangle",
            "noise_level": 0.06,

            "attack":  0.001,    # 1ms
            "decay":   0.14,     # 140ms
            "sustain": 0.0,
            "release": 0.05,     # 50ms

            # Open filter lets harmonics through for tom brightness
            "cutoff_freq": 6000,
            "resonance":   0.40,
            "filter_mode": "ladder",   # warm tom character

            "volume": 0.80,
        }
    },

    "Tom Mid": {
        "midi_note": 47,        # Mid Tom  (175 Hz)
        "display_name": "Tom Mid",
        "synth_params": {
            "oscillator_type": "triangle",
            "noise_level": 0.06,

            "attack":  0.001,
            "decay":   0.19,     # Slightly longer than hi-tom
            "sustain": 0.0,
            "release": 0.06,

            "cutoff_freq": 4500,
            "resonance":   0.35,
            "filter_mode": "ladder",

            "volume": 0.80,
        }
    },

    "Tom Low": {
        "midi_note": 43,        # Low Tom  (156 Hz)
        "display_name": "Tom Low",
        "synth_params": {
            "oscillator_type": "triangle",
            "noise_level": 0.08,   # Slightly more noise for floor-tom "thud"

            "attack":  0.002,    # 2ms
            "decay":   0.26,     # 260ms — longest tom decay
            "sustain": 0.0,
            "release": 0.09,

            # Lower cutoff focuses on the body frequency
            "cutoff_freq": 3000,
            "resonance":   0.30,
            "filter_mode": "ladder",

            "volume": 0.82,
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
