# ABOUTME: Test script that analyzes SynthEngine for amplitude discontinuities
# ABOUTME: during MONO/UNISON note transitions by comparing transition vs. steady-state deltas.

import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from music.synth_engine import SynthEngine

BUFFER_SIZE = 256
SAMPLE_RATE = 48000
SUSTAIN_BUFFERS = 80   # let the note fully reach sustain
WARMUP_BUFFERS  = 20   # steady-state buffers AFTER transition to compute baseline
ARTIFACT_RATIO  = 3.0  # transition delta is an artifact if > ratio × steady-state median
ABS_THRESHOLD   = 0.05 # minimum absolute delta to be considered audible (5% of full scale)

TEST_CASES = [
    {"attack": 0.001, "sustain": 0.9, "waveform": "sawtooth"},
    {"attack": 0.01,  "sustain": 0.7, "waveform": "sine"},
    {"attack": 0.001, "sustain": 0.5, "waveform": "square"},
    {"attack": 0.05,  "sustain": 0.8, "waveform": "triangle"},
    {"attack": 0.005, "sustain": 0.8, "waveform": "sawtooth"},   # fast attack high sustain
    {"attack": 0.001, "sustain": 0.9, "waveform": "sine"},       # very fast attack
]

VOICE_TYPES = ["mono", "unison"]


def make_engine(params: dict, voice_type: str) -> SynthEngine:
    eng = SynthEngine()
    # Stop the PyAudio stream so its background thread doesn't race with our
    # direct _audio_callback calls below.  Without this, the stream thread
    # can drain the MIDI queue or consume _transition_xf_remaining before the
    # test's direct call, causing non-deterministic failures.
    if hasattr(eng, 'stream'):
        try:
            eng.stream.stop_stream()
        except Exception:
            pass
    eng.running = True
    eng.sample_rate = SAMPLE_RATE
    eng.buffer_size = BUFFER_SIZE
    eng.waveform    = params["waveform"]
    eng.attack      = params["attack"]
    eng.decay       = 0.1
    eng.sustain     = params["sustain"]
    eng.release     = 0.05
    eng.cutoff = eng.cutoff_current = eng.cutoff_target = 3000.0
    eng.resonance = eng.resonance_current = eng.resonance_target = 0.2
    eng.intensity = eng.intensity_current = eng.intensity_target = 0.8
    eng.amp_level = eng.amp_level_target = eng.amp_level_current = 0.8
    eng.noise_level = eng.noise_level_current = eng.noise_level_target = 0.0
    eng.lfo_depth   = 0.0
    eng.chorus_mix  = 0.0
    eng.delay_mix   = 0.0
    eng.voice_type  = voice_type
    return eng


def callback(eng: SynthEngine) -> np.ndarray:
    raw, _ = eng._audio_callback(None, BUFFER_SIZE, {}, 0)
    pcm = np.frombuffer(raw, dtype=np.int16)
    return pcm[0::2].astype(np.float32) / 32768.0   # left channel, normalised


def boundary_delta(buf_a: np.ndarray, buf_b: np.ndarray) -> float:
    """Amplitude step between last sample of buf_a and first sample of buf_b."""
    return float(abs(buf_a[-1] - buf_b[0]))


def run_test(params: dict, voice_type: str) -> dict:
    np.random.seed(42)   # fix RNG so noise paths are deterministic across test cases
    eng = make_engine(params, voice_type)

    # --- phase 1: note 60 for SUSTAIN_BUFFERS buffers (reach sustain plateau) ---
    eng.midi_event_queue.put({"type": "note_on", "note": 60, "velocity": 0.8})
    pre_bufs = []
    for _ in range(SUSTAIN_BUFFERS):
        pre_bufs.append(callback(eng))

    # --- phase 2: release 60, immediately press 64 (staccato/overlap transition) ---
    eng.midi_event_queue.put({"type": "note_off", "note": 60})
    eng.midi_event_queue.put({"type": "note_on",  "note": 64, "velocity": 0.8})

    # Buffer right at the transition — this is where the click would occur.
    trans_buf = callback(eng)
    transition_delta = boundary_delta(pre_bufs[-1], trans_buf)

    # --- phase 3: capture WARMUP_BUFFERS steady-state buffers after note 64 settles ---
    post_bufs = [trans_buf]
    for _ in range(WARMUP_BUFFERS - 1):
        post_bufs.append(callback(eng))

    # Compute boundary deltas for the steady-state buffers (skip the first which is trans)
    steady_deltas = [boundary_delta(post_bufs[i], post_bufs[i+1])
                     for i in range(5, len(post_bufs)-1)]   # skip first 5 (settling)
    steady_median = float(np.median(steady_deltas)) if steady_deltas else 0.0
    steady_max    = float(np.max(steady_deltas))    if steady_deltas else 0.0

    # The transition is an artifact if its delta is ARTIFACT_RATIO times the steady median
    # AND exceeds the absolute audibility threshold.  The ratio alone is insufficient
    # because a tiny steady-state baseline (e.g. 0.003) makes harmless tiny deltas
    # (e.g. 0.010) look like 3× artifacts even though they are completely inaudible.
    baseline = max(steady_median, 0.005)   # floor prevents division issues at near-silence
    ratio    = transition_delta / baseline if baseline > 0 else 0.0
    is_artifact = ratio > ARTIFACT_RATIO and transition_delta > ABS_THRESHOLD

    return {
        "voice_type":        voice_type,
        "params":            params,
        "transition_delta":  transition_delta,
        "pre_last":          float(pre_bufs[-1][-1]),
        "trans_first":       float(trans_buf[0]),
        "steady_median":     steady_median,
        "steady_max":        steady_max,
        "ratio":             ratio,
        "verdict":           "ARTIFACT" if is_artifact else "CLEAN",
    }


def print_result(r: dict):
    p = r["params"]
    print(f"  {r['voice_type'].upper():6s}  {p['waveform']:8s}  "
          f"atk={p['attack']:.3f}  sus={p['sustain']:.1f}  "
          f"pre={r['pre_last']:+.4f}  t0={r['trans_first']:+.4f}  "
          f"trans={r['transition_delta']:.4f}  "
          f"ss_med={r['steady_median']:.4f}  ss_max={r['steady_max']:.4f}  "
          f"ratio={r['ratio']:.1f}x  "
          f"→ {r['verdict']}")


def main():
    print("=" * 80)
    print("  Acordes — Note Transition Artifact Analysis")
    print(f"  Buffer={BUFFER_SIZE}  SR={SAMPLE_RATE}  "
          f"SustainBufs={SUSTAIN_BUFFERS}  WarmupBufs={WARMUP_BUFFERS}")
    print(f"  ARTIFACT if transition_delta > {ARTIFACT_RATIO}× steady-state median"
          f"  AND  > {ABS_THRESHOLD} absolute")
    print("=" * 80)
    print()
    print(f"  {'Mode':6s}  {'Wave':8s}  {'atk':9s}  {'sus':5s}  "
          f"{'trans Δ':9s}  {'ss med Δ':10s}  {'ratio':7s}  verdict")
    print("  " + "-" * 74)

    results = []
    for vt in VOICE_TYPES:
        for p in TEST_CASES:
            try:
                r = run_test(p, vt)
                results.append(r)
                print_result(r)
            except Exception as exc:
                import traceback
                print(f"  ERROR {p} / {vt}: {exc}")
                traceback.print_exc()

    print()
    print("=" * 80)
    artifacts = [r for r in results if r["verdict"] == "ARTIFACT"]
    clean     = [r for r in results if r["verdict"] == "CLEAN"]
    print(f"  CLEAN: {len(clean)}/{len(results)}   ARTIFACT: {len(artifacts)}/{len(results)}")
    if artifacts:
        print()
        print("  Failing cases:")
        for r in artifacts:
            p = r["params"]
            print(f"    {r['voice_type'].upper()} / {p['waveform']:8s}  "
                  f"atk={p['attack']:.3f}  sus={p['sustain']:.1f}  "
                  f"trans={r['transition_delta']:.4f}  "
                  f"ratio={r['ratio']:.1f}x  "
                  f"steady_max={r['steady_max']:.4f}")
    print()


if __name__ == "__main__":
    main()
