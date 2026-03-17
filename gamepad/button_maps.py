# ABOUTME: Maps raw hardware button/axis IDs to GP semantic action names.
# ABOUTME: Separate maps for pygame (SDL2 GameController) and evdev (Linux ARM) backends.

from gamepad.actions import GP

# ---------------------------------------------------------------------------
# pygame backend — SDL2 GameController API (pygame 2.x CONTROLLERBUTTONDOWN
# events).  SDL2's gamecontrollerdb already normalises all known controllers
# to the Xbox positional layout, so no per-controller VID/PID lookup needed.
#
# pygame.constants.CONTROLLER_BUTTON_* values:
#   A=0, B=1, X=2, Y=3, BACK=4, GUIDE=5, START=6,
#   LEFTSTICK=7, RIGHTSTICK=8,
#   LEFTSHOULDER=9, RIGHTSHOULDER=10,
#   DPAD_UP=11, DPAD_DOWN=12, DPAD_LEFT=13, DPAD_RIGHT=14
# ---------------------------------------------------------------------------

PYGAME_CONTROLLER_BUTTON_MAP: dict[int, str] = {
    0:  GP.CONFIRM,    # A        — south face button
    1:  GP.BACK,       # B        — east face button
    2:  GP.ACTION_1,   # X        — west face button
    3:  GP.ACTION_2,   # Y        — north face button
    4:  GP.BACK_BTN,   # Back/View
    # 5 = Guide/Xbox button — intentionally unmapped
    6:  GP.START,      # Start/Menu
    7:  GP.L3,         # Left stick click
    8:  GP.R3,         # Right stick click
    9:  GP.LB,         # Left bumper / L1
    10: GP.RB,         # Right bumper / R1
    11: GP.DPAD_UP,
    12: GP.DPAD_DOWN,
    13: GP.DPAD_LEFT,
    14: GP.DPAD_RIGHT,
}

# pygame.constants.CONTROLLER_AXIS_* values:
#   LEFTX=0, LEFTY=1, RIGHTX=2, RIGHTY=3,
#   TRIGGERLEFT=4, TRIGGERRIGHT=5
PYGAME_CONTROLLER_AXIS_MAP: dict[int, str] = {
    0: GP.AXIS_LX,
    1: GP.AXIS_LY,
    2: GP.AXIS_RX,
    3: GP.AXIS_RY,
    4: GP.LT,
    5: GP.RT,
}

# ---------------------------------------------------------------------------
# pygame joystick fallback — used when pygame.controller is unavailable.
# Assumes XInput-style button layout (Xbox 360/One on Windows or via xpad).
#
# Button order: 0=A, 1=B, 2=X, 3=Y, 4=LB, 5=RB, 6=Back, 7=Start, 8=L3, 9=R3
# Axes:         0=LX, 1=LY, 2=LT, 3=RT, 4=RX, 5=RY  (Windows XInput order)
# Hat 0:        D-pad as (x, y) tuple — see PYGAME_HAT_MAP below
# ---------------------------------------------------------------------------

PYGAME_JOYSTICK_BUTTON_MAP: dict[int, str] = {
    0:  GP.CONFIRM,
    1:  GP.BACK,
    2:  GP.ACTION_1,
    3:  GP.ACTION_2,
    4:  GP.LB,
    5:  GP.RB,
    6:  GP.BACK_BTN,
    7:  GP.START,
    8:  GP.L3,
    9:  GP.R3,
}

PYGAME_JOYSTICK_AXIS_MAP: dict[int, str] = {
    0: GP.AXIS_LX,
    1: GP.AXIS_LY,
    2: GP.LT,
    3: GP.RT,
    4: GP.AXIS_RX,
    5: GP.AXIS_RY,
}

# Hat (x, y) tuple → GP action (press only; release = (0, 0))
PYGAME_HAT_MAP: dict[tuple, str] = {
    (0,  1): GP.DPAD_UP,
    (0, -1): GP.DPAD_DOWN,
    (-1, 0): GP.DPAD_LEFT,
    (1,  0): GP.DPAD_RIGHT,
}

# ---------------------------------------------------------------------------
# evdev backend — Linux kernel EV_KEY / EV_ABS codes (ecodes module).
#
# BTN_SOUTH/EAST/WEST/NORTH are positional names used by the kernel for HID
# gamepads.  The xpad driver (Xbox), hid-sony (PlayStation), and the
# nintendo driver all use this positional convention, so no VID/PID lookup
# is needed for the face buttons.
#
# ABS_HAT0X / ABS_HAT0Y deliver D-pad as ±1 / 0 values.
# ---------------------------------------------------------------------------

# EV_KEY code → GP action
EVDEV_KEY_MAP: dict[int, str] = {
    # Face buttons (positional names)
    0x130: GP.CONFIRM,    # BTN_SOUTH / BTN_A   (A/Cross/B-Nintendo)
    0x131: GP.BACK,       # BTN_EAST  / BTN_B   (B/Circle/A-Nintendo)
    0x133: GP.ACTION_1,   # BTN_WEST  / BTN_X   (X/Square/Y-Nintendo)
    0x134: GP.ACTION_2,   # BTN_NORTH / BTN_Y   (Y/Triangle/X-Nintendo)

    # Shoulder buttons
    0x136: GP.LB,         # BTN_TL  (LB/L1/L)
    0x137: GP.RB,         # BTN_TR  (RB/R1/R)

    # Trigger buttons (digital press; analogue value via ABS_Z/ABS_RZ)
    0x138: GP.LT,         # BTN_TL2 (digital LT — not present on all controllers)
    0x139: GP.RT,         # BTN_TR2 (digital RT — not present on all controllers)

    # Menu buttons
    0x13a: GP.BACK_BTN,   # BTN_SELECT / BTN_BACK
    0x13b: GP.START,      # BTN_START  / BTN_MENU

    # Stick clicks
    0x13d: GP.L3,         # BTN_THUMBL
    0x13e: GP.R3,         # BTN_THUMBR
}

# EV_ABS code → GP action (analogue axes)
EVDEV_ABS_AXIS_MAP: dict[int, str] = {
    0x00: GP.AXIS_LX,   # ABS_X  — left stick horizontal
    0x01: GP.AXIS_LY,   # ABS_Y  — left stick vertical
    0x02: GP.LT,        # ABS_Z  — left trigger analogue
    0x03: GP.AXIS_RX,   # ABS_RX — right stick horizontal
    0x04: GP.AXIS_RY,   # ABS_RY — right stick vertical
    0x05: GP.RT,        # ABS_RZ — right trigger analogue
}

# ABS_HAT0X/Y codes — D-pad via hat axis
EVDEV_HAT0X = 0x10   # ABS_HAT0X
EVDEV_HAT0Y = 0x11   # ABS_HAT0Y

# Axis value normalisation: evdev axes report raw integers.
# Each axis has an info object with min/max; we normalise to -1.0..+1.0.
# Triggers (ABS_Z/ABS_RZ) typically have min=0, max=255; we normalise to 0.0..1.0.
EVDEV_TRIGGER_ABS = {0x02, 0x05}   # ABS_Z, ABS_RZ — triggers (0.0-1.0 range)
