import sys, os, numpy as np
sys.path.insert(0, r"C:\DEV\Claudes\acordes")
os.chdir(r"C:\DEV\Claudes\acordes")
from music.synth_engine import SynthEngine

BUFFER_SIZE = 256
SAMPLE_RATE = 48000
SUSTAIN_BUFFERS = 80
WARMUP_BUFFERS = 20
ARTIFACT_RATIO = 3.0
ABS_THRESHOLD = 0.05

TEST_CASES = [
    {"attack": 0.001, "sustain": 0.9, "waveform": "sawtooth"},
    {"attack": 0.01,  "sustain": 0.7, "waveform": "sine"},
    {"attack": 0.001, "sustain": 0.5, "waveform": "square"},
    {"attack": 0.05,  "sustain": 0.8, "waveform": "triangle"},
    {"attack": 0.005, "sustain": 0.8, "waveform": "sawtooth"},
    {"attack": 0.001, "sustain": 0.9, "waveform": "sine"},
]

def make_engine(attack, sustain, waveform, voice_type, use_oversampling=True):
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
    eng.ENABLE_OVERSAMPLING = use_oversampling
    return eng

def callback(eng):
    raw, _ = eng._audio_callback(None, BUFFER_SIZE, {}, 0)
    pcm = np.frombuffer(raw, dtype=np.int16)
    return pcm[0::2].astype(np.float32) / 32768.0

def boundary_delta(a, b):
    return float(abs(a[-1] - b[0]))

def run_case(attack, sustain, waveform, voice_type, use_oversampling):
    np.random.seed(42)
    eng = make_engine(attack, sustain, waveform, voice_type, use_oversampling)
    eng.midi_event_queue.put({"type": "note_on", "note": 60, "velocity": 0.8})
    pre_bufs = []
    for _ in range(SUSTAIN_BUFFERS):
        pre_bufs.append(callback(eng))
    
    eng.midi_event_queue.put({"type": "note_off", "note": 60})
    eng.midi_event_queue.put({"type": "note_on", "note": 64, "velocity": 0.8})
    trans_buf = callback(eng)
    trans_delta = boundary_delta(pre_bufs[-1], trans_buf)
    
    post_bufs = [trans_buf]
    for _ in range(WARMUP_BUFFERS - 1):
        post_bufs.append(callback(eng))
    steady_deltas = [boundary_delta(post_bufs[i], post_bufs[i+1]) for i in range(5, len(post_bufs)-1)]
    steady_median = float(np.median(steady_deltas)) if steady_deltas else 0.0
    steady_max = float(np.max(steady_deltas)) if steady_deltas else 0.0
    baseline = max(steady_median, 0.005)
    ratio = trans_delta / baseline
    verdict = "ARTIFACT" if (ratio > ARTIFACT_RATIO and trans_delta > ABS_THRESHOLD) else "CLEAN"
    
    return trans_delta, ratio, verdict, float(pre_bufs[-1][-1]), float(trans_buf[0])

print("=== Testing WITH oversampling (3 runs each case) ===")
for p in TEST_CASES:
    results = []
    for _ in range(3):
        td, r, v, pre, t0 = run_case(p["attack"], p["sustain"], p["waveform"], "mono", True)
        results.append((td, r, v))
    tds = [x[0] for x in results]
    unique = len(set(f"{x:.4f}" for x in tds))
    print(f"  {p['waveform']:8s} atk={p['attack']:.3f}: deltas={[f'{x:.4f}' for x in tds]} unique={unique} {'VARIES' if unique>1 else 'STABLE'}")

print("\n=== Testing WITHOUT oversampling (3 runs each case) ===")
for p in TEST_CASES:
    results = []
    for _ in range(3):
        td, r, v, pre, t0 = run_case(p["attack"], p["sustain"], p["waveform"], "mono", False)
        results.append((td, r, v))
    tds = [x[0] for x in results]
    unique = len(set(f"{x:.4f}" for x in tds))
    print(f"  {p['waveform']:8s} atk={p['attack']:.3f}: deltas={[f'{x:.4f}' for x in tds]} unique={unique} {'VARIES' if unique>1 else 'STABLE'}")
