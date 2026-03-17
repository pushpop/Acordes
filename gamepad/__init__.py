# ABOUTME: Gamepad input module for Acordes.
# ABOUTME: Provides cross-platform controller support via pygame (desktop) and evdev (ARM Linux).

from gamepad.input_handler import GamepadHandler
from gamepad.actions import GP

__all__ = ["GamepadHandler", "GP"]
