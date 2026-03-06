"""ABOUTME: IPC protocol definitions for subprocess communication.
ABOUTME: Defines message types for MIDI events, parameter updates, and state queries."""

from typing import Any, NamedTuple, Optional


class MIDIEvent(NamedTuple):
    """MIDI event to be processed by synth subprocess."""
    type: str  # "note_on", "note_off", "all_notes_off"
    note: int
    velocity: float
    timestamp: float


class ParameterUpdate(NamedTuple):
    """Parameter change to be applied by synth subprocess."""
    param_name: str
    value: Any
    timestamp: float


class QueryRequest(NamedTuple):
    """Synchronous state query from main process."""
    request_id: int
    query: str  # "get_state", "get_presets", "get_preset_data"
    args: dict


class QueryResponse(NamedTuple):
    """Response to a QueryRequest."""
    request_id: int
    data: Any
    error: Optional[str]


class MuteGateEvent(NamedTuple):
    """Special event to arm randomize mute/fade gate."""
    timestamp: float


class DrumTriggerEvent(NamedTuple):
    """Atomic drum trigger: synthesis params + note_on bundled together.

    Prevents cross-contamination between simultaneous drums on a sequencer step
    by ensuring each drum's params are applied immediately before its note_on
    with no other drum's params interleaved.
    """
    note: int
    velocity: int
    params: dict
    timestamp: float
