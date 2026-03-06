import sys
import os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(".")))
os.chdir(r"C:\DEV\Claudes\acordes")
sys.path.insert(0, r"C:\DEV\Claudes\acordes")
from music.synth_engine import SynthEngine

BUFFER_SIZE = 256
SAMPLE_RATE = 48000
SUSTAIN_BUFFERS = 80

def make_engine(voice_type="mono"):
    eng = SynthEngine()
    eng.running = True
    eng.sample_rate = SAMPLE_RATE
    eng.buffer_size = BUFFER_SIZE
    eng.waveform = "sine"
    eng.attack = 0.01
    eng.decay = 0.1
    eng.sustain = 0.7
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

eng = make_engine("mono")
eng.midi_event_queue.put({"type": "note_on", "note": 60, "velocity": 0.8})
pre_bufs = []
for _ in range(SUSTAIN_BUFFERS):
    pre_bufs.append(callback(eng))

mono_v = eng.voices[eng.mono_voice_index]
print(f"Before transition:")
print(f"  last_envelope_level = {mono_v.last_envelope_level:.6f}")
print(f"  envelope_time = {mono_v.envelope_time:.6f}")
print(f"  note_active = {mono_v.note_active}")
print(f"  is_releasing = {mono_v.is_releasing}")
print(f"  onset_samples = {mono_v.onset_samples}")
print(f"  steal_start_level = {mono_v.steal_start_level}")
print(f"  velocity = {mono_v.velocity:.6f}")
print(f"  velocity_target = {mono_v.velocity_target:.6f}")
print(f"  Last sample of pre_buf[-1]: {pre_bufs[-1][-1]:.6f}")
print(f"  Second-to-last sample: {pre_bufs[-1][-2]:.6f}")

eng.midi_event_queue.put({"type": "note_off", "note": 60})
eng.midi_event_queue.put({"type": "note_on", "note": 64, "velocity": 0.8})

trans_buf = callback(eng)

print(f"\nAfter transition:")
print(f"  last_envelope_level = {mono_v.last_envelope_level:.6f}")
print(f"  steal_start_level = {mono_v.steal_start_level:.6f}")
print(f"  First sample of trans_buf: {trans_buf[0]:.6f}")
print(f"  Second sample: {trans_buf[1]:.6f}")
print(f"  Third sample: {trans_buf[2]:.6f}")
print(f"  Boundary delta: {abs(pre_bufs[-1][-1] - trans_buf[0]):.6f}")
print(f"  Pre[-1] last 5: {pre_bufs[-1][-5:]}")
print(f"  Trans[0] first 5: {trans_buf[:5]}")
