# ABOUTME: Horizontal parameter bar widget for the ARM Pygame UI.
# ABOUTME: Draws a filled bar, label, and percentage value onto a parent surface.

import pygame
from arm_ui import theme


class BarDisplay:
    """Draws a labeled horizontal fill-bar directly onto a parent surface.

    No separate Surface is allocated; all drawing uses the parent surface at
    the given rect position to keep memory and GPU overhead low on the Pi.

    value is expected to be pre-normalized to 0.0-1.0 by the caller.
    """

    _LABEL_WIDTH = 80   # Pixels reserved for the label on the left
    _PCT_WIDTH   = 40   # Pixels reserved for the percentage text on the right
    _BAR_HEIGHT  = 12   # Filled bar height in pixels
    _RADIUS      = 4    # Border radius on the bar

    def __init__(self, rect: pygame.Rect, label: str, value: float = 0.0) -> None:
        self.rect  = rect
        self.label = label
        self.value = max(0.0, min(1.0, value))

    def set_value(self, value: float) -> None:
        self.value = max(0.0, min(1.0, value))

    def draw(self, surface: pygame.Surface) -> None:
        font = theme.FONTS[theme.FONT_SMALL]
        rx, ry, rw, rh = self.rect

        # Label (left-aligned)
        lbl_surf = font.render(self.label, True, theme.TEXT_SECONDARY)
        lbl_y    = ry + (rh - lbl_surf.get_height()) // 2
        surface.blit(lbl_surf, (rx, lbl_y))

        # Percentage text (right-aligned)
        pct_text = f"{int(self.value * 100)}%"
        pct_surf = font.render(pct_text, True, theme.TEXT_SECONDARY)
        pct_x    = rx + rw - pct_surf.get_width()
        pct_y    = ry + (rh - pct_surf.get_height()) // 2
        surface.blit(pct_surf, (pct_x, pct_y))

        # Bar area between label and percentage
        bar_x     = rx + self._LABEL_WIDTH
        bar_total = rw - self._LABEL_WIDTH - self._PCT_WIDTH - 4
        bar_y     = ry + (rh - self._BAR_HEIGHT) // 2

        # Background track
        pygame.draw.rect(
            surface, theme.BAR_BG,
            (bar_x, bar_y, bar_total, self._BAR_HEIGHT),
            border_radius=self._RADIUS,
        )
        # Fill
        fill_w = max(0, int(bar_total * self.value))
        if fill_w > 0:
            pygame.draw.rect(
                surface, theme.BAR_FG,
                (bar_x, bar_y, fill_w, self._BAR_HEIGHT),
                border_radius=self._RADIUS,
            )
