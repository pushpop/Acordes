#!/usr/bin/env python3
"""
Test script to analyze MONO mode note transition artifacts
with different parameter combinations
"""

import numpy as np
import sys
import os

# Add the music module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'music'))

from synth_engine import SynthEngine

def analyze_signal(samples, sample_rate, note_on_sample, note_off_sample, window_size=1024):
    """Analyze signal for discontinuities and artifacts"""
    results = {
        'peak_amplitude': np.max(np.abs(samples)),
        'rms': np.sqrt(np.mean(samples**2)),
        'discontinuities': [],
        'amplitude_jumps': [],
        'high_frequency_content': []
    }

    # Check for amplitude discontinuities around note transitions
    if note_on_sample > window_size:
        window_start = note_on_sample - window_size
        window_end = note_on_sample + window_size
        transition_window = samples[window_start:window_end]

        # Calculate first derivative (amplitude change rate)
        diff = np.abs(np.diff(transition_window))

        # Find sudden jumps (discontinuities)
        mean_diff = np.mean(diff)
        std_diff = np.std(diff)
        threshold = mean_diff + 3 * std_diff

        jumps = np.where(diff > threshold)[0]
        if len(jumps) > 0:
            results['discontinuities'] = jumps.tolist()
            results['amplitude_jumps'] = diff[jumps].tolist()

    # Analyze high-frequency content (clicks are high-frequency)
    fft = np.fft.fft(samples)
    freqs = np.fft.fftfreq(len(samples), 1/sample_rate)

    # Energy in high frequencies (>5kHz indicates clicks)
    high_freq_mask = np.abs(freqs) > 5000
    high_freq_energy = np.mean(np.abs(fft[high_freq_mask])**2)
    results['high_frequency_content'] = float(high_freq_energy)

    return results

def test_mono_note_transition(params):
    """Test MONO mode note transition with given parameters"""
    sample_rate = 48000
    duration = 0.5  # 500ms
    num_samples = int(sample_rate * duration)

    # Create synth engine
    engine = SynthEngine(sample_rate=sample_rate)

    # Set parameters
    engine.waveform = params.get('waveform', 'sawtooth')
    engine.attack = params.get('attack', 0.01)
    engine.decay = params.get('decay', 0.1)
    engine.sustain = params.get('sustain', 0.7)
    engine.release = params.get('release', 0.2)
    engine.cutoff = params.get('cutoff', 5000)
    engine.resonance = params.get('resonance', 0.3)
    engine.intensity = params.get('intensity', 0.8)
    engine.voice_type = 'mono'

    # Generate audio
    samples = np.zeros(num_samples, dtype=np.float32)

    # Note 1: C4 (60)
    note1_time = 0.1  # Start at 100ms
    note1_sample = int(note1_time * sample_rate)

    # Note 2: E4 (64) - transition at 300ms
    note2_time = 0.3
    note2_sample = int(note2_time * sample_rate)

    # Release at 450ms
    release_time = 0.45
    release_sample = int(release_time * sample_rate)

    # Process audio in chunks
    chunk_size = 512
    pos = 0

    while pos < num_samples:
        chunk = min(chunk_size, num_samples - pos)

        # Trigger note 1
        if pos == note1_sample:
            engine.note_on(60, 100)

        # Trigger note 2 (while note 1 still playing)
        elif pos == note2_sample:
            engine.note_on(64, 100)

        # Release note
        elif pos == release_sample:
            engine.note_off(64)

        # Generate chunk (mock - we'll just store when events happen)
        samples[pos:pos+chunk] = np.zeros(chunk)
        pos += chunk

    return {
        'note1_sample': note1_sample,
        'note2_sample': note2_sample,
        'release_sample': release_sample,
        'params': params
    }

def print_test_results(test_name, params, results):
    """Pretty print test results"""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"{'='*60}")
    print(f"Parameters:")
    for key, val in params.items():
        print(f"  {key:20s}: {val}")
    print(f"\nResults:")
    print(f"  Peak Amplitude      : {results.get('peak_amplitude', 0):.4f}")
    print(f"  RMS Level           : {results.get('rms', 0):.4f}")
    print(f"  High-Freq Energy    : {results.get('high_frequency_content', 0):.6f}")
    if results.get('discontinuities'):
        print(f"  Discontinuities     : {len(results['discontinuities'])} detected")
        print(f"  Jump Magnitudes     : {[f'{x:.4f}' for x in results.get('amplitude_jumps', [])[:3]]}")
    else:
        print(f"  Discontinuities     : None")

def run_analysis():
    """Run comprehensive analysis of different parameter combinations"""

    print("\n" + "="*60)
    print("MONO MODE NOTE TRANSITION ARTIFACT ANALYSIS")
    print("="*60)

    # Test 1: Fast attack (causes discontinuity)
    test_configs = [
        {
            'name': 'Fast Attack (0.001s)',
            'params': {
                'waveform': 'sawtooth',
                'attack': 0.001,
                'decay': 0.1,
                'sustain': 0.7,
                'release': 0.2,
                'cutoff': 5000,
                'resonance': 0.3
            }
        },
        {
            'name': 'Slow Attack (0.05s)',
            'params': {
                'waveform': 'sawtooth',
                'attack': 0.05,
                'decay': 0.1,
                'sustain': 0.7,
                'release': 0.2,
                'cutoff': 5000,
                'resonance': 0.3
            }
        },
        {
            'name': 'Low Sustain (0.1)',
            'params': {
                'waveform': 'sawtooth',
                'attack': 0.01,
                'decay': 0.1,
                'sustain': 0.1,
                'release': 0.2,
                'cutoff': 5000,
                'resonance': 0.3
            }
        },
        {
            'name': 'High Sustain (0.95)',
            'params': {
                'waveform': 'sawtooth',
                'attack': 0.01,
                'decay': 0.1,
                'sustain': 0.95,
                'release': 0.2,
                'cutoff': 5000,
                'resonance': 0.3
            }
        },
        {
            'name': 'High Resonance (0.9)',
            'params': {
                'waveform': 'sawtooth',
                'attack': 0.01,
                'decay': 0.1,
                'sustain': 0.7,
                'release': 0.2,
                'cutoff': 5000,
                'resonance': 0.9
            }
        },
        {
            'name': 'Square Wave',
            'params': {
                'waveform': 'square',
                'attack': 0.01,
                'decay': 0.1,
                'sustain': 0.7,
                'release': 0.2,
                'cutoff': 5000,
                'resonance': 0.3
            }
        },
        {
            'name': 'Pure Sine',
            'params': {
                'waveform': 'pure_sine',
                'attack': 0.01,
                'decay': 0.1,
                'sustain': 0.7,
                'release': 0.2,
                'cutoff': 20000,
                'resonance': 0.0
            }
        }
    ]

    print("\nKey Hypothesis:")
    print("- Artifacts appear when ENVELOPE is at non-zero level during note switch")
    print("- Legato mode keeps envelope_time running, avoiding envelope retrigger")
    print("- BUT: If sustain is low, the envelope level might jump")
    print("- If resonance is high, stale filter states might ring")
    print("- Fast attack means envelope goes from 0→max quickly = discontinuity risk\n")

    for config in test_configs:
        result = test_mono_note_transition(config['params'])
        print_test_results(config['name'], config['params'], result)

    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    print("""
Potential Culprits:
1. ENVELOPE LEVEL MISMATCH
   - If envelope continues from sustain level, but the NEW note starts with
     a different velocity, there could be a level jump

2. FILTER STATE CONTINUATION
   - In legato mode, filter states are NOT reset (good)
   - But filter resonance might still ring from previous note
   - When frequency changes, the filter ring might create artifacts

3. SUSTAIN LEVEL DISCONTINUITY
   - If sustain is low (0.1), the envelope is at 0.1 × intensity
   - If we play a new note while at this low level, the amplitude jump
     might be audible as a "pop"

4. ONSET RAMP INTERACTION
   - onset_samples is reset, which restarts the DC blocker fade-in
   - This might create a fade that conflicts with the sustain level

5. ENVELOPE ATTACK DURING SUSTAIN
   - In legato, if envelope_time is not reset, we're at sustain level
   - But steal_start_level creates an 8ms crossfade
   - This crossfade might interfere with the sustain level

RECOMMENDATION:
Test if the issue is the steal_start_level crossfade or the envelope
not restarting. Check if removing steal_start_level helps.
    """)

if __name__ == '__main__':
    run_analysis()
