# ABOUTME: Visual theme constants for the ARM Pygame UI (480x320 framebuffer).
# ABOUTME: All colors, font sizes, and layout values are defined here - nowhere else.

import pygame

# Screen dimensions (matches TFT-LCD and HDMI output configured in tft_config.txt)
SCREEN_W = 480
SCREEN_H = 320

# ── Colors ──────────────────────────────────────────────────────────────────
# Dark grey base matches IdleManager screensaver color (not pure black, so the
# screen never looks completely dead).
BG_COLOR        = (30,  30,  30)   # Main background
BG_DARK         = (18,  18,  18)   # Darker panels / separators
BG_PANEL        = (42,  42,  42)   # Slightly lighter panel backgrounds
ACCENT          = (0,  180, 230)   # Cyan accent (matches Textual theme)
ACCENT_DIM      = (0,  100, 140)   # Dimmed accent for inactive / unfocused items
TEXT_PRIMARY    = (240, 240, 240)  # Primary text
TEXT_SECONDARY  = (160, 160, 160)  # Secondary / muted text
TEXT_DIM        = (75,  75,  75)   # Placeholder, disabled
HIGHLIGHT       = (255, 220,   0)  # Selected item (yellow highlight)
ACTIVE_STEP     = (255, 140,   0)  # Tambor active step indicator
SUCCESS         = (0,  200,  80)   # Ready / playing / OK state
ERROR_COLOR     = (220,  60,  60)  # Error / warning state
BAR_BG          = (55,  55,  55)   # Parameter bar background
BAR_FG          = ACCENT           # Parameter bar fill
BADGE_BUILTIN   = (60,  80, 120)   # "Built-in" origin badge background
BADGE_USER      = (60, 100,  60)   # "User" origin badge background

# Minimum touch target size in pixels (both axes)
MIN_TOUCH = 60

# ── Font sizes ───────────────────────────────────────────────────────────────
FONT_GIANT  = 72   # BPM display, large numeric readouts
FONT_LARGE  = 36   # Preset name, chord name
FONT_MEDIUM = 24   # Button labels, section headers
FONT_SMALL  = 16   # Parameter labels, info text
FONT_TINY   = 12   # Status footnotes, counters

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


def _load_fonts() -> dict:
    """Load all font sizes once. Returns a dict keyed by size constant."""
    sizes = [FONT_TINY, FONT_SMALL, FONT_MEDIUM, FONT_LARGE, FONT_GIANT]
    return {s: pygame.font.Font(None, s) for s in sizes}


# Fonts are populated by arm_ui.app after pygame.init() has been called.
# Access via: theme.FONTS[theme.FONT_MEDIUM]
FONTS: dict = {}


def init_fonts() -> None:
    """Populate FONTS dict. Must be called after pygame.init()."""
    global FONTS
    FONTS = _load_fonts()
