# ABOUTME: Shared pytest setup: tests never read the locally built drum sample kit.
# ABOUTME: Tests that need samples build their own synthetic kit and give it to the engine.
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import music.drum_kit


@pytest.fixture(autouse=True)
def no_local_drum_kit(tmp_path, monkeypatch):
    """The result of a test must not depend on whether a kit has been built."""
    monkeypatch.setattr(music.drum_kit, "DEFAULT_KIT", str(tmp_path / "no-kit.npz"))
