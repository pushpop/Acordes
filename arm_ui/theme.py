# ABOUTME: Visual theme constants for the ARM Pygame UI (480x320 framebuffer).
# ABOUTME: All colors, font sizes, and layout values are defined here - nowhere else.

import os
import pygame

# -- Render dimensions --------------------------------------------------------
# Screens render to SCREEN_W x SCREEN_H (240x160). The app scales 2x to
# DISPLAY_W x DISPLAY_H (480x320) using nearest-neighbor before writing to fb0.
SCREEN_W     = 240
SCREEN_H     = 160
DISPLAY_W    = 480
DISPLAY_H    = 320
RENDER_SCALE = 2

# -- Colors -------------------------------------------------------------------
# Elektron/OP-1 inspired: black bg, white body text, green/orange accents only.
BG_COLOR        = (  0,   0,   0)   # Pure black background
BG_DARK         = (  0,   0,   0)   # Same black for inner panels
BG_PANEL        = (  8,   8,   8)   # Very slightly lighter panel
ACCENT          = (  0, 210,  70)   # Green (active, enabled, playing)
ACCENT_DIM      = (  0,  70,  25)   # Dim green for inactive accent elements
HIGHLIGHT       = (255, 140,   0)   # Orange (status indicators, warnings)
HIGHLIGHT_DIM   = ( 90,  50,   0)   # Dim orange
TEXT_PRIMARY    = (255, 255, 255)   # Pure white - all body text
TEXT_SECONDARY  = (160, 160, 160)   # Mid grey for secondary info
TEXT_DIM        = ( 70,  70,  70)   # Dark grey for hints and disabled
BORDER_ACTIVE   = (255, 255, 255)   # White - selected/active box border
BORDER_INACTIVE = ( 45,  45,  45)   # Dark grey - inactive box border
SUCCESS         = (  0, 255,  80)   # Ready / OK
ERROR_COLOR     = (255,  60,  60)   # Error / warning
BAR_BG          = ( 18,  18,  18)   # Parameter bar background track
BAR_FG          = ACCENT            # Parameter bar fill (green)
SEPARATOR       = ( 35,  35,  35)   # Horizontal rule lines

MIN_TOUCH = 30

# -- Font sizes (at 240x160 internal; appear 2x larger on 480x320 display) ----
# PixelCode is designed on a 6x12 grid; at size 12 each char is ~6x12px.
# All three variants (Regular, Italic, Medium) share these size constants.
FONT_GIANT  = 32
FONT_LARGE  = 20
FONT_MEDIUM = 14
FONT_SMALL  = 11
FONT_TINY   =  8

# -- Character grid dimensions (pixels per cell at FONT_SMALL) ----------------
# Computed at runtime by init_fonts() from actual pygame font metrics.
# widgets.py uses these to snap widget dimensions to the character grid so
# box-drawing borders tile perfectly with no gaps or overruns.
CELL_W = 6    # updated by init_fonts()
CELL_H = 11   # updated by init_fonts()

# -- Carousel layout ----------------------------------------------------------
# All items share the same 3:2 (1.5:1) aspect ratio matching the display.
# Dimensions are snapped to the character grid in init_fonts().
CAROUSEL_CENTER_W  = 90
CAROUSEL_CENTER_H  = 60
CAROUSEL_SIDE_W    = 60
CAROUSEL_SIDE_H    = 40
CAROUSEL_FAR_W     = 36
CAROUSEL_FAR_H     = 24
CAROUSEL_CENTER_X  = (SCREEN_W - CAROUSEL_CENTER_W) // 2
CAROUSEL_CENTER_Y  = 28
CAROUSEL_ITEM_GAP  = 6


# -- Font loading -------------------------------------------------------------
# Three PixelCode variants loaded from arm_ui/fonts/:
#   PixelCode.ttf         -> Regular: body text, box chrome, parameter labels
#   PixelCode-Italic.ttf  -> Italic:  hints, secondary info, dim text
#   PixelCode-Medium.ttf  -> Medium:  section headers, selected item names
#
# To download on Pi (fonts are committed to the repo; use git pull):
#   BASE="https://github.com/qwerasd205/PixelCode/raw/main/dist/ttf"
#   wget "$BASE/PixelCode.ttf"         -O arm_ui/fonts/PixelCode.ttf
#   wget "$BASE/PixelCode-Italic.ttf"  -O arm_ui/fonts/PixelCode-Italic.ttf
#   wget "$BASE/PixelCode-Medium.ttf"  -O arm_ui/fonts/PixelCode-Medium.ttf

# Font dicts - populated by init_fonts(), keyed by font size int.
FONTS_R = {}   # Regular: body text, box chrome, labels
FONTS_I = {}   # Italic:  hints, secondary info, status messages
FONTS_M = {}   # Medium:  headers, selected names, emphasis
FONTS   = {}   # Backward-compat alias pointing to FONTS_R


def _load_font_file(filename, size):
    """Load a TTF from arm_ui/fonts/. Returns None if the file is missing."""
    fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
    path = os.path.join(fonts_dir, filename)
    if os.path.isfile(path):
        try:
            return pygame.font.Font(path, size)
        except Exception:
            pass
    return None


def _fallback_font(size):
    """Return the best available monospace system font as a fallback."""
    for name in ("terminus", "Terminus", "terminusfont",
                 "dejavusansmono", "couriernew", "courier", "monospace"):
        try:
            f = pygame.font.SysFont(name, size)
            if f:
                return f
        except Exception:
            pass
    return pygame.font.Font(None, size)


def _snap(value, cell):
    """Round value up to the nearest multiple of cell size."""
    if cell <= 0:
        return value
    return ((value + cell - 1) // cell) * cell


def init_fonts():
    """Populate font dicts and compute grid cell size. Must be called after pygame.init()."""
    global FONTS_R, FONTS_I, FONTS_M, FONTS, CELL_W, CELL_H
    global CAROUSEL_CENTER_W, CAROUSEL_CENTER_H
    global CAROUSEL_SIDE_W,   CAROUSEL_SIDE_H
    global CAROUSEL_FAR_W,    CAROUSEL_FAR_H
    global CAROUSEL_CENTER_X

    sizes = [FONT_TINY, FONT_SMALL, FONT_MEDIUM, FONT_LARGE, FONT_GIANT]

    for s in sizes:
        r = _load_font_file("PixelCode.ttf", s) or _fallback_font(s)
        i = _load_font_file("PixelCode-Italic.ttf", s) or r
        m = _load_font_file("PixelCode-Medium.ttf", s) or r
        FONTS_R[s] = r
        FONTS_I[s] = i
        FONTS_M[s] = m

    FONTS = FONTS_R   # backward compat

    # Compute cell dimensions from actual rendered metrics at FONT_SMALL.
    # Block character (U+2588) is guaranteed full-advance-width in PixelCode.
    cell = FONTS_R[FONT_SMALL].size("\u2588")
    CELL_W = max(1, cell[0])
    CELL_H = max(1, cell[1])

    # Snap carousel tile sizes to the character grid so box borders tile cleanly.
    # All tiles maintain the 3:2 (1.5:1) aspect ratio of the physical display.
    CAROUSEL_CENTER_W = _snap(90, CELL_W)
    CAROUSEL_CENTER_H = _snap(60, CELL_H)
    CAROUSEL_SIDE_W   = _snap(60, CELL_W)
    CAROUSEL_SIDE_H   = _snap(40, CELL_H)
    CAROUSEL_FAR_W    = _snap(36, CELL_W)
    CAROUSEL_FAR_H    = _snap(24, CELL_H)
    CAROUSEL_CENTER_X = (SCREEN_W - CAROUSEL_CENTER_W) // 2


# -- Text rendering helpers ---------------------------------------------------

def txt(font_size, text, color):
    """Render with Regular variant, antialias=False (body text, labels, box chrome)."""
    return FONTS_R[font_size].render(text, False, color)


def txt_italic(font_size, text, color):
    """Render with Italic variant (hints, secondary info, dim text)."""
    return FONTS_I[font_size].render(text, False, color)


def txt_medium(font_size, text, color):
    """Render with Medium variant (section headers, selected item names)."""
    return FONTS_M[font_size].render(text, False, color)


# -- Legacy drawing helpers ---------------------------------------------------

def draw_box(surface, rect, active=False):
    """Draw a solid-border filled box. White border when active, dark grey when not.

    Kept for backward compatibility; new code should use widgets.Box instead.
    rect can be a pygame.Rect or (x, y, w, h) tuple.
    """
    color = BORDER_ACTIVE if active else BORDER_INACTIVE
    pygame.draw.rect(surface, BG_PANEL, rect)
    pygame.draw.rect(surface, color, rect, 1)


def draw_dotted_rect(surface, color, rect, step=3):
    """Draw a dotted border (used for parameter bar tracks)."""
    if isinstance(rect, (tuple, list)):
        x, y, w, h = rect
    else:
        x, y, w, h = rect.x, rect.y, rect.width, rect.height

    for px in range(x, x + w, step):
        surface.set_at((px, y),         color)
        surface.set_at((px, y + h - 1), color)
    for py in range(y, y + h, step):
        surface.set_at((x,         py), color)
        surface.set_at((x + w - 1, py), color)
