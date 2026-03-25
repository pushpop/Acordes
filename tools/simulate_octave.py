# ABOUTME: Simulation tool: drives SynthEngine without hardware, captures waveform output.
# ABOUTME: Plays C3-C4 in MONO/UNISON sequential and overlapping (steal) modes, renders PNG.

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from music.synth_engine import SynthEngine

NOTES      = [48, 50, 52, 53, 55, 57, 59, 60]
NOTE_NAMES = ["C3","D3","E3","F3","G3","A3","B3","C4"]

SAMPLE_RATE   = 48000
BUFFER_SIZE   = 480
NOTE_DUR_S    = 1.0
RELEASE_DUR_S = 0.15
GAP_DUR_S     = 0.05
OVERLAP_DUR_S = 0.25

NOTE_SAMPS    = int(SAMPLE_RATE * NOTE_DUR_S)
RELEASE_SAMPS = int(SAMPLE_RATE * RELEASE_DUR_S)
GAP_SAMPS     = int(SAMPLE_RATE * GAP_DUR_S)
OVERLAP_SAMPS = int(SAMPLE_RATE * OVERLAP_DUR_S)


class _FakeTime:
    inputBufferAdcTime = 0.0
    outputBufferDacTime = 0.0
    currentTime = 0.0


def make_engine(voice_type: str) -> SynthEngine:
    eng = SynthEngine(output_device_index=-1, enable_oversampling=False)
    eng._startup_silence_samples = 0
    eng.update_parameters(
        waveform="pure_sine",
        voice_type=voice_type,
        attack=0.008,
        decay=0.3,
        sustain=0.75,
        release=0.08,
        amp_level=0.9,
        master_vol=1.0,
        lfo_depth=0.0,
        chorus_mix=0.0,
        delay_mix=0.0,
        noise_level=0.0,
        num_voices=4,
    )
    _run_buffers(eng, 1)
    return eng


def _run_buffers(eng: SynthEngine, n: int) -> np.ndarray:
    chunks = []
    t = _FakeTime()
    for _ in range(n):
        out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
        eng._audio_callback(out, BUFFER_SIZE, t, None)
        chunks.append(out[:, 0].copy())
    return np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)


def _run_exact(eng: SynthEngine, n_samples: int) -> np.ndarray:
    n_full    = n_samples // BUFFER_SIZE
    remainder = n_samples % BUFFER_SIZE
    parts = [_run_buffers(eng, n_full)]
    if remainder:
        t = _FakeTime()
        out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
        eng._audio_callback(out, BUFFER_SIZE, t, None)
        parts.append(out[:remainder, 0].copy())
    return np.concatenate(parts)


def simulate_sequential(voice_type: str):
    """Each note plays fully, then releases, then a short gap."""
    eng = make_engine(voice_type)
    parts, starts = [], []
    for midi_note, name in zip(NOTES, NOTE_NAMES):
        print(f"  [{voice_type:6}] SEQ {name}")
        starts.append(sum(len(p) for p in parts))
        eng.note_on(midi_note, 1.0)
        parts.append(_run_exact(eng, NOTE_SAMPS))
        eng.note_off(midi_note)
        parts.append(_run_exact(eng, RELEASE_SAMPS))
        parts.append(np.zeros(GAP_SAMPS, dtype=np.float32))
    return np.concatenate(parts), starts


def simulate_overlapping(voice_type: str):
    """
    Next note_on fires OVERLAP_DUR_S before current note_off, forcing voice steal.
    Models fast playing / legato where notes overlap.
    """
    eng = make_engine(voice_type)
    parts, starts = [], []
    for idx, (midi_note, name) in enumerate(zip(NOTES, NOTE_NAMES)):
        print(f"  [{voice_type:6}] OVL {name}")
        starts.append(sum(len(p) for p in parts))
        eng.note_on(midi_note, 1.0)
        if idx < len(NOTES) - 1:
            # Play until steal point
            parts.append(_run_exact(eng, NOTE_SAMPS - OVERLAP_SAMPS))
            # Fire next note while current is still held — STEAL
            eng.note_on(NOTES[idx + 1], 1.0)
            # Overlap window: new note attacking, old note (may be) releasing
            parts.append(_run_exact(eng, OVERLAP_SAMPS))
            # Release the old note explicitly after overlap window
            eng.note_off(midi_note)
            # Short release drain
            parts.append(_run_exact(eng, RELEASE_SAMPS))
        else:
            parts.append(_run_exact(eng, NOTE_SAMPS))
            eng.note_off(midi_note)
            parts.append(_run_exact(eng, RELEASE_SAMPS))
            parts.append(np.zeros(GAP_SAMPS, dtype=np.float32))
    return np.concatenate(parts), starts


def print_stats(audio, starts, label):
    diff = np.abs(np.diff(audio.astype(np.float64)))
    print(f"\n{'─'*66}")
    print(f"  {label}")
    print(f"  {'Note':<5} {'Peak':>7} {'RMS':>7} {'DC':>9} {'ZeroCross':>10} {'MaxJump':>9}")
    print(f"  {'─'*60}")
    seg_len = min(NOTE_SAMPS, NOTE_SAMPS - OVERLAP_SAMPS)
    for s, name in zip(starts, NOTE_NAMES):
        seg = audio[s : s + seg_len]
        if len(seg) == 0:
            continue
        d   = diff[s : s + seg_len - 1]
        peak = float(np.max(np.abs(seg)))
        rms  = float(np.sqrt(np.mean(seg**2)))
        dc   = float(np.mean(seg))
        zx   = int(np.sum(np.diff(np.sign(seg)) != 0))
        mxj  = float(np.max(d)) if len(d) else 0.0
        print(f"  {name:<5} {peak:>7.4f} {rms:>7.4f} {dc:>9.5f} {zx:>10} {mxj:>9.5f}")
    print(f"  {'─'*60}")
    glitch_threshold = 0.10
    glitches = np.where(diff > glitch_threshold)[0]
    print(f"  Global peak={np.max(np.abs(audio)):.4f}  RMS={np.sqrt(np.mean(audio**2)):.4f}")
    print(f"  Glitch candidates (|Δ|>{glitch_threshold}): {len(glitches)}")
    for gi in glitches[:20]:
        t_ms = gi / SAMPLE_RATE * 1000
        closest = min(range(len(starts)), key=lambda i: abs(starts[i] - gi))
        print(f"    sample {gi:8d}  t={t_ms:8.2f}ms  near={NOTE_NAMES[closest]}  Δ={diff[gi]:.5f}")


def draw_waveform(datasets, out_path):
    """datasets: list of (label, audio, starts) tuples."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BG = "#0d0d14"
    note_colors = plt.cm.Set2(np.linspace(0, 1, len(NOTE_NAMES)))
    n = len(datasets)
    heights = []
    for _ in datasets:
        heights += [2.5, 0.85]

    fig, axes = plt.subplots(n * 2, 1, figsize=(22, 3.8 * n),
                             gridspec_kw={"height_ratios": heights})
    fig.suptitle(
        "SynthEngine simulation — C3→C4  |  pure_sine  |  48000 Hz  |  BUFFER=480\n"
        "SEQ = sequential notes   OVL = overlapping notes (voice steal active)   |   Glitch map = |Δ| per sample",
        fontsize=10, fontweight="bold", color="#eee"
    )
    fig.patch.set_facecolor(BG)

    wave_colors   = ["#00c8ff", "#00ffaa", "#ffaa00", "#ff6688"]
    glitch_colors = ["#ff3333", "#ff8800", "#cc8800", "#cc44ff"]

    def shade(ax, starts, yhi=1.1):
        for i, s in enumerate(starts):
            x0 = s / SAMPLE_RATE
            x1 = (s + NOTE_SAMPS) / SAMPLE_RATE
            ax.axvspan(x0, x1, alpha=0.07, color=note_colors[i % len(note_colors)])
            ax.axvline(x0, color=note_colors[i % len(note_colors)], lw=0.5, alpha=0.5)
            ax.text((x0 + x1) / 2, yhi * 0.88, NOTE_NAMES[i],
                    ha="center", va="top", fontsize=6,
                    color=note_colors[i % len(note_colors)], fontweight="bold")

    def style(ax):
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_color("#333")
        ax.tick_params(colors="#777", labelsize=7)
        ax.yaxis.label.set_color("#999")
        ax.title.set_color("#ddd")

    for row, (label, audio, starts) in enumerate(datasets):
        ax_w = axes[row * 2]
        ax_g = axes[row * 2 + 1]
        t = np.arange(len(audio)) / SAMPLE_RATE
        wc = wave_colors[row % len(wave_colors)]
        gc = glitch_colors[row % len(glitch_colors)]

        ax_w.plot(t, audio, color=wc, lw=0.2, alpha=0.9)
        shade(ax_w, starts)
        ax_w.set_ylim(-1.2, 1.2)
        ax_w.set_xlim(0, t[-1])
        ax_w.axhline(0, color="#333", lw=0.3)
        ax_w.set_ylabel("Amp", fontsize=8)
        ax_w.set_title(f"{label} — waveform", fontsize=9)
        style(ax_w)

        d = np.abs(np.diff(audio.astype(np.float64)))
        t_d = np.arange(len(d)) / SAMPLE_RATE
        n_spikes = int(np.sum(d > 0.10))
        ax_g.fill_between(t_d, d, color=gc, alpha=0.75, lw=0)
        ax_g.axhline(0.10, color="#ffff00", lw=0.7, ls="--", alpha=0.8,
                     label=f"|Δ|=0.10  ({n_spikes} spikes)")
        shade(ax_g, starts, yhi=max(0.12, float(np.percentile(d, 99.9))))
        ax_g.set_xlim(0, t_d[-1])
        ax_g.set_ylabel("|Δ|", fontsize=8)
        ax_g.set_title(f"{label} — glitch map", fontsize=9)
        ax_g.legend(fontsize=7, loc="upper right", facecolor="#1a1a22", labelcolor="#ddd")
        style(ax_g)
        if row == len(datasets) - 1:
            ax_g.set_xlabel("Time (seconds)", color="#888", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close()
    print(f"\n  PNG saved: {out_path}")


if __name__ == "__main__":
    out_path = os.path.join(os.path.dirname(__file__), "octave_sim.png")

    print("=== MONO sequential ===")
    mono_seq,  mono_seq_s  = simulate_sequential("mono")
    print("\n=== MONO overlapping ===")
    mono_ovl,  mono_ovl_s  = simulate_overlapping("mono")
    print("\n=== UNISON sequential ===")
    uni_seq,   uni_seq_s   = simulate_sequential("unison")
    print("\n=== UNISON overlapping ===")
    uni_ovl,   uni_ovl_s   = simulate_overlapping("unison")

    print_stats(mono_seq,  mono_seq_s,  "MONO  sequential")
    print_stats(mono_ovl,  mono_ovl_s,  "MONO  overlapping (steal)")
    print_stats(uni_seq,   uni_seq_s,   "UNISON sequential")
    print_stats(uni_ovl,   uni_ovl_s,   "UNISON overlapping (steal)")

    datasets = [
        ("MONO seq",    mono_seq,  mono_seq_s),
        ("MONO ovl",    mono_ovl,  mono_ovl_s),
        ("UNISON seq",  uni_seq,   uni_seq_s),
        ("UNISON ovl",  uni_ovl,   uni_ovl_s),
    ]

    print("\nRendering waveform ...")
    draw_waveform(datasets, out_path)
    print("Done.")
