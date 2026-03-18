# ABOUTME: Visual theme constants for the ARM Pygame UI (480x320 framebuffer).
# ABOUTME: All colors, font sizes, and layout values are defined here - nowhere else.

import pygame

# Screen dimensions (matches TFT-LCD and HDMI output configured in tft_config.txt)
SCREEN_W = 480
SCREEN_H = 320

# ── Colors ──────────────────────────────────────────────────────────────────
# Pixel art / terminal aesthetic: pure black background, green + orange palette.
BG_COLOR        = (  0,   0,   0)   # Pure black background
BG_DARK         = (  0,   0,   0)   # Same black for inner panels
BG_PANEL        = ( 10,  10,  10)   # Barely visible panel inset
ACCENT          = (  0, 220,  80)   # Green (primary accent)
ACCENT_DIM      = (  0,  80,  30)   # Dim green for inactive items
HIGHLIGHT       = (255, 140,   0)   # Orange highlight (selected / active)
HIGHLIGHT_DIM   = (120,  55,   0)   # Dim orange
TEXT_PRIMARY    = (220, 220, 220)   # Near-white text
TEXT_SECONDARY  = (130, 130, 130)   # Muted text
TEXT_DIM        = ( 50,  50,  50)   # Disabled / placeholder
SUCCESS         = (  0, 255,  80)   # Ready / OK - bright green
ERROR_COLOR     = (255,  60,  60)   # Error / warning
BAR_BG          = ( 20,  20,  20)   # Parameter bar background
BAR_FG          = ACCENT            # Parameter bar fill (green)
BADGE_BUILTIN   = (  0,  60,  25)   # "Built-in" badge background
BADGE_USER      = ( 60,  40,   0)   # "User" badge background

# Minimum touch target size in pixels (both axes)
MIN_TOUCH = 60

# ── Font sizes ───────────────────────────────────────────────────────────────
# Pixel art aesthetic: use exact power-of-2 sizes for crisp bitmap rendering.
FONT_GIANT  = 64   # BPM display, large numeric readouts
FONT_LARGE  = 32   # Preset name, chord name
FONT_MEDIUM = 20   # Button labels, section headers
FONT_SMALL  = 14   # Parameter labels, info text
FONT_TINY   = 10   # Status footnotes, counters

# ── Carousel layout ──────────────────────────────────────────────────────────
CAROUSEL_CENTER_W  = 150
CAROUSEL_CENTER_H  = 160
CAROUSEL_SIDE_W    = 96
CAROUSEL_SIDE_H    = 110
CAROUSEL_FAR_W     = 60
CAROUSEL_FAR_H     = 75
CAROUSEL_CENTER_X  = (SCREEN_W - CAROUSEL_CENTER_W) // 2
CAROUSEL_CENTER_Y  = 50
CAROUSEL_ITEM_GAP  = 12   # Pixels between carousel items


def _try_pixel_font(size: int) -> pygame.font.Font:
    """Try to load a pixel-art/monospace font, fall back to pygame built-in.

    Tries Terminus first (installed on OStra), then common monospace fonts.
    All text is rendered with antialias=False for the crisp pixel art look.
    """
    candidates = [
        "terminus",
        "Terminus",
        "terminusfont",
        "dejavusansmono",
        "couriernew",
        "courier",
        "monospace",
    ]
    for name in candidates:
        try:
            font = pygame.font.SysFont(name, size)
            if font:
                return font
        except Exception:
            pass
    return pygame.font.Font(None, size)


# Fonts are populated by arm_ui.app after pygame.init() has been called.
# Access via: theme.FONTS[theme.FONT_MEDIUM]
FONTS: dict = {}


def init_fonts() -> None:
    """Populate FONTS dict. Must be called after pygame.init()."""
    global FONTS
    sizes = [FONT_TINY, FONT_SMALL, FONT_MEDIUM, FONT_LARGE, FONT_GIANT]
    FONTS = {s: _try_pixel_font(s) for s in sizes}


def txt(font_size: int, text: str, color: tuple) -> pygame.Surface:
    """Render text with antialias=False for crisp pixel art look."""
    return FONTS[font_size].render(text, False, color)
