# ARM UI Widget Reference

Font rules:
- `theme.txt(size, text, color)` - **Silkscreen** - titles, labels, buttons, menus, hints, param names
- `theme.glyph(size, text, color)` - **PixelCode** - box chrome, bars, shapes, indicators, long text

Canvas: 240x160 internal (rendered 2x to 480x320 on TFT).
Character grid at FONT_SMALL: 7x15px per cell (34 cols x 10 rows).

---

## Widget List

When you use a symbol in a Photoshop mockup that is NOT in this list,
I will treat it as a new widget request and add it.

---

### box
Rectangular border using PixelCode box-drawing characters.
```
widgets.box(surface, x, y, w_px, h_px, color, double=False, fill=None)
```
- Single line: `┌─┐ │ │ └─┘`
- Double line: `╔═╗ ║ ║ ╚═╝` (double=True)
- fill: optional background color inside the border
- Layer names in mockup: `box_*`, `panel_*`, `border_*`

---

### box_inner
Returns the pygame.Rect of the usable area inside a box (one cell inset from border).
```
rect = widgets.box_inner(x, y, w_px, h_px)
```
Use this to position content inside a box without hardcoding offsets.

---

### hline
Horizontal separator using `─` characters.
```
widgets.hline(surface, x, y, w_px, color)
```
- Layer names in mockup: `hline_*`, `separator_*`, `rule_*`

---

### vline
Vertical separator using `│` characters.
```
widgets.vline(surface, x, y, h_px, color)
```
- Layer names in mockup: `vline_*`

---

### hbar
Horizontal progress / level bar using block characters `█▉▊▋▌▍▎▏░`.
```
widgets.hbar(surface, x, y, w_px, value, max_value, fg_color, bg_color=None)
```
- Sub-character precision (1/8 steps) via fractional block glyphs
- bg_color draws a light `░` track behind the fill
- Layer names in mockup: `bar_*`, `level_*`, `progress_*`

---

### vbar
Vertical level bar (fills bottom to top) using `█` characters.
```
widgets.vbar(surface, x, y, h_px, value, max_value, fg_color, bg_color=None)
```
- Layer names in mockup: `vbar_*`, `meter_*`

---

### toggle
On/off switch using geometric characters.
```
widgets.toggle(surface, x, y, value, color_on, color_off=None)
```
- On:  `[● ]`  in color_on
- Off: `[ ○]`  in color_off (default TEXT_DIM)
- Layer names in mockup: `toggle_*`, `switch_*`

---

### label
Text label using Silkscreen (readable text).
```
widgets.label(surface, x, y, text, color=None, size=None, variant="regular")
```
- variant="ui" forces Silkscreen; variant="glyph" forces PixelCode
- Layer names in mockup: `label_*`, `text_*`, `name_*`

---

### hint_bar
Bottom strip showing key:action navigation hints.
```
widgets.hint_bar(surface, hints, y=None)
```
- hints: list of (key, action) tuples e.g. `[("L/R", "move"), ("Enter", "select")]`
- Draws a separator line above, then dim italic text centered
- Layer names in mockup: `hint_bar`, `hints`

---

### title_bar
Top strip with mode name (left, green) and sub-label (right, dim).
```
widgets.title_bar(surface, left_text, right_text=None, y=0)
```
- Draws a separator line below
- Layer names in mockup: `title_bar`, `header`

---

### status_dot
Filled/empty circle indicator with optional label.
```
widgets.status_dot(surface, x, y, active, label_text="", size=None)
```
- active=True  -> `●` in ACCENT green
- active=False -> `○` in TEXT_DIM grey
- Layer names in mockup: `dot_*`, `indicator_*`, `status_*`

---

### selector
Value browser with left/right arrows: `◀ VALUE ▶`
```
left_rect, right_rect = widgets.selector(surface, x, y, value_text, color=None, size=None)
```
- Returns hit rects for touch/click detection
- Layer names in mockup: `selector_*`, `picker_*`

---

### param_row
Single parameter row: `NAME ........ VALUE [bar]`
```
widgets.param_row(surface, x, y, w_px, name, value_text, bar_value=None, bar_max=1.0)
```
- name in Silkscreen dim, value in Silkscreen primary
- Optional inline hbar between name and value
- Layer names in mockup: `param_*`, `row_*`

---

### draw_char / draw_str
Low-level primitives: render a single char or string at pixel position.
```
widgets.draw_char(surface, x, y, char, color, size=None, variant="regular")
widgets.draw_str(surface, x, y, text, color, size=None, variant="regular")
```
- variant="ui" -> Silkscreen, variant="glyph" (default) -> PixelCode
- Used internally; also available for custom one-off rendering

---

## PNG / Sprite Icons

Custom pixel art icons (not font-based) go in `arm_ui/assets/`.
- Design at 1x (internal 240x160 resolution) in Photoshop
- Export as PNG-24 with transparency
- Load with `pygame.image.load("arm_ui/assets/icon_name.png").convert_alpha()`
- No scaling on export (2x doubling happens automatically in the renderer)

---

## NEW WIDGET PROTOCOL

If a Photoshop layer uses a shape, symbol, or layout element not in this list,
name the layer with a descriptive prefix (e.g. `new_waveform_display`,
`new_checkbox`, `new_stepper`) and I will implement it and add it here.
