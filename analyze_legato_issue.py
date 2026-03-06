#!/usr/bin/env python3
"""
Diagnostic analysis of MONO/UNISON legato envelope behavior
to identify the source of artifacts on note press
"""

print("""
╔════════════════════════════════════════════════════════════════════╗
║         MONO/UNISON NOTE TRANSITION ARTIFACT ANALYSIS              ║
╚════════════════════════════════════════════════════════════════════╝

CURRENT LEGATO IMPLEMENTATION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When note is pressed while previous note is ACTIVE:

✓ Updates: midi_note, frequency, base_frequency
✓ Updates: velocity_target, velocity_current, velocity
✓ Sets: steal_start_level = last_envelope_level
✓ Sets: onset_samples = 0
✓ KEEPS: envelope_time (doesn't reset)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POTENTIAL ISSUES IDENTIFIED:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. STEAL_START_LEVEL CROSSFADE CONFLICT
   ─────────────────────────────────────
   Problem: In legato mode, we set steal_start_level = last_envelope_level

   Effect in _apply_envelope() [line 697-706]:
   - Creates 8ms linear crossfade if steal_start_level > 0.001
   - Crossfade: from old level → new attack envelope

   Issue: But we DON'T restart envelope_time, so attack never happens!
   Result: Crossfade from sustain → sustain = no effect
           But the envelope calculation logic is confused

   ➜ HYPOTHESIS: The crossfade code path is executing when it shouldn't

2. ENVELOPE CALCULATION DURING LEGATO
   ──────────────────────────────────
   In _apply_envelope():
   - times = voice.envelope_time + np.arange(num_samples) * dt
   - Since envelope_time wasn't reset, times continues BEYOND attack+decay
   - Envelope is at sustain level

   But: steal_start_level creates crossfade code that doesn't expect this!

   ➜ HYPOTHESIS: The crossfade mechanism expects envelope to restart

3. ONSET RAMP RESET DURING SUSTAIN
   ───────────────────────────────
   Problem: We reset onset_samples = 0 for DC blocker stability

   Effect: The DC blocker gets a fade-in again
   - DC blocker does: output = input - xp + coeff * yp
   - Fade-in smooths this: output *= ramp (0→1 over ~3ms)

   Issue: Fade-in happens while envelope is at sustain level
   Result: Amplitude ramp-up during sustain = audible "surge"

   ➜ HYPOTHESIS: This could be the culprit!

4. VELOCITY SYNC TIMING
   ───────────────────
   We set velocity_current = vel immediately
   But velocity smoothing in audio callback [line 1308-1312]:
   - velocity_current *= 0.92 + velocity_target * 0.08

   If velocity changed from (say) 0.8 to 1.0:
   - We sync to 1.0 immediately
   - Smoothing then blends: 1.0*0.92 + 1.0*0.08 = 1.0 (no change)
   - But the envelope still uses OLD velocity for sustain calculation!

   ➜ HYPOTHESIS: Velocity envelope level mismatch

5. FILTER STATE PRESERVATION
   ─────────────────────────
   Good: Filter states are NOT reset in legato

   But: When frequency changes, filter resonance might ring
   Example:
   - Old note at 440Hz with resonance=0.9
   - Filter is ringing with note's overtones
   - New note at 880Hz starts
   - Old filter resonance still ringing = frequency collision = CLICK

   ➜ HYPOTHESIS: Stale filter resonance with frequency change

RECOMMENDED DIAGNOSTIC TESTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Test 1: Disable steal_start_level in legato mode
   Set: mono_v.steal_start_level = 0.0 (don't use crossfade)
   Expected: If this was the culprit, artifacts should disappear

Test 2: Don't reset onset_samples in legato mode
   Remove: mono_v.onset_samples = 0
   Expected: If this was the culprit, artifacts might get worse

Test 3: Test with resonance = 0.0
   Expected: If filter resonance was culprit, no artifacts with low res

Test 4: Test with different sustain levels
   sustain=0.95 (high) vs sustain=0.1 (low)
   Expected: Low sustain might have MORE artifacts (lower amplitude)

Test 5: Disable legato, force hard trigger every note
   In MONO: Always call trigger(), even during legato
   Expected: No artifacts, but also less "musical"

NEXT STEPS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. TEST: Remove steal_start_level from legato transitions
2. VERIFY: Does it fix the artifacts?
3. If yes: steal_start_level crossfade was the issue
4. If no: Try disabling onset_samples reset instead
5. Isolate: Find which parameter causes the click
""")

print("\n" + "="*70)
print("SPECIFIC CODE LOCATIONS TO MODIFY FOR TESTING:")
print("="*70)

print("""
FILE: music/synth_engine.py

LOCATION 1 - MONO Mode Legato [~line 1080-1085]:
    mono_v.steal_start_level = mono_v.last_envelope_level if ...

    TEST A: Comment this line out
    mono_v.steal_start_level = 0.0  # Disable crossfade

    TEST B: Comment out onset_samples reset instead
    # mono_v.onset_samples = 0


LOCATION 2 - UNISON Mode Legato [~line 1118-1119]:
    v.steal_start_level = v.last_envelope_level if ...

    TEST: Same as MONO - try disabling steal_start_level


LOCATION 3 - Audio Callback Envelope [line 697-706]:
    The crossfade code path - verify it's not executing in legato mode
    Add debug output:
    if voice.steal_start_level > 0.001:
        print(f"CROSSFADE ACTIVE: {voice.steal_start_level}, "
              f"envelope_time={voice.envelope_time}")
""")

print("\n" + "="*70)
print("MY BEST GUESS:")
print("="*70)
print("""
The issue is likely ONE of these TWO:

1. STEAL_START_LEVEL CROSSFADE (60% confidence)
   ➜ The 8ms crossfade code expects envelope to restart (attack phase)
   ➜ But in legato, we DON'T restart envelope
   ➜ This creates a conflict in the envelope calculation

2. ONSET_SAMPLES RESET (40% confidence)
   ➜ Resetting onset_samples creates a fade-in ramp DURING sustain
   ➜ This adds an extra amplitude ramp that causes audible surge

RECOMMENDATION:
Test by REMOVING the steal_start_level line from legato transitions.
If artifacts disappear, that was the culprit.
If not, try removing onset_samples reset instead.
""")
