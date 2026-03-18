# ABOUTME: Character-based widget framework for the ARM Pygame UI using PixelCode glyphs.
# ABOUTME: Every widget is built from Unicode box-drawing, block, and geometric characters.

"""
Widget framework overview
--------------------------
All widgets render using PixelCode's monospace glyph set. Because every
character has the same advance width (CELL_W x CELL_H pixels), we can think
in character-grid units and get perfectly tiled box borders automatically.

The three font variants map to visual roles:
  Regular  -> labels, box chrome, body text        (theme.FONTS_R)
  Italic   -> hints, secondary values, dim text    (theme.FONTS_I)
  Medium   -> section headers, active/selected     (theme.FONTS_M)

Coordinate system: all functions accept pixel (x, y) positions unless the
function name ends in _g, which means grid-column/grid-row coordinates.
Use cx(col) / cy(row) to convert grid coords to pixels.

Glyph reference (PixelCode Unicode coverage):
  Box single:  U+250C U+2510 U+2514 U+2518 U+2500 U+2502  (corners + sides)
  Box double:  U+2554 U+2557 U+255A U+255D U+2550 U+2551  (corners + sides)
  Block fills: U+2588 U+2593 U+2592 U+2591              (full/dark/med/light)
  Fractional:  U+258F..U+2588  left 1/8 -> full (horizontal fill precision)
  Geometric:   U+25CF U+25CB U+25A0 U+25A1 U+25B2 U+25B6 U+25C0 U+25C6
  Arrows:      U+2190 U+2192 U+2191 U+2193
  Checks:      U+2713 U+2717 U+2714 U+2718
"""

import pygame
from arm_ui import theme

# -- Box-drawing characters ---------------------------------------------------
# Single-line
_TL = "\u250c"   # top-left     corner  (┌)
_TR = "\u2510"   # top-right    corner  (┐)
_BL = "\u2514"   # bottom-left  corner  (└)
_BR = "\u2518"   # bottom-right corner  (┘)
_H  = "\u2500"   # horizontal   line    (─)
_V  = "\u2502"   # vertical     line    (│)
_LT = "\u251c"   # left T junction      (├)
_RT = "\u2524"   # right T junction     (┤)
_TT = "\u252c"   # top T junction       (┬)
_BT = "\u2534"   # bottom T junction    (┴)
_XX = "\u253c"   # cross                (┼)

# Double-line
_DTL = "\u2554"  # (╔)
_DTR = "\u2557"  # (╗)
_DBL = "\u255a"  # (╚)
_DBR = "\u255d"  # (╝)
_DH  = "\u2550"  # (═)
_DV  = "\u2551"  # (║)

# Block elements for progress bars
_BLOCK_FULL  = "\u2588"  # █ 100%
_BLOCK_DARK  = "\u2593"  # ▓  75%
_BLOCK_MED   = "\u2592"  # ▒  50%
_BLOCK_LIGHT = "\u2591"  # ░  25%

# Sub-character horizontal fractions (1/8 increments, left-aligned fill)
_FRACS = [
    "\u258f",  # 1/8  ▏
    "\u258e",  # 2/8  ▎
    "\u258d",  # 3/8  ▍
    "\u258c",  # 4/8  ▌
    "\u258b",  # 5/8  ▋
    "\u258a",  # 6/8  ▊
    "\u2589",  # 7/8  ▉
    "\u2588",  # 8/8  █
]

# Geometric / indicator shapes
SYM_DOT_FULL  = "\u25cf"   # ●  filled circle
SYM_DOT_EMPTY = "\u25cb"   # ○  empty  circle
SYM_SQ_FULL   = "\u25a0"   # ■  filled square
SYM_SQ_EMPTY  = "\u25a1"   # □  empty  square
SYM_DIAMOND   = "\u25c6"   # ◆  filled diamond
SYM_TRI_UP    = "\u25b2"   # ▲  triangle up
SYM_ARROW_R   = "\u25b6"   # ▶  arrow right
SYM_ARROW_L   = "\u25c0"   # ◀  arrow left
SYM_ARROW_LR  = "\u2194"   # ↔  bidirectional arrow
SYM_CHECK     = "\u2713"   # ✓  check mark
SYM_CROSS     = "\u2717"   # ✗  cross mark


# -- Grid coordinate helpers --------------------------------------------------

def cx(col):
    """Convert grid column index to pixel x coordinate."""
    return col * theme.CELL_W


def cy(row):
    """Convert grid row index to pixel y coordinate."""
    return row * theme.CELL_H


def cols_for(width_px):
    """Number of full character columns that fit in width_px."""
    return max(1, width_px // theme.CELL_W)


def rows_for(height_px):
    """Number of full character rows that fit in height_px."""
    return max(1, height_px // theme.CELL_H)


# -- Core rendering primitives ------------------------------------------------

def _font(variant, size):
    """Return the pygame.Font for a given variant and size."""
    if variant == "italic":
        return theme.FONTS_I.get(size) or theme.FONTS_R.get(size)
    if variant == "medium":
        return theme.FONTS_M.get(size) or theme.FONTS_R.get(size)
    return theme.FONTS_R.get(size)


def draw_char(surface, x, y, char, color, size=None, variant="regular"):
    """Blit a single character at pixel position (x, y)."""
    if size is None:
        size = theme.FONT_SMALL
    s = _font(variant, size).render(char, False, color)
    surface.blit(s, (x, y))


def draw_str(surface, x, y, text, color, size=None, variant="regular"):
    """Blit a string at pixel position (x, y). Returns the rendered Surface."""
    if size is None:
        size = theme.FONT_SMALL
    s = _font(variant, size).render(text, False, color)
    surface.blit(s, (x, y))
    return s


# -- Widget: Box --------------------------------------------------------------

def box(surface, x, y, w_px, h_px, color, double=False, fill=None):
    """Draw a box using PixelCode box-drawing characters.

    The box is drawn character-by-character so borders tile perfectly on the
    character grid. Dimensions are treated as the outer pixel size including
    the border characters; the inner content area starts at (x+CELL_W, y+CELL_H).

    Args:
        surface:  pygame.Surface to draw on
        x, y:     pixel position of the top-left corner
        w_px:     total width  in pixels (snapped down to CELL_W multiples)
        h_px:     total height in pixels (snapped down to CELL_H multiples)
        color:    border color (RGB tuple)
        double:   use double-line characters (╔═╗) instead of single (┌─┐)
        fill:     optional background fill color for the interior
    """
    cw, ch = theme.CELL_W, theme.CELL_H
    font = theme.FONTS_R[theme.FONT_SMALL]
    cols = max(2, w_px // cw)
    rows = max(2, h_px // ch)

    if double:
        tl, tr, bl, br, hh, vv = _DTL, _DTR, _DBL, _DBR, _DH, _DV
    else:
        tl, tr, bl, br, hh, vv = _TL, _TR, _BL, _BR, _H, _V

    # Fill interior
    if fill is not None:
        inner_rect = pygame.Rect(x + cw, y + ch,
                                 (cols - 2) * cw, (rows - 2) * ch)
        pygame.draw.rect(surface, fill, inner_rect)

    def _blit(col, row, char):
        s = font.render(char, False, color)
        surface.blit(s, (x + col * cw, y + row * ch))

    # Top row
    _blit(0, 0, tl)
    for c in range(1, cols - 1):
        _blit(c, 0, hh)
    _blit(cols - 1, 0, tr)

    # Middle rows (vertical sides only)
    for r in range(1, rows - 1):
        _blit(0,        r, vv)
        _blit(cols - 1, r, vv)

    # Bottom row
    _blit(0, rows - 1, bl)
    for c in range(1, cols - 1):
        _blit(c, rows - 1, hh)
    _blit(cols - 1, rows - 1, br)


def box_inner(x, y, w_px, h_px):
    """Return the pygame.Rect of the inner content area of a box() call.

    The content area is one cell inset from every edge (inside the border chars).
    """
    cw, ch = theme.CELL_W, theme.CELL_H
    cols = max(2, w_px // cw)
    rows = max(2, h_px // ch)
    return pygame.Rect(x + cw, y + ch, (cols - 2) * cw, (rows - 2) * ch)


def hline(surface, x, y, w_px, color):
    """Draw a horizontal rule using box-drawing H characters."""
    cw = theme.CELL_W
    font = theme.FONTS_R[theme.FONT_SMALL]
    cols = max(1, w_px // cw)
    s = font.render(_H * cols, False, color)
    surface.blit(s, (x, y))


def vline(surface, x, y, h_px, color):
    """Draw a vertical rule using box-drawing V characters."""
    ch = theme.CELL_H
    font = theme.FONTS_R[theme.FONT_SMALL]
    rows = max(1, h_px // ch)
    for r in range(rows):
        s = font.render(_V, False, color)
        surface.blit(s, (x, y + r * ch))


# -- Widget: Progress bar -----------------------------------------------------

def hbar(surface, x, y, w_px, value, max_value, fg_color, bg_color=None):
    """Draw a horizontal progress bar using PixelCode block characters.

    Fills character columns proportionally. The last partial column uses a
    fractional block glyph (1/8 precision) for smooth-looking fills.

    Args:
        value:     current value (0 to max_value)
        max_value: maximum value
        fg_color:  fill color
        bg_color:  optional background/track color (uses light block ░)
    """
    cw = theme.CELL_W
    font = theme.FONTS_R[theme.FONT_SMALL]
    cols = max(1, w_px // cw)

    if bg_color is not None:
        bg_str = _BLOCK_LIGHT * cols
        s = font.render(bg_str, False, bg_color)
        surface.blit(s, (x, y))

    ratio = max(0.0, min(1.0, value / max_value)) if max_value > 0 else 0.0
    filled_f = ratio * cols
    filled   = int(filled_f)
    frac     = filled_f - filled

    if filled > 0:
        s = font.render(_BLOCK_FULL * filled, False, fg_color)
        surface.blit(s, (x, y))

    if filled < cols and frac >= 0.125:
        frac_idx = min(7, int(frac * 8))
        s = font.render(_FRACS[frac_idx], False, fg_color)
        surface.blit(s, (x + filled * cw, y))


def vbar(surface, x, y, h_px, value, max_value, fg_color, bg_color=None):
    """Draw a vertical progress bar (fills bottom to top) using block characters.

    Uses full-block █ characters stacked vertically. One character = one step.
    """
    ch = theme.CELL_H
    font = theme.FONTS_R[theme.FONT_SMALL]
    rows = max(1, h_px // ch)
    ratio = max(0.0, min(1.0, value / max_value)) if max_value > 0 else 0.0
    filled = round(ratio * rows)

    for r in range(rows):
        row_from_bottom = rows - 1 - r
        char  = _BLOCK_FULL  if row_from_bottom < filled else (_BLOCK_LIGHT if bg_color else " ")
        color = fg_color     if row_from_bottom < filled else (bg_color or fg_color)
        s = font.render(char, False, color)
        surface.blit(s, (x, y + r * ch))


# -- Widget: Toggle -----------------------------------------------------------

def toggle(surface, x, y, value, color_on, color_off=None):
    """Draw a toggle switch using geometric characters.

    On:  [● ] with color_on
    Off: [ ○] with color_off (defaults to TEXT_DIM)
    """
    color_off = color_off or theme.TEXT_DIM
    font = theme.FONTS_R[theme.FONT_SMALL]
    if value:
        text  = "[" + SYM_DOT_FULL  + " ]"
        color = color_on
    else:
        text  = "[ " + SYM_DOT_EMPTY + "]"
        color = color_off
    s = font.render(text, False, color)
    surface.blit(s, (x, y))


# -- Widget: Label / hint bar -------------------------------------------------

def label(surface, x, y, text, color=None, size=None, variant="regular"):
    """Draw a text label. Convenience wrapper around draw_str."""
    return draw_str(surface, x, y, text,
                    color or theme.TEXT_PRIMARY,
                    size  or theme.FONT_SMALL,
                    variant)


def hint_bar(surface, hints, y=None):
    """Draw the bottom hint bar showing key:action pairs in italic dim text.

    Args:
        hints: list of (key_label, action_label) tuples
               e.g. [("L/R", "move"), ("Enter", "select"), ("Esc", "quit")]
        y:     pixel y position; defaults to one row above screen bottom
    """
    if y is None:
        y = theme.SCREEN_H - theme.CELL_H

    # Horizontal separator line
    hline(surface, 0, y - 2, theme.SCREEN_W, theme.SEPARATOR)

    parts = []
    for key, action in hints:
        parts.append(key + ":" + action)
    text = "  ".join(parts)

    font = theme.FONTS_I[theme.FONT_TINY]
    s = font.render(text, False, theme.TEXT_DIM)
    surface.blit(s, s.get_rect(centerx=theme.SCREEN_W // 2, y=y))


# -- Widget: Title bar --------------------------------------------------------

def title_bar(surface, left_text, right_text=None, y=0):
    """Draw a top title bar with left and optional right label.

    Left text uses Medium variant in accent color (app/mode name).
    Right text uses Italic variant in dim color (version / sub-label).
    """
    font_l = theme.FONTS_M[theme.FONT_TINY]
    font_r = theme.FONTS_I[theme.FONT_TINY]

    sl = font_l.render(left_text,  False, theme.ACCENT)
    surface.blit(sl, (theme.CELL_W, y))

    if right_text:
        sr = font_r.render(right_text, False, theme.TEXT_DIM)
        surface.blit(sr, (theme.SCREEN_W - sr.get_width() - theme.CELL_W, y))

    # Underline separator
    hline(surface, 0, y + theme.CELL_H, theme.SCREEN_W, theme.SEPARATOR)


# -- Widget: Status indicator -------------------------------------------------

def status_dot(surface, x, y, active, label_text="", size=None):
    """Draw a filled/empty circle with an optional label to the right.

    active=True  -> filled ● in ACCENT green
    active=False -> empty  ○ in TEXT_DIM grey
    """
    size = size or theme.FONT_SMALL
    color = theme.ACCENT if active else theme.TEXT_DIM
    char  = SYM_DOT_FULL if active else SYM_DOT_EMPTY
    draw_str(surface, x, y, char, color, size)
    if label_text:
        lx = x + theme.CELL_W + 2
        draw_str(surface, lx, y, label_text, color, size)


# -- Widget: Selector (left/right arrows around a value) ----------------------

def selector(surface, x, y, value_text, color=None, size=None):
    """Draw a value selector:  ◀ VALUE ▶  for parameter browsing.

    Returns a tuple (left_rect, right_rect) as pygame.Rects for hit-testing.
    """
    size  = size  or theme.FONT_SMALL
    color = color or theme.TEXT_PRIMARY
    font  = theme.FONTS_R[size]
    cw    = theme.CELL_W

    arrow_l = font.render(SYM_ARROW_L, False, color)
    value_s = font.render(value_text,  False, color)
    arrow_r = font.render(SYM_ARROW_R, False, color)

    total_w = arrow_l.get_width() + cw + value_s.get_width() + cw + arrow_r.get_width()
    ax = x
    vx = ax + arrow_l.get_width() + cw
    rx = vx + value_s.get_width() + cw

    surface.blit(arrow_l, (ax, y))
    surface.blit(value_s, (vx, y))
    surface.blit(arrow_r, (rx, y))

    left_rect  = pygame.Rect(ax, y, arrow_l.get_width(), arrow_l.get_height())
    right_rect = pygame.Rect(rx, y, arrow_r.get_width(), arrow_r.get_height())
    return left_rect, right_rect


# -- Widget: Parameter row ----------------------------------------------------

def param_row(surface, x, y, w_px, name, value_text, bar_value=None, bar_max=1.0):
    """Draw a single parameter row: NAME ........ VALUE [bar].

    Designed for the synth screen parameter list. The bar is optional.
    Name uses Regular dim, value uses Medium primary, bar fills remaining space.
    """
    font_name  = theme.FONTS_R[theme.FONT_TINY]
    font_value = theme.FONTS_M[theme.FONT_SMALL]
    cw = theme.CELL_W

    name_s  = font_name.render(name.upper(),  False, theme.TEXT_DIM)
    value_s = font_value.render(value_text,    False, theme.TEXT_PRIMARY)

    surface.blit(name_s, (x, y + 1))

    if bar_value is not None:
        bar_x = x + name_s.get_width() + cw
        bar_w = w_px - name_s.get_width() - value_s.get_width() - cw * 3
        if bar_w > cw:
            hbar(surface, bar_x, y + 2, bar_w, bar_value, bar_max,
                 theme.ACCENT, theme.BAR_BG)
        vx = x + w_px - value_s.get_width()
    else:
        vx = x + w_px - value_s.get_width()

    surface.blit(value_s, (vx, y))
