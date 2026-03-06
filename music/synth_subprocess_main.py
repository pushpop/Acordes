"""ABOUTME: Subprocess entry point and main event loop.
ABOUTME: Runs in child process, owns SynthEngine instance and audio callback thread."""

import queue
import sys
import time

from music.synth_engine import SynthEngine
from music.synth_ipc import MIDIEvent, ParameterUpdate, QueryRequest, QueryResponse, MuteGateEvent, DrumTriggerEvent


def synth_subprocess_main(from_main_queue, to_main_queue):
    """
    Main loop running in child process.
    Args:
        from_main_queue: Inbound queue (messages FROM main process to this subprocess).
        to_main_queue:   Outbound queue (responses FROM this subprocess TO main process).

    - Creates SynthEngine instance (separate GIL)
    - Processes IPC events (MIDI, parameter updates, queries)
    - Generates audio via PyAudio callback thread
    """
    engine = None
    try:
        engine = SynthEngine()

        while True:
            # Block briefly waiting for a message (avoids busy-spin, low latency)
            try:
                msg = from_main_queue.get(timeout=0.005)
            except queue.Empty:
                # No message within 5ms — loop back and wait again
                continue

            # None is the shutdown sentinel
            if msg is None:
                break

            # Process MIDI events
            if isinstance(msg, MIDIEvent):
                try:
                    if msg.type == "note_on":
                        engine.note_on(msg.note, int(msg.velocity * 127))
                    elif msg.type == "note_off":
                        engine.note_off(msg.note)
                    elif msg.type == "all_notes_off":
                        engine.all_notes_off()
                except Exception as e:
                    print(f"[synth subprocess] MIDI error: {e}", file=sys.stderr)

            # Process mute gate (for randomize click suppression)
            elif isinstance(msg, MuteGateEvent):
                try:
                    engine.midi_event_queue.put({'type': 'mute_gate'})
                except Exception as e:
                    print(f"[synth subprocess] mute gate error: {e}", file=sys.stderr)

            # Process parameter updates (enqueued via engine's own queue for thread safety)
            elif isinstance(msg, ParameterUpdate):
                try:
                    engine.update_parameters(**{msg.param_name: msg.value})
                except Exception as e:
                    print(f"[synth subprocess] param update error ({msg.param_name}): {e}", file=sys.stderr)

            # Process atomic drum trigger (params + note_on bundled)
            elif isinstance(msg, DrumTriggerEvent):
                try:
                    engine.drum_trigger(msg.note, msg.velocity, msg.params)
                except Exception as e:
                    print(f"[synth subprocess] drum trigger error: {e}", file=sys.stderr)

            # Process state queries
            elif isinstance(msg, QueryRequest):
                try:
                    response = _handle_query(engine, msg)
                    to_main_queue.put(response)
                except Exception as e:
                    to_main_queue.put(QueryResponse(msg.request_id, None, str(e)))

    except Exception as e:
        print(f"[synth subprocess] fatal error: {e}", file=sys.stderr)
    finally:
        if engine is not None:
            try:
                engine.all_notes_off()
                engine.close()
            except Exception:
                pass


def _handle_query(engine: SynthEngine, request: QueryRequest) -> QueryResponse:
    """Handle synchronous state queries from main process."""
    try:
        if request.query == "get_presets":
            data = engine.preset_manager.get_all_names()
            return QueryResponse(request.request_id, data, None)

        elif request.query == "get_preset_data":
            name = request.args.get("name", "")
            data = engine.preset_manager.load(name)
            return QueryResponse(request.request_id, data, None)

        elif request.query == "get_state":
            # Full parameter snapshot — must stay in sync with SynthEngine.get_current_params()
            state = {
                "waveform":       engine.waveform,
                "octave":         engine.octave,
                "noise_level":    engine.noise_level_target,
                "amp_level":      engine.amp_level,
                "cutoff":         engine.cutoff,
                "hpf_cutoff":     engine.hpf_cutoff,
                "resonance":      engine.resonance,
                "hpf_resonance":  engine.hpf_resonance,
                "key_tracking":   engine.key_tracking_target,
                "attack":         engine.attack,
                "decay":          engine.decay,
                "sustain":        engine.sustain,
                "release":        engine.release,
                "rank2_enabled":  engine.rank2_enabled,
                "rank2_waveform": engine.rank2_waveform,
                "rank2_detune":   engine.rank2_detune,
                "rank2_mix":      engine.rank2_mix,
                "sine_mix":       engine.sine_mix,
                "lfo_freq":       engine.lfo_freq,
                "lfo_vco_mod":    engine.lfo_vco_mod,
                "lfo_vcf_mod":    engine.lfo_vcf_mod,
                "lfo_vca_mod":    engine.lfo_vca_mod,
                "lfo_shape":      engine.lfo_shape,
                "lfo_target":     engine.lfo_target,
                "lfo_depth":      engine.lfo_depth,
                "delay_time":     engine.delay_time,
                "delay_feedback": engine.delay_feedback,
                "delay_mix":      engine.delay_mix,
                "chorus_rate":    engine.chorus_rate,
                "chorus_depth":   engine.chorus_depth,
                "chorus_mix":     engine.chorus_mix,
                "chorus_voices":  engine.chorus_voices,
                "arp_enabled":    engine.arp_enabled,
                "arp_mode":       engine.arp_mode,
                "arp_gate":       engine.arp_gate,
                "arp_range":      engine.arp_range,
                "voice_type":     engine.voice_type,
                "feg_attack":     engine.feg_attack,
                "feg_decay":      engine.feg_decay,
                "feg_sustain":    engine.feg_sustain,
                "feg_release":    engine.feg_release,
                "feg_amount":     engine.feg_amount,
            }
            return QueryResponse(request.request_id, state, None)

        else:
            return QueryResponse(request.request_id, None, f"Unknown query: {request.query}")

    except Exception as e:
        return QueryResponse(request.request_id, None, str(e))
