# ABOUTME: XInput-based gamepad backend for Windows via ctypes.
# ABOUTME: Pure polling API — no SDL, no Win32 message loop, no keyboard event injection.

import ctypes
import ctypes.wintypes
import sys
from typing import Optional

from gamepad.actions import GP

# ---------------------------------------------------------------------------
# XInput button bitmask constants
# ---------------------------------------------------------------------------
_DPAD_UP        = 0x0001
_DPAD_DOWN      = 0x0002
_DPAD_LEFT      = 0x0004
_DPAD_RIGHT     = 0x0008
_START          = 0x0010
_BACK           = 0x0020
_L3             = 0x0040
_R3             = 0x0080
_LB             = 0x0100
_RB             = 0x0200
_A              = 0x1000
_B              = 0x2000
_X              = 0x4000
_Y              = 0x8000

# Map XInput button bit → GP semantic action
_BUTTON_MAP: dict[int, str] = {
    _DPAD_UP:   GP.DPAD_UP,
    _DPAD_DOWN: GP.DPAD_DOWN,
    _DPAD_LEFT: GP.DPAD_LEFT,
    _DPAD_RIGHT:GP.DPAD_RIGHT,
    _START:     GP.START,
    _BACK:      GP.BACK_BTN,
    _L3:        GP.L3,
    _R3:        GP.R3,
    _LB:        GP.LB,
    _RB:        GP.RB,
    _A:         GP.CONFIRM,
    _B:         GP.BACK,
    _X:         GP.ACTION_1,
    _Y:         GP.ACTION_2,
}

_TRIGGER_DEAD_ZONE = 30    # 0-255 range; XInput recommends 30
_AXIS_DEAD_ZONE    = 7849  # -32768..32767; XInput recommends 7849 for left stick

# ---------------------------------------------------------------------------
# XInput structs
# ---------------------------------------------------------------------------

class _XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons",      ctypes.c_ushort),
        ("bLeftTrigger",  ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX",      ctypes.c_short),
        ("sThumbLY",      ctypes.c_short),
        ("sThumbRX",      ctypes.c_short),
        ("sThumbRY",      ctypes.c_short),
    ]


class _XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", ctypes.c_ulong),
        ("Gamepad",        _XINPUT_GAMEPAD),
    ]


def _load_xinput() -> Optional[ctypes.WinDLL]:
    """Try loading xinput1_4, then xinput1_3, then xinput9_1_0."""
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = ctypes.windll.LoadLibrary(name)
            # Verify the function exists
            _ = dll.XInputGetState
            return dll
        except (OSError, AttributeError):
            continue
    return None


class XInputGamepadBackend:
    """Polls Xbox/XInput controller state directly via xinput*.dll.

    No SDL, no Win32 message loop, no keyboard event injection.
    Completely isolated from Windows Terminal's input handling.

    Call poll() from a Textual set_interval timer (e.g. every 16ms).
    Fires GP.* action callbacks directly on the calling thread.
    """

    # Trigger dead zone: 0-255 scale, normalised to 0.0-1.0 after applying.
    _TRIGGER_DZ = _TRIGGER_DEAD_ZONE / 255.0
    # Axis dead zone: applied before normalising -32768..32767 → -1.0..1.0
    _AXIS_DZ = _AXIS_DEAD_ZONE / 32767.0

    def __init__(self):
        self._xinput: Optional[ctypes.WinDLL] = None
        self._controller_index: int = 0
        self._connected: bool = False

        self._fire_callback = None             # called on button-down; set by GamepadHandler
        self._fire_button_up_callback = None   # called on button-up; set by GamepadHandler
        self._fire_axis_callback = None        # set by GamepadHandler

        # Previous state for change detection
        self._prev_buttons: int = 0
        self._prev_lt: float = 0.0
        self._prev_rt: float = 0.0
        self._prev_axes: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Load XInput DLL and find the first connected controller."""
        self._xinput = _load_xinput()
        if self._xinput is None:
            print("[gamepad] XInput DLL not found", file=sys.stderr)
            return False

        # Probe up to 4 controller slots
        state = _XINPUT_STATE()
        for idx in range(4):
            result = self._xinput.XInputGetState(idx, ctypes.byref(state))
            if result == 0:  # ERROR_SUCCESS
                self._controller_index = idx
                self._connected = True
                self._prev_buttons = state.Gamepad.wButtons
                return True

        return False

    def disconnect(self):
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def poll(self):
        """Read current XInput state and fire callbacks for any changes."""
        if not self._connected or self._xinput is None:
            return

        state = _XINPUT_STATE()
        result = self._xinput.XInputGetState(self._controller_index, ctypes.byref(state))
        if result != 0:
            # ERROR_DEVICE_NOT_CONNECTED (0x48F) or other error
            self._connected = False
            return

        gp = state.Gamepad

        # --- Buttons ---
        current = gp.wButtons
        changed = current ^ self._prev_buttons
        if changed:
            for bit, action in _BUTTON_MAP.items():
                if changed & bit:
                    if current & bit:
                        if self._fire_callback:
                            self._fire_callback(action)
                    else:
                        if self._fire_button_up_callback:
                            self._fire_button_up_callback(action)
        self._prev_buttons = current

        # --- Left trigger ---
        lt_raw = gp.bLeftTrigger / 255.0
        lt = lt_raw if lt_raw > self._TRIGGER_DZ else 0.0
        if abs(lt - self._prev_lt) >= 0.01:
            self._prev_lt = lt
            if self._fire_axis_callback:
                self._fire_axis_callback(GP.LT, lt)

        # --- Right trigger ---
        rt_raw = gp.bRightTrigger / 255.0
        rt = rt_raw if rt_raw > self._TRIGGER_DZ else 0.0
        if abs(rt - self._prev_rt) >= 0.01:
            self._prev_rt = rt
            if self._fire_axis_callback:
                self._fire_axis_callback(GP.RT, rt)

        # --- Sticks ---
        self._dispatch_stick(GP.AXIS_LX, gp.sThumbLX / 32767.0)
        self._dispatch_stick(GP.AXIS_LY, gp.sThumbLY / 32767.0)
        self._dispatch_stick(GP.AXIS_RX, gp.sThumbRX / 32767.0)
        self._dispatch_stick(GP.AXIS_RY, gp.sThumbRY / 32767.0)

    def _dispatch_stick(self, action: str, raw: float):
        """Apply dead zone and fire axis callback if value changed enough."""
        value = raw if abs(raw) > self._AXIS_DZ else 0.0
        prev = self._prev_axes.get(action, 0.0)
        if abs(value - prev) >= 0.01:
            self._prev_axes[action] = value
            if self._fire_axis_callback:
                self._fire_axis_callback(action, value)
