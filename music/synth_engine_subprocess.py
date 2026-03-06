"""ABOUTME: Subprocess wrapper maintaining SynthEngine interface via IPC.
ABOUTME: Spawns and manages a child process running the audio engine with complete isolation."""

import multiprocessing
import sys
import time
from typing import Any, Dict, Optional

from music.synth_ipc import MIDIEvent, ParameterUpdate, QueryRequest, QueryResponse, MuteGateEvent, DrumTriggerEvent


class _MIDIQueueProxy:
    """Proxy that converts dict-based MIDI events to IPC messages."""

    def __init__(self, to_synth_queue: multiprocessing.Queue):
        self.queue = to_synth_queue

    def put(self, item: Any):
        """Put a MIDI event or special message into the queue."""
        if isinstance(item, dict):
            # Handle special message types
            msg_type = item.get("type")
            if msg_type == "mute_gate":
                # Special event for randomize click suppression
                self.queue.put(MuteGateEvent(time.time()))
            elif msg_type == "note_on":
                event = MIDIEvent(
                    "note_on",
                    item.get("note", 0),
                    item.get("velocity", 127) / 127.0,
                    time.time(),
                )
                self.queue.put(event)
            elif msg_type == "note_off":
                event = MIDIEvent(
                    "note_off",
                    item.get("note", 0),
                    item.get("velocity", 0) / 127.0,
                    time.time(),
                )
                self.queue.put(event)
            elif msg_type == "all_notes_off":
                event = MIDIEvent("all_notes_off", 0, 0.0, time.time())
                self.queue.put(event)
            else:
                # Unknown message type - try to queue as-is
                self.queue.put(item)
        else:
            # Non-dict items - queue as-is
            self.queue.put(item)


class SynthEngineSubprocess:
    """
    Wrapper that mimics SynthEngine API but communicates via IPC queues.
    Maintains identical interface so all modes work without changes.
    """

    def __init__(self):
        self.process: Optional[multiprocessing.Process] = None
        self.to_synth_queue: Optional[multiprocessing.Queue] = None
        self.from_synth_queue: Optional[multiprocessing.Queue] = None
        self.running = False
        self._request_counter = 0
        self._response_cache: Dict[int, QueryResponse] = {}
        self._midi_queue_proxy: Optional[_MIDIQueueProxy] = None
        self._start_subprocess()

    def _start_subprocess(self):
        """Spawn the synth subprocess."""
        self.to_synth_queue = multiprocessing.Queue()
        self.from_synth_queue = multiprocessing.Queue()
        self._midi_queue_proxy = _MIDIQueueProxy(self.to_synth_queue)

        # Import here to avoid circular imports
        from music.synth_subprocess_main import synth_subprocess_main

        self.process = multiprocessing.Process(
            target=synth_subprocess_main,
            args=(self.to_synth_queue, self.from_synth_queue),
            daemon=True,
        )
        self.process.start()
        self.running = True

    def _next_request_id(self) -> int:
        """Generate unique request ID."""
        self._request_counter += 1
        return self._request_counter

    def _wait_response(self, request_id: int, timeout: float = 5.0) -> QueryResponse:
        """Wait for response to a query request."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = self.from_synth_queue.get_nowait()
                if response.request_id == request_id:
                    return response
                else:
                    # Cache unexpected responses
                    self._response_cache[response.request_id] = response
            except Exception:
                pass
            time.sleep(0.001)

        raise RuntimeError(f"Query request {request_id} timed out after {timeout}s")

    # ========== MIDI Interface (identical to SynthEngine) ==========

    def note_on(self, note: int, velocity: int = 127):
        """Queue a note-on MIDI event."""
        if not self.running:
            return
        event = MIDIEvent("note_on", note, velocity / 127.0, time.time())
        self.to_synth_queue.put(event)

    def note_off(self, note: int, velocity: int = 0):
        """Queue a note-off MIDI event."""
        if not self.running:
            return
        event = MIDIEvent("note_off", note, velocity / 127.0, time.time())
        self.to_synth_queue.put(event)

    def all_notes_off(self):
        """Queue an all-notes-off event."""
        if not self.running:
            return
        event = MIDIEvent("all_notes_off", 0, 0.0, time.time())
        self.to_synth_queue.put(event)

    # ========== MIDI Control Changes ==========

    def pitch_bend_change(self, value: int):
        """Handle pitch bend wheel change (0-16383, center at 8192)."""
        if not self.running:
            return
        pitch_bend_target = ((value - 8192) / 8192.0) * 2.0
        self.update_parameters(pitch_bend_target=pitch_bend_target)

    def modulation_change(self, value: int):
        """Handle modulation wheel change (0-127)."""
        if not self.running:
            return
        mod_wheel = value / 127.0
        self.update_parameters(mod_wheel=mod_wheel)

    def is_available(self) -> bool:
        """Check if audio system is available and running."""
        return self.running

    # ========== Parameter Updates ==========

    def update_parameters(self, **kwargs):
        """Queue parameter updates."""
        if not self.running:
            return
        for param_name, value in kwargs.items():
            update = ParameterUpdate(param_name, value, time.time())
            self.to_synth_queue.put(update)

    def drum_trigger(self, note: int, velocity: int, params: dict):
        """Enqueue an atomic drum trigger event (params + note_on bundled)."""
        if not self.running:
            return
        self.to_synth_queue.put(DrumTriggerEvent(note, velocity, params, time.time()))

    # ========== State Queries (synchronous request-response) ==========

    def get_preset_names(self) -> list:
        """Query preset names from subprocess."""
        if not self.running:
            return []
        request_id = self._next_request_id()
        request = QueryRequest(request_id, "get_presets", {})
        self.to_synth_queue.put(request)
        response = self._wait_response(request_id)
        if response.error:
            raise RuntimeError(response.error)
        return response.data or []

    def get_preset_data(self, name: str) -> Dict[str, Any]:
        """Query preset data from subprocess."""
        if not self.running:
            return {}
        request_id = self._next_request_id()
        request = QueryRequest(request_id, "get_preset_data", {"name": name})
        self.to_synth_queue.put(request)
        response = self._wait_response(request_id)
        if response.error:
            raise RuntimeError(response.error)
        return response.data or {}

    def get_state(self) -> Dict[str, Any]:
        """Query complete synth state from subprocess."""
        if not self.running:
            return {}
        request_id = self._next_request_id()
        request = QueryRequest(request_id, "get_state", {})
        self.to_synth_queue.put(request)
        response = self._wait_response(request_id)
        if response.error:
            raise RuntimeError(response.error)
        return response.data or {}

    def get_current_params(self) -> Dict[str, Any]:
        """Return a snapshot of all synth parameters, suitable for save/restore.

        Delegates to get_state() which performs a synchronous IPC round-trip to
        the subprocess. Used by modes that temporarily override parameters
        (e.g. piano mode) and need to restore the previous state on exit.
        """
        return self.get_state()

    # ========== MIDI Queue Access ==========

    @property
    def midi_event_queue(self) -> _MIDIQueueProxy:
        """Access to MIDI event queue for direct enqueuing."""
        return self._midi_queue_proxy

    # ========== Properties (via state queries) ==========

    @property
    def waveform(self) -> str:
        """Get current waveform."""
        state = self.get_state()
        return state.get("waveform", "sine")

    @waveform.setter
    def waveform(self, value: str):
        """Set waveform."""
        self.update_parameters(waveform=value)

    @property
    def cutoff(self) -> float:
        """Get current filter cutoff."""
        state = self.get_state()
        return state.get("cutoff", 5000.0)

    @cutoff.setter
    def cutoff(self, value: float):
        """Set filter cutoff."""
        self.update_parameters(cutoff=value)

    @property
    def resonance(self) -> float:
        """Get current filter resonance."""
        state = self.get_state()
        return state.get("resonance", 0.5)

    @resonance.setter
    def resonance(self, value: float):
        """Set filter resonance."""
        self.update_parameters(resonance=value)

    @property
    def attack(self) -> float:
        """Get envelope attack time."""
        state = self.get_state()
        return state.get("attack", 0.01)

    @attack.setter
    def attack(self, value: float):
        """Set envelope attack time."""
        self.update_parameters(attack=value)

    @property
    def decay(self) -> float:
        """Get envelope decay time."""
        state = self.get_state()
        return state.get("decay", 0.1)

    @decay.setter
    def decay(self, value: float):
        """Set envelope decay time."""
        self.update_parameters(decay=value)

    @property
    def sustain(self) -> float:
        """Get envelope sustain level."""
        state = self.get_state()
        return state.get("sustain", 0.7)

    @sustain.setter
    def sustain(self, value: float):
        """Set envelope sustain level."""
        self.update_parameters(sustain=value)

    @property
    def release(self) -> float:
        """Get envelope release time."""
        state = self.get_state()
        return state.get("release", 0.1)

    @release.setter
    def release(self, value: float):
        """Set envelope release time."""
        self.update_parameters(release=value)

    @property
    def intensity(self) -> float:
        """Get LFO intensity."""
        state = self.get_state()
        return state.get("intensity", 0.0)

    @intensity.setter
    def intensity(self, value: float):
        """Set LFO intensity."""
        self.update_parameters(intensity=value)

    @property
    def voice_type(self) -> str:
        """Get voice type (mono/poly/unison)."""
        state = self.get_state()
        return state.get("voice_type", "poly")

    @voice_type.setter
    def voice_type(self, value: str):
        """Set voice type."""
        self.update_parameters(voice_type=value)

    # ========== Lifecycle ==========

    def warm_up(self):
        """Warm up the audio system (called during startup)."""
        # The subprocess initializes and warms up its own SynthEngine instance.
        # No action needed here in the wrapper.
        pass

    def shutdown(self):
        """Gracefully shut down the subprocess."""
        if not self.running:
            return
        self.running = False
        if self.to_synth_queue:
            self.to_synth_queue.put(None)  # Sentinel
        if self.process:
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                self.process.terminate()

    def __del__(self):
        """Clean shutdown on deletion."""
        try:
            self.shutdown()
        except Exception:
            pass
