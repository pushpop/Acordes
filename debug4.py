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

# Run this specific failing case 5 times to show variability
print("Running MONO/sine atk=0.001 sus=0.9 case 5 times:")
for run in range(5):
    eng = make_engine(0.001, 0.9, "sine", "mono")
    eng.midi_event_queue.put({"type": "note_on", "note": 60, "velocity": 0.8})
    pre_bufs = []
    for _ in range(80):
        pre_bufs.append(callback(eng))

    v = eng.voices[eng.mono_voice_index]
    pre_last = pre_bufs[-1][-1]
    env_level = v.last_envelope_level
    phase_val = v.phase

    eng.midi_event_queue.put({"type": "note_off", "note": 60})
    eng.midi_event_queue.put({"type": "note_on", "note": 64, "velocity": 0.8})
    trans_buf = callback(eng)
    trans_first = trans_buf[0]
    delta = abs(pre_last - trans_first)

    print(f"  Run {run+1}: pre_last={pre_last:.4f}  trans_first={trans_first:.4f}  delta={delta:.4f}  env={env_level:.4f}  phase={phase_val:.4f}")

# Also run sawtooth for comparison
print("\nRunning MONO/sawtooth atk=0.001 sus=0.9 case 3 times:")
for run in range(3):
    eng = make_engine(0.001, 0.9, "sawtooth", "mono")
    eng.midi_event_queue.put({"type": "note_on", "note": 60, "velocity": 0.8})
    pre_bufs = []
    for _ in range(80):
        pre_bufs.append(callback(eng))

    v = eng.voices[eng.mono_voice_index]
    pre_last = pre_bufs[-1][-1]

    eng.midi_event_queue.put({"type": "note_off", "note": 60})
    eng.midi_event_queue.put({"type": "note_on", "note": 64, "velocity": 0.8})
    trans_buf = callback(eng)
    trans_first = trans_buf[0]
    delta = abs(pre_last - trans_first)
    print(f"  Run {run+1}: pre_last={pre_last:.4f}  trans_first={trans_first:.4f}  delta={delta:.4f}  env={v.last_envelope_level:.4f}  phase={v.phase:.4f}")
