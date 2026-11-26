# ABOUTME: Shared pytest setup: tests run without the drum kit unless they ask for it.
# ABOUTME: Tests that need samples request generated_kit, or give the engine their own kit.
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from music.drum_kit import DrumKit

_LOAD_KIT = DrumKit.__dict__["load"]


@pytest.fixture(autouse=True)
def no_drum_kit(monkeypatch):
    """Engines and screens use the synth drums, which also keeps engine setup quick."""
    monkeypatch.setattr(DrumKit, "load", classmethod(lambda cls: None))


@pytest.fixture
def generated_kit(no_drum_kit, monkeypatch):
    """Load the drum kit as the application does."""
    monkeypatch.setattr(DrumKit, "load", _LOAD_KIT)
