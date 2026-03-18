# ABOUTME: Stub placeholder screen for modes not yet implemented in the ARM UI.
# ABOUTME: Uses PixelCode box widget; B/Esc returns to main menu.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme, widgets
from gamepad.actions import GP


class StubScreen(BaseScreen):
    """Placeholder shown for modes not yet fully implemented. Coords: 240x160."""

    def __init__(self, app, title="Mode") -> None:
        super().__init__(app)
        self._title = title.upper()

    def on_enter(self, **kwargs) -> None:
        gp = self.app.gamepad_handler
        gp.set_button_callback(GP.BACK, lambda: self.app.goto("main_menu"))

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE, pygame.K_b):
                self.app.goto("main_menu")

    def draw(self, surface) -> None:
        surface.fill(theme.BG_COLOR)

        # Title bar
        widgets.title_bar(surface, self._title, "ACORDES")

        # Centered info box using PixelCode box-drawing characters
        box_w = theme.CELL_W * 20   # 20 columns wide
        box_h = theme.CELL_H * 5    # 5 rows tall
        bx = (theme.SCREEN_W - box_w) // 2
        by = (theme.SCREEN_H - box_h) // 2

        widgets.box(surface, bx, by, box_w, box_h,
                    theme.BORDER_ACTIVE, fill=theme.BG_PANEL)

        # "COMING SOON" centered inside the box
        inner = widgets.box_inner(bx, by, box_w, box_h)
        label_s = theme.FONTS_M[theme.FONT_SMALL].render(
            "COMING SOON", False, theme.TEXT_PRIMARY)
        surface.blit(label_s, label_s.get_rect(
            centerx=inner.centerx, centery=inner.centery))

        widgets.hint_bar(surface, [("Esc", "back")])
