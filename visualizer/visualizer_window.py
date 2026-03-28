# ABOUTME: Visualizer pygame window - runs as a detached subprocess on Windows, macOS, and Linux desktop.
# ABOUTME: Hosts six visual modes (bar VU with info panel, oscilloscope, needle VU, wireframe globe, Unknown Pleasures ridgelines, asteroid field) in VFD amber palette.

import sys
import os
import json
import math
import random
import struct
import platform
import collections
import numpy as np
import pygame
from pathlib import Path
from multiprocessing.shared_memory import SharedMemory


# Visual constants
WINDOW_WIDTH  = 216
WINDOW_HEIGHT = 162
WINDOW_TITLE  = "Acordes Visualizer"
FPS           = 60

# ── VU meter layout ───────────────────────────────────────────────────────────

# Bar layout — three zones: left info panel | middle meter column | right VU bars.
# Left panel:    x=4   .. INFO_PANEL_RIGHT  (static metadata)
# Middle column: x=METER_COL_L .. METER_COL_R  (live dBFS + LUFS large values)
# dB scale:      ticks at DB_SCALE_X, labels right-aligned to DB_SCALE_X-1
# Bars:          BAR_LEFT_X and BAR_RIGHT_X hug the right margin
BAR_WIDTH        = 16
BAR_GAP          = 6
BAR_TOP          = 8
BAR_HEIGHT       = 126
INFO_PANEL_RIGHT = 88    # right edge of the left info box (x-exclusive)
METER_COL_L      = 91    # left edge of the middle dBFS/LUFS column
METER_COL_R      = 152   # right edge of the middle column
# dB scale: ticks at DB_SCALE_X, labels rendered right-aligned to DB_SCALE_X-1
DB_SCALE_X       = 160   # x of the 4-px tick line
BAR_LEFT_X       = 168   # first (left) bar starts here   (ends at 184)
BAR_RIGHT_X      = BAR_LEFT_X + BAR_WIDTH + BAR_GAP  # = 190, ends at 206

# dB scale: bar fraction maps linearly from DB_MIN to DB_MAX (0 dBFS).
DB_MIN = -48.0
DB_MAX =   0.0
DB_TICKS = [0, -6, -12, -18, -24, -36, -48]


# Asymmetric smoothing coefficients at 60 FPS.
SMOOTH_ATTACK  = 0.6
SMOOTH_RELEASE = 0.88
PEAK_HOLD_FRAMES = 180   # frames to hold peak before falling (3 s at 60 FPS)
PEAK_FALL_RATE   = 0.08  # dB per frame decay once hold expires

# ── Oscilloscope layout ───────────────────────────────────────────────────────

# Waveform display area (reuses BAR_TOP / BAR_HEIGHT for vertical alignment)
SCOPE_LEFT    = 8
SCOPE_RIGHT   = WINDOW_WIDTH - 8
SCOPE_WIDTH   = SCOPE_RIGHT - SCOPE_LEFT
SCOPE_TOP     = BAR_TOP
SCOPE_HEIGHT  = BAR_HEIGHT

# Number of samples read from shm circular buffer and number displayed per frame
WAVEFORM_SAMPLES = 2048   # must match engine_proxy / synth_engine constant
DISPLAY_SAMPLES  = 256    # samples shown across the scope width (~11.6 ms at 44100 Hz)

# Oscilloscope layout uses the shared VFD palette defined in the Needle VU section.

# ── Shared colours ────────────────────────────────────────────────────────────

BG_COLOR   = (18, 18, 18)     # background for VU bar and scope modes
TEXT_COLOR = (240, 240, 240)  # mode label text (non-needle modes)

# Shared memory layout (set by synth_mode.py):
#   bytes  0-3:  level_l  (f32)
#   bytes  4-7:  level_r  (f32)
#   bytes  8-11: command  (i32)  0=idle, 1=toggle fullscreen, 2=cycle mode
#   bytes 12-15: write_pos (i32) circular waveform buffer head
#   bytes 16+:   WAVEFORM_SAMPLES x f32 waveform data
SHM_SIZE = 16 + WAVEFORM_SAMPLES * 4   # 8208 bytes

# Note ring buffer offsets (immediately after waveform data in SHM)
NOTE_SHM_BASE   = 16 + WAVEFORM_SAMPLES * 4   # = 8208
NOTE_RING_SLOTS = 8

# Position persistence file - stored next to this module
_POSITION_FILE = Path(__file__).parent / 'window_position.json'

# Visual mode indices
MODE_VU_METER    = 0
MODE_OSCILLOSCOPE = 1
MODE_NEEDLE_VU   = 2
MODE_SPHERE      = 3
MODE_GRID        = 4
MODE_ASTEROIDS   = 5
MODE_COF         = 6
MODE_DOT         = 7
MODE_COUNT       = 8
MODE_NAMES       = ["VU Meter", "Scope", "Needle VU", "Globe", "Pulsar", "Asteroids", "Circle of 5ths", "Dot"]

# ── Mode picker overlay ────────────────────────────────────────────────────────
# Shown briefly after each Tab press; auto-hides after PICKER_FRAMES frames.
# No extra key binds required — Tab already arrives via the SHM command channel.
PICKER_FRAMES     = 90    # frames the overlay stays visible (~1.8 s at 50 FPS)
PICKER_COLS       = 2     # columns in the name grid
PICKER_CELL_W     = 96    # width of each cell in pixels
PICKER_CELL_H     = 14    # height of each cell in pixels
PICKER_PAD_X      = 6     # horizontal text padding inside a cell
PICKER_PAD_Y      = 3     # vertical text padding inside a cell


def _draw_mode_picker(target_surf, current_mode: int, font_small, alpha: int,
                      font_title=None):
    """Render the mode picker overlay onto target_surf.

    Panel sits in the bottom half of the screen, horizontally centred.
    Above the name grid a larger title shows the active visual name.
    The panel background is fully opaque; text uses alpha for colour scaling.
    """
    TITLE_PAD_Y = 4   # padding above/below the title text inside the panel
    TITLE_H     = (font_title.size("A")[1] if font_title else 0) + TITLE_PAD_Y * 2

    rows      = math.ceil(MODE_COUNT / PICKER_COLS)
    panel_w   = PICKER_COLS * PICKER_CELL_W + 4
    panel_h   = TITLE_H + rows * PICKER_CELL_H + 4
    panel_x   = (WINDOW_WIDTH  - panel_w) // 2
    panel_y   = (WINDOW_HEIGHT - panel_h) // 2

    # Opaque background.
    pygame.draw.rect(target_surf, (8, 4, 0),
                     (panel_x, panel_y, panel_w, panel_h))

    # Border.
    border_col = (
        int(VFD_BRACKET[0] * alpha / 255),
        int(VFD_BRACKET[1] * alpha / 255),
        int(VFD_BRACKET[2] * alpha / 255),
    )
    pygame.draw.rect(target_surf, border_col,
                     (panel_x, panel_y, panel_w, panel_h), 1)

    # Title: current visual name in larger font above the grid.
    if font_title is not None:
        title_col = (
            int(VFD_BRIGHT[0] * alpha / 255),
            int(VFD_BRIGHT[1] * alpha / 255),
            int(VFD_BRIGHT[2] * alpha / 255),
        )
        title_surf = font_title.render(MODE_NAMES[current_mode].upper(), False, title_col)
        tx = panel_x + (panel_w - title_surf.get_width()) // 2
        ty = panel_y + TITLE_PAD_Y
        target_surf.blit(title_surf, (tx, ty))

    # Separator line between title and grid.
    sep_y = panel_y + TITLE_H
    pygame.draw.line(target_surf, border_col,
                     (panel_x + 1, sep_y), (panel_x + panel_w - 2, sep_y), 1)

    # Mode name cells.
    for idx, name in enumerate(MODE_NAMES):
        col = idx % PICKER_COLS
        row = idx // PICKER_COLS
        cx  = panel_x + 2 + col * PICKER_CELL_W
        cy  = panel_y + TITLE_H + row * PICKER_CELL_H

        if idx == current_mode:
            pygame.draw.rect(target_surf, VFD_DIM,
                             (cx, cy, PICKER_CELL_W, PICKER_CELL_H))
            txt_col = (
                int(VFD_BRIGHT[0] * alpha / 255),
                int(VFD_BRIGHT[1] * alpha / 255),
                int(VFD_BRIGHT[2] * alpha / 255),
            )
        else:
            txt_col = (
                int(VFD_DIM[0] * alpha / 255),
                int(VFD_DIM[1] * alpha / 255),
                int(VFD_DIM[2] * alpha / 255),
            )

        label = font_small.render(name.upper(), False, txt_col)
        target_surf.blit(label, (cx + PICKER_PAD_X, cy + PICKER_PAD_Y))


# ── Position persistence ─────────────────────────────────────────────────────

def _load_position():
    """Load last saved window position. Returns (x, y) or (None, None)."""
    try:
        data = json.loads(_POSITION_FILE.read_text())
        return int(data['x']), int(data['y'])
    except Exception:
        return None, None


def _save_position(x: int, y: int):
    """Save current window position to disk."""
    try:
        _POSITION_FILE.write_text(json.dumps({'x': x, 'y': y}))
    except Exception:
        pass


# ── Platform window helpers ───────────────────────────────────────────────────
#
# Three tiers:
#   Windows  - Win32 API via ctypes (always-on-top, drag, restore, screen size)
#   Linux    - wmctrl subprocess calls (always-on-top, drag); requires wmctrl
#              package (available on all major desktop distros via apt/dnf/pacman)
#   macOS    - No always-on-top or drag (would require pyobjc); window works fully
#              but stays at default Z-order and cannot be dragged by title-less frame.

_SYSTEM    = platform.system()
# Wayland compositors enforce focus isolation at the protocol level, so focus
# stealing does not occur and xdotool/wmctrl are not needed (or available).
# Always-on-top via _NET_WM_STATE_ABOVE is also X11-only; on Wayland the window
# behaves like a normal surface unless the compositor exposes layer-shell.
_ON_WAYLAND = _SYSTEM == "Linux" and bool(os.environ.get('WAYLAND_DISPLAY'))
_ON_X11     = _SYSTEM == "Linux" and not _ON_WAYLAND


# ── Windows / Win32 ──────────────────────────────────────────────────────────

def _get_win32():
    """Return (user32, ctypes) or (None, None) on non-Windows."""
    if _SYSTEM != "Windows":
        return None, None
    try:
        import ctypes
        import ctypes.wintypes
        return ctypes.windll.user32, ctypes
    except Exception:
        return None, None


def _setup_always_on_top_win32(user32, ctypes):
    """
    Locate the window handle via FindWindowW and apply always-on-top.
    Sets WS_EX_TOPMOST | WS_EX_NOACTIVATE extended styles so the window stays
    on top but never steals keyboard focus (even when clicked).
    Returns hwnd or None.
    """
    if user32 is None:
        return None
    try:
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return None
        GWL_EXSTYLE      = -20
        WS_EX_TOPMOST    = 0x00000008
        WS_EX_NOACTIVATE = 0x08000000   # never steal keyboard focus
        current = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                              current | WS_EX_TOPMOST | WS_EX_NOACTIVATE)
        HWND_TOPMOST  = ctypes.wintypes.HWND(-1)
        SWP_NOSIZE    = 0x0001
        SWP_NOMOVE    = 0x0002
        SWP_NOACTIVATE = 0x0010
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
        return hwnd
    except Exception:
        return None


def _return_focus_win32(user32, terminal_hwnd: int):
    """Return keyboard focus to the terminal window (Windows only)."""
    if not terminal_hwnd or user32 is None:
        return
    try:
        user32.SetForegroundWindow(terminal_hwnd)
    except Exception:
        pass


def _return_focus_linux(terminal_xid: int):
    """Return keyboard focus to the terminal X11 window (X11 Linux only).
    On Wayland this is a no-op: the compositor prevents focus stealing natively,
    so the terminal retains focus without any intervention from the app.
    """
    if not terminal_xid or not _ON_X11:
        return
    try:
        import subprocess as _sp
        _sp.Popen(
            ['xdotool', 'windowfocus', str(terminal_xid)],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except Exception:
        pass


def _get_window_pos_win32(user32, ctypes, hwnd):
    """Return (x, y) of the window's top-left corner in screen coords."""
    try:
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect.left, rect.top
    except Exception:
        return 0, 0


def _set_window_pos_win32(user32, hwnd, x: int, y: int):
    """Move the window to (x, y) without changing size or Z-order."""
    try:
        SWP_NOSIZE   = 0x0001
        SWP_NOZORDER = 0x0004
        user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER)
    except Exception:
        pass


def _get_cursor_screen_pos_win32(user32, ctypes):
    """Return current cursor position in screen coordinates."""
    try:
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 0, 0


def _restore_if_minimized_win32(user32, ctypes, hwnd):
    """Restore the window if it was minimized (Win32 only)."""
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    except Exception:
        pass


def _get_screen_size_win32(user32, ctypes):
    """Return (width, height) of the primary monitor via Win32."""
    try:
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        info = pygame.display.Info()
        return info.current_w, info.current_h


# ── Linux / wmctrl ───────────────────────────────────────────────────────────

def _get_x11_window_id():
    """Return the X11 window ID from pygame WM info, or None."""
    try:
        wm = pygame.display.get_wm_info()
        return wm.get('window')
    except Exception:
        return None


def _setup_always_on_top_linux(x11_wid):
    """
    Use wmctrl to add the _NET_WM_STATE_ABOVE hint.
    Silently ignored if wmctrl is not installed or not on X11.
    """
    if x11_wid is None:
        return
    try:
        import subprocess as _sp
        _sp.Popen(
            ['wmctrl', '-i', '-r', hex(x11_wid), '-b', 'add,above'],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except Exception:
        pass


def _move_window_linux(x11_wid, x: int, y: int):
    """
    Move window to (x, y) via wmctrl -e gravity,x,y,w,h.
    -1 means "keep current" for width/height.
    """
    if x11_wid is None:
        return
    try:
        import subprocess as _sp
        _sp.Popen(
            ['wmctrl', '-i', '-r', hex(x11_wid), '-e', f'0,{x},{y},-1,-1'],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except Exception:
        pass


def _get_window_pos_linux(x11_wid) -> tuple:
    """
    Read window position via xwininfo.
    Returns (x, y) or (0, 0) on failure.
    """
    if x11_wid is None:
        return 0, 0
    try:
        import subprocess as _sp
        out = _sp.check_output(
            ['xwininfo', '-id', str(x11_wid)],
            stderr=_sp.DEVNULL, text=True
        )
        x = y = 0
        for line in out.splitlines():
            line = line.strip()
            if line.startswith('Absolute upper-left X:'):
                x = int(line.split(':')[1].strip())
            elif line.startswith('Absolute upper-left Y:'):
                y = int(line.split(':')[1].strip())
        return x, y
    except Exception:
        return 0, 0


# ── Unified interface (called by render loop) ─────────────────────────────────

def _setup_always_on_top(user32, ctypes):
    """Apply always-on-top for the current platform."""
    if _SYSTEM == "Windows":
        return _setup_always_on_top_win32(user32, ctypes)
    elif _ON_X11:
        wid = _get_x11_window_id()
        _setup_always_on_top_linux(wid)
        return wid   # used as the opaque "hwnd" on X11 Linux
    # Wayland: compositor controls Z-order; layer-shell not available without
    # a dedicated Wayland protocol library (e.g. pywayland + wlr-layer-shell).
    # macOS: not supported without pyobjc.
    return None


def _get_window_pos(user32, ctypes, hwnd):
    if _SYSTEM == "Windows":
        return _get_window_pos_win32(user32, ctypes, hwnd)
    elif _ON_X11:
        return _get_window_pos_linux(hwnd)
    return 0, 0


def _set_window_pos(user32, hwnd, x: int, y: int):
    if _SYSTEM == "Windows":
        _set_window_pos_win32(user32, hwnd, x, y)
    elif _ON_X11:
        _move_window_linux(hwnd, x, y)


def _get_cursor_screen_pos(user32, ctypes):
    if _SYSTEM == "Windows":
        return _get_cursor_screen_pos_win32(user32, ctypes)
    # Linux / macOS: pygame mouse position is window-relative; caller adds window origin
    mx, my = pygame.mouse.get_pos()
    return mx, my


def _restore_if_minimized(user32, ctypes, hwnd):
    if _SYSTEM == "Windows":
        _restore_if_minimized_win32(user32, ctypes, hwnd)
    # Linux/macOS: not needed; wmctrl handles focus, macOS no-op


def _get_screen_size(user32, ctypes):
    if _SYSTEM == "Windows":
        return _get_screen_size_win32(user32, ctypes)
    info = pygame.display.Info()
    return info.current_w, info.current_h


# ── VU meter drawing ─────────────────────────────────────────────────────────

def _level_to_bar_fraction(level: float) -> float:
    """Map linear amplitude (0-1) to bar fill fraction via dB scale + gain boost."""
    if level <= 0.0:
        return 0.0
    db = 20.0 * math.log10(max(level, 1e-9))
    fraction = (db - DB_MIN) / (DB_MAX - DB_MIN)
    return max(0.0, min(1.0, fraction))


def _build_grid_surface():
    """Pre-render the VFD background grid to a surface once at startup.
    Straight grid lines drawn at a fixed step; callers blit this surface
    instead of reissuing draw calls every frame.
    """
    surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    surf.fill(VFD_BG)

    step = 18

    # Horizontal lines
    for y in range(0, WINDOW_HEIGHT + 1, step):
        pygame.draw.line(surf, VFD_GRID, (0, y), (WINDOW_WIDTH, y), 1)

    # Vertical lines
    for x in range(0, WINDOW_WIDTH + 1, step):
        pygame.draw.line(surf, VFD_GRID, (x, 0), (x, WINDOW_HEIGHT), 1)

    return surf


# Module-level cache: populated by _init_grid_surface() after pygame.init().
_grid_surface = None


def _init_grid_surface():
    """Call once after pygame.display.set_mode() to build the grid cache."""
    global _grid_surface
    _grid_surface = _build_grid_surface()


def _draw_vfd_grid(surface):
    """Blit the pre-rendered grid background onto surface.
    Falls back to live drawing if the cache has not been initialised yet.
    """
    if _grid_surface is not None:
        surface.blit(_grid_surface, (0, 0))
    else:
        # Fallback: draw live (only happens before _init_grid_surface is called)
        step = 18
        for x in range(0, WINDOW_WIDTH + 1, step):
            pygame.draw.line(surface, VFD_GRID, (x, 0), (x, WINDOW_HEIGHT), 1)
        for y in range(0, WINDOW_HEIGHT + 1, step):
            pygame.draw.line(surface, VFD_GRID, (0, y), (WINDOW_WIDTH, y), 1)


# ── Unknown Pleasures — stacked hidden-line waveform ridgelines ───────────────
#
# Inspired by the Joy Division "Unknown Pleasures" album cover (Peter Saville,
# 1979 — derived from Harold Craft's pulsar radio data plot).
#
# Each frame a waveform snapshot is captured and prepended to a history list.
# The list is drawn as evenly-spaced horizontal ridgelines, oldest at the top
# and newest at the bottom.  Before drawing each line its filled polygon is
# painted in VFD_BG, erasing any previously drawn content in that area — this
# is the classic hidden-line-removal trick that produces the mountain silhouette
# occlusion effect.  Peaks rise upward; the newest line is always fully bright;
# older lines dim toward VFD_BG giving a phosphor-decay look.

UNPL_N_LINES    = 48     # number of stacked ridgelines
UNPL_LINE_STEP  = 5      # vertical pixels between baselines
UNPL_WAVE_SCL   = 28.0   # peak height in screen pixels (upward from baseline)
# Full line spans edge-to-edge; waveform is active only in the centre band.
UNPL_MARGIN_L   = 6                   # left edge of the full flat line (px)
UNPL_MARGIN_R   = WINDOW_WIDTH - 6   # right edge of the full flat line (px)
UNPL_WAVE_L     = WINDOW_WIDTH // 2 - 55   # left edge of the active waveform band
UNPL_WAVE_R     = WINDOW_WIDTH // 2 + 55   # right edge of the active waveform band
UNPL_BOTTOM_Y   = WINDOW_HEIGHT - 10 # baseline Y of the newest (bottom) line
UNPL_HISTORY_N  = 30     # snapshot buffer length (matches UNPL_N_LINES)
UNPL_CAPTURE_N  = 2      # capture a new snapshot every N render frames


def _draw_unknown_pleasures(surface, history: list):
    """Stacked hidden-line waveform ridgelines in VFD amber palette.

    Draws UNPL_N_LINES evenly spaced horizontal lines from oldest (top) to
    newest (bottom).  Each line:
      1. Fills its mountain polygon with VFD_BG  — hidden line removal.
      2. Draws the waveform outline in an amber colour that dims with age.
    The newest line always gets the two-pass glow treatment (halo + core).
    """
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    if not history:
        return

    n       = min(len(history), UNPL_N_LINES)
    # Number of points used for the active waveform band only
    n_wave  = max(2, min(UNPL_WAVE_R - UNPL_WAVE_L, DISPLAY_SAMPLES))
    wave_xs = np.linspace(UNPL_WAVE_L, UNPL_WAVE_R, n_wave, dtype=np.float32)

    # Cosine taper envelope: smoothly ramps displacement from 0 at the band
    # edges to 1 in the centre, eliminating the sharp flat→wave kink.
    taper_n  = max(1, n_wave // 5)   # taper spans the outer 20% on each side
    envelope = np.ones(n_wave, dtype=np.float32)
    for k in range(taper_n):
        t = 0.5 * (1.0 - math.cos(math.pi * k / taper_n))
        envelope[k]               = t
        envelope[n_wave - 1 - k]  = t

    # Draw oldest lines first (top of screen) down to newest (bottom).
    # Painter's algorithm: each foreground line's polygon erases background lines.
    for i in range(n - 1, -1, -1):
        wave, amp = history[i]

        # i=0 is newest (bottom); i=n-1 is oldest (top)
        y_base = UNPL_BOTTOM_Y - i * UNPL_LINE_STEP

        if y_base < 0:
            continue

        y_b = min(y_base, WINDOW_HEIGHT - 1)

        # ── Build three-section polyline: flat-left + wave-centre + flat-right ──
        # Displacement is tapered by the cosine envelope so the wave fades in and
        # out smoothly from the flat baseline — no abrupt joint.
        wi      = np.linspace(0, len(wave) - 1, n_wave).astype(np.int32)
        wave_ys = np.clip(y_base - wave[wi] * UNPL_WAVE_SCL * envelope,
                          0, WINDOW_HEIGHT - 1).astype(np.int32)

        # Combine: flat anchor points on each side + tapered wave in the middle
        pts = (
            [(UNPL_MARGIN_L, y_b), (UNPL_WAVE_L, y_b)]
            + list(zip(wave_xs.astype(np.int32).tolist(), wave_ys.tolist()))
            + [(UNPL_WAVE_R, y_b), (UNPL_MARGIN_R, y_b)]
        )

        # ── Hidden line removal ──────────────────────────────────────────────
        # Close the full-width polygon at the baseline and fill with VFD_BG.
        # This erases any older lines that fall within the mountain silhouette.
        poly = pts + [(UNPL_MARGIN_R, y_b), (UNPL_MARGIN_L, y_b)]
        pygame.draw.polygon(surface, VFD_BG, poly)

        # ── Draw outline — full opacity, no age fade ──────────────────────────
        pygame.draw.lines(surface, VFD_CYAN, False, pts, 1)


def _draw_info_panel(surface, font, font_small, sys_info: dict):
    """Draw a VFD-style information panel on the left side of the bar VU mode.

    Shows system/audio metadata (sample rate, buffer size, bit depth, OS, MIDI
    device) in retro vacuum fluorescent display style: dim label row above a
    bright value row, all inside a bracketed box matching the other VFD modes.
    """
    pad_x = 7    # horizontal padding inside panel
    pad_y = 6    # top padding
    panel_w = INFO_PANEL_RIGHT - 4  # inner content width (box starts at x=4)
    x0 = 4       # left edge of panel box (matches corner bracket)

    # Outer border box (dim amber, same colour as corner brackets)
    box_rect = pygame.Rect(x0, 4, panel_w, WINDOW_HEIGHT - 8)
    pygame.draw.rect(surface, VFD_DIM, box_rect, 1)

    # App name header
    hdr = font.render("ACORDES", True, VFD_BRIGHT)
    surface.blit(hdr, hdr.get_rect(centerx=x0 + panel_w // 2, top=4 + pad_y))

    # Thin separator below header
    sep_y = 4 + pad_y + hdr.get_height() + 2
    pygame.draw.line(surface, VFD_DIM,
                     (x0 + 2, sep_y), (x0 + panel_w - 2, sep_y), 1)

    # Data rows: (label_text, value_text, value_colour)
    rate_hz = sys_info.get('sample_rate', 44100)
    rate_khz = rate_hz / 1000.0
    rate_str = f"{rate_khz:.1f} kHz"

    buf = sys_info.get('buffer_size', 512)
    buf_str = f"{buf} SMP"

    bits_str = sys_info.get('bit_depth', 'INT 16')

    os_raw = sys_info.get('os', platform.system()).upper()
    os_map = {'DARWIN': 'MACOS', 'WINDOWS': 'WIN', 'LINUX': 'LINUX'}
    os_str = os_map.get(os_raw, os_raw[:6])

    midi_raw = sys_info.get('midi_device', '')
    if midi_raw and midi_raw.lower() not in ('none', ''):
        # Truncate long device names to fit the panel width
        midi_str = midi_raw[:9].upper() if len(midi_raw) > 9 else midi_raw.upper()
        midi_col = VFD_CYAN
    else:
        midi_str = 'NO MIDI'
        midi_col = VFD_DIM

    rows = [
        ('RATE', rate_str,  VFD_CYAN),
        ('BUFF', buf_str,   VFD_CYAN),
        ('BITS', bits_str,  VFD_CYAN),
        ('SYS',  os_str,    VFD_CYAN),
        ('MIDI', midi_str,  midi_col),
    ]

    row_h   = (WINDOW_HEIGHT - 8 - (sep_y - 4) - pad_y) // len(rows)
    row_y   = sep_y + 4
    lbl_col = VFD_DIM

    for lbl, val, val_col in rows:
        lbl_s = font_small.render(lbl, True, lbl_col)
        val_s = font_small.render(val, True, val_col)
        surface.blit(lbl_s, (x0 + pad_x, row_y))
        surface.blit(val_s, (x0 + pad_x, row_y + lbl_s.get_height() + 1))
        row_y += row_h


def _draw_meter_column(surface, font, font_small,
                       db_val: float, lufs_val: float, val_font=None):
    """Middle column showing live dBFS and LUFS as large centred values.

    Occupies x=METER_COL_L..METER_COL_R, full window height.
    Split into two equal halves: dBFS on top, LUFS on bottom.
    Colour coding: VFD_CYAN (normal), VFD_BRIGHT (loud), VFD_HOT (peak).
    """
    cx      = (METER_COL_L + METER_COL_R) // 2
    col_w   = METER_COL_R - METER_COL_L
    usable_h = WINDOW_HEIGHT - 8   # y=4 to y=158
    half_h  = usable_h // 2
    pad_y   = 5

    # Outer border box
    pygame.draw.rect(surface, VFD_DIM,
                     pygame.Rect(METER_COL_L, 4, col_w, usable_h), 1)

    # Horizontal divider between the two halves
    div_y = 4 + half_h
    pygame.draw.line(surface, VFD_DIM,
                     (METER_COL_L + 2, div_y), (METER_COL_R - 2, div_y), 1)

    def _level_colour(val, hot_thr, bright_thr):
        if val >= hot_thr:
            return VFD_HOT
        if val >= bright_thr:
            return VFD_BRIGHT
        return VFD_CYAN

    # Each half: label (dim) → value (colour) → unit (dim), all centred
    halves = [
        ('dBFS', '-00' if db_val <= -100.0 else f"{db_val:+.1f}", 'dB',
         _level_colour(db_val,  -3.0, -12.0),
         4 + pad_y,  4 + half_h),
        ('LUFS', '-\u221e' if lufs_val <= -100.0 else f"{lufs_val:+.1f}", 'LU',
         _level_colour(lufs_val, -9.0, -18.0),
         4 + half_h + pad_y, 4 + usable_h),
    ]

    _val_font = val_font if val_font is not None else font
    for lbl_txt, num_txt, unit_txt, val_col, y_top, y_bot in halves:
        inner_h = y_bot - y_top
        lbl_s  = font_small.render(lbl_txt,  True, VFD_DIM)
        num_s  = _val_font.render(num_txt,   True, val_col)
        unit_s = font_small.render(unit_txt, True, VFD_DIM)

        total_h = lbl_s.get_height() + 2 + num_s.get_height() + 2 + unit_s.get_height()
        start_y = y_top + (inner_h - total_h) // 2

        surface.blit(lbl_s,  lbl_s.get_rect(centerx=cx, top=start_y))
        surface.blit(num_s,  num_s.get_rect(centerx=cx,
                                             top=start_y + lbl_s.get_height() + 2))
        surface.blit(unit_s, unit_s.get_rect(centerx=cx,
                                              top=start_y + lbl_s.get_height() + 2
                                                  + num_s.get_height() + 2))


def _draw_bar_vu(surface, smooth_l: float, smooth_r: float, font, font_small,
                 sys_info: dict = None, db_val: float = -96.0,
                 lufs_val: float = -70.0, meter_font=None,
                 peak_db_l: float = DB_MIN, peak_db_r: float = DB_MIN):
    """VFD-style segmented bar VU meter.

    Fills the surface with VFD_BG and draws the same corner brackets, palette,
    and typography as the needle VU mode.  Each bar is divided into 4 px segments
    separated by 1 px gaps; inactive segments glow in the dim VFD track colour
    so the full scale is always visible, lit segments switch to amber above -3 dB.
    """
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets — identical to needle VU mode
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    # Segment geometry
    SEG_H    = 4
    SEG_GAP  = 1
    SEG_STEP = SEG_H + SEG_GAP
    num_segs = BAR_HEIGHT // SEG_STEP   # 22 segments for BAR_HEIGHT=110

    # Three colour zones mapped to segment indices:
    #   low  zone: -48 dB → -16 dB  (yellow)
    #   mid  zone: -16 dB → -3 dB   (cyan)
    #   hot  zone:  -3 dB →  0 dB   (amber)
    low_seg = int(((-16.0 - DB_MIN) / (DB_MAX - DB_MIN)) * num_segs)
    hot_seg = int((( -3.0 - DB_MIN) / (DB_MAX - DB_MIN)) * num_segs)

    for bar_x, level, lbl in (
        (BAR_LEFT_X,  smooth_l, "L"),
        (BAR_RIGHT_X, smooth_r, "R"),
    ):
        fraction = _level_to_bar_fraction(level)
        lit_segs = int(fraction * num_segs)

        for i in range(num_segs):
            seg_y = BAR_TOP + BAR_HEIGHT - (i + 1) * SEG_STEP
            lit   = i < lit_segs
            if i >= hot_seg:
                col = VFD_HOT        if lit else VFD_HOT_DIM     # top: amber
            elif i >= low_seg:
                col = VFD_YELLOW     if lit else VFD_YELLOW_DIM  # mid: yellow
            else:
                col = VFD_CYAN       if lit else VFD_DIM         # low: cyan
            pygame.draw.rect(surface, col,
                             pygame.Rect(bar_x + 1, seg_y, BAR_WIDTH - 2, SEG_H))

        # Channel label below bar
        ls = font.render(lbl, True, VFD_CYAN)
        surface.blit(ls, ls.get_rect(
            centerx=bar_x + BAR_WIDTH // 2, top=BAR_TOP + BAR_HEIGHT + 6))

    # Peak hold indicators — cyan single segment per channel, drawn after bars
    for bar_x, pk_db in ((BAR_LEFT_X, peak_db_l), (BAR_RIGHT_X, peak_db_r)):
        if pk_db > DB_MIN:
            pk_frac  = max(0.0, min(1.0, (pk_db - DB_MIN) / (DB_MAX - DB_MIN)))
            pk_seg   = int(pk_frac * num_segs)
            if 0 <= pk_seg < num_segs:
                pk_y = BAR_TOP + BAR_HEIGHT - (pk_seg + 1) * SEG_STEP
                pygame.draw.rect(surface, VFD_CYAN,
                                 pygame.Rect(bar_x + 1, pk_y, BAR_WIDTH - 2, SEG_H))

    # dB scale tick marks only — labels removed to avoid overlap with middle column
    for db in DB_TICKS:
        frac = max(0.0, min(1.0, (db - DB_MIN) / (DB_MAX - DB_MIN)))
        y    = BAR_TOP + int(BAR_HEIGHT * (1.0 - frac))
        if db >= -3:
            col = VFD_HOT
        elif db >= -16:
            col = VFD_YELLOW
        else:
            col = VFD_CYAN
        pygame.draw.line(surface, col, (DB_SCALE_X, y), (DB_SCALE_X + 4, y), 1)

    # Info panel on the left side
    if sys_info:
        _draw_info_panel(surface, font, font_small, sys_info)
        _draw_meter_column(surface, font, font_small, db_val, lufs_val,
                           meter_font or font)


# ── Oscilloscope drawing ──────────────────────────────────────────────────────

def _read_waveform(shm_buf) -> np.ndarray:
    """Read the waveform circular buffer from shm and return samples in time order.
    Uses numpy frombuffer (zero-copy view) and np.roll for reordering — much faster
    than struct.unpack + Python list concatenation.
    """
    try:
        write_pos = struct.unpack_from('i', shm_buf, 12)[0]
        # frombuffer gives a read-only view; .copy() makes it writeable for np.roll
        raw = np.frombuffer(shm_buf, dtype=np.float32,
                            count=WAVEFORM_SAMPLES, offset=16).copy()
        return np.roll(raw, -write_pos)
    except Exception:
        return np.zeros(WAVEFORM_SAMPLES, dtype=np.float32)


def _find_trigger(samples: np.ndarray) -> int:
    """
    Find a zero-crossing trigger (negative to positive transition) using
    vectorised numpy comparisons instead of a Python loop.
    Searches the middle quarter of the buffer so there is always room to
    display DISPLAY_SAMPLES samples after the trigger point.
    Returns the trigger index, or the search-start fallback if none found.
    """
    search_start = WAVEFORM_SAMPLES // 4
    search_end   = WAVEFORM_SAMPLES - DISPLAY_SAMPLES - 1
    region = samples[search_start:search_end]
    crossings = np.where((region[:-1] <= 0.0) & (region[1:] > 0.0))[0]
    if len(crossings):
        return search_start + int(crossings[0])
    return search_start


def _draw_oscilloscope(surface, shm_buf, font_small):
    """VFD-style triggered oscilloscope.

    Fills the surface with VFD_BG, draws corner brackets and a dim zero-reference
    line, then renders the waveform with two passes: a wide dim glow halo (VFD_DIM,
    width 3) followed by a narrow bright core (VFD_CYAN, width 1), matching the
    needle phosphor treatment.  All coordinate mapping is vectorised via numpy.
    """
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets — same pattern used by all three VFD modes
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    y_mid   = SCOPE_TOP + SCOPE_HEIGHT * 0.5
    y_scale = SCOPE_HEIGHT * 0.5 * 0.9

    samples = _read_waveform(shm_buf)
    trigger = _find_trigger(samples)
    window  = samples[trigger:trigger + DISPLAY_SAMPLES]

    if len(window) < 2:
        return

    # Vectorised coordinate computation
    idx = np.arange(len(window), dtype=np.float32)
    px  = (SCOPE_LEFT + idx * (SCOPE_WIDTH / (DISPLAY_SAMPLES - 1))).astype(np.int32)
    py  = (y_mid - window * y_scale).astype(np.int32)
    points = list(zip(px.tolist(), py.tolist()))

    if len(points) >= 2:
        pygame.draw.lines(surface, VFD_CYAN, False, points, 1)


# ── Needle VU Meter (VFD / retro-futurism style) ──────────────────────────────
#
# Layout: semicircular arc, pivot near bottom-centre.  Two overlapping needles
# (L bright cyan, R dim teal) sweep the scale independently.
# The VFD palette uses a near-black blue background with cyan phosphor elements
# and amber for the hot zone above 0 dBFS, evoking 1980s vacuum fluorescent
# instrument panels.

VU_CX        = WINDOW_WIDTH // 2   # 108 — horizontal centre
VU_CY        = 120                  # pivot row — centred vertically in usable area
VU_RADIUS    = 78                   # arc radius in pixels
VU_MIN_DB    = -20.0
VU_MAX_DB    =   3.0
VU_ANGLE_MIN = 148.0   # degrees at -20 dB (upper-left)
VU_ANGLE_MAX =  32.0   # degrees at  +3 dB (upper-right)
VU_HOT_DB    =   0.0   # amber zone starts here

# Major ticks shown with labels; minor ticks drawn shorter with no label
VU_TICKS_MAJOR = [(-20, "-20"), (-10, "-10"), (-7, "-7"),
                  (-5,  "-5"),  (-3,  "-3"),  ( 0, "0"), (3, "+3")]
VU_TICKS_MINOR = [-15, -8, -6, -4, -2]

# VFD colour palette — Vacuum Fluorescent Display cyan-teal phosphor look
VFD_BG         = ( 10,   5,   0)   # near-black warm dark background
VFD_DIM        = ( 55,  35,   0)   # dark amber — inactive elements / glow halo
VFD_CYAN       = (215, 155,   0)   # primary golden amber phosphor glow
VFD_BRIGHT     = (255, 215,  55)   # bright gold — peak highlights, pivot
VFD_HOT        = (220,  28,   0)   # red — hot zone above -3 dB (contrast anchor)
VFD_HOT_DIM    = ( 55,   7,   0)   # dim red — inactive hot segments
VFD_YELLOW     = (150, 100,   0)   # dark amber — low zone below -16 dB
VFD_YELLOW_DIM = ( 38,  22,   0)   # very dim amber — inactive low segments
VFD_BRACKET    = ( 95,  58,   0)   # amber corner bracket decorations
VFD_GRID       = ( 15,   7,   0)   # barely-visible warm grid on VFD_BG

# Note label color palette for asteroid visual (randomized per trigger)
AST_NOTE_COLORS = [
    (255, 215,  55),   # gold
    (255, 255,   0),   # yellow
    (220,  28,   0),   # red
    (  0, 255, 255),   # cyan
]


def _db_to_vu_angle(db: float) -> float:
    """Map a dB value to a needle angle in degrees.
    VU_ANGLE_MIN (148°) = VU_MIN_DB (-20 dB), VU_ANGLE_MAX (32°) = VU_MAX_DB (+3 dB).
    """
    db = max(VU_MIN_DB, min(VU_MAX_DB, db))
    t  = (db - VU_MIN_DB) / (VU_MAX_DB - VU_MIN_DB)
    return VU_ANGLE_MIN + t * (VU_ANGLE_MAX - VU_ANGLE_MIN)


def _arc_pt(cx: int, cy: int, r: float, angle_deg: float) -> tuple:
    """Return integer (x, y) on a circle given centre, radius, and angle in degrees."""
    rad = math.radians(angle_deg)
    return (int(cx + r * math.cos(rad)),
            int(cy - r * math.sin(rad)))


def _draw_needle_vu(surface, smooth_l: float, smooth_r: float, font_small):
    """Draw retro-futurist VFD-style needle VU meter.

    Fills the surface with VFD_BG, draws a semicircular arc scale with labelled
    tick marks, then draws a single needle representing the average of L and R (bright
    cyan), each pinned to the pivot and tipped to their respective level angle.
    Corner brackets and a centre VU label complete the retro panel aesthetic.
    """
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    cx, cy = VU_CX, VU_CY
    r      = VU_RADIUS
    arc_r  = pygame.Rect(cx - r, cy - r, r * 2, r * 2)

    angle_zero = _db_to_vu_angle(VU_HOT_DB)          # ~47° — 0 dB marker
    a_min      = math.radians(VU_ANGLE_MIN)           # 148° — far-left limit
    a_max      = math.radians(VU_ANGLE_MAX)           # 32°  — far-right limit
    a_zero     = math.radians(angle_zero)

    # ── Corner bracket decorations (retro-futurism frame) ────────────────────
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    # ── Scale arc ─────────────────────────────────────────────────────────────
    # Normal zone: dim cyan track from +3 dB angle up to 0 dB angle (CCW = through top)
    # Note: pygame.draw.arc goes CCW from start_angle to stop_angle in radians.
    pygame.draw.arc(surface, VFD_DIM,     arc_r, a_zero, a_min, 1)   # 0 dB → -20 dB
    pygame.draw.arc(surface, VFD_HOT_DIM, arc_r, a_max,  a_zero, 1)  # +3 dB → 0 dB

    # ── Tick marks and labels ─────────────────────────────────────────────────
    for db, lbl in VU_TICKS_MAJOR:
        angle    = _db_to_vu_angle(db)
        is_hot   = db >= VU_HOT_DB
        col      = VFD_HOT if is_hot else VFD_CYAN
        inner_pt = _arc_pt(cx, cy, r - 5, angle)
        outer_pt = _arc_pt(cx, cy, r + 4, angle)
        pygame.draw.line(surface, col, inner_pt, outer_pt, 1)
        lbl_pt = _arc_pt(cx, cy, r + 14, angle)
        ls = font_small.render(lbl, True, col)
        surface.blit(ls, ls.get_rect(centerx=lbl_pt[0], centery=lbl_pt[1]))

    for db in VU_TICKS_MINOR:
        angle    = _db_to_vu_angle(db)
        inner_pt = _arc_pt(cx, cy, r - 3, angle)
        outer_pt = _arc_pt(cx, cy, r + 2, angle)
        pygame.draw.line(surface, VFD_DIM, inner_pt, outer_pt, 1)

    # ── Single needle — average of L and R channels ───────────────────────────
    db_l   = 20.0 * math.log10(max(smooth_l, 1e-9))
    db_r   = 20.0 * math.log10(max(smooth_r, 1e-9))
    db_avg = (db_l + db_r) * 0.5
    ang    = _db_to_vu_angle(db_avg)
    tip    = _arc_pt(cx, cy, r - 4, ang)
    pygame.draw.line(surface, VFD_CYAN, (cx, cy), tip, 1)

    # ── Pivot dot ─────────────────────────────────────────────────────────────
    pygame.draw.circle(surface, VFD_BRIGHT, (cx, cy), 3)
    pygame.draw.circle(surface, VFD_DIM,    (cx, cy), 5, 1)

    # ── Centre "VU" label ─────────────────────────────────────────────────────
    vu_s = font_small.render("VU", True, VFD_DIM)
    surface.blit(vu_s, vu_s.get_rect(centerx=cx, centery=cy - 28))

    # ── L / R channel labels ──────────────────────────────────────────────────
    l_s = font_small.render("L", True, VFD_CYAN)
    r_s = font_small.render("R", True, VFD_DIM)
    surface.blit(l_s, l_s.get_rect(right=cx - 8, centery=cy + 10))
    surface.blit(r_s, r_s.get_rect(left=cx + 8,  centery=cy + 10))


# ── 3-D Wireframe Globe ───────────────────────────────────────────────────────
#
# A unit sphere rendered as latitude rings + longitude meridians.
# The axial tilt is baked into the pre-generated point arrays at startup so
# each frame only needs a single Y-axis rotation matrix.
# Depth cueing: front-facing segments (positive Z after rotation) → VFD_CYAN,
# back-facing → VFD_DIM.  Back segments drawn first so cyan always reads on top.
#
# Rotation physics:
#   angular_velocity accelerates toward SPHERE_MAX_VEL while audio level
#   exceeds SPHERE_GATE_THR, then decays via SPHERE_FRICTION when gate closes.

# ── Disco mirror ball visual ───────────────────────────────────────────────────
#
# The sphere is tessellated into DISCO_ROWS × DISCO_COLS flat quad tiles.
# Each frame a rotation matrix is applied, back-facing tiles are culled, and
# visible tiles are painter-sorted (back-to-front) then drawn as filled polygons.
# Random tiles flash bright each frame; flash brightness decays over ~14 frames.
# Audio level controls how many new flashes spawn per frame.
# A hang wire drops from the top of the window to the ball top.

DISCO_COLS       = 18     # tile columns around the equator
DISCO_ROWS       = 10     # tile rows pole to pole
DISCO_R          = 44     # ball radius in pixels
DISCO_CX         = WINDOW_WIDTH  // 2
DISCO_CY         = WINDOW_HEIGHT // 2 - 4   # slightly above centre (hanging)
DISCO_TILT       = 0.18   # slight sideways tilt in radians (cosmetic lean)
DISCO_SPIN_IDLE  = 0.20   # degrees/frame constant slow spin (no audio)
DISCO_SPIN_ACCEL = 2.0    # extra degrees/frame² added per unit of audio level
DISCO_SPIN_MAX   = 3.0    # maximum degrees/frame
DISCO_SPIN_FRIC  = 0.97   # velocity multiplier per frame when audio below gate
DISCO_GATE_THR   = 0.005  # linear level below which gate is considered closed
DISCO_FLASH_DECAY = 0.07  # brightness lost per frame (~14 frames to fully fade)
DISCO_MAX_FLASH  = 8      # new random flashes per frame at full audio level
# Flash colours: near-white, amber gold, red, icy blue
DISCO_FLASH_COLS = [
    (255, 250, 210),
    (255, 215,  55),
    (220,  28,   0),
    ( 80, 210, 255),
]

_disco_tiles  = None   # list of tile dicts built once on first draw
_disco_bright = None   # 2-D list [DISCO_ROWS][DISCO_COLS] float brightness
_disco_fcol   = None   # 2-D list [DISCO_ROWS][DISCO_COLS] flash colour tuple


def _init_disco_tiles():
    """Tessellate a unit sphere into DISCO_ROWS × DISCO_COLS quad tiles.
    Each tile stores its 4 corner points and face normal (unit sphere centre
    of the tile) as float32 numpy arrays. Called once on first draw.
    """
    global _disco_tiles, _disco_bright, _disco_fcol
    tiles = []
    for row in range(DISCO_ROWS):
        phi1 = -math.pi / 2 + row       * math.pi / DISCO_ROWS
        phi2 = -math.pi / 2 + (row + 1) * math.pi / DISCO_ROWS
        for col in range(DISCO_COLS):
            lam1 = col       * 2 * math.pi / DISCO_COLS
            lam2 = (col + 1) * 2 * math.pi / DISCO_COLS
            corners = np.array([
                [math.cos(phi1) * math.cos(lam1), math.sin(phi1), math.cos(phi1) * math.sin(lam1)],
                [math.cos(phi1) * math.cos(lam2), math.sin(phi1), math.cos(phi1) * math.sin(lam2)],
                [math.cos(phi2) * math.cos(lam2), math.sin(phi2), math.cos(phi2) * math.sin(lam2)],
                [math.cos(phi2) * math.cos(lam1), math.sin(phi2), math.cos(phi2) * math.sin(lam1)],
            ], dtype=np.float32)
            phi_mid = (phi1 + phi2) * 0.5
            lam_mid = (lam1 + lam2) * 0.5
            normal = np.array([
                math.cos(phi_mid) * math.cos(lam_mid),
                math.sin(phi_mid),
                math.cos(phi_mid) * math.sin(lam_mid),
            ], dtype=np.float32)
            tiles.append({'corners': corners, 'normal': normal, 'row': row, 'col': col})
    _disco_tiles  = tiles
    _disco_bright = [[0.0] * DISCO_COLS for _ in range(DISCO_ROWS)]
    _disco_fcol   = [[DISCO_FLASH_COLS[0]] * DISCO_COLS for _ in range(DISCO_ROWS)]


def _draw_disco_ball(surface, angle_rad: float, level: float):
    """Draw the disco mirror ball: tessellated sphere with randomly flashing tiles.

    angle_rad: current Y-axis rotation angle.
    level: smoothed audio level (0.0-1.0) controlling flash spawn rate and spin.
    """
    global _disco_tiles, _disco_bright, _disco_fcol
    if _disco_tiles is None:
        _init_disco_tiles()

    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    # Pure Y-axis spin — no tilt so the ball hangs straight
    c_a, s_a = math.cos(angle_rad), math.sin(angle_rad)
    R = np.array([[ c_a, 0.0, s_a],
                  [ 0.0, 1.0, 0.0],
                  [-s_a, 0.0, c_a]], dtype=np.float32)

    cx, cy = DISCO_CX, DISCO_CY

    # Decay existing flash brightnesses
    for row in range(DISCO_ROWS):
        for col in range(DISCO_COLS):
            b = _disco_bright[row][col] - DISCO_FLASH_DECAY
            _disco_bright[row][col] = b if b > 0.0 else 0.0

    # Spawn new random flashes: count scales with audio level
    n_flash = max(1, int(level * DISCO_MAX_FLASH))
    for _ in range(n_flash):
        if random.random() < 0.25 + level * 0.75:
            r = random.randrange(DISCO_ROWS)
            c = random.randrange(DISCO_COLS)
            _disco_bright[r][c] = 1.0
            _disco_fcol[r][c]   = random.choice(DISCO_FLASH_COLS)

    # Cull back-facing tiles, collect visible ones with depth for painter sort
    visible = []
    for tile in _disco_tiles:
        n_rot = R @ tile['normal']
        if n_rot[2] <= 0.0:
            continue   # back-facing — hidden
        corners_rot = tile['corners'] @ R.T
        pts = [
            (int(cx + c[0] * DISCO_R), int(cy - c[1] * DISCO_R))
            for c in corners_rot
        ]
        visible.append((
            float(n_rot[2]),        # depth key (larger = closer to viewer)
            pts,
            _disco_bright[tile['row']][tile['col']],
            _disco_fcol[tile['row']][tile['col']],
        ))

    # Painter's sort: back (low z) to front (high z)
    visible.sort(key=lambda x: x[0])

    for _z, pts, bright, fcol in visible:
        if bright > 0.02:
            # Flashing tile: filled with flash colour scaled by brightness
            fill = (
                int(VFD_DIM[0] + (fcol[0] - VFD_DIM[0]) * bright),
                int(VFD_DIM[1] + (fcol[1] - VFD_DIM[1]) * bright),
                int(VFD_DIM[2] + (fcol[2] - VFD_DIM[2]) * bright),
            )
            pygame.draw.polygon(surface, fill, pts)
            pygame.draw.polygon(surface, VFD_BG, pts, 1)   # dark gap between tiles
        else:
            # Unlit tile: solid background fill masks the grid, dim outline on top
            pygame.draw.polygon(surface, VFD_BG,  pts)
            pygame.draw.polygon(surface, VFD_DIM, pts, 1)

    # Hang wire from top of window to top of ball, with a small anchor dot
    top_ball = (cx, cy - DISCO_R)
    pygame.draw.line(surface, VFD_DIM, (cx, 2), top_ball, 1)
    pygame.draw.circle(surface, VFD_CYAN, top_ball, 2)


# ── Asteroid field visual ─────────────────────────────────────────────────────
AST_N_DEST          = 10    # destructible asteroids (one slot per synth voice)
AST_N_BG            = 15    # drifting background asteroids (decoration only)
AST_NOTE_FRAMES     = 10    # frames to show note name before explosion
AST_EXPLODE_FRAMES  = 25    # frames for explosion particle animation
AST_RESPAWN_MIN     = 55    # min frames before dead asteroid respawns (~1 s)
AST_RESPAWN_MAX     = 160   # max frames before respawn (~2.5 s)
_AST_NOTE_NAMES     = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']


def _midi_to_note_name(n: int) -> str:
    """Convert MIDI note number to a human-readable name like C4 or D#3."""
    return f"{_AST_NOTE_NAMES[n % 12]}{n // 12 - 1}"


# ── Circle of Fifths visual ────────────────────────────────────────────────────
COF_CX       = WINDOW_WIDTH  // 2
COF_CY       = WINDOW_HEIGHT // 2

COF_R_OUTER  = 65    # outer radius of major key ring
COF_R_MID    = 46    # boundary between major/minor rings
COF_R_INNER  = 29    # inner radius of minor key ring (edge of center hole)
COF_GAP      = math.radians(2.5)   # angular gap between adjacent segments

COF_DECAY      = 0.014   # segment brightness decay per frame (~70 frames to fade)
COF_ARC_FADE   = 0.010   # arc alpha decay per frame (~100 frames)
COF_RIPPLE_V   = 2.2     # ripple expansion speed px/frame
COF_RIPPLE_F   = 0.016   # ripple alpha decay per frame (~62 frames)

# Clockwise from top: C G D A E B F# Db Ab Eb Bb F
COF_MAJOR_LABELS = ['C', 'G', 'D', 'A', 'E', 'B', 'F#', 'Db', 'Ab', 'Eb', 'Bb', 'F']
COF_MINOR_LABELS = ['Am', 'Em', 'Bm', 'F#m', 'C#m', 'G#m', 'Ebm', 'Bbm', 'Fm', 'Cm', 'Gm', 'Dm']

# MIDI pitch class (0=C) -> COF ring position (0=C at top, clockwise)
_PITCH_TO_COF_MAJ = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5]
# MIDI pitch class -> COF position of relative minor key sharing that position
_PITCH_TO_COF_MIN = [9, 4, 11, 6, 1, 8, 3, 10, 5, 0, 7, 2]


def _make_ast(destructible: bool = True) -> dict:
    """Create one asteroid dict with a random jagged polygon shape."""
    n_v = random.randint(5, 9)
    rad = random.uniform(5, 20) if destructible else random.uniform(2, 5)
    verts = []
    for i in range(n_v):
        a = math.radians((i / n_v) * 360.0 + random.uniform(-25.0, 25.0))
        verts.append((rad * random.uniform(0.60, 1.0), a))
    return {
        'x': random.uniform(12, WINDOW_WIDTH  - 12),
        'y': random.uniform(12, WINDOW_HEIGHT - 12),
        'vx': random.uniform(-0.3, 0.3),
        'vy': random.uniform(-0.3, 0.3),
        'rot':  random.uniform(0, math.pi * 2),
        'rspd': random.uniform(-0.025, 0.025),
        'rad':  rad,
        'verts': verts,
        'dest': destructible,
        'state':    'alive',   # alive | note | explode | wait
        'note':     '',
        'note_num': -1,        # MIDI note number for held-gate tracking (-1 = none)
        'note_col': AST_NOTE_COLORS[0],  # color assigned at trigger time
        'anim':     0,
        'wait':     0,
        'frags':    [],
    }


def _ast_pts(a: dict) -> list:
    """Return screen-space polygon vertices for an asteroid."""
    return [
        (int(a['x'] + r * math.cos(ang + a['rot'])),
         int(a['y'] + r * math.sin(ang + a['rot'])))
        for r, ang in a['verts']
    ]


def _ast_explode(a: dict):
    """Transition asteroid to explode state and spawn fragment particles."""
    a['state'] = 'explode'
    a['anim']  = AST_EXPLODE_FRAMES
    n = random.randint(6, 10)
    a['frags'] = []
    for _ in range(n):
        ang  = random.uniform(0, math.pi * 2)
        spd  = random.uniform(0.8, 2.8)
        # Each fragment is a small random polygon (3-5 vertices) scaled to
        # a fraction of the parent radius, so pieces look like they broke off
        n_fv  = random.randint(3, 5)
        frad  = a['rad'] * random.uniform(0.15, 0.40)
        fverts = []
        for fi in range(n_fv):
            fa = math.radians((fi / n_fv) * 360.0 + random.uniform(-30, 30))
            fverts.append((frad * random.uniform(0.55, 1.0), fa))
        a['frags'].append({
            'x': a['x'], 'y': a['y'],
            'vx': math.cos(ang) * spd,
            'vy': math.sin(ang) * spd,
            'rot':  random.uniform(0, math.pi * 2),
            'rspd': random.uniform(-0.10, 0.10),
            'verts': fverts,
            'life': AST_EXPLODE_FRAMES,
        })


def _ast_update(a: dict):
    """Advance one asteroid by one frame."""
    if a['state'] == 'alive':
        a['x']   = (a['x'] + a['vx']) % WINDOW_WIDTH
        a['y']   = (a['y'] + a['vy']) % WINDOW_HEIGHT
        a['rot'] += a['rspd']

    elif a['state'] == 'note':
        a['x']   = (a['x'] + a['vx']) % WINDOW_WIDTH
        a['y']   = (a['y'] + a['vy']) % WINDOW_HEIGHT
        a['rot'] += a['rspd']
        a['anim'] -= 1
        if a['anim'] <= 0:
            _ast_explode(a)

    elif a['state'] == 'explode':
        a['anim'] -= 1
        for f in a['frags']:
            f['x']   += f['vx']
            f['y']   += f['vy']
            f['vy']  += 0.05    # gentle gravity on fragments
            f['rot'] += f['rspd']
            f['life'] -= 1
        if a['anim'] <= 0:
            a['state']    = 'wait'
            a['frags']    = []
            a['wait']     = random.randint(AST_RESPAWN_MIN, AST_RESPAWN_MAX)
            a['note_num'] = -1   # release note ownership so same note can trigger again

    elif a['state'] == 'wait':
        a['wait'] -= 1
        if a['wait'] <= 0:
            # Respawn with new shape and position
            a['x']    = random.uniform(12, WINDOW_WIDTH  - 12)
            a['y']    = random.uniform(12, WINDOW_HEIGHT - 12)
            a['vx']   = random.uniform(-0.3, 0.3)
            a['vy']   = random.uniform(-0.3, 0.3)
            a['rot']  = random.uniform(0, math.pi * 2)
            a['rspd'] = random.uniform(-0.025, 0.025)
            n_v = random.randint(5, 9)
            a['verts'] = []
            for i in range(n_v):
                ang = math.radians((i / n_v) * 360.0 + random.uniform(-25, 25))
                a['verts'].append((a['rad'] * random.uniform(0.60, 1.0), ang))
            a['state']    = 'alive'
            a['note']     = ''
            a['note_num'] = -1
            a['note_col'] = AST_NOTE_COLORS[0]


def _draw_asteroids(surface, ast_dest: list, ast_bg: list, font, font_small,
                    held_notes: set = None, note_font=None):
    """Asteroid field visual mode.

    Renders AST_N_BG drifting background asteroids in VFD_DIM and
    AST_N_DEST destructible asteroids in VFD_CYAN. When a note triggers
    an asteroid it shows the note name, then explodes into particles.
    """
    _nfont = note_font if note_font is not None else font
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets
    blen = 8
    for bx, by, hd, vd in (
        (4, 4, 1, 1), (WINDOW_WIDTH - 4, 4, -1, 1),
        (4, WINDOW_HEIGHT - 4, 1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd*blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd*blen), 1)

    # Background asteroids (dim, non-interactive)
    for a in ast_bg:
        pts = _ast_pts(a)
        if len(pts) >= 3:
            pygame.draw.polygon(surface, VFD_DIM, pts, 1)

    # Destructible asteroids
    for a in ast_dest:
        if a['state'] in ('alive', 'note'):
            pts = _ast_pts(a)
            if len(pts) >= 3:
                col = VFD_BRIGHT if a['state'] == 'note' else VFD_CYAN
                pygame.draw.polygon(surface, col, pts, 1)

            # Note label above asteroid during note phase, solid color.
            if a['state'] == 'note' and a['note']:
                ns = _nfont.render(a['note'], True, a['note_col'])
                surface.blit(ns, ns.get_rect(
                    centerx=int(a['x']),
                    centery=int(a['y']) - int(a['rad']) - 9))

        elif a['state'] == 'explode':
            for f in a['frags']:
                if f['life'] <= 0:
                    continue
                # Fade fragment from VFD_YELLOW toward VFD_BG as life runs out
                t  = f['life'] / AST_EXPLODE_FRAMES   # 1.0 = fresh, 0.0 = gone
                fc = (
                    int(VFD_BG[0] + (VFD_YELLOW[0] - VFD_BG[0]) * t),
                    int(VFD_BG[1] + (VFD_YELLOW[1] - VFD_BG[1]) * t),
                    int(VFD_BG[2] + (VFD_YELLOW[2] - VFD_BG[2]) * t),
                )
                # Project the fragment's own random polygon shape
                cos_r = math.cos(f['rot'])
                sin_r = math.sin(f['rot'])
                fp = [
                    (int(f['x'] + r * math.cos(a) * cos_r
                                - r * math.sin(a) * sin_r),
                     int(f['y'] + r * math.cos(a) * sin_r
                                + r * math.sin(a) * cos_r))
                    for r, a in f['verts']
                ]
                if len(fp) >= 3:
                    pygame.draw.polygon(surface, fc, fp, 1)

            # Note label persists through the full explosion, solid color.
            if a['note']:
                ns = _nfont.render(a['note'], True, a['note_col'])
                surface.blit(ns, ns.get_rect(
                    centerx=int(a['x']),
                    centery=int(a['y']) - 14))

        elif a['state'] == 'wait':
            # While the gate is still held, keep the note name visible at the
            # explosion site so the player sees which note is ringing.
            if (a['note'] and a['note_num'] >= 0
                    and held_notes and a['note_num'] in held_notes):
                ns = _nfont.render(a['note'], True, a['note_col'])
                surface.blit(ns, ns.get_rect(
                    centerx=int(a['x']),
                    centery=int(a['y']) - 14))


# ── Circle of Fifths helpers ──────────────────────────────────────────────────

def _cof_seg_center_angle(pos: int) -> float:
    """Center angle (radians) of COF position pos. 0=top (C), clockwise."""
    return -math.pi / 2.0 + (pos + 0.5) * 2.0 * math.pi / 12.0


def _cof_wedge_pts(cx: int, cy: int, r_inner: float, r_outer: float,
                   pos: int, n_arc: int = 10) -> list:
    """Polygon points for one COF wedge segment with a small gap on each side."""
    a0 = -math.pi / 2.0 + pos * 2.0 * math.pi / 12.0 + COF_GAP
    a1 = -math.pi / 2.0 + (pos + 1) * 2.0 * math.pi / 12.0 - COF_GAP
    pts = []
    for j in range(n_arc + 1):
        t = j / n_arc
        a = a0 + t * (a1 - a0)
        pts.append((cx + r_outer * math.cos(a), cy + r_outer * math.sin(a)))
    for j in range(n_arc + 1):
        t = j / n_arc
        a = a1 - t * (a1 - a0)
        pts.append((cx + r_inner * math.cos(a), cy + r_inner * math.sin(a)))
    return pts


def _cof_blend(c1: tuple, c2: tuple, t: float) -> tuple:
    """Linear interpolate two RGB colors. t=0 returns c1, t=1 returns c2."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _cof_inner_pt(pos: int) -> tuple:
    """Point at the inner edge of the major ring (COF_R_MID) at segment center."""
    a = _cof_seg_center_angle(pos)
    return (COF_CX + COF_R_MID * math.cos(a), COF_CY + COF_R_MID * math.sin(a))


# ── Dot / Solar System visual constants ───────────────────────────────────────
_DOT_N_SUNORB    = 6       # bodies orbiting the sun directly
_DOT_N_MOONS     = 2       # smallest 2 bodies become moons of random planets
_DOT_G           = 0.10    # weak inter-body gravity keeps orbits stable
_DOT_SUN_MASS    = 20.0
_DOT_RESTORE_K   = 0.055   # stronger spring keeps planets on their lanes
_DOT_RESTORE_K_M = 0.15    # tighter spring for moons
_DOT_MOON_V      = 0.80    # moon orbital speed around parent (px/frame)
_DOT_MOON_RADII  = [14, 18] # moon orbital radius around parent, one per moon
_DOT_DAMPING     = 0.920    # deviation damping — higher rate keeps orbits from stalling
_DOT_MAX_SPEED   = 2.4
_DOT_RESTITUTION = 0.55
_DOT_PARTICLE_AGE = 55     # fixed short max_age for all particles
_DOT_FADE_FRAMES = 20      # fade window at end of particle life
_DOT_SUN_COL     = (255, 200,  20)
_DOT_SUN_FLASH   = (255, 255, 255)
_DOT_FLASH_DUR   = 25
_DOT_SUN_RAY_TICK = 0          # global slow-rotation counter for sun rays

# 6 orbital radii for sun-orbiting planets (tight spacing, well inside screen).
_DOT_ORB_RADII = [28, 42, 55, 66, 76, 85]

_DOT_BODY_COLS = [
    VFD_BRIGHT,
    VFD_CYAN,
    (255, 255,   0),
    (220,  28,   0),
    (  0, 255, 255),
    (200, 100, 255),
    (255, 140,   0),
    VFD_DIM,
]

_DOT_AMBER_COLS  = [VFD_DIM, VFD_CYAN, VFD_BRIGHT]
_DOT_ACCENT_COLS = [(255, 255, 0), (220, 28, 0), (0, 255, 255), (255, 215, 55)]


def _dot_birth_col() -> tuple:
    if random.random() < 0.80:
        return random.choice(_DOT_AMBER_COLS)
    return random.choice(_DOT_ACCENT_COLS)


def _draw_pixel_sun(surface, cx: int, cy: int, flash_t: float) -> None:
    """Pixel-art sun: glow rings, solid core, 8 slowly-rotating ray stubs."""
    global _DOT_SUN_RAY_TICK
    _DOT_SUN_RAY_TICK += 1

    # Interpolate all colours toward white on flash.
    def _sc(base, t):
        return (int(base[0] + (255 - base[0]) * t),
                int(base[1] + (255 - base[1]) * t),
                int(base[2] + (255 - base[2]) * t))

    col_core  = _sc((255, 220,  50), flash_t)   # bright yellow core
    col_mid   = _sc((200, 120,   0), flash_t)   # orange mid ring
    col_glow1 = _sc(( 80,  40,   0), flash_t)   # dim glow ring 1
    col_glow2 = _sc(( 30,  14,   0), flash_t)   # barely-there halo
    col_ray   = _sc((220, 160,  10), flash_t)   # ray colour

    # Glow halos (outermost first so core paints on top).
    pygame.draw.circle(surface, col_glow2, (cx, cy), 13, 1)
    pygame.draw.circle(surface, col_glow1, (cx, cy), 11, 1)
    pygame.draw.circle(surface, col_mid,   (cx, cy),  9, 1)

    # Solid bright core.
    pygame.draw.circle(surface, col_core, (cx, cy), 7)

    # 8 ray stubs — 4 cardinal + 4 diagonal, slowly rotating.
    # Angle offset drifts 1 degree every 4 frames.
    angle_off = math.radians((_DOT_SUN_RAY_TICK // 4) % 360)
    for i in range(8):
        a      = angle_off + i * math.pi / 4.0
        ca     = math.cos(a);  sa = math.sin(a)
        # Gap between core edge and ray start.
        r_near = 9
        # Alternating long / short rays for classic pixel-sun look.
        r_far  = 13 if i % 2 == 0 else 11
        x1 = int(cx + ca * r_near);  y1 = int(cy + sa * r_near)
        x2 = int(cx + ca * r_far);   y2 = int(cy + sa * r_far)
        pygame.draw.line(surface, col_ray, (x1, y1), (x2, y2), 1)


def _dot_make_system() -> list:
    """Sun (fixed, centre) + 6 sun-orbiting planets + 2 moons.

    Planets sorted by mass ascending: lighter planets orbit closer.
    The 2 moons (smallest masses) each orbit a randomly chosen planet.
    Bodies list layout: [sun, planet0..planet5, moon0, moon1]
    Each moon stores 'parent_idx' pointing to its parent in bodies list.
    """
    sx = WINDOW_WIDTH  // 2
    sy = WINDOW_HEIGHT // 2

    sun = {
        'x': float(sx), 'y': float(sy),
        'vx': 0.0, 'vy': 0.0,
        'mass':      _DOT_SUN_MASS,
        'radius':    7,
        'col':       _DOT_SUN_COL,
        'active':    False,
        'fixed':     True,
        'is_sun':    True,
        'is_moon':   False,
        'flash':     0,
        'r_home':    0.0,
        'orbit_dir': 1,
        'parent_idx': -1,
    }

    # Generate masses sorted ascending: smallest → moons, rest → planets.
    all_masses = sorted(random.uniform(1.0, 3.2) for _ in range(_DOT_N_SUNORB + _DOT_N_MOONS))
    planet_masses = all_masses[_DOT_N_MOONS:]   # 6 larger masses
    moon_masses   = all_masses[:_DOT_N_MOONS]   # 2 smallest masses

    # Build sun-orbiting planets (indices 1..6 in bodies list).
    planets = []
    for i, (mass, r_orb) in enumerate(zip(planet_masses, _DOT_ORB_RADII)):
        angle     = random.uniform(0.0, 2.0 * math.pi)
        v_circ    = math.sqrt(_DOT_G * _DOT_SUN_MASS / r_orb)
        orbit_dir = random.choice((-1, 1))
        # Give each planet a slightly uneven elliptical visual path.
        orb_rx    = float(r_orb) + random.uniform(-4.0, 4.0)
        orb_ry    = orb_rx * random.uniform(0.82, 1.0)
        orb_tilt  = random.uniform(0.0, math.pi)
        # Place body ON its ellipse at the chosen angle so the spring starts at rest.
        cos_t     = math.cos(orb_tilt);  sin_t = math.sin(orb_tilt)
        lx        = orb_rx * math.cos(angle)
        ly        = orb_ry * math.sin(angle)
        wx        = sx + lx * cos_t - ly * sin_t
        wy        = sy + lx * sin_t + ly * cos_t
        # Tangent on ellipse at this parameter gives the correct initial velocity.
        dtx       = -orb_rx * math.sin(angle)
        dty       =  orb_ry * math.cos(angle)
        tlen      = math.sqrt(dtx*dtx + dty*dty) or 1.0
        wtx       = (dtx * cos_t - dty * sin_t) / tlen
        wty       = (dtx * sin_t + dty * cos_t) / tlen
        planets.append({
            'x':         wx,
            'y':         wy,
            'vx':        orbit_dir * wtx * v_circ,
            'vy':        orbit_dir * wty * v_circ,
            'mass':      mass,
            'radius':    max(2, int(1.5 + mass * 0.8)),
            'col':       _DOT_BODY_COLS[i % len(_DOT_BODY_COLS)],
            'active':    False,
            'fixed':     False,
            'is_sun':    False,
            'is_moon':   False,
            'flash':     0,
            'r_home':    float(r_orb),
            'orb_rx':    orb_rx,
            'orb_ry':    orb_ry,
            'orb_tilt':  orb_tilt,
            'orbit_dir': orbit_dir,
            'parent_idx': 0,   # orbits sun
        })

    bodies = [sun] + planets   # indices: 0=sun, 1-6=planets

    # Build moons — each orbits a randomly chosen planet (avoid same parent).
    parent_indices = random.sample(range(1, _DOT_N_SUNORB + 1), _DOT_N_MOONS)
    moons = []
    for k, (mass, par_idx, moon_r) in enumerate(
            zip(moon_masses, parent_indices, _DOT_MOON_RADII)):
        parent    = bodies[par_idx]
        angle     = random.uniform(0.0, 2.0 * math.pi)
        orbit_dir = random.choice((-1, 1))
        # Moon world position = parent position + offset at moon_r.
        mx = parent['x'] + moon_r * math.cos(angle)
        my = parent['y'] + moon_r * math.sin(angle)
        # Moon world velocity = parent velocity + tangential orbit around parent.
        tx = -orbit_dir * math.sin(angle)
        ty =  orbit_dir * math.cos(angle)
        m_orb_rx   = float(moon_r) + random.uniform(-2.0, 2.0)
        m_orb_ry   = m_orb_rx * random.uniform(0.80, 1.0)
        m_orb_tilt = random.uniform(0.0, math.pi)
        # Place moon ON its ellipse around the parent.
        cos_tm     = math.cos(m_orb_tilt);  sin_tm = math.sin(m_orb_tilt)
        mlx        = m_orb_rx * math.cos(angle)
        mly        = m_orb_ry * math.sin(angle)
        mx         = parent['x'] + mlx * cos_tm - mly * sin_tm
        my         = parent['y'] + mlx * sin_tm + mly * cos_tm
        # Tangent on moon ellipse at this parameter.
        mdtx       = -m_orb_rx * math.sin(angle)
        mdty       =  m_orb_ry * math.cos(angle)
        mtlen      = math.sqrt(mdtx*mdtx + mdty*mdty) or 1.0
        mwtx       = (mdtx * cos_tm - mdty * sin_tm) / mtlen
        mwty       = (mdtx * sin_tm + mdty * cos_tm) / mtlen
        moons.append({
            'x':         mx,
            'y':         my,
            'vx':        parent['vx'] + orbit_dir * mwtx * _DOT_MOON_V,
            'vy':        parent['vy'] + orbit_dir * mwty * _DOT_MOON_V,
            'mass':      mass,
            'radius':    2,
            'col':       _DOT_BODY_COLS[(6 + k) % len(_DOT_BODY_COLS)],
            'active':    False,
            'fixed':     False,
            'is_sun':    False,
            'is_moon':   True,
            'flash':     0,
            'r_home':    float(moon_r),
            'orb_rx':    m_orb_rx,
            'orb_ry':    m_orb_ry,
            'orb_tilt':  m_orb_tilt,
            'orbit_dir': orbit_dir,
            'parent_idx': par_idx,
        })

    return bodies + moons


def _dot_physics(bodies: list, gravity_on: bool = True) -> None:
    """N-body physics: sun fixed, planets orbit sun, moons orbit their parent planet.

    Each body uses a restoring spring toward its home orbit radius (relative to
    its parent), and deviation-only damping so orbits never decay to a stop.
    Inter-body gravity is disabled while notes are held so orbits stay clean.
    """
    n   = len(bodies)
    fx  = [0.0] * n
    fy  = [0.0] * n
    sun = bodies[0]

    # Pairwise gravity — disabled while a note gate is open for stable orbits.
    if gravity_on:
        for i in range(n):
            for j in range(i + 1, n):
                dx    = bodies[j]['x'] - bodies[i]['x']
                dy    = bodies[j]['y'] - bodies[i]['y']
                r     = math.sqrt(dx * dx + dy * dy) or 0.001
                nx    = dx / r;  ny = dy / r
                r_eff = max(r, float(bodies[i]['radius'] + bodies[j]['radius']))
                f     = _DOT_G * bodies[i]['mass'] * bodies[j]['mass'] / (r_eff * r_eff)
                fx[i] += f * nx;  fy[i] += f * ny
                fx[j] -= f * nx;  fy[j] -= f * ny

    for i, b in enumerate(bodies):
        if b['fixed']:
            continue

        b['vx'] += fx[i] / b['mass']
        b['vy'] += fy[i] / b['mass']

        if b['is_moon']:
            # Moon: elliptical spring + ideal velocity relative to parent.
            parent  = bodies[b['parent_idx']]
            cx, cy  = parent['x'], parent['y']
            orx, ory, otilt = b['orb_rx'], b['orb_ry'], b['orb_tilt']
            # Rotate body offset into local ellipse frame.
            dx_p    = b['x'] - cx;  dy_p = b['y'] - cy
            cos_t   = math.cos(otilt);  sin_t = math.sin(otilt)
            lx      =  dx_p * cos_t + dy_p * sin_t
            ly      = -dx_p * sin_t + dy_p * cos_t
            a_param = math.atan2(ly, lx)
            # Target point on ellipse at this parameter.
            ex      = orx * math.cos(a_param)
            ey      = ory * math.sin(a_param)
            tx_e    = ex * cos_t - ey * sin_t + cx
            ty_e    = ex * sin_t + ey * cos_t + cy
            # Spring toward ellipse surface — normal component only so the
            # tangential orbital velocity is never reduced by spring forces.
            sdx      = b['x'] - tx_e;  sdy = b['y'] - ty_e
            # Outward normal of ellipse at a_param (gradient of f = (lx/orx)²+(ly/ory)²).
            en_lx    = math.cos(a_param) / orx
            en_ly    = math.sin(a_param) / ory
            en_len   = math.sqrt(en_lx*en_lx + en_ly*en_ly) or 1.0
            en_wx    = (en_lx * cos_t - en_ly * sin_t) / en_len
            en_wy    = (en_lx * sin_t + en_ly * cos_t) / en_len
            sm       = sdx * en_wx + sdy * en_wy   # signed distance along normal
            b['vx'] -= _DOT_RESTORE_K_M * sm * en_wx
            b['vy'] -= _DOT_RESTORE_K_M * sm * en_wy
            # Tangent direction on ellipse for ideal velocity.
            od      = b['orbit_dir']
            dtx     = -orx * math.sin(a_param)
            dty     =  ory * math.cos(a_param)
            tlen    = math.sqrt(dtx*dtx + dty*dty) or 1.0
            wtx     = (dtx * cos_t - dty * sin_t) / tlen
            wty     = (dtx * sin_t + dty * cos_t) / tlen
            ideal_vx = parent['vx'] + od * wtx * _DOT_MOON_V
            ideal_vy = parent['vy'] + od * wty * _DOT_MOON_V
        else:
            # Planet: elliptical spring + ideal velocity relative to sun.
            cx, cy  = sun['x'], sun['y']
            orx, ory, otilt = b['orb_rx'], b['orb_ry'], b['orb_tilt']
            dx_s    = b['x'] - cx;  dy_s = b['y'] - cy
            cos_t   = math.cos(otilt);  sin_t = math.sin(otilt)
            lx      =  dx_s * cos_t + dy_s * sin_t
            ly      = -dx_s * sin_t + dy_s * cos_t
            a_param = math.atan2(ly, lx)
            ex      = orx * math.cos(a_param)
            ey      = ory * math.sin(a_param)
            tx_e    = ex * cos_t - ey * sin_t + cx
            ty_e    = ex * sin_t + ey * cos_t + cy
            # Spring toward ellipse surface — normal component only.
            sdx      = b['x'] - tx_e;  sdy = b['y'] - ty_e
            en_lx    = math.cos(a_param) / orx
            en_ly    = math.sin(a_param) / ory
            en_len   = math.sqrt(en_lx*en_lx + en_ly*en_ly) or 1.0
            en_wx    = (en_lx * cos_t - en_ly * sin_t) / en_len
            en_wy    = (en_lx * sin_t + en_ly * cos_t) / en_len
            sm       = sdx * en_wx + sdy * en_wy
            b['vx'] -= _DOT_RESTORE_K * sm * en_wx
            b['vy'] -= _DOT_RESTORE_K * sm * en_wy
            # Tangent on ellipse = ideal velocity direction.
            od      = b['orbit_dir']
            dtx     = -orx * math.sin(a_param)
            dty     =  ory * math.cos(a_param)
            tlen    = math.sqrt(dtx*dtx + dty*dty) or 1.0
            wtx     = (dtx * cos_t - dty * sin_t) / tlen
            wty     = (dtx * sin_t + dty * cos_t) / tlen
            r_s     = math.sqrt(dx_s*dx_s + dy_s*dy_s) or 1.0
            v_ideal = math.sqrt(_DOT_G * _DOT_SUN_MASS / max(r_s, 8.0))
            ideal_vx = od * wtx * v_ideal
            ideal_vy = od * wty * v_ideal

        # Damp only the deviation from ideal so the orbit never decays.
        dev_vx  = b['vx'] - ideal_vx
        dev_vy  = b['vy'] - ideal_vy
        b['vx'] = ideal_vx + dev_vx * _DOT_DAMPING
        b['vy'] = ideal_vy + dev_vy * _DOT_DAMPING

        spd = math.sqrt(b['vx'] ** 2 + b['vy'] ** 2)
        if spd > _DOT_MAX_SPEED:
            b['vx'] *= _DOT_MAX_SPEED / spd
            b['vy'] *= _DOT_MAX_SPEED / spd

        b['x'] += b['vx']
        b['y'] += b['vy']

    # Collision resolution — no body may overlap another.
    for i in range(n):
        for j in range(i + 1, n):
            bi = bodies[i];  bj = bodies[j]
            # Moons don't collide with their own parent (they orbit inside it).
            if bj.get('is_moon') and bj['parent_idx'] == i:
                continue
            if bi.get('is_moon') and bi['parent_idx'] == j:
                continue
            dx    = bj['x'] - bi['x']
            dy    = bj['y'] - bi['y']
            r     = math.sqrt(dx * dx + dy * dy) or 0.001
            min_r = bi['radius'] + bj['radius'] + 1
            if r >= min_r:
                continue
            nx = dx / r;  ny = dy / r
            ov = min_r - r
            if bi['fixed']:
                bj['x'] += nx * ov;  bj['y'] += ny * ov
            elif bj['fixed']:
                bi['x'] -= nx * ov;  bi['y'] -= ny * ov
            else:
                tm = bi['mass'] + bj['mass']
                bi['x'] -= nx * ov * bj['mass'] / tm
                bi['y'] -= ny * ov * bj['mass'] / tm
                bj['x'] += nx * ov * bi['mass'] / tm
                bj['y'] += ny * ov * bi['mass'] / tm
            if bi['fixed']:
                vn = bj['vx'] * nx + bj['vy'] * ny
                if vn < 0:
                    bj['vx'] -= (1.0 + _DOT_RESTITUTION) * vn * nx
                    bj['vy'] -= (1.0 + _DOT_RESTITUTION) * vn * ny
            elif bj['fixed']:
                vn = -(bi['vx'] * nx + bi['vy'] * ny)
                if vn < 0:
                    bi['vx'] += (1.0 + _DOT_RESTITUTION) * vn * nx
                    bi['vy'] += (1.0 + _DOT_RESTITUTION) * vn * ny
            else:
                dvx = bj['vx'] - bi['vx'];  dvy = bj['vy'] - bi['vy']
                vn  = dvx * nx + dvy * ny
                if vn < 0:
                    j_imp = -(1.0 + _DOT_RESTITUTION) * vn / (
                        1.0 / bi['mass'] + 1.0 / bj['mass'])
                    bi['vx'] -= j_imp * nx / bi['mass']
                    bi['vy'] -= j_imp * ny / bi['mass']
                    bj['vx'] += j_imp * nx / bj['mass']
                    bj['vy'] += j_imp * ny / bj['mass']

    # No screen clamping — bodies are kept on-screen by the restoring spring
    # that pulls them back toward their home orbital radius around the sun.


def _draw_dot(surface, samples: np.ndarray, dot_state: dict,
              gate_open: bool, audio_level: float,
              held_notes: set) -> None:
    """Dot visual — mini solar system with n-body physics and gate-driven particles.

    The sun sits fixed at centre; planets orbit it in stable lanes, perturbing
    each other slightly.  Each new note kicks a random planet and flashes the sun.
    Only the kicked planet emits particles while its gate is held.
    """
    # Draw background matching all other visuals.
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets — same pattern used by all VFD modes.
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    lvl = max(0.0, min(1.0, audio_level))

    # Lazy-init solar system on first call.
    if not dot_state['bodies']:
        dot_state['bodies'] = _dot_make_system()

    bodies     = dot_state['bodies']
    particles  = dot_state['particles']
    prev_notes = dot_state.get('prev_notes', set())
    prev_gate  = dot_state.get('prev_gate', False)
    sun        = bodies[0]
    planets    = bodies[1:]

    # New-note detection: kick a random planet + flash the sun.
    new_notes = held_notes - prev_notes
    for _ in new_notes:
        # Flash sun.
        sun['flash'] = _DOT_FLASH_DUR
        # Kick a random planet in a random direction.
        target = random.choice(planets)
        target['active'] = True
        # Kick in the planet's own orbital direction (prograde boost) so it
        # swings outward naturally then arcs back — like a real orbital burn.
        _sun  = bodies[0]
        _dx   = target['x'] - _sun['x']
        _dy   = target['y'] - _sun['y']
        _r    = math.sqrt(_dx * _dx + _dy * _dy) or 1.0
        _od   = target['orbit_dir']
        _tx   = -_od * (_dy / _r)   # tangential unit vector
        _ty   =  _od * (_dx / _r)
        kick  = random.uniform(1.2, 2.2)
        target['vx'] += kick * _tx
        target['vy'] += kick * _ty

    dot_state['prev_notes'] = set(held_notes)

    # Gate-close transition: stop emission. Particles have short fixed lifetimes
    # so they naturally trail off without needing staggered death assignment.
    if prev_gate and not gate_open:
        for b in planets:
            b['active'] = False

    dot_state['prev_gate'] = gate_open

    if gate_open:
        dot_state['emit_rate'] = min(1.0, dot_state['emit_rate'] + 0.09)
    else:
        dot_state['emit_rate'] = max(0.0, dot_state['emit_rate'] - 0.015)

    emit_rate = dot_state['emit_rate']

    # Physics update every frame. Gravity off while gate is open so note kicks
    # cause clean orbital swings instead of chaotic body interactions.
    _dot_physics(bodies, gravity_on=not gate_open)

    # Emit 1 particle per active planet per frame.
    # Particles are ejected mostly opposite to the body's movement direction
    # (comet-tail effect) with a narrow lateral spread.
    if emit_rate > 0.01:
        lateral = 0.10 + lvl * 0.20   # narrow perpendicular spread
        for b in planets:
            if not b['active']:
                continue
            spd = math.sqrt(b['vx'] * b['vx'] + b['vy'] * b['vy']) or 1.0
            # Unit vector opposite to travel direction.
            rx = -b['vx'] / spd
            ry = -b['vy'] / spd
            # Perpendicular unit vector for lateral spread.
            px = -ry
            py =  rx
            tail_speed = spd * random.uniform(0.3, 0.8)
            lat_jitter  = random.uniform(-lateral, lateral)
            particles.append({
                'x':       b['x'] + rx * b['radius'],
                'y':       b['y'] + ry * b['radius'],
                'vx':      rx * tail_speed + px * lat_jitter,
                'vy':      ry * tail_speed + py * lat_jitter,
                'age':     0,
                'max_age': random.randint(20, _DOT_PARTICLE_AGE),
                'col':     _dot_birth_col(),
            })

    # Update and draw particles.
    next_particles = []
    for p in particles:
        p['x']  += p['vx']
        p['y']  += p['vy']
        p['age'] += 1
        age     = p['age']
        max_age = p['max_age']
        if age >= max_age:
            continue
        fade_start = max_age - _DOT_FADE_FRAMES
        if age >= fade_start:
            f   = 1.0 - (age - fade_start) / _DOT_FADE_FRAMES
            bc  = p['col']
            col = (int(bc[0] * f), int(bc[1] * f), int(bc[2] * f))
        else:
            col = p['col']
        px = int(p['x'])
        py = int(p['y'])
        if 0 <= px < WINDOW_WIDTH and 0 <= py < WINDOW_HEIGHT:
            surface.set_at((px, py), col)
        next_particles.append(p)

    dot_state['particles'] = next_particles

    # Draw orbital paths — slightly oval, tilted ellipses for each body.
    _ORB_PATH_COL = (30, 18, 0)   # barely visible VFD amber tint
    _ORB_STEPS    = 48            # polygon segments per ellipse
    sx_f = sun['x'];  sy_f = sun['y']

    def _ellipse_pts(ox, oy, rx, ry, tilt):
        """Sample a rotated ellipse as a list of integer (x, y) points."""
        cos_t = math.cos(tilt);  sin_t = math.sin(tilt)
        pts = []
        for s in range(_ORB_STEPS):
            a   = 2.0 * math.pi * s / _ORB_STEPS
            lx  = rx * math.cos(a)
            ly  = ry * math.sin(a)
            pts.append((int(ox + lx * cos_t - ly * sin_t),
                        int(oy + lx * sin_t + ly * cos_t)))
        return pts

    for b in planets:
        if b['is_moon']:
            parent = bodies[b['parent_idx']]
            pts = _ellipse_pts(parent['x'], parent['y'],
                               b['orb_rx'], b['orb_ry'], b['orb_tilt'])
        else:
            pts = _ellipse_pts(sx_f, sy_f,
                               b['orb_rx'], b['orb_ry'], b['orb_tilt'])
        if len(pts) > 1:
            pygame.draw.lines(surface, _ORB_PATH_COL, True, pts, 1)

    # Draw planets.
    for b in planets:
        col = (255, 255, 255) if b['active'] and emit_rate > 0.01 else b['col']
        pygame.draw.circle(surface, col, (int(b['x']), int(b['y'])), b['radius'])

    # Draw pixel-art sun — flashes white on note-on, returns to warm yellow.
    if sun['flash'] > 0:
        sun['flash'] -= 1
    flash_t = sun['flash'] / _DOT_FLASH_DUR
    _draw_pixel_sun(surface, int(sun['x']), int(sun['y']), flash_t)


def _draw_cof(surface, cof_major: list, cof_minor: list,
              cof_arcs: list, cof_ripples: list, font, note_font):
    """Circle of Fifths visual.

    Outer ring: 12 major keys. Inner ring: 12 relative minor keys.
    Activated segments pulse bright. Resonance arcs connect to fifth/fourth.
    Expanding ripple rings radiate from the center on each note-on.
    """
    surface.fill(VFD_BG)
    _draw_vfd_grid(surface)

    # Corner brackets — same pattern used by all VFD modes.
    blen = 8
    for bx, by, hd, vd in (
        (4,                4,                 1,  1),
        (WINDOW_WIDTH - 4, 4,                -1,  1),
        (4,                WINDOW_HEIGHT - 4,  1, -1),
        (WINDOW_WIDTH - 4, WINDOW_HEIGHT - 4, -1, -1),
    ):
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx + hd * blen, by), 1)
        pygame.draw.line(surface, VFD_BRACKET, (bx, by), (bx, by + vd * blen), 1)

    cx, cy = COF_CX, COF_CY

    # Resonance arcs drawn first so segments render on top
    for arc in cof_arcs:
        alpha = arc['alpha']
        if alpha <= 0.01:
            continue
        col = _cof_blend(VFD_BG, arc['col'], alpha)
        p0 = _cof_inner_pt(arc['frm'])
        p1 = _cof_inner_pt(arc['to'])
        # Quadratic bezier through the circle center for a natural curve
        bpts = []
        for i in range(21):
            t = i / 20.0
            bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * cx + t ** 2 * p1[0]
            by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * cy + t ** 2 * p1[1]
            bpts.append((int(bx), int(by)))
        for i in range(len(bpts) - 1):
            pygame.draw.line(surface, col, bpts[i], bpts[i + 1], 1)

    # Minor ring segments (inner)
    for i in range(12):
        br = cof_minor[i]
        fill_col    = _cof_blend(VFD_YELLOW_DIM, VFD_CYAN, br)
        outline_col = _cof_blend(VFD_DIM, VFD_BRIGHT, br)
        pts = _cof_wedge_pts(cx, cy, COF_R_INNER, COF_R_MID, i)
        if len(pts) >= 3:
            pygame.draw.polygon(surface, fill_col, pts, 0)
            pygame.draw.polygon(surface, outline_col, pts, 1)

    # Major ring segments (outer)
    for i in range(12):
        br = cof_major[i]
        fill_col    = _cof_blend(VFD_DIM, VFD_BRIGHT, br)
        outline_col = _cof_blend(VFD_DIM, VFD_BRIGHT, max(0.3, br))
        pts = _cof_wedge_pts(cx, cy, COF_R_MID, COF_R_OUTER, i)
        if len(pts) >= 3:
            pygame.draw.polygon(surface, fill_col, pts, 0)
            pygame.draw.polygon(surface, outline_col, pts, 1)

    # Segment labels
    for i in range(12):
        a = _cof_seg_center_angle(i)
        # Major label — fades from VFD_DIM toward black as segment brightens,
        # so the letter stays readable against the bright gold fill.
        maj_r  = (COF_R_MID + COF_R_OUTER) / 2.0
        lc_maj = _cof_blend(VFD_BRIGHT, (0, 0, 0), cof_major[i])
        ls_maj = font.render(COF_MAJOR_LABELS[i], True, lc_maj)
        surface.blit(ls_maj, ls_maj.get_rect(
            center=(int(cx + maj_r * math.cos(a)), int(cy + maj_r * math.sin(a)))))
        # Minor label — same inversion toward black when active
        min_r  = (COF_R_INNER + COF_R_MID) / 2.0
        lc_min = _cof_blend(VFD_CYAN, (0, 0, 0), cof_minor[i])
        ls_min = font.render(COF_MINOR_LABELS[i], True, lc_min)
        surface.blit(ls_min, ls_min.get_rect(
            center=(int(cx + min_r * math.cos(a)), int(cy + min_r * math.sin(a)))))

    # Ripples — expanding circles from center
    for rp in cof_ripples:
        alpha = rp['alpha']
        if alpha <= 0.01:
            continue
        col = _cof_blend(VFD_BG, VFD_BRIGHT, alpha)
        r = int(rp['radius'])
        if r > 0:
            pygame.draw.circle(surface, col, (cx, cy), r, 1)

    # Center hole outline
    pygame.draw.circle(surface, VFD_DIM, (cx, cy), COF_R_INNER - 2, 1)



# ── Main render loop ──────────────────────────────────────────────────────────

def main(shm_name: str, terminal_wid: int = 0, sys_info: dict = None):
    """
    Pygame render loop. Reads levels and waveform from shared memory by name.
    terminal_wid: HWND (Windows) or X11 window ID (Linux) of the parent terminal,
    used to return focus immediately after the visualizer window is created.
    sys_info: optional dict with keys sample_rate, buffer_size, bit_depth, os,
    midi_device — shown in the VFD info panel of the bar VU mode.
    Tab cycles between visual modes. 'f' toggles fullscreen. 'v' closes window.
    Supports click-drag to move window (windowed mode). Remembers last position.
    """
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

    try:
        shm = SharedMemory(name=shm_name)
    except Exception as e:
        print(f"Visualizer: cannot open shared memory '{shm_name}': {e}")
        return

    # Set spawn position BEFORE pygame creates the window so there is no
    # white-flash-then-jump. SDL reads this env var at display init time.
    saved_x, saved_y = _load_position()
    if saved_x is not None:
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{saved_x},{saved_y}"
    else:
        os.environ.pop('SDL_VIDEO_WINDOW_POS', None)

    pygame.init()
    surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.NOFRAME | pygame.DOUBLEBUF)
    pygame.display.set_caption(WINDOW_TITLE)

    # Build the cached grid surface now that pygame display is initialised.
    # This replaces ~40 draw.line calls per frame with a single blit.
    _init_grid_surface()

    # Paint BG_COLOR immediately so there is no black flash before the first frame
    surface.fill(BG_COLOR)
    pygame.display.flip()

    user32, ctypes = _get_win32()
    hwnd = _setup_always_on_top(user32, ctypes)

    # Return keyboard focus to the terminal that spawned us.
    # WS_EX_NOACTIVATE (set inside _setup_always_on_top_win32) prevents future
    # click-to-activate focus steals. This call handles the initial steal that
    # occurs when SDL first creates the window.
    if terminal_wid:
        if _SYSTEM == "Windows":
            _return_focus_win32(user32, terminal_wid)
        elif _SYSTEM == "Linux":
            _return_focus_linux(terminal_wid)

    clock       = pygame.time.Clock()
    _font_path  = Path(__file__).parent.parent / 'arm_ui' / 'fonts' / 'Silkscreen.ttf'
    font           = pygame.font.Font(str(_font_path), 8)
    title_font     = pygame.font.Font(str(_font_path), 8)
    scale_font     = pygame.font.Font(str(_font_path), 8)
    meter_font     = pygame.font.Font(str(_font_path), 16)  # larger font for dBFS/LUFS values
    ast_note_font  = pygame.font.Font(str(_font_path), 16)  # note label in asteroid visual
    picker_title_font = pygame.font.Font(str(_font_path), 12)  # visual name in picker overlay
    running       = True
    dragging      = False
    drag_offset_x = 0
    drag_offset_y = 0
    smooth_l      = 0.0
    smooth_r      = 0.0
    peak_db_l     = DB_MIN   # held peak in dBFS for left channel
    peak_db_r     = DB_MIN   # held peak in dBFS for right channel
    peak_hold_l   = 0        # frames remaining in hold phase (>0 = holding)
    peak_hold_r   = 0
    vis_mode       = MODE_VU_METER
    sphere_angle   = 0.0   # current Y-rotation in degrees
    sphere_ang_vel = 0.0   # current angular velocity in degrees/frame
    trail_history  = []    # list of (wave_array, amplitude) snapshots, newest at index 0
    trail_frame    = 0     # frame counter for capture rate throttle
    picker_frames  = 0     # countdown frames for mode picker overlay (0 = hidden)
    # Asteroid mode state
    ast_dest       = [_make_ast(destructible=True)  for _ in range(AST_N_DEST)]
    ast_bg         = [_make_ast(destructible=False) for _ in range(AST_N_BG)]
    ast_note_rptr  = 0   # last note_write_ptr value read from SHM (uint8)
    ast_held_notes: set = set()  # MIDI note numbers currently held (gate open)

    # Circle of Fifths state
    cof_major   = [0.0] * 12   # segment brightness 0.0-1.0 for major keys
    cof_minor   = [0.0] * 12   # segment brightness 0.0-1.0 for minor keys
    cof_arcs    = []            # active resonance arcs [{frm, to, alpha, col}]
    cof_ripples = []            # expanding ripple rings [{radius, alpha}]
    dot_state   = {'bodies': [], 'particles': [], 'emit_rate': 0.0,
                   'prev_gate': False, 'prev_notes': set()}  # Dot mode
    # LUFS integration window: ~3 s of mean-square samples at 60 Hz = 180 slots.
    # Simplified ITU BS.1770 without K-weighting: LUFS = -0.691 + 10*log10(mean_sq).
    _LUFS_WINDOW_SIZE = 180
    lufs_window   = collections.deque([0.0] * _LUFS_WINDOW_SIZE,
                                      maxlen=_LUFS_WINDOW_SIZE)
    db_val        = -96.0  # current peak dBFS (both channels)
    lufs_val      = -70.0  # current short-term LUFS estimate

    # render_surf is the fixed-size canvas; always drawn here then optionally scaled
    render_surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
    fullscreen  = False

    def _toggle_fullscreen():
        nonlocal fullscreen, surface, hwnd, saved_x, saved_y
        fullscreen = not fullscreen
        if fullscreen:
            screen_w, screen_h = _get_screen_size(user32, ctypes)
            surface = pygame.display.set_mode(
                (screen_w, screen_h),
                pygame.FULLSCREEN | pygame.NOFRAME | pygame.DOUBLEBUF
            )
        else:
            surface = pygame.display.set_mode(
                (WINDOW_WIDTH, WINDOW_HEIGHT),
                pygame.NOFRAME | pygame.DOUBLEBUF
            )
            pygame.display.set_caption(WINDOW_TITLE)
            if saved_x is not None:
                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{saved_x},{saved_y}"
        hwnd = _setup_always_on_top(user32, ctypes)
        if not fullscreen and hwnd and saved_x is not None:
            _set_window_pos(user32, hwnd, saved_x, saved_y)

    while running:
        if hwnd:
            _restore_if_minimized(user32, ctypes, hwnd)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_v:
                    running = False
                elif event.key == pygame.K_f:
                    _toggle_fullscreen()
                elif event.key == pygame.K_TAB:
                    # Shift+Tab = reverse; plain Tab = forward.
                    # Only fires in fullscreen when pygame has keyboard focus.
                    if event.mod & pygame.KMOD_SHIFT:
                        vis_mode     = (vis_mode - 1) % MODE_COUNT
                    else:
                        vis_mode     = (vis_mode + 1) % MODE_COUNT
                    picker_frames = PICKER_FRAMES

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not fullscreen and hwnd:
                    if _SYSTEM == "Windows" and user32:
                        win_x, win_y = _get_window_pos(user32, ctypes, hwnd)
                        cur_x, cur_y = _get_cursor_screen_pos(user32, ctypes)
                        drag_offset_x = cur_x - win_x
                        drag_offset_y = cur_y - win_y
                    elif _ON_X11:
                        # X11: record mouse-in-window position as drag anchor
                        drag_offset_x, drag_offset_y = event.pos
                    dragging = True

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging and hwnd:
                    final_x, final_y = _get_window_pos(user32, ctypes, hwnd)
                    _save_position(final_x, final_y)
                    saved_x, saved_y = final_x, final_y
                dragging = False

            elif event.type == pygame.MOUSEMOTION and dragging and hwnd:
                if _SYSTEM == "Windows" and user32:
                    cur_x, cur_y = _get_cursor_screen_pos(user32, ctypes)
                    _set_window_pos(user32, hwnd,
                                    cur_x - drag_offset_x,
                                    cur_y - drag_offset_y)
                elif _ON_X11:
                    # X11: compute target screen position from saved window origin
                    # and the delta between current and anchor mouse position
                    rel_dx = event.pos[0] - drag_offset_x
                    rel_dy = event.pos[1] - drag_offset_y
                    base_x, base_y = _get_window_pos(user32, ctypes, hwnd)
                    _set_window_pos(user32, hwnd,
                                    base_x + rel_dx,
                                    base_y + rel_dy)

        # Read levels and command from shared memory
        try:
            level_l, level_r = struct.unpack_from('ff', shm.buf, 0)
            cmd = struct.unpack_from('i', shm.buf, 8)[0]
        except Exception:
            level_l = level_r = 0.0
            cmd = 0

        # NaN = shutdown sentinel from parent.
        # Exit fullscreen first so the desktop is visible immediately; without
        # this the display stays black until pygame.quit() runs, which blocks
        # user interaction with any underlying window.
        if level_l != level_l:
            if fullscreen:
                _toggle_fullscreen()
                pygame.display.flip()
            running = False
            break

        # Commands from Textual keybindings
        if cmd == 1:   # toggle fullscreen
            try:
                struct.pack_into('i', shm.buf, 8, 0)
            except Exception:
                pass
            _toggle_fullscreen()
        elif cmd == 2:  # cycle visual mode forward (Tab)
            try:
                struct.pack_into('i', shm.buf, 8, 0)
            except Exception:
                pass
            vis_mode      = (vis_mode + 1) % MODE_COUNT
            picker_frames = PICKER_FRAMES
        elif cmd == 3:  # cycle visual mode backward (Shift+Tab)
            try:
                struct.pack_into('i', shm.buf, 8, 0)
            except Exception:
                pass
            vis_mode      = (vis_mode - 1) % MODE_COUNT
            picker_frames = PICKER_FRAMES

        # Smooth VU levels (used by VU mode; still computed so switching modes is seamless)
        coeff_l = SMOOTH_ATTACK  if level_l > smooth_l else SMOOTH_RELEASE
        coeff_r = SMOOTH_ATTACK  if level_r > smooth_r else SMOOTH_RELEASE
        smooth_l = smooth_l * coeff_l + level_l * (1.0 - coeff_l)
        smooth_r = smooth_r * coeff_r + level_r * (1.0 - coeff_r)

        # Per-channel peak hold: new peak → hold 3 s → fall → disappear.
        _db_l = 20.0 * math.log10(max(smooth_l, 1e-9))
        _db_r = 20.0 * math.log10(max(smooth_r, 1e-9))
        if _db_l >= peak_db_l:
            peak_db_l, peak_hold_l = _db_l, PEAK_HOLD_FRAMES
        elif peak_hold_l > 0:
            peak_hold_l -= 1
        else:
            peak_db_l = max(DB_MIN, peak_db_l - PEAK_FALL_RATE)
        if _db_r >= peak_db_r:
            peak_db_r, peak_hold_r = _db_r, PEAK_HOLD_FRAMES
        elif peak_hold_r > 0:
            peak_hold_r -= 1
        else:
            peak_db_r = max(DB_MIN, peak_db_r - PEAK_FALL_RATE)

        # Peak dBFS — instantaneous, both channels worst-case.
        peak = max(smooth_l, smooth_r, 1e-9)
        db_val = 20.0 * math.log10(peak)

        # Short-term LUFS (simplified BS.1770, no K-weighting).
        # Push mean-square of this frame into the 3-second rolling window.
        lufs_window.append((smooth_l ** 2 + smooth_r ** 2) * 0.5)
        mean_sq = sum(lufs_window) / len(lufs_window)
        lufs_val = -0.691 + 10.0 * math.log10(max(mean_sq, 1e-9))

        # Read new note events from SHM note ring buffer, trigger and track.
        # Each slot is BBBx: (midi_note, velocity, type) where type 0=on, 1=off.
        try:
            _wptr = struct.unpack_from('B', shm.buf, NOTE_SHM_BASE)[0]
            while ast_note_rptr != _wptr:
                _slot = ast_note_rptr % NOTE_RING_SLOTS
                _nn, _nv, _nt = struct.unpack_from('BBB', shm.buf,
                                                   NOTE_SHM_BASE + 4 + _slot * 4)
                ast_note_rptr = (ast_note_rptr + 1) & 0xFF
                if _nt == 1:
                    # Note-off: remove from held set
                    ast_held_notes.discard(_nn)
                else:
                    # Note-on: update held set, trigger asteroid and COF
                    ast_held_notes.add(_nn)

                    # Asteroid: skip duplicate if already active for this note
                    _already = any(a['note_num'] == _nn
                                   and a['state'] in ('note', 'explode')
                                   for a in ast_dest)
                    if not _already:
                        _alive = [a for a in ast_dest if a['state'] == 'alive']
                        if _alive:
                            _target = random.choice(_alive)
                            _target['state']    = 'note'
                            _target['note']     = _midi_to_note_name(_nn)
                            _target['note_num'] = _nn
                            _target['note_col'] = random.choice(AST_NOTE_COLORS)
                            _target['anim']     = AST_NOTE_FRAMES

                    # Circle of Fifths: light up segment, emit arcs and ripple
                    _pc       = _nn % 12
                    _maj_pos  = _PITCH_TO_COF_MAJ[_pc]
                    _min_pos  = _PITCH_TO_COF_MIN[_pc]
                    cof_major[_maj_pos] = 1.0
                    cof_minor[_min_pos] = 1.0
                    # Ripple starts at the outer ring and expands outward
                    cof_ripples.append({'radius': float(COF_R_OUTER), 'alpha': 1.0})
                    # Arc to perfect fifth (one step clockwise) in bright gold
                    _fifth  = (_maj_pos + 1) % 12
                    # Arc to perfect fourth (one step counter-clockwise) in amber
                    _fourth = (_maj_pos - 1) % 12
                    cof_arcs.append({'frm': _maj_pos, 'to': _fifth,
                                     'alpha': 1.0, 'col': VFD_BRIGHT})
                    cof_arcs.append({'frm': _maj_pos, 'to': _fourth,
                                     'alpha': 1.0, 'col': VFD_CYAN})
        except Exception:
            pass

        # Update asteroid states every frame
        for _a in ast_dest:
            _ast_update(_a)
        for _a in ast_bg:
            _a['x'] = (_a['x'] + _a['vx']) % WINDOW_WIDTH
            _a['y'] = (_a['y'] + _a['vy']) % WINDOW_HEIGHT
            _a['rot'] += _a['rspd']

        # Circle of Fifths state decay — held notes stay lit, others fade.
        _held_maj = {_PITCH_TO_COF_MAJ[n % 12] for n in ast_held_notes}
        _held_min = {_PITCH_TO_COF_MIN[n % 12] for n in ast_held_notes}
        for _i in range(12):
            if _i not in _held_maj:
                cof_major[_i] = max(0.0, cof_major[_i] - COF_DECAY)
            if _i not in _held_min:
                cof_minor[_i] = max(0.0, cof_minor[_i] - COF_DECAY)
        for _arc in cof_arcs:
            _arc['alpha'] = max(0.0, _arc['alpha'] - COF_ARC_FADE)
        cof_arcs = [_a for _a in cof_arcs if _a['alpha'] > 0.01]
        for _rp in cof_ripples:
            _rp['radius'] += COF_RIPPLE_V
            _rp['alpha']   = max(0.0, _rp['alpha'] - COF_RIPPLE_F)
        cof_ripples = [_rp for _rp in cof_ripples
                       if _rp['alpha'] > 0.01 and _rp['radius'] < WINDOW_WIDTH]

        # Draw to fixed-size render surface.
        # MODE_NEEDLE_VU fills the surface itself (VFD_BG overrides); other modes
        # use the standard background so we fill it here first.
        if vis_mode != MODE_NEEDLE_VU:
            bg = (0, 0, 0) if fullscreen else BG_COLOR
            render_surf.fill(bg)

        if vis_mode == MODE_VU_METER:
            _draw_bar_vu(render_surf, smooth_l, smooth_r, font, scale_font,
                         sys_info, db_val, lufs_val, meter_font,
                         peak_db_l, peak_db_r)

        elif vis_mode == MODE_OSCILLOSCOPE:
            _draw_oscilloscope(render_surf, shm.buf, scale_font)

        elif vis_mode == MODE_NEEDLE_VU:
            _draw_needle_vu(render_surf, smooth_l, smooth_r, scale_font)

        elif vis_mode == MODE_SPHERE:
            # Spin physics: audio boosts velocity; idle floor keeps it always turning
            gate = max(smooth_l, smooth_r)
            if gate > DISCO_GATE_THR:
                sphere_ang_vel = min(
                    sphere_ang_vel + gate * DISCO_SPIN_ACCEL, DISCO_SPIN_MAX
                )
            else:
                sphere_ang_vel = max(
                    sphere_ang_vel * DISCO_SPIN_FRIC, DISCO_SPIN_IDLE
                )
            sphere_angle = (sphere_angle + sphere_ang_vel) % 360.0
            _draw_disco_ball(render_surf, math.radians(sphere_angle), gate)

        elif vis_mode == MODE_GRID:
            # Capture a new waveform snapshot every UNPL_CAPTURE_N frames
            trail_frame += 1
            if trail_frame >= UNPL_CAPTURE_N:
                trail_frame = 0
                raw     = _read_waveform(shm.buf)
                trigger = _find_trigger(raw)
                snap    = raw[trigger:trigger + DISPLAY_SAMPLES].copy()
                if len(snap) < DISPLAY_SAMPLES:
                    snap = np.zeros(DISPLAY_SAMPLES, dtype=np.float32)
                amp = float(max(smooth_l, smooth_r))
                # Prepend newest snapshot; trim to history length
                trail_history.insert(0, (snap, amp))
                if len(trail_history) > UNPL_HISTORY_N:
                    trail_history.pop()
            _draw_unknown_pleasures(render_surf, trail_history)

        elif vis_mode == MODE_ASTEROIDS:
            _draw_asteroids(render_surf, ast_dest, ast_bg, font, scale_font,
                            ast_held_notes, ast_note_font)

        elif vis_mode == MODE_COF:
            _draw_cof(render_surf, cof_major, cof_minor,
                      cof_arcs, cof_ripples, font, ast_note_font)

        elif vis_mode == MODE_DOT:
            _draw_dot(render_surf, _read_waveform(shm.buf), dot_state,
                      bool(ast_held_notes), max(smooth_l, smooth_r),
                      ast_held_notes)

        # Mode picker overlay — held for PICKER_FRAMES then gone instantly.
        if picker_frames > 0:
            _draw_mode_picker(render_surf, vis_mode, scale_font, 255,
                              font_title=picker_title_font)
            picker_frames -= 1

        # Blit to display, scaling to fill screen in fullscreen mode
        if fullscreen:
            sw, sh = surface.get_size()
            scale  = min(sw / WINDOW_WIDTH, sh / WINDOW_HEIGHT)
            scaled_w = int(WINDOW_WIDTH  * scale)
            scaled_h = int(WINDOW_HEIGHT * scale)
            scaled = pygame.transform.scale(render_surf, (scaled_w, scaled_h))
            surface.fill((0, 0, 0))
            surface.blit(scaled, ((sw - scaled_w) // 2, (sh - scaled_h) // 2))
        else:
            surface.blit(render_surf, (0, 0))

        pygame.display.flip()
        clock.tick(FPS)

    # Save position on any exit path
    if hwnd and not fullscreen:
        final_x, final_y = _get_window_pos(user32, ctypes, hwnd)
        _save_position(final_x, final_y)

    shm.close()
    pygame.quit()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m visualizer.visualizer_window <shm_name> [terminal_wid]"
              " [sample_rate] [buffer_size] [bit_depth] [os] [midi_device]")
        sys.exit(1)
    _terminal_wid = 0
    if len(sys.argv) >= 3:
        try:
            _terminal_wid = int(sys.argv[2])
        except ValueError:
            _terminal_wid = 0
    _sys_info = None
    # Extra args: sample_rate buffer_size bit_depth os midi_device
    if len(sys.argv) >= 5:
        try:
            _sys_info = {
                'sample_rate':  int(sys.argv[3]),
                'buffer_size':  int(sys.argv[4]),
                'bit_depth':    sys.argv[5] if len(sys.argv) >= 6 else 'INT 16',
                'os':           sys.argv[6] if len(sys.argv) >= 7 else platform.system(),
                'midi_device':  sys.argv[7] if len(sys.argv) >= 8 else '',
            }
        except (ValueError, IndexError):
            _sys_info = None
    main(sys.argv[1], _terminal_wid, _sys_info)
