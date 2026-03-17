# ABOUTME: Semantic gamepad action name constants used throughout Acordes.
# ABOUTME: Modes register callbacks against these names, never against raw button integers.


class GP:
    """Semantic gamepad action identifiers.

    All gamepad callbacks are registered by semantic name so the rest of the
    application never depends on raw button IDs from a specific controller.
    The backend modules translate hardware events to these constants before
    firing callbacks.

    Face button names follow the Xbox/PlayStation positional convention:
      CONFIRM  = south button  (Xbox A, PS Cross, Nintendo B)
      BACK     = east button   (Xbox B, PS Circle, Nintendo A)
      ACTION_1 = west button   (Xbox X, PS Square, Nintendo Y)
      ACTION_2 = north button  (Xbox Y, PS Triangle, Nintendo X)

    The SDL2 GameController API (used by the pygame backend) normalises all
    controllers to this positional layout, so Nintendo users press the south
    button (labelled B) to confirm, which matches Nintendo's own convention.
    """

    # Face buttons
    CONFIRM  = "confirm"   # South  — Xbox A  / PS Cross    / Nintendo B
    BACK     = "cancel"    # East   — Xbox B  / PS Circle   / Nintendo A
    ACTION_1 = "action1"   # West   — Xbox X  / PS Square   / Nintendo Y
    ACTION_2 = "action2"   # North  — Xbox Y  / PS Triangle / Nintendo X

    # Shoulder buttons
    LB = "lb"   # Left bumper  — Xbox LB / PS L1 / Switch L
    RB = "rb"   # Right bumper — Xbox RB / PS R1 / Switch R

    # Analog triggers (reported as float 0.0-1.0 via axis callbacks)
    LT = "lt"   # Left trigger  — Xbox LT / PS L2 / Switch ZL
    RT = "rt"   # Right trigger — Xbox RT / PS R2 / Switch ZR

    # D-pad directions
    DPAD_UP    = "dpad_up"
    DPAD_DOWN  = "dpad_down"
    DPAD_LEFT  = "dpad_left"
    DPAD_RIGHT = "dpad_right"

    # Menu buttons
    START    = "start"    # Xbox Menu    / PS Options / Nintendo +
    BACK_BTN = "back_btn" # Xbox View    / PS Share   / Nintendo -

    # Stick clicks
    L3 = "l3"   # Left stick click
    R3 = "r3"   # Right stick click

    # Analog stick axes (reported as float -1.0 to 1.0 via axis callbacks)
    AXIS_LX = "axis_lx"   # Left stick horizontal
    AXIS_LY = "axis_ly"   # Left stick vertical
    AXIS_RX = "axis_rx"   # Right stick horizontal
    AXIS_RY = "axis_ry"   # Right stick vertical
