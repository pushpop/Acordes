# ABOUTME: pygame-based gamepad backend for Windows, macOS, and Linux x86.
# ABOUTME: Uses direct state polling (no SDL event queue) to avoid Win32 message-loop crashes.

import os
import sys

# SDL_VIDEODRIVER=dummy: no SDL window (Acordes uses Textual, not SDL rendering).
# SDL_AUDIODRIVER=dummy: Acordes owns the audio device via sounddevice/PyAudio.
# SDL_JOYSTICK_THREAD=1: SDL polls joystick state in its own background thread so
#   we can read get_button()/get_axis() directly without calling SDL_PumpEvents().
#   This is the key setting that avoids the Win32 message-loop crash when running
#   inside Windows Terminal without a real SDL window.
if "SDL_VIDEODRIVER" not in os.environ:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
if "SDL_AUDIODRIVER" not in os.environ:
    os.environ["SDL_AUDIODRIVER"] = "dummy"
if "SDL_JOYSTICK_THREAD" not in os.environ:
    os.environ["SDL_JOYSTICK_THREAD"] = "1"

from gamepad.actions import GP
from gamepad.button_maps import (
    PYGAME_CONTROLLER_BUTTON_MAP,
    PYGAME_CONTROLLER_AXIS_MAP,
    PYGAME_JOYSTICK_BUTTON_MAP,
    PYGAME_JOYSTICK_AXIS_MAP,
    PYGAME_HAT_MAP,
)

try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False


class PygameGamepadBackend:
    """Polls gamepad state via pygame's SDL2 GameController/Joystick API.

    Uses direct state polling (get_button / get_axis / get_hat) rather than
    the SDL event queue.  This avoids calling SDL_PumpEvents(), which on
    Windows requires a real Win32 window and crashes Windows Terminal when
    SDL_VIDEODRIVER=dummy is active.

    Call poll() on a regular timer (e.g. every 16ms) from the Textual asyncio
    event loop.  Fires GP.* action callbacks directly on the calling thread.

    Tries pygame.controller (SDL2 GameController, fully normalised) first.
    Falls back to pygame.joystick (XInput-style layout assumed) if the
    controller module is unavailable.
    """

    # Axis dead zone: values whose absolute magnitude is below this threshold
    # are treated as zero and do not trigger axis callbacks.
    DEAD_ZONE = 0.15

    # How many button / axis slots to probe when using direct state polling.
    # Most controllers have at most 32 buttons and 8 axes.
    _MAX_BUTTONS = 32
    _MAX_AXES = 8
    _MAX_HATS = 1

    def __init__(self):
        self._use_controller_api = False   # True if pygame.controller available
        self._controller = None            # pygame.controller.Controller instance
        self._joystick = None              # pygame.joystick.Joystick instance (fallback)
        self._connected = False
        self._fire_callback = None         # called on button-down; set by GamepadHandler
        self._fire_button_up_callback = None  # called on button-up; set by GamepadHandler
        self._fire_axis_callback = None    # set by GamepadHandler

        # Previous state for change detection (direct polling requires this)
        self._prev_buttons: dict[int, bool] = {}
        self._prev_axes: dict[int, float] = {}
        self._prev_hat: tuple = (0, 0)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Initialise pygame and open the first available gamepad.

        Returns True if a controller was found and opened.
        """
        if not _PYGAME_AVAILABLE:
            return False

        try:
            if not pygame.get_init():
                pygame.init()

            # Try the SDL2 GameController API first (better normalisation).
            controller_mod = getattr(pygame, "controller", None)
            if controller_mod is not None:
                try:
                    if not controller_mod.get_init():
                        controller_mod.init()
                    if controller_mod.get_count() > 0:
                        self._controller = controller_mod.Controller(0)
                        self._use_controller_api = True
                        self._connected = True
                        self._reset_prev_state()
                        return True
                except Exception:
                    pass  # fall through to joystick fallback

            # Fallback: pygame.joystick (XInput-style layout assumed)
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                self._joystick = pygame.joystick.Joystick(0)
                self._joystick.init()
                self._use_controller_api = False
                self._connected = True
                self._reset_prev_state()
                return True

        except Exception as exc:
            print(f"[gamepad] pygame init error: {exc}", file=sys.stderr)

        return False

    def disconnect(self):
        """Close the gamepad device."""
        try:
            if self._controller is not None:
                self._controller.quit()
        except Exception:
            pass
        try:
            if self._joystick is not None:
                self._joystick.quit()
        except Exception:
            pass
        self._controller = None
        self._joystick = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _reset_prev_state(self):
        """Clear previous-state tracking so the first poll fires fresh."""
        self._prev_buttons = {}
        self._prev_axes = {}
        self._prev_hat = (0, 0)

    # ------------------------------------------------------------------
    # Polling — called from the Textual asyncio timer (no event queue)
    # ------------------------------------------------------------------

    def poll(self):
        """Read current gamepad state directly and fire GP callbacks on changes.

        Deliberately avoids pygame.event.get() / pygame.event.pump() to prevent
        SDL from touching the Win32 message loop, which crashes Windows Terminal
        when no SDL window exists (SDL_VIDEODRIVER=dummy).
        """
        if not self._connected or not _PYGAME_AVAILABLE:
            return

        try:
            if self._use_controller_api:
                self._poll_controller()
            else:
                self._poll_joystick()
        except Exception as exc:
            print(f"[gamepad] poll error: {exc}", file=sys.stderr)
            self._connected = False

    # ------------------------------------------------------------------
    # SDL2 GameController direct state polling
    # ------------------------------------------------------------------

    def _poll_controller(self):
        """Poll pygame.controller.Controller state directly."""
        ctrl = self._controller
        if ctrl is None:
            return

        # Buttons
        for btn_id, action in PYGAME_CONTROLLER_BUTTON_MAP.items():
            try:
                pressed = bool(ctrl.get_button(btn_id))
            except Exception:
                continue
            prev = self._prev_buttons.get(btn_id, False)
            if pressed and not prev:
                if self._fire_callback:
                    self._fire_callback(action)
            elif not pressed and prev:
                if self._fire_button_up_callback:
                    self._fire_button_up_callback(action)
            self._prev_buttons[btn_id] = pressed

        # Axes
        for axis_id, action in PYGAME_CONTROLLER_AXIS_MAP.items():
            try:
                raw = ctrl.get_axis(axis_id)
            except Exception:
                continue
            # Triggers (axes 4 and 5) report -1.0 at rest, +1.0 fully pressed.
            # Normalise to 0.0-1.0.
            if axis_id in (4, 5):
                value = (raw + 1.0) / 2.0
            else:
                value = float(raw)
            self._dispatch_axis(action, axis_id, value)

    # ------------------------------------------------------------------
    # pygame.joystick fallback direct state polling
    # ------------------------------------------------------------------

    def _poll_joystick(self):
        """Poll pygame.joystick.Joystick state directly."""
        joy = self._joystick
        if joy is None:
            return

        # Buttons
        num_buttons = min(joy.get_numbuttons(), self._MAX_BUTTONS)
        for btn_id in range(num_buttons):
            action = PYGAME_JOYSTICK_BUTTON_MAP.get(btn_id)
            if action is None:
                continue
            try:
                pressed = bool(joy.get_button(btn_id))
            except Exception:
                continue
            prev = self._prev_buttons.get(btn_id, False)
            if pressed and not prev:
                if self._fire_callback:
                    self._fire_callback(action)
            elif not pressed and prev:
                if self._fire_button_up_callback:
                    self._fire_button_up_callback(action)
            self._prev_buttons[btn_id] = pressed

        # Axes
        num_axes = min(joy.get_numaxes(), self._MAX_AXES)
        for axis_id in range(num_axes):
            action = PYGAME_JOYSTICK_AXIS_MAP.get(axis_id)
            if action is None:
                continue
            try:
                value = float(joy.get_axis(axis_id))
            except Exception:
                continue
            # Trigger axes report -1 at rest, +1 fully pressed; normalise to 0-1.
            if action in (GP.LT, GP.RT):
                value = (value + 1.0) / 2.0
            self._dispatch_axis(action, axis_id, value)

        # Hat (D-pad on most controllers)
        if joy.get_numhats() > 0:
            try:
                hat_val = joy.get_hat(0)
            except Exception:
                hat_val = (0, 0)
            if hat_val != self._prev_hat:
                prev_action = PYGAME_HAT_MAP.get(self._prev_hat)
                new_action = PYGAME_HAT_MAP.get(hat_val)
                # Fire release for the direction that was held
                if prev_action and self._fire_button_up_callback:
                    self._fire_button_up_callback(prev_action)
                # Fire press for the new direction (if any)
                if new_action and self._fire_callback:
                    self._fire_callback(new_action)
                self._prev_hat = hat_val

    # ------------------------------------------------------------------
    # Axis dispatching with dead zone and change detection
    # ------------------------------------------------------------------

    def _dispatch_axis(self, action: str, axis_id: int, value: float):
        """Apply dead zone and dispatch axis callback if value changed."""
        if abs(value) < self.DEAD_ZONE:
            value = 0.0
        prev = self._prev_axes.get(axis_id, 0.0)
        # Only fire if value changed enough to matter (avoids noise)
        if abs(value - prev) < 0.01:
            return
        self._prev_axes[axis_id] = value
        if self._fire_axis_callback:
            self._fire_axis_callback(action, value)
