# ABOUTME: Stub placeholder screen used for modes not yet implemented in the ARM UI.
# ABOUTME: Displays the mode name and a "coming soon" message; B returns to main menu.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme
from gamepad.actions import GP


class StubScreen(BaseScreen):
    """Placeholder shown for modes that are not yet fully implemented in the ARM UI."""

    def __init__(self, app, title: str = "Mode") -> None:
        super().__init__(app)
        self._title = title

    def on_enter(self, **kwargs) -> None:
        gp = self.app.gamepad_handler
        gp.set_button_callback(GP.BACK, lambda: self.app.goto("main_menu"))

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(theme.BG_COLOR)
        font_large  = theme.FONTS[theme.FONT_LARGE]
        font_medium = theme.FONTS[theme.FONT_MEDIUM]
        font_small  = theme.FONTS[theme.FONT_SMALL]
        cx = theme.SCREEN_W // 2
        cy = theme.SCREEN_H // 2

        title_surf = font_large.render(self._title, True, theme.ACCENT)
        surface.blit(title_surf, title_surf.get_rect(centerx=cx, centery=cy - 30))

        soon_surf = font_medium.render("Coming soon", True, theme.TEXT_SECONDARY)
        surface.blit(soon_surf, soon_surf.get_rect(centerx=cx, centery=cy + 20))

        back_surf = font_small.render("B: back", True, theme.TEXT_DIM)
        surface.blit(back_surf, back_surf.get_rect(centerx=cx, y=theme.SCREEN_H - 24))
