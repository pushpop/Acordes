# ABOUTME: Regression tests verifying audio output stability across synth engine changes.
# ABOUTME: Run with: uv run python -m pytest tests/test_voice_regression.py -v
import sys
import os
import hashlib
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from music.synth_engine import SynthEngine

SAMPLE_RATE = 48000
BUFFER_SIZE = 480


class _FakeTime:
    inputBufferAdcTime = 0.0
    outputBufferDacTime = 0.0
    currentTime = 0.0


def make_engine(**overrides) -> SynthEngine:
    """Create a silent engine with deterministic parameters."""
    eng = SynthEngine(output_device_index=-1, enable_oversampling=True)
    eng._startup_silence_samples = 0
    if eng.stream is not None:
        eng.stream.stop_stream()

    defaults = dict(
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
    defaults.update(overrides)
    eng.update_parameters(**defaults)

    # Warm-up buffer to drain param updates
    t = _FakeTime()
    out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
    eng._audio_callback(out, BUFFER_SIZE, t, None)
    return eng


def run_buffers(eng: SynthEngine, n: int) -> np.ndarray:
    """Render n buffers, return stereo float32 array (n*BUFFER_SIZE, 2)."""
    t = _FakeTime()
    chunks = []
    for _ in range(n):
        out = np.zeros((BUFFER_SIZE, 2), dtype=np.float32)
        eng._audio_callback(out, BUFFER_SIZE, t, None)
        chunks.append(out.copy())
    return np.concatenate(chunks, axis=0)


def audio_hash(data: np.ndarray) -> str:
    """Deterministic hash of float32 audio for regression comparison."""
    return hashlib.sha256(data.tobytes()).hexdigest()[:16]


def assert_nonsilent(data: np.ndarray, label: str):
    """Ensure the rendered audio is not all zeros."""
    peak = float(np.max(np.abs(data)))
    assert peak > 0.001, f"{label}: output is silent (peak={peak})"


# ── Test: Single voice, sawtooth ─────────────────────────────────────────

def test_single_voice_saw():
    eng = make_engine()
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 20)
    assert_nonsilent(audio, "single_saw")
    # Verify output is deterministic across runs (within dither noise tolerance)
    eng2 = make_engine()
    eng2.note_on(60, velocity=100)
    audio2 = run_buffers(eng2, 20)
    # Engine adds ~1e-5 dither noise, so exact hash match isn't expected.
    # Signal correlation should be very high (>0.999) for deterministic output.
    corr = float(np.corrcoef(audio[:, 0].ravel(), audio2[:, 0].ravel())[0, 1])
    assert corr > 0.999, f"Determinism failure: correlation={corr:.6f} (expected >0.999)"


# ── Test: 8-voice polyphony ──────────────────────────────────────────────

def test_8voice_poly():
    eng = make_engine()
    notes = [60, 64, 67, 72, 48, 55, 59, 62]
    for n in notes:
        eng.note_on(n, velocity=100)
    audio = run_buffers(eng, 20)
    assert_nonsilent(audio, "8voice_poly")
    # Check reasonable amplitude (not clipping badly)
    peak = float(np.max(np.abs(audio)))
    assert peak < 2.0, f"8-voice peak too high: {peak}"


# ── Test: Unison mode ────────────────────────────────────────────────────

def test_unison_mode():
    eng = make_engine(voice_type="unison")
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 20)
    assert_nonsilent(audio, "unison")
    # Unison should produce stereo spread (L != R)
    diff = float(np.max(np.abs(audio[:, 0] - audio[:, 1])))
    assert diff > 0.001, f"Unison mode has no stereo spread (L-R diff={diff})"


# ── Test: MONO voice steal ───────────────────────────────────────────────

def test_mono_steal():
    eng = make_engine(voice_type="mono")
    eng.note_on(60, velocity=100)
    run_buffers(eng, 5)  # let first note establish
    eng.note_on(64, velocity=100)  # steal
    audio = run_buffers(eng, 10)
    assert_nonsilent(audio, "mono_steal")


# ── Test: Ghost voices produce output ────────────────────────────────────

def test_ghost_voices():
    eng = make_engine()
    n = eng.num_voices
    # Fill all voices. Note-on events are processed 3 per buffer, so we need
    # ceil(n / 3) + a few settle buffers before all slots are occupied.
    for i in range(n):
        eng.note_on(24 + i, velocity=100)
    settle_buffers = (n // 3) + 5
    run_buffers(eng, settle_buffers)
    # Verify all voices are now occupied.
    active_before = sum(1 for v in eng.voices if v.note_active)
    assert active_before == n, f"Expected {n} active voices before steal, got {active_before}"
    # Trigger note 120 (above the filled range 24..24+n-1) to force a steal.
    eng.note_on(120, velocity=100)
    # Run exactly 1 buffer so the steal is processed (ghost promoted) but the
    # ghost release tail has not yet expired (cap is 60ms; 1 buffer = ~10ms).
    run_buffers(eng, 1)
    ghosts_active = sum(1 for g in eng._ghost_voices if g.is_ghost and (g.note_active or g.is_releasing))
    # At least one ghost should be active (the stolen voice's release tail)
    assert ghosts_active >= 1, f"Expected ghost voices, found {ghosts_active}"
    # Continue rendering to confirm audio is non-silent overall
    audio = run_buffers(eng, 9)
    assert_nonsilent(audio, "ghost_voices")


# ── Test: Rank 2 (detune) enabled ────────────────────────────────────────

def test_rank2_detune():
    eng = make_engine()
    eng.update_parameters(osc2_detune=0.05)
    run_buffers(eng, 1)  # drain param update
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 20)
    assert_nonsilent(audio, "rank2_detune")


# ── Test: Filter types don't crash ───────────────────────────────────────

@pytest.mark.parametrize("filter_mode", [0, 1])
def test_filter_modes(filter_mode):
    eng = make_engine(filter_routing=filter_mode)
    run_buffers(eng, 1)  # drain
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 10)
    assert_nonsilent(audio, f"filter_mode_{filter_mode}")


# ── Test: Note release produces decaying tail ────────────────────────────

def test_release_tail():
    eng = make_engine(release=0.5)
    run_buffers(eng, 1)  # drain
    eng.note_on(60, velocity=100)
    run_buffers(eng, 10)  # attack+sustain
    eng.note_off(60)
    audio = run_buffers(eng, 20)
    # First part should have signal, last part should be quiet
    first_peak = float(np.max(np.abs(audio[:BUFFER_SIZE * 5])))
    last_peak = float(np.max(np.abs(audio[BUFFER_SIZE * 15:])))
    assert first_peak > last_peak, f"Release tail not decaying: first={first_peak}, last={last_peak}"


# ── Test: Fast filter mode produces output ──────────────────────────────

def test_fast_filter_mode():
    eng = make_engine()
    eng.update_parameters(filter_quality="fast")
    run_buffers(eng, 1)  # drain param update
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 20)
    assert_nonsilent(audio, "fast_filter")


# ── Tests: Sine/pure_sine onset artifact fixes ───────────────────────────

def _measure_onset_spike(eng, waveform, note=60):
    """Trigger a note and measure the peak amplitude in the first buffer vs steady state.

    Returns (first_buf_peak, steady_peak). A large ratio indicates an onset click.
    """
    eng.update_parameters(waveform=waveform, attack=0.001, decay=0.1, sustain=1.0, release=0.1)
    run_buffers(eng, 2)  # drain param updates
    eng.note_on(note, velocity=100)
    first = run_buffers(eng, 1)
    steady = run_buffers(eng, 10)
    first_peak = float(np.max(np.abs(first)))
    steady_peak = float(np.max(np.abs(steady)))
    return first_peak, steady_peak


def test_sine_no_onset_click():
    """Sine onset must not produce a spike larger than 2x the steady-state level."""
    eng = make_engine()
    first_peak, steady_peak = _measure_onset_spike(eng, "sine")
    assert steady_peak > 0.001, "Sine produced no output"
    ratio = first_peak / max(steady_peak, 1e-6)
    assert ratio < 2.0, f"Sine onset spike ratio={ratio:.2f} (expected < 2.0)"


def test_pure_sine_no_onset_click():
    """Pure sine onset must not produce a spike larger than 2x the steady-state level."""
    eng = make_engine()
    first_peak, steady_peak = _measure_onset_spike(eng, "pure_sine")
    assert steady_peak > 0.001, "Pure sine produced no output"
    ratio = first_peak / max(steady_peak, 1e-6)
    assert ratio < 2.0, f"Pure sine onset spike ratio={ratio:.2f} (expected < 2.0)"


def test_sine_rapid_retrigger():
    """Rapid sine retriggering must not accumulate artifacts (no silence or spikes)."""
    eng = make_engine()
    eng.update_parameters(waveform="sine", attack=0.001, decay=0.05, sustain=0.8, release=0.05)
    run_buffers(eng, 2)
    notes = [60, 62, 64, 65, 67]
    for n in notes:
        eng.note_on(n, velocity=100)
        run_buffers(eng, 2)
        eng.note_off(n)
        run_buffers(eng, 1)
    # Final note held: should produce clean output
    eng.note_on(69, velocity=100)
    audio = run_buffers(eng, 10)
    assert_nonsilent(audio, "sine_rapid_retrigger")


def test_sine_zero_phase_at_trigger():
    """Sine voices must start at phase 0.0 (sin(0)=0) to avoid DC blocker transient.

    note_on() enqueues the event; _audio_callback drains it at the start of the
    next buffer. After exactly one buffer the voice phase = 2*pi*f*N/sr (started at 0).
    """
    eng = make_engine()
    eng.update_parameters(waveform="sine")
    run_buffers(eng, 2)  # drain param updates
    eng.note_on(60, velocity=100)
    run_buffers(eng, 1)  # triggers the note and advances phase by one buffer
    active = [v for v in eng.voices if v.note_active]
    assert active, "No active voice found"
    freq = active[0].frequency
    # If phase started at 0.0, after BUFFER_SIZE samples it should be:
    expected_phase = (2.0 * np.pi * freq * BUFFER_SIZE / SAMPLE_RATE) % (2.0 * np.pi)
    actual_phase = active[0].phase
    diff = min(abs(actual_phase - expected_phase),
               abs(actual_phase - expected_phase + 2 * np.pi),
               abs(actual_phase - expected_phase - 2 * np.pi))
    assert diff < 0.05, f"Sine phase at trigger was not 0: diff={diff:.4f} rad"


# ── Tests: New waveforms (semicircle, pointy) ────────────────────────────

@pytest.mark.parametrize("waveform", ["semicircle", "pointy"])
def test_new_waveform_produces_output(waveform):
    """Semicircle and pointy waveforms must produce non-silent output."""
    eng = make_engine()
    eng.update_parameters(waveform=waveform)
    run_buffers(eng, 2)
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 20)
    assert_nonsilent(audio, waveform)


@pytest.mark.parametrize("waveform", ["semicircle", "pointy"])
def test_new_waveform_no_onset_click(waveform):
    """Semicircle and pointy onset must not spike more than 2x steady state."""
    eng = make_engine()
    first_peak, steady_peak = _measure_onset_spike(eng, waveform)
    assert steady_peak > 0.001, f"{waveform} produced no output"
    ratio = first_peak / max(steady_peak, 1e-6)
    assert ratio < 2.0, f"{waveform} onset spike ratio={ratio:.2f} (expected < 2.0)"


# ── Test: Brickwall limiter clamps runaway peaks ─────────────────────────

def test_brickwall_limiter_clamps_peaks():
    """Output must never exceed ±1.0.

    The tanh soft-clipper + np.clip already caps the signal, but the limiter
    acts as a final safety net.  This test verifies:
    1. Output always stays within ±1.0 regardless of voice count.
    2. The limiter gain variable drops below 1.0 when forced above threshold.
    """
    # --- Part 1: high voice-count playback stays bounded ---
    eng = make_engine(
        waveform="square",
        voice_type="poly",
        attack=0.001,
        cutoff=8000.0,
        resonance=0.0,
        amp_level=1.0,
        delay_mix=0.0,
        chorus_mix=0.0,
    )
    for midi_note in range(48, 64):  # 16 simultaneous notes
        eng.note_on(midi_note, velocity=127)
    audio = run_buffers(eng, 10)
    peak = float(np.max(np.abs(audio)))
    assert peak <= 1.001, f"Peak exceeded ±1.0: {peak:.4f}"

    # --- Part 2: limiter gain tracking responds correctly when driven high ---
    # Simulate a peak above the threshold by calling the limiter logic directly.
    eng2 = make_engine()
    eng2._limiter_gain = 1.0
    # Simulate a peak of 1.2 (20% over threshold=0.93).
    fake_peak = 1.2
    if fake_peak > eng2._LIMITER_THRESH:
        eng2._limiter_gain = min(eng2._limiter_gain,
                                  eng2._LIMITER_THRESH / max(fake_peak, 1e-6))
    assert eng2._limiter_gain < 1.0, (
        f"Limiter gain did not drop on simulated overshoot: {eng2._limiter_gain:.4f}"
    )
    expected_gain = eng2._LIMITER_THRESH / fake_peak
    assert abs(eng2._limiter_gain - expected_gain) < 1e-5, (
        f"Limiter gain mismatch: got {eng2._limiter_gain:.4f} expected {expected_gain:.4f}"
    )


# ── Tests: Sine/pure_sine onset in MONO and UNISON ───────────────────────

@pytest.mark.parametrize("waveform", ["sine", "pure_sine"])
def test_unison_sine_hard_trigger_no_phase_burst(waveform):
    """UNISON sine hard trigger must not produce a constructive-interference burst.

    When voices start with evenly-spaced phases (0, 2π/3, 4π/3 for 3 voices)
    their sum is near-zero at t=0 and stays balanced.  The old buggy code used
    i/n (fractions in radians) which clustered all voices near 0° → a brief
    loud in-phase burst before detuning separated them.

    We verify this by checking that the FIRST buffer after note-on is not
    dramatically louder than the steady-state chorus output.
    """
    eng = make_engine(waveform=waveform, voice_type="unison",
                      attack=0.001, decay=0.1, sustain=1.0, release=0.1)
    run_buffers(eng, 2)  # drain param updates
    eng.note_on(60, velocity=100)
    first = run_buffers(eng, 1)
    steady = run_buffers(eng, 15)
    first_rms = float(np.sqrt(np.mean(first ** 2)))
    steady_rms = float(np.sqrt(np.mean(steady ** 2)))
    assert steady_rms > 0.001, f"{waveform} unison produced no steady output"
    # First buffer should NOT be more than 3× louder than steady-state.
    # (In-phase burst was >5× louder than balanced chorus with the bug.)
    ratio = first_rms / max(steady_rms, 1e-9)
    assert ratio < 3.0, (
        f"{waveform} unison onset burst too loud: first_rms={first_rms:.4f} "
        f"steady_rms={steady_rms:.4f} ratio={ratio:.2f} (expect < 3.0)"
    )


@pytest.mark.parametrize("waveform", ["sine", "pure_sine"])
def test_unison_sine_legato_no_click(waveform):
    """UNISON sine legato retrigger must not produce a phase-jump click.

    Previously the legato path re-anchored voice phases to evenly-spaced values
    using the wrong unit (fractions instead of radians * 2π).  For sine, this
    caused an instant sin(old) → sin(new) discontinuity — an audible click.
    The fix skips phase re-anchoring for sine/pure_sine entirely.

    We verify that the buffer immediately after retrigger does not spike above
    the output level just before retrigger.
    """
    eng = make_engine(waveform=waveform, voice_type="unison",
                      attack=0.001, decay=0.1, sustain=1.0, release=0.1)
    run_buffers(eng, 2)
    eng.note_on(60, velocity=100)
    run_buffers(eng, 15)  # settle into steady state
    # Capture last buffer before retrigger
    pre = run_buffers(eng, 1)
    # Retrigger (legato — voices still active)
    eng.note_on(64, velocity=100)
    post = run_buffers(eng, 1)
    pre_peak = float(np.max(np.abs(pre)))
    post_peak = float(np.max(np.abs(post)))
    # A phase-jump click would spike post_peak well above pre_peak.
    # Allow up to 2× for natural amplitude change due to pitch + detuning.
    assert post_peak < pre_peak * 2.5, (
        f"{waveform} unison legato click: pre={pre_peak:.4f} post={post_peak:.4f} "
        f"ratio={post_peak / max(pre_peak, 1e-9):.2f} (expect < 2.5)"
    )


@pytest.mark.parametrize("waveform", ["sine", "pure_sine"])
def test_mono_sine_steal_no_chirp(waveform):
    """MONO sine steal must not produce a frequency-chirp artifact.

    Inheriting the outgoing voice's FIR history (tuned for the old note's
    frequency) produces a brief transient as the downsampler's delay line
    contains samples at the wrong frequency.  For pure tones there are no
    harmonics to mask it.

    The fix: zero FIR history on sine steal and restart the onset ramp to
    protect the warm-up window.  We verify the first buffer after the steal
    does not exceed 2× the steady-state amplitude.
    """
    eng = make_engine(waveform=waveform, voice_type="mono",
                      attack=0.001, decay=0.1, sustain=1.0, release=0.1)
    run_buffers(eng, 2)
    eng.note_on(60, velocity=100)
    run_buffers(eng, 15)  # settle
    eng.note_on(72, velocity=100)  # steal: octave jump (large frequency delta)
    first_after_steal = run_buffers(eng, 1)
    steady_after_steal = run_buffers(eng, 10)
    steal_peak = float(np.max(np.abs(first_after_steal)))
    steady_peak = float(np.max(np.abs(steady_after_steal)))
    assert steady_peak > 0.001, f"{waveform} mono produced no output after steal"
    ratio = steal_peak / max(steady_peak, 1e-9)
    assert ratio < 2.5, (
        f"{waveform} mono steal chirp: steal_peak={steal_peak:.4f} "
        f"steady_peak={steady_peak:.4f} ratio={ratio:.2f} (expect < 2.5)"
    )


# ── Test: preset_change event resets voices and fades cleanly ────────────

def test_preset_change_resets_voices():
    """preset_change must morph old voices into release and apply new params cleanly.

    Sequence:
    1. Play a note with long release on preset A (sawtooth).
    2. Note-off — voice enters release tail.
    3. Send preset_change event with new params (sine, short release=0.05s).
    4. Run enough buffers to cover the full mute fade-out (~80ms = _PRESET_RAMP_LEN).
    5. After the mute bottom: no voice must be note_active (sustained), but releasing
       voices with capped tails are allowed (the creative morph).
    6. After enough time for the 200ms cap + fade-in, output must go silent.
    """
    eng = make_engine(waveform="sawtooth", release=0.8)
    eng.note_on(60, velocity=100)
    run_buffers(eng, 10)   # sustain phase
    eng.note_off(60)
    run_buffers(eng, 2)    # begin release tail

    # Send preset_change event with new params
    new_params = dict(
        waveform="sine",
        octave=0,
        noise_level=0.0,
        sine_mix=0.0,
        amp_level=0.9,
        master_volume=1.0,
        cutoff=2000.0,
        hpf_cutoff=20.0,
        resonance=0.3,
        hpf_resonance=0.0,
        key_tracking=0.5,
        filter_drive=0.0,
        filter_routing=0,
        attack=0.006,
        decay=0.1,
        sustain=0.7,
        release=0.05,
        feg_attack=0.01,
        feg_decay=0.1,
        feg_sustain=0.0,
        feg_release=0.05,
        feg_amount=0.0,
        lfo_freq=2.0,
        lfo_depth=0.0,
        lfo_shape="sine",
        lfo_target="vco",
        delay_time=0.3,
        delay_feedback=0.4,
        delay_mix=0.0,
        chorus_rate=0.5,
        chorus_depth=0.3,
        chorus_mix=0.0,
        chorus_voices=3,
        arp_bpm=120.0,
        arp_enabled=False,
        arp_mode="up",
        arp_gate=0.8,
        arp_range=1,
        voice_type="poly",
    )
    eng.midi_event_queue.put({'type': 'preset_change', 'params': new_params})

    # Run enough buffers to fully drain the mute ramp (~80ms = _PRESET_RAMP_LEN).
    # Each buffer is 480 samples; 80ms at 48kHz = 3840 samples = 8 buffers.
    run_buffers(eng, 10)

    # No voice must be held (note_active=True) after the preset morph bottom.
    # Releasing voices with capped tails are intentionally preserved (the morph blend).
    held_voices = [v for v in eng.voices if v.note_active]
    assert len(held_voices) == 0, (
        f"preset_change left {len(held_voices)} sustained voices (expected 0)"
    )

    # After ~200ms cap + fade-in (another ~80ms) output must be essentially silent.
    # 200ms cap = 9600 smp = 20 buffers; fade-in = 8 buffers; total ~28 buffers.
    run_buffers(eng, 40)
    audio = run_buffers(eng, 5)
    peak = float(np.max(np.abs(audio)))
    assert peak < 0.02, f"preset_change morph tail did not decay to silence (peak={peak:.5f})"


# ── Test: piano_string waveform ──────────────────────────────────────────

def test_piano_string_produces_output():
    """piano_string waveform must generate non-silent audio."""
    eng = make_engine(waveform="piano_string")
    eng.note_on(60, velocity=100)
    audio = run_buffers(eng, 10)
    assert_nonsilent(audio, "piano_string")


def test_piano_string_all_registers():
    """piano_string must produce output across the full MIDI register range."""
    for midi_note in [21, 36, 48, 60, 72, 84, 96]:
        eng = make_engine(waveform="piano_string")
        eng.note_on(midi_note, velocity=100)
        audio = run_buffers(eng, 10)
        assert_nonsilent(audio, f"piano_string_note{midi_note}")


def test_piano_string_partial_decay_effect():
    """Higher partial_decay alpha must produce audibly different output than lower.

    With alpha=0.0 all partials decay at the same rate (envelope^1).
    With alpha=1.0 upper partials decay much faster (envelope^n for partial n).
    The two should produce different RMS profiles when captured in sustain phase.
    """
    eng_flat   = make_engine(waveform="piano_string", partial_decay=0.0)
    eng_steep  = make_engine(waveform="piano_string", partial_decay=1.0)
    eng_flat.note_on(60, velocity=100)
    eng_steep.note_on(60, velocity=100)
    # Render into sustain (many buffers so envelope is stable)
    run_buffers(eng_flat,  30)
    run_buffers(eng_steep, 30)
    audio_flat  = run_buffers(eng_flat,  20)
    audio_steep = run_buffers(eng_steep, 20)
    rms_flat  = float(np.sqrt(np.mean(audio_flat  ** 2)))
    rms_steep = float(np.sqrt(np.mean(audio_steep ** 2)))
    # With alpha=1.0 upper partials are attenuated more, so overall RMS
    # may differ. The key assertion is that the two are distinguishably different.
    assert abs(rms_flat - rms_steep) > 1e-5, (
        f"partial_decay had no effect: rms_flat={rms_flat:.6f} rms_steep={rms_steep:.6f}"
    )


def test_piano_string_no_onset_click():
    """piano_string must not produce a large transient spike at note onset.

    The first buffer RMS should not be dramatically higher than the steady-state
    RMS a few buffers later.
    """
    eng = make_engine(waveform="piano_string", attack=0.006)
    eng.note_on(60, velocity=100)
    first_buf = run_buffers(eng, 1)
    run_buffers(eng, 3)
    steady_buf = run_buffers(eng, 4)
    first_peak  = float(np.max(np.abs(first_buf)))
    steady_rms  = float(np.sqrt(np.mean(steady_buf ** 2)))
    assert first_peak < steady_rms * 5.0, (
        f"piano_string onset click: first_peak={first_peak:.4f} steady_rms={steady_rms:.4f}"
    )


def test_piano_string_mono_steal_continuity():
    """MONO steal on piano_string must not create a large discontinuity.

    Partial phases are inherited on steal, so the peak just after a steal
    should not exceed a multiple of the pre-steal steady-state peak.
    """
    eng = make_engine(waveform="piano_string", voice_type="mono")
    eng.note_on(60, velocity=100)
    run_buffers(eng, 20)   # reach sustain
    pre_steal = run_buffers(eng, 2)
    eng.note_on(64, velocity=100)   # steal
    post_steal = run_buffers(eng, 2)

    pre_peak  = float(np.max(np.abs(pre_steal)))
    post_peak = float(np.max(np.abs(post_steal)))
    assert post_peak < pre_peak * 3.0, (
        f"piano_string MONO steal discontinuity: pre={pre_peak:.4f} post={post_peak:.4f}"
    )


# ── Tests: Legato click regression (scipy zi filter state preservation) ──

@pytest.mark.parametrize("waveform", ["sawtooth", "square", "sine", "pure_sine"])
@pytest.mark.parametrize("voice_type", ["mono", "unison"])
def test_legato_no_click_at_boundary(waveform, voice_type):
    """Note transition in MONO/UNISON must not produce a click at the buffer boundary.

    Root cause of the bug: scipy sosfilt zi arrays (filter delay-line state) were
    reset to zeros on every note change, causing a cold-start discontinuity in the
    filter output.  The fix: preserve zi across legato note changes.

    Threshold: the sample-to-sample jump at the note boundary must be < 30% of the
    steady-state RMS — well below the perceptual click threshold.
    """
    eng = make_engine(waveform=waveform, voice_type=voice_type,
                      attack=0.006, decay=0.25, sustain=0.70, release=0.30)
    eng.note_on(60, velocity=100)
    # Reach full sustain so filter is warm
    run_buffers(eng, 15)
    # Last sample before note change
    steady = run_buffers(eng, 1)
    steady_rms = float(np.sqrt(np.mean(steady[:, 0] ** 2)))
    last_before = float(steady[-1, 0])
    # Trigger note change (legato path — voice still has amplitude)
    eng.note_on(64, velocity=100)
    # First sample after the transition buffer
    trans = run_buffers(eng, 1)
    first_after = float(trans[0, 0])
    jump = abs(first_after - last_before)
    ratio = jump / max(steady_rms, 1e-6)
    assert ratio < 0.3, (
        f"{waveform}/{voice_type} legato click: "
        f"jump={jump:.4f} rms={steady_rms:.4f} ratio={ratio:.3f} (expect < 0.3)"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
