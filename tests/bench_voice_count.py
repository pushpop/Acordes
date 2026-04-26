# ABOUTME: Benchmark script measuring audio callback time at various voice counts.
# ABOUTME: Run with: uv run python tests/bench_voice_count.py
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from music.synth_engine import SynthEngine

SAMPLE_RATE = 48000
BUFFER_SIZE = 480
NUM_BUFFERS = 200


class _FakeTime:
    inputBufferAdcTime = 0.0
    outputBufferDacTime = 0.0
    currentTime = 0.0


def make_engine() -> SynthEngine:
    """Create a silent engine with standard synth params."""
    eng = SynthEngine(output_device_index=-1, enable_oversampling=True)
    eng._startup_silence_samples = 0
    if eng.stream is not None:
        eng.stream.stop_stream()
    eng.update_parameters(
        waveform="sawtooth",
        voice_type="poly",
        attack=0.006,
        decay=0.25,
        sustain=0.70,
        release=0.30,
        amp_level=0.9,
        master_vol=1.0,
        lfo_depth=0.0,
        chorus_mix=0.0,
        delay_mix=0.0,
        noise_level=0.0,
        cutoff=2000,
        resonance=0.3,
    )
    # Warm-up: 2 buffers to let smoothing settle
    t = _FakeTime()
    out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
    for _ in range(2):
        eng._audio_callback(out, BUFFER_SIZE, t, None)
    return eng


def run_benchmark(eng: SynthEngine, n_voices: int) -> dict:
    """Trigger n_voices notes and measure callback time over NUM_BUFFERS."""
    # Release any active notes first
    eng.all_notes_off()
    t = _FakeTime()
    out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
    # Drain the all_notes_off
    eng._audio_callback(out, BUFFER_SIZE, t, None)

    # Trigger n_voices notes (C3 upward, velocity 100)
    base_note = 48
    for i in range(n_voices):
        eng.note_on(base_note + i, velocity=100)

    # Let attack settle (5 buffers)
    for _ in range(5):
        eng._audio_callback(out, BUFFER_SIZE, t, None)

    # Measure
    times = []
    for _ in range(NUM_BUFFERS):
        start = time.perf_counter()
        eng._audio_callback(out, BUFFER_SIZE, t, None)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    times_ms = np.array(times) * 1000.0
    budget_ms = (BUFFER_SIZE / SAMPLE_RATE) * 1000.0

    return {
        "voices": n_voices,
        "avg_ms": float(np.mean(times_ms)),
        "p95_ms": float(np.percentile(times_ms, 95)),
        "max_ms": float(np.max(times_ms)),
        "budget_ms": budget_ms,
        "headroom_pct": float((1.0 - np.mean(times_ms) / budget_ms) * 100),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Use 'fast' filter quality (scipy sosfilt)")
    args = parser.parse_args()

    voice_counts = [1, 4, 8, 12, 16, 24, 32]

    # Filter out counts that exceed engine's num_voices
    eng = make_engine()
    if args.fast:
        eng.update_parameters(filter_quality="fast")
        # Drain the param update
        t = _FakeTime()
        out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
        eng._audio_callback(out, BUFFER_SIZE, t, None)
    max_v = eng.num_voices
    voice_counts = [v for v in voice_counts if v <= max_v]

    budget_ms = (BUFFER_SIZE / SAMPLE_RATE) * 1000.0
    fq = eng.filter_quality
    print(f"Synth Engine Voice Benchmark (filter_quality={fq})")
    print(f"  Buffer: {BUFFER_SIZE} samples ({budget_ms:.1f}ms budget)")
    print(f"  Engine voices: {max_v}")
    print(f"  Oversampling: {eng.ENABLE_OVERSAMPLING} ({eng.OVERSAMPLE_FACTOR}x)")
    print(f"  Buffers per test: {NUM_BUFFERS}")
    print()
    print(f"{'Voices':>7} {'Avg(ms)':>9} {'P95(ms)':>9} {'Max(ms)':>9} {'Headroom':>10}")
    print("-" * 50)

    for n in voice_counts:
        result = run_benchmark(eng, n)
        headroom = f"{result['headroom_pct']:.1f}%"
        print(f"{result['voices']:>7} {result['avg_ms']:>9.3f} {result['p95_ms']:>9.3f} "
              f"{result['max_ms']:>9.3f} {headroom:>10}")

    print()
    print(f"Budget per callback: {budget_ms:.1f}ms")
    print(f"Values above budget indicate real-time underruns.")


if __name__ == "__main__":
    main()
