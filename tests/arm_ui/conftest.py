# ABOUTME: Pytest configuration for ARM UI tests.
# ABOUTME: Sets SDL_VIDEODRIVER=offscreen so Pygame runs without a physical display.

import os

# Must be set before pygame is imported anywhere in the test session.
os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def pygame_session():
    """Initialize Pygame once per test session using the offscreen driver."""
    pygame.init()
    from arm_ui import theme
    theme.init_fonts()
    yield
    pygame.quit()
