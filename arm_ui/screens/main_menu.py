# ABOUTME: Main menu carousel screen for the ARM Pygame UI.
# ABOUTME: Shows 6 mode tiles as PixelCode box-drawing widgets, navigated by D-pad/keyboard/touch.

import pygame

from arm_ui.screens.base import BaseScreen
from arm_ui import theme, widgets
from gamepad.actions import GP

# Mode definitions: (screen_name, display_label, icon_glyph)
# Icon glyphs use PixelCode geometric characters for a hardware-instrument feel.
_MODES = [
    ("piano",      "PIANO",  widgets.SYM_DIAMOND),    # ◆
    ("synth",      "SYNTH",  widgets.SYM_TRI_UP),     # ▲
    ("metronome",  "METRO",  widgets.SYM_DOT_FULL),   # ●
    ("tambor",     "TAMBOR", widgets.SYM_SQ_FULL),    # ■
    ("compendium", "CHORDS", widgets.SYM_ARROW_LR),   # ↔
    ("config",     "CONFIG", "*"),
]


class MainMenuScreen(BaseScreen):
    """Horizontal carousel main menu. All coords are in the 240x160 render space."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._selected   = 1   # Start on SYNTH
        self._quit_armed = False

    def on_enter(self, **kwargs) -> None:
        self._quit_armed = False
        gp = self.app.gamepad_handler
        gp.set_button_callback(GP.DPAD_LEFT,  self._go_left)
        gp.set_button_callback(GP.DPAD_RIGHT, self._go_right)
        gp.set_button_callback(GP.CONFIRM,    self._select)
        gp.set_button_callback(GP.BACK,       self._back_pressed)

    def on_exit(self) -> None:
        self._quit_armed = False

    # -- Navigation -----------------------------------------------------------

    def _go_left(self) -> None:
        self._selected = max(0, self._selected - 1)
        self._quit_armed = False
        self.app.request_redraw()

    def _go_right(self) -> None:
        self._selected = min(len(_MODES) - 1, self._selected + 1)
        self._quit_armed = False
        self.app.request_redraw()

    def _select(self) -> None:
        self.app.goto(_MODES[self._selected][0])

    def _back_pressed(self) -> None:
        if self._quit_armed:
            self.app.quit()
        else:
            self._quit_armed = True
            self.app.request_redraw()

    # -- Event handling -------------------------------------------------------

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            # Scale touch position from display (480x320) to render (240x160) space
            sx = event.pos[0] // theme.RENDER_SCALE
            sy = event.pos[1] // theme.RENDER_SCALE
            self._handle_touch((sx, sy))

    def _handle_key(self, key) -> None:
        if key in (pygame.K_LEFT, pygame.K_a):
            self._go_left()
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._go_right()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._select()
        elif key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self._back_pressed()

    def _handle_touch(self, pos) -> None:
        x, y = pos
        center_x    = theme.SCREEN_W // 2
        item_stride = theme.CAROUSEL_CENTER_W + theme.CAROUSEL_ITEM_GAP
        for i in range(len(_MODES)):
            offset  = i - self._selected
            item_cx = center_x + int(offset * item_stride)
            w = theme.CAROUSEL_CENTER_W
            h = theme.CAROUSEL_CENTER_H
            ix = item_cx - w // 2
            iy = theme.CAROUSEL_CENTER_Y
            if pygame.Rect(ix, iy, w, h).collidepoint(x, y):
                if i == self._selected:
                    self._select()
                else:
                    self._selected = i
                    self.app.request_redraw()
                return

    def update(self, dt) -> None:
        pass   # tiles snap instantly, no animation needed

    # -- Drawing --------------------------------------------------------------

    def draw(self, surface) -> None:
        surface.fill(theme.BG_COLOR)

        # Title bar: ACORDES (left, green medium) + OStra (right, dim italic)
        widgets.title_bar(surface, "ACORDES", "OStra")

        center_x    = theme.SCREEN_W // 2
        item_stride = theme.CAROUSEL_CENTER_W + theme.CAROUSEL_ITEM_GAP

        for i, (_, lbl, icon) in enumerate(_MODES):
            offset = i - self._selected
            is_sel = (i == self._selected)

            # Only render tiles that are potentially visible
            if abs(offset) > 2.5:
                continue

            # Tile size scales from CENTER (selected) down to FAR (2 steps away).
            # All sizes maintain the 3:2 aspect ratio of the physical display.
            t = max(0.0, 1.0 - abs(offset))
            w = int(theme.CAROUSEL_FAR_W + (theme.CAROUSEL_CENTER_W - theme.CAROUSEL_FAR_W) * t)
            h = int(theme.CAROUSEL_FAR_H + (theme.CAROUSEL_CENTER_H - theme.CAROUSEL_FAR_H) * t)

            # Snap to character grid so box-drawing borders tile with no gaps
            w = max(theme.CELL_W * 2, (w // theme.CELL_W) * theme.CELL_W)
            h = max(theme.CELL_H * 2, (h // theme.CELL_H) * theme.CELL_H)

            item_cx = center_x + int(offset * item_stride)
            ix = item_cx - w // 2
            iy = theme.CAROUSEL_CENTER_Y + (theme.CAROUSEL_CENTER_H - h) // 2

            # All tiles share the same box-drawing style.
            # Selected = white border + panel bg.  Inactive = dim border + black bg.
            border_color = theme.BORDER_ACTIVE   if is_sel else theme.BORDER_INACTIVE
            fill_color   = theme.BG_PANEL        if is_sel else theme.BG_COLOR
            widgets.box(surface, ix, iy, w, h, border_color, fill=fill_color)

            # Large icon glyph centered in the upper portion of the tile
            icon_size  = theme.FONT_LARGE   if is_sel else theme.FONT_MEDIUM
            icon_color = theme.TEXT_PRIMARY  if is_sel else theme.TEXT_DIM
            icon_surf  = theme.FONTS_UI[icon_size].render(icon, False, icon_color)
            icon_x     = item_cx - icon_surf.get_width() // 2
            icon_y     = iy + h // 2 - icon_surf.get_height() // 2 - theme.CELL_H // 2
            surface.blit(icon_surf, (icon_x, icon_y))

            # Mode label below the icon, inside the tile bottom area
            lbl_color = theme.ACCENT if is_sel else theme.TEXT_DIM
            lbl_surf  = theme.FONTS_UI[theme.FONT_TINY].render(lbl, False, lbl_color)
            lbl_x     = item_cx - lbl_surf.get_width() // 2
            lbl_y     = icon_y + icon_surf.get_height() + 2
            surface.blit(lbl_surf, (lbl_x, lbl_y))

        # Hint bar at bottom
        if self._quit_armed:
            s = theme.FONTS_UI[theme.FONT_TINY].render(
                "PRESS ESC AGAIN TO QUIT", False, theme.ERROR_COLOR)
            y = theme.SCREEN_H - theme.CELL_H
            widgets.hline(surface, 0, y - 2, theme.SCREEN_W, theme.SEPARATOR)
            surface.blit(s, s.get_rect(centerx=theme.SCREEN_W // 2, y=y))
        else:
            widgets.hint_bar(surface, [
                ("L/R", "move"),
                ("Enter", "select"),
                ("Esc", "quit"),
            ])
