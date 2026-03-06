import sys, os, numpy as np
sys.path.insert(0, r"C:\DEV\Claudes\acordes")
os.chdir(r"C:\DEV\Claudes\acordes")
from music.synth_engine import SynthEngine

BUFFER_SIZE = 256
SAMPLE_RATE = 48000

def make_engine(attack, sustain, waveform, voice_type):
    eng = SynthEngine()
    eng.running = True
    eng.sample_rate = SAMPLE_RATE
    eng.buffer_size = BUFFER_SIZE
    eng.waveform = waveform
    eng.attack = attack
    eng.decay = 0.1
    eng.sustain = sustain
    eng.release = 0.05
    eng.cutoff = eng.cutoff_current = eng.cutoff_target = 3000.0
    eng.resonance = eng.resonance_current = eng.resonance_target = 0.2
    eng.intensity = eng.intensity_current = eng.intensity_target = 0.8
    eng.amp_level = eng.amp_level_target = eng.amp_level_current = 0.8
    eng.noise_level = eng.noise_level_current = eng.noise_level_target = 0.0
    eng.lfo_depth = 0.0
    eng.chorus_mix = 0.0
    eng.delay_mix = 0.0
    eng.voice_type = voice_type
    return eng

def callback(eng):
    raw, _ = eng._audio_callback(None, BUFFER_SIZE, {}, 0)
    pcm = np.frombuffer(raw, dtype=np.int16)
    return pcm[0::2].astype(np.float32) / 32768.0

# Test the specific failing case: MONO/sine atk=0.001 sus=0.9
print("=== MONO/sine atk=0.001 sus=0.9 ===")
eng = make_engine(0.001, 0.9, "sine", "mono")
eng.midi_event_queue.put({"type": "note_on", "note": 60, "velocity": 0.8})
pre_bufs = []
for _ in range(80):
    pre_bufs.append(callback(eng))

mono_v = eng.voices[eng.mono_voice_index]
print(f"Voice state before transition:")
print(f"  last_envelope_level={mono_v.last_envelope_level:.6f}")
print(f"  envelope_time={mono_v.envelope_time:.6f}")
print(f"  sine_phase={mono_v.sine_phase:.6f}")
print(f"  onset_samples={mono_v.onset_samples}")
print(f"  Pre-buf last 5: {pre_bufs[-1][-5:]}")

# Transition
eng.midi_event_queue.put({"type": "note_off", "note": 60})
eng.midi_event_queue.put({"type": "note_on", "note": 64, "velocity": 0.8})
trans_buf = callback(eng)

print(f"Voice state after transition buffer:")
print(f"  steal_start_level={mono_v.steal_start_level:.6f}")
print(f"  last_envelope_level={mono_v.last_envelope_level:.6f}")
print(f"  Trans-buf first 10: {trans_buf[:10]}")
print(f"  BOUNDARY DELTA = {abs(pre_bufs[-1][-1] - trans_buf[0]):.6f}")

# Also print the last 10 samples of pre-buf and first 10 of trans-buf to see the waveform shape
print(f"\nFull boundary context:")
for i in range(-5, 0):
    print(f"  pre[{i}] = {pre_bufs[-1][i]:.6f}")
for i in range(5):
    print(f"  trans[{i}] = {trans_buf[i]:.6f}")
