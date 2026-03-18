# ABOUTME: Abstract base class for all ARM UI screens.
# ABOUTME: Defines the lifecycle contract: on_enter/on_exit, handle_event, update, draw.


class BaseScreen:
    """Base class for all Pygame UI screens.

    Lifecycle:
      on_enter(**kwargs) - called when this screen becomes active; register gamepad callbacks
      on_exit()          - called when leaving; gamepad callbacks already cleared by ArmApp.goto()
      handle_event(evt)  - called for each pygame.Event (keyboard, mouse/touch, QUIT)
      update(dt)         - logic update; dt is seconds since last frame
      draw(surface)      - render to the given pygame.Surface
    """

    def __init__(self, app: "ArmApp") -> None:  # noqa: F821
        self.app = app

    def on_enter(self, **kwargs) -> None:
        """Called when this screen becomes active. Register gamepad callbacks here."""

    def on_exit(self) -> None:
        """Called just before leaving. Gamepad callbacks are cleared by ArmApp.goto()."""

    def handle_event(self, event) -> None:
        """Handle a pygame.Event (keyboard, MOUSEBUTTONDOWN for touch, QUIT)."""

    def update(self, dt: float) -> None:
        """Update internal state. dt is seconds since the last frame."""

    def draw(self, surface) -> None:
        """Render to the given pygame.Surface."""
