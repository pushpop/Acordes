# ABOUTME: Script to generate the PixelCode glyph reference sheet PNG.
# ABOUTME: Run with: python arm_ui/gen_glyph_sheet.py

"""
Generates arm_ui/GLYPH_REFERENCE.png - a visual catalog of every
PixelCode glyph useful for designing the Acordes ARM UI.
Organized by category, rendered at 2x display scale (14x30px cells).
"""

import os
import sys

# Must set dummy driver before importing pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

# ── Config ────────────────────────────────────────────────────────────────────
FONT_PATH   = os.path.join(os.path.dirname(__file__), "fonts", "PixelCode.ttf")
FONT_SIZE   = 18          # readable at reference-sheet scale
PADDING     = 12          # outer margin
GAP_X       = 4           # between glyph columns
GAP_Y       = 6           # between rows
COLS        = 16          # glyphs per row
LABEL_SIZE  = 9           # category header font size

BG          = (  0,   0,   0)
FG          = (255, 255, 255)
DIM         = (100, 100, 100)
ACCENT      = (  0, 200,  70)   # green - section headers
HIGHLIGHT   = (255, 140,   0)   # orange - special callouts
SEPARATOR   = ( 40,  40,  40)

# ── Glyph categories ─────────────────────────────────────────────────────────
# Format: ("Category Name", "description", [list of chars])

CATEGORIES = [

    ("BOX DRAWING - single line",
     "borders, panels, dividers",
     list("─━│┃┄┅┆┇┊┋") +
     list("┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛") +
     list("├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫") +
     list("┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻") +
     list("┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋") +
     list("╌╍╎╏")),

    ("BOX DRAWING - double line",
     "emphasis panels, selected states",
     list("═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬") +
     list("╭╮╯╰╱╲╳╴╵╶╷╸╹╺╻╼╽╾╿")),

    ("BLOCK ELEMENTS",
     "bars, meters, fills, gradients",
     list("▀▁▂▃▄▅▆▇▉▊▋▌▍▎▏▐░▒▓▔▕") +
     list("▖▗▘▙▚▛▜▝▞▟")),

    ("GEOMETRIC SHAPES - filled",
     "buttons, indicators, bullets, icons",
     list("■▪▬▮▲▴▶▸►▼▾◀◂◄◆◉●◘◙◚◛◼") +
     list("◢◣◤◥◦◐◑◒◓◔◕◖◗")),

    ("GEOMETRIC SHAPES - outline",
     "empty states, inactive indicators",
     list("□▢▣▤▥▦▧▨▩▫▭▯△▵▷▹▻▽▿◁◃◅◇◈◊○◌◍◎◯") +
     list("◰◱◲◳◴◵◶◷◻◿")),

    ("ARROWS",
     "navigation, direction, scroll hints",
     list("←↑→↓↕↖↗↘↙↩↪↰↱↲↳↴↵↶↷↺↻") +
     list("↼↽↾↿⇀⇁⇂⇃⇠⇡⇢⇣⇦⇧⇨⇩⇪") +
     list("⬅⬆⬇⬈⬉⬊⬋⭠⭡⭢⭣⭥⭦⭧⭨⭩⭮⭯") +
     list("➔➘➙➚➛➜➝➞➟➠➡➢➣➤➥➦➧➨➩➪➫➬➭➮➯") +
     list("⮌⮍⮎⮏⮐⮑⮒⮓⮕⮬⮭⮮⮯⮺⮻⮼") +
     list("⯅⯆⯇⯈⯊⯋")),

    ("UI SYMBOLS",
     "actions, status, checkboxes, toggles",
     list("✓✔✕✖✗✘✙✚✛✜✡✢✣✤✥✦✧✨✳✴✿❀❇❈") +
     list("❌❎❏❐❑❒❓❔❕❗❘❙❚❛❜❝❞❡❢❣❤❥❦❧") +
     list("❨❩❪❫❬❭❮❯❰❱❲❳❴❵") +
     list("➕➖➗➰➱")),

    ("CIRCLED NUMBERS",
     "step sequencer, track numbers, slots",
     list("❶❷❸❹❺❻❼❽❾❿➀➁➂➃➄➅➆➇➈➉➊➋➌➍➎➏➐➑➒➓")),

    ("MATH & OPERATORS",
     "values, parameters, indicators",
     list("+-*/=<>~^") +
     list("·•′″‴‵‶‷⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ") +
     list("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎") +
     list("⟲⟳⟵⟶")),

    ("BRAILLE PATTERNS - samples",
     "custom pixel art, waveforms, mini graphics (U+2800-U+28FF full set available)",
     [
         "\u2800","\u2801","\u2802","\u2803","\u2804","\u2805","\u2806","\u2807",
         "\u2808","\u2809","\u280a","\u280b","\u280c","\u280d","\u280e","\u280f",
         "\u2810","\u2811","\u2812","\u2813","\u2814","\u2815","\u2816","\u2817",
         "\u2818","\u2819","\u281a","\u281b","\u281c","\u281d","\u281e","\u281f",
         "\u2820","\u2821","\u2822","\u2823","\u2824","\u2825","\u2826","\u2827",
         "\u2828","\u2829","\u282a","\u282b","\u282c","\u282d","\u282e","\u282f",
         "\u2830","\u2831","\u2832","\u2833","\u2834","\u2835","\u2836","\u2837",
         "\u2838","\u2839","\u283a","\u283b","\u283c","\u283d","\u283e","\u283f",
         "\u2840","\u2841","\u2842","\u2843","\u2844","\u2845","\u2846","\u2847",
         "\u2848","\u2849","\u284a","\u284b","\u284c","\u284d","\u284e","\u284f",
         "\u2860","\u2861","\u2862","\u2863","\u2864","\u2865","\u2866","\u2867",
         "\u2870","\u2871","\u2872","\u2873","\u2874","\u2875","\u2876","\u2877",
         "\u2880","\u2881","\u2882","\u2883","\u2884","\u2885","\u2886","\u2887",
         "\u28c0","\u28c1","\u28c2","\u28c3","\u28c4","\u28c5","\u28c6","\u28c7",
         "\u28e0","\u28e1","\u28e2","\u28e3","\u28e4","\u28e5","\u28e6","\u28e7",
         "\u28f0","\u28f1","\u28f2","\u28f3","\u28f4","\u28f5","\u28f6","\u28f7",
         "\u28f8","\u28f9","\u28fa","\u28fb","\u28fc","\u28fd","\u28fe","\u28ff",
     ]),

    ("PUNCTUATION & TEXT",
     "labels, separators, text decoration",
     list('!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~') +
     list("--...''\"\"") +
     list("+-|/\\<>~")),
]

# ── Widget reference table ────────────────────────────────────────────────────
WIDGETS = [
    ("Box",        "single line border panel",         "┌────────┐ │        │ └────────┘"),
    ("DBox",       "double line, selected/emphasis",   "╔════════╗ ║        ║ ╚════════╝"),
    ("HRule",      "horizontal separator",             "────────────────────"),
    ("VRule",      "vertical separator",               "│"),
    ("Label",      "text  regular/italic/medium",      "PRESET NAME  or  Preset Name"),
    ("HBar",       "horizontal level/progress bar",    "████████▒▒░░░░░░"),
    ("VBar",       "vertical meter / envelope",        "▁▂▃▅▆▇"),
    ("Toggle",     "on/off boolean switch",            "[●  ]  or  [  ○]"),
    ("Button",     "action button with border",        "┌──────────┐ │  PLAY ▶  │ └──────────┘"),
    ("Select",     "option picker / mode selector",    "◀ SAWTOOTH ▶"),
    ("Stepper",    "numeric stepper",                  "◄ 127 ►"),
    ("Checkbox",   "boolean option",                   "[✓] ENABLE    [ ] DISABLE"),
    ("StatusDot",  "state / connection indicator",     "● CONNECTED   ○ IDLE"),
    ("Tag",        "small label badge",                "■ LIVE   ■ REC   ■ PLAY"),
    ("HintBar",    "bottom key hints strip",           "◀▶:navigate  ●:play  ◆:save  Esc:back"),
    ("TitleBar",   "top strip with title and info",    "ACORDES                        OStra"),
    ("Meter",      "VU / audio level meter",           "▁▂▃▅▇▇▅▃▂▁"),
    ("Waveform",   "mini waveform via braille",        "\u28c0\u28e4\u28f6\u28ff\u28f6\u28e4\u28c0\u2880"),
    ("Grid",       "layout container for widgets",     "(organises rows and columns)"),
]


def make_sheet() -> pygame.Surface:
    pygame.init()
    font      = pygame.font.Font(FONT_PATH, FONT_SIZE)
    font_hdr  = pygame.font.Font(FONT_PATH, LABEL_SIZE + 4)
    font_lbl  = pygame.font.Font(FONT_PATH, LABEL_SIZE)
    font_wgt  = pygame.font.Font(FONT_PATH, LABEL_SIZE + 1)

    cell_w, cell_h = font.size("\u2588")

    # ── First pass: compute total height ─────────────────────────────────────
    def section_height(chars):
        rows = (len(chars) + COLS - 1) // COLS
        return rows * (cell_h + GAP_Y)

    total_h = PADDING
    for name, desc, chars in CATEGORIES:
        total_h += font_hdr.size(name)[1] + 4
        total_h += font_lbl.size(desc)[1] + 6
        total_h += section_height(chars) + PADDING + 4

    # widget table height
    total_h += font_hdr.size("W")[1] + 8
    total_h += len(WIDGETS) * (font_wgt.size("W")[1] + 4)
    total_h += PADDING * 2

    # Width must fit both the glyph grid and the widget table
    glyph_w  = PADDING * 2 + COLS * (cell_w + GAP_X)
    widget_w = PADDING * 2 + 130 + 260 + 480   # name + desc + example
    sheet_w  = max(glyph_w, widget_w)

    surf = pygame.Surface((sheet_w, total_h))
    surf.fill(BG)

    y = PADDING

    # ── Draw glyph categories ─────────────────────────────────────────────────
    for cat_name, cat_desc, chars in CATEGORIES:
        # Category header in green
        hdr = font_hdr.render(cat_name, False, ACCENT)
        surf.blit(hdr, (PADDING, y))
        y += hdr.get_height() + 4

        # Description in dim grey
        dsc = font_lbl.render(cat_desc, False, DIM)
        surf.blit(dsc, (PADDING, y))
        y += dsc.get_height() + 6

        # Glyphs in white grid
        for i, ch in enumerate(chars):
            col = i % COLS
            row = i // COLS
            gx  = PADDING + col * (cell_w + GAP_X)
            gy  = y + row * (cell_h + GAP_Y)
            try:
                gs = font.render(ch, False, FG)
                surf.blit(gs, (gx, gy))
            except Exception:
                pass

        rows = (len(chars) + COLS - 1) // COLS
        y   += rows * (cell_h + GAP_Y) + PADDING

        # Thin separator line
        pygame.draw.line(surf, SEPARATOR,
                         (PADDING, y - PADDING // 2),
                         (sheet_w - PADDING, y - PADDING // 2))

    # ── Widget reference table ────────────────────────────────────────────────
    hdr = font_hdr.render("WIDGET REFERENCE", False, HIGHLIGHT)
    surf.blit(hdr, (PADDING, y))
    y += hdr.get_height() + 8

    pygame.draw.line(surf, SEPARATOR, (PADDING, y - 4), (sheet_w - PADDING, y - 4))

    row_h = font_wgt.size("W")[1] + 4
    for wname, wdesc, wexample in WIDGETS:
        # Widget name in orange
        ns = font_wgt.render(f"{wname}", False, HIGHLIGHT)
        surf.blit(ns, (PADDING, y))

        # Description in dim
        col2 = PADDING + 130
        ds = font_lbl.render(wdesc, False, DIM)
        surf.blit(ds, (col2, y + 2))

        # Example in white using main font
        col3 = col2 + 260
        es = font.render(wexample, False, FG)
        surf.blit(es, (col3, y))

        y += row_h

    return surf


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "GLYPH_REFERENCE.png")
    sheet = make_sheet()
    pygame.image.save(sheet, out)
    w, h = sheet.get_size()
    print(f"Saved: {out}")
    print(f"Size:  {w} x {h} px")
    pygame.quit()
