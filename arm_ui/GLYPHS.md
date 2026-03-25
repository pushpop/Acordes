# ARM UI - PixelCode Glyph Reference & Design Grid

## Screen dimensions

| Layer | Size | Notes |
|---|---|---|
| Internal render | 240 × 160 px | All widget coords use this |
| Physical display | 480 × 320 px | Scaled 2x nearest-neighbor |

## Character grid at each font size

| Constant | Size | Cell | Grid (cols × rows) | Use |
|---|---|---|---|---|
| FONT_TINY | 8 pt | 5 × 11 px | 48 × 14 | hints, secondary values, small labels |
| FONT_SMALL | 11 pt | 7 × 15 px | 34 × 10 | **box borders, body text** (design baseline) |
| FONT_MEDIUM | 14 pt | 9 × 19 px | 26 × 8 | section headers, active names |
| FONT_LARGE | 20 pt | 13 × 27 px | 18 × 5 | mode icons, big values |
| FONT_GIANT | 32 pt | 21 × 43 px | 11 × 3 | splash / BPM counter |

**Design baseline: FONT_SMALL = 34 columns × 10 rows.**
Box borders, hint bar, and title bar all use this grid.
Content inside boxes can use FONT_TINY for more density.

---

## Sketch canvas (34 × 10 at FONT_SMALL)

Copy this as your starting point. Row 0 = title bar, row 9 = hint bar.

```
col: 0         1         2         3
     0123456789012345678901234567890123
r 0: [  title bar - left    right   ]
r 1: ┌──────────────────────────────┐
r 2: │                              │
r 3: │                              │
r 4: │                              │
r 5: │                              │
r 6: │                              │
r 7: │                              │
r 8: └──────────────────────────────┘
r 9: [  hint bar - key:action pairs ]
```

Content rows 1-8 = 8 usable rows inside a full-screen box.
The title bar and hint bar each consume one row (row 0 and row 9).

---

## Box-drawing characters

### Single line (standard panels, tiles, buttons)
```
┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
│                                 │
├ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┤
│                                 │
└ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
```
Corners: `┌ ┐ └ ┘`  Sides: `─ │`  T-junctions: `├ ┤ ┬ ┴`  Cross: `┼`

### Double line (emphasis, selected state, important panels)
```
╔ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ╗
║                                 ║
╚ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ═ ╝
```
Corners: `╔ ╗ ╚ ╝`  Sides: `═ ║`

---

## Block elements (progress bars, level meters, fills)

```
Direction    Chars        Meaning
horizontal   ▏▎▍▌▋▊▉█    1/8 increments left-fill
vertical     ▁▂▃▄▅▆▇█    1/8 increments bottom-fill
shading      ░ ▒ ▓ █     25% 50% 75% 100%
halves       ▀ ▄         top-half  bottom-half
quarters     ▌ ▐         left-half right-half
```

**Progress bar examples (8 chars wide):**
```
Empty:    ░░░░░░░░
25%:      ██░░░░░░
50%:      ████░░░░
75%:      ██████░░
Full:     ████████
Fractional 33%: ██▋░░░░░
```

---

## Geometric shapes (indicators, icons, toggles)

```
Symbol  Char  Code    Use
●       ●     U+25CF  filled circle  - active, on, playing
○       ○     U+25CB  empty  circle  - inactive, off, stopped
■       ■     U+25A0  filled square  - beat active, step on
□       □     U+25A1  empty  square  - beat inactive, step off
◆       ◆     U+25C6  filled diamond - piano, chord mode icon
◇       ◇     U+25C7  empty  diamond
▲       ▲     U+25B2  triangle up    - synth mode icon
▶       ▶     U+25B6  arrow right    - play, confirm
◀       ◀     U+25C0  arrow left     - back, cancel
▼       ▼     U+25BC  triangle down
◉       ◉     U+25C9  bullseye       - selected/focused item
```

---

## Arrows

```
← → ↑ ↓    standard arrows      (U+2190-U+2193)
↔ ↕         bidirectional        (U+2194-U+2195)
⇐ ⇒ ⇑ ⇓   double arrows        (U+21D0-U+21D3)
```

---

## Status / check symbols

```
✓  U+2713   check  (OK, confirmed)
✗  U+2717   cross  (error, off)
✔  U+2714   heavy check
✘  U+2718   heavy cross
```

---

## Common widget patterns (sketch vocabulary)

### Toggle (3 chars wide)
```
On:   [● ]    color = ACCENT green
Off:  [ ○]    color = TEXT_DIM grey
```

### Selector / browser (variable width)
```
◀ SAWTOOTH ▶
◀ 128 BPM  ▶
```

### Parameter row (full width, FONT_TINY inside FONT_SMALL box)
```
CUTOFF ░░░░░░░░░░░░░░░░░░ 1200Hz
RESO   ████░░░░░░░░░░░░░░  45%
ATK    ██░░░░░░░░░░░░░░░░   8ms
REL    ████████░░░░░░░░░░ 320ms
```

### Step sequencer row (16 steps, each = 1 char)
```
KICK  ■□□□■□□□■□□□■□□□
SNARE □□□□■□□□□□□□■□□□
HIHAT ■□■□■□■□■□■□■□■□
```

### Level meter (vertical, 8 rows tall)
```
█
█
▓
▒
░



```

---

## Font variant roles

| Variant | When to use | Example |
|---|---|---|
| **Regular** | body text, box chrome, param names | `CUTOFF  1200Hz` |
| *Italic* | hints, secondary info, dim labels | *`L/R: move  Enter: select`* |
| **Medium** | headers, selected names, titles | `SYNTH PRESET` |

---

## Sketch tool recommendation

**Best option: VS Code with PixelCode font**
1. Install the PixelCode font on your machine (the TTFs are in `arm_ui/fonts/`)
2. In VS Code settings: `"editor.fontFamily": "PixelCode"`, `"editor.fontSize": 12`
3. Create a `.txt` file and sketch directly - what you type is exactly what renders

**For box drawing in VS Code:**
- Plugin: "Draw.io Integration" or "ASCII Decorator" for auto-box drawing
- Or just copy-paste the characters from this file

**Quick workflow:**
1. Copy the 34×10 canvas template above into a `.txt` file
2. Sketch your layout using the glyph table
3. Paste the sketch into chat - I map it directly to `widgets.*` calls

**One cell = one character = 7×15px at FONT_SMALL (appearing as 14×30px on the physical display after 2x scaling).**


## Full font set Glyphs

  ! " # $ % & ' ( ) * + , - . / 0 1 2 3 4 5 6 7 8 9 : ; < = >
      ? @ A B C D E F G H I J K L M N O P Q R S T U V W X Y Z [ \ ] ^
      _ ` a b c d e f g h i j k l m n o p q r s t u v w x y z { | } ~
      ¡ ¢ £ ¤ ¥ ¦ § ¨ ª « ¬ ¯ ° ± ² ³ ´ µ ¶ · ¸ ¹ º » ¼ ½ ¾ ¿ À Á Â Ã
      Ä Å Æ Ç È É Ê Ë Ì Í Î Ï Ð Ñ Ò Ó Ô Õ Ö × Ø Ù Ú Û Ü Ý Þ ß à á â ã
      ä å æ ç è é ê ë ì í î ï ð ñ ò ó ô õ ö ÷ ø ù ú û ü ý þ ÿ Ā ā Ă ă
      Ą ą Ć ć Ĉ ĉ Ċ ċ Č č Ď ď Đ đ Ē ē Ĕ ĕ Ė ė Ę ę Ě ě Ĝ ĝ Ğ ğ Ġ ġ Ģ ģ
      Ĥ ĥ Ħ ħ Ĩ ĩ Ī ī Ĭ ĭ Į į İ ı Ĳ ĳ Ĵ ĵ Ķ ķ ĸ Ĺ ĺ Ļ ļ Ľ ľ Ŀ ŀ Ł ł Ń
      ń Ņ ņ Ň ň ŉ Ŋ ŋ Ō ō Ŏ ŏ Ő ő Œ œ Ŕ ŕ Ŗ ŗ Ř ř Ś ś Ŝ ŝ Ş ş Š š Ţ ţ
      Ť ť Ŧ ŧ Ũ ũ Ū ū Ŭ ŭ Ů ů Ű ű Ų ų Ŵ ŵ Ŷ ŷ Ÿ Ź ź Ż ż Ž ž ʰ ʱ ʲ ʳ ʴ
      ʶ ʷ ʸ ˀ ˁ ˂ ˃ ˄ ˅ ˆ ˇ ˈ ˉ ˊ ˋ ˌ ˍ ˎ ˏ ː ˑ ˔ ˕ ˖ ˗ ˘ ˙ ˚ ˜ ˝ ˟ ˡ
      ˢ ˣ ˤ ˥ ˦ ˧ ˨ ˩ ˪ ˫ ˬ ˭ ˯ ˰ ˱ ˲ ˳ ˴ ˵ ˶ ˷ ˸ ˹ ˺ ˻ ˼ ˽ ˾ Ͱ ͱ Ͳ ͳ
      ʹ ͵ Ͷ ͷ ͺ ͻ ͼ ͽ ; Ϳ ΄ ΅ Ά · Έ Ή Ί Ό Ύ Ώ ΐ Α Β Γ Δ Ε Ζ Η Θ Ι Κ Λ
      Μ Ν Ξ Ο Π Ρ Σ Τ Υ Φ Χ Ψ Ω Ϊ Ϋ ά έ ή ί ΰ α β γ δ ε ζ η θ ι κ λ μ
      ν ξ ο π ρ ς σ τ υ φ χ ψ ω ϊ ϋ ό ύ ώ Ϗ ϐ ϑ ϒ ϓ ϔ ϕ ϖ ϗ Ϙ ϙ Ϛ ϛ Ϝ
      ϝ Ϟ ϟ Ϡ ϡ ϱ ϲ ϳ ϴ ϵ ϶ Ϸ ϸ Ϲ Ϻ ϻ ϼ Ͻ Ͼ Ͽ Ѐ Ё Ђ Ѓ Є Ѕ І Ї Ј Љ Њ Ћ
      Ќ Ѝ Ў Џ А Б В Г Д Е Ж З И Й К Л М Н О П Р С Т У Ф Х Ц Ч Ш Щ Ъ Ы
      Ь Э Ю Я а б в г д е ж з и й к л м н о п р с т у ф х ц ч ш щ ъ ы
      ь э ю я ѐ ё ђ ѓ є ѕ і ї ј љ њ ћ ќ ѝ ў џ א ב ג ד ה ו ז ח ט י ך כ
      ל ם מ ן נ ס ע ף פ ץ צ ק ר ש ת ׳ ״ ᴬ ᴭ ᴮ ᴰ ᴱ ᴲ ᴳ ᴴ ᴵ ᴶ ᴷ ᴸ ᴹ ᴺ ᴻ
      ᴼ ᴽ ᴾ ᴿ ᵀ ᵁ ᵂ ᵃ ᵅ ᵇ ᵈ ᵉ ᵍ ᵎ ᵏ ᵐ ᵑ ᵒ ᵖ ᵗ ᵘ ᵛ ᵝ ᵢ ᵣ ᵤ ᵥ ᵦ ‐ ‑ ‒ –
      — ― ‖ ‘ ’ ‚ ‛ “ ” „ ‟ † ‡ • ‣ ․ ‥ … ‧ ′ ″ ‴ ‵ ‶ ‷ ‸ ‹ › ‼ ‽ ‾ ‿
      ⁀ ⁁ ⁂ ⁃ ⁅ ⁆ ⁇ ⁈ ⁉ ⁋ ⁌ ⁍ ⁎ ⁐ ⁑ ⁒ ⁓ ⁔ ⁕ ⁖ ⁘ ⁙ ⁚ ⁛ ⁜ ⁝ ⁞ ⁰ ⁱ ⁴ ⁵ ⁶
      ⁷ ⁸ ⁹ ⁺ ⁻ ⁼ ⁽ ⁾ ⁿ ₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ₊ ₋ ₌ ₍ ₎ ₐ ₑ ₒ ₓ ₕ ₖ ₗ ₘ
      ₙ ₚ ₛ ₜ ← ↑ → ↓ ↕ ↖ ↗ ↘ ↙ ↩ ↪ ↰ ↱ ↲ ↳ ↴ ↵ ↶ ↷ ↸ ↺ ↻ ↼ ↽ ↾ ↿ ⇀ ⇁
      ⇂ ⇃ ⇠ ⇡ ⇢ ⇣ ⇦ ⇧ ⇨ ⇩ ⇪ ─ ━ │ ┃ ┄ ┅ ┆ ┇ ┊ ┋ ┌ ┍ ┎ ┏ ┐ ┑ ┒ ┓ └ ┕ ┖
      ┗ ┘ ┙ ┚ ┛ ├ ┝ ┞ ┟ ┠ ┡ ┢ ┣ ┤ ┥ ┦ ┧ ┨ ┩ ┪ ┫ ┬ ┭ ┮ ┯ ┰ ┱ ┲ ┳ ┴ ┵ ┶
      ┷ ┸ ┹ ┺ ┻ ┼ ┽ ┾ ┿ ╀ ╁ ╂ ╃ ╄ ╅ ╆ ╇ ╈ ╉ ╊ ╋ ╌ ╍ ╎ ╏ ═ ║ ╒ ╓ ╔ ╕ ╖
      ╗ ╘ ╙ ╚ ╛ ╜ ╝ ╞ ╟ ╠ ╡ ╢ ╣ ╤ ╥ ╦ ╧ ╨ ╩ ╪ ╫ ╬ ╭ ╮ ╯ ╰ ╱ ╲ ╳ ╴ ╵ ╶
      ╷ ╸ ╹ ╺ ╻ ╼ ╽ ╾ ╿ ▀ ▁ ▂ ▃ ▄ ▅ ▆ ▇ ▉ ▊ ▋ ▌ ▍ ▎ ▏ ▐ ░ ▒ ▓ ▔ ▕ ▖ ▗
      ▘ ▙ ▚ ▛ ▜ ▝ ▞ ▟ ■ □ ▢ ▣ ▤ ▥ ▦ ▧ ▨ ▩ ▪ ▫ ▬ ▭ ▮ ▯ ▲ △ ▴ ▵ ▶ ▷ ▸ ▹
      ► ▻ ▼ ▽ ▾ ▿ ◀ ◁ ◂ ◃ ◄ ◅ ◆ ◇ ◈ ◉ ◊ ○ ◌ ◍ ◎ ● ◐ ◑ ◒ ◓ ◔ ◕ ◖ ◗ ◘ ◙
      ◚ ◛ ◜ ◝ ◞ ◟ ◠ ◡ ◢ ◣ ◤ ◥ ◦ ◧ ◨ ◩ ◪ ◫ ◭ ◮ ◯ ◰ ◱ ◲ ◳ ◴ ◵ ◶ ◷ ◸ ◹ ◺
      ◻ ◼ ◿ ✅✉ ✊✋✌ ✓ ✔ ✕ ✖ ✗ ✘ ✙ ✚ ✛ ✜ ✡ ✢ ✣ ✤ ✥ ✦ ✧ ✨✳ ✴ ✿ ❀ ❇ ❈
      ❌❎❏ ❐ ❑ ❒ ❓❔❕❗❘ ❙ ❚ ❛ ❜ ❝ ❞ ❡ ❢ ❣ ❤ ❥ ❦ ❧ ❨ ❩ ❪ ❫ ❬ ❭ ❮ ❯
      ❰ ❱ ❲ ❳ ❴ ❵ ❶ ❷ ❸ ❹ ❺ ❻ ❼ ❽ ❾ ❿ ➀ ➁ ➂ ➃ ➄ ➅ ➆ ➇ ➈ ➉ ➊ ➋ ➌ ➍ ➎ ➏
      ➐ ➑ ➒ ➓ ➔ ➕➖➗➘ ➙ ➚ ➛ ➜ ➝ ➞ ➟ ➠ ➡ ➢ ➣ ➤ ➥ ➦ ➧ ➨ ➩ ➪ ➫ ➬ ➭ ➮ ➯
      ➰➱ ➲ ➳ ➴ ➵ ➶ ➷ ➸ ➹ ➺ ➻ ➼ ➽ ➾ ➿⟲ ⟳ ⟵ ⟶ ⠁ ⠂ ⠃ ⠄ ⠅ ⠆ ⠇ ⠈ ⠉ ⠊ ⠋ ⠌
      ⠍ ⠎ ⠏ ⠐ ⠑ ⠒ ⠓ ⠔ ⠕ ⠖ ⠗ ⠘ ⠙ ⠚ ⠛ ⠜ ⠝ ⠞ ⠟ ⠠ ⠡ ⠢ ⠣ ⠤ ⠥ ⠦ ⠧ ⠨ ⠩ ⠪ ⠫ ⠬
      ⠭ ⠮ ⠯ ⠰ ⠱ ⠲ ⠳ ⠴ ⠵ ⠶ ⠷ ⠸ ⠹ ⠺ ⠻ ⠼ ⠽ ⠾ ⠿ ⡀ ⡁ ⡂ ⡃ ⡄ ⡅ ⡆ ⡇ ⡈ ⡉ ⡊ ⡋ ⡌
      ⡍ ⡎ ⡏ ⡐ ⡑ ⡒ ⡓ ⡔ ⡕ ⡖ ⡗ ⡘ ⡙ ⡚ ⡛ ⡜ ⡝ ⡞ ⡟ ⡠ ⡡ ⡢ ⡣ ⡤ ⡥ ⡦ ⡧ ⡨ ⡩ ⡪ ⡫ ⡬
      ⡭ ⡮ ⡯ ⡰ ⡱ ⡲ ⡳ ⡴ ⡵ ⡶ ⡷ ⡸ ⡹ ⡺ ⡻ ⡼ ⡽ ⡾ ⡿ ⢀ ⢁ ⢂ ⢃ ⢄ ⢅ ⢆ ⢇ ⢈ ⢉ ⢊ ⢋ ⢌
      ⢍ ⢎ ⢏ ⢐ ⢑ ⢒ ⢓ ⢔ ⢕ ⢖ ⢗ ⢘ ⢙ ⢚ ⢛ ⢜ ⢝ ⢞ ⢟ ⢠ ⢡ ⢢ ⢣ ⢤ ⢥ ⢦ ⢧ ⢨ ⢩ ⢪ ⢫ ⢬
      ⢭ ⢮ ⢯ ⢰ ⢱ ⢲ ⢳ ⢴ ⢵ ⢶ ⢷ ⢸ ⢹ ⢺ ⢻ ⢼ ⢽ ⢾ ⢿ ⣀ ⣁ ⣂ ⣃ ⣄ ⣅ ⣆ ⣇ ⣈ ⣉ ⣊ ⣋ ⣌
      ⣍ ⣎ ⣏ ⣐ ⣑ ⣒ ⣓ ⣔ ⣕ ⣖ ⣗ ⣘ ⣙ ⣚ ⣛ ⣜ ⣝ ⣞ ⣟ ⣠ ⣡ ⣢ ⣣ ⣤ ⣥ ⣦ ⣧ ⣨ ⣩ ⣪ ⣫ ⣬
      ⣭ ⣮ ⣯ ⣰ ⣱ ⣲ ⣳ ⣴ ⣵ ⣶ ⣷ ⣸ ⣹ ⣺ ⣻ ⣼ ⣽ ⣾ ⣿ ⤌ ⤍ ⤎ ⤏ ⤙ ⤚ ⤛ ⤜ ⤡ ⤢ ⤣ ⤤ ⤥
      ⤦ ⤴ ⤵ ⤶ ⤷ ⤸ ⤹ ⤺ ⤻ ⤾ ⤿ ⥢ ⥣ ⥤ ⥥ ⥦ ⥧ ⥨ ⥩ ⥪ ⥫ ⥬ ⥭ ⥮ ⥯ ⥰ ⬀ ⬁ ⬂ ⬃ ⬅ ⬆
      ⬇ ⬈ ⬉ ⬊ ⬋ ⬎ ⬏ ⬐ ⬑ ⬒ ⬓ ⬔ ⬕ ⬖ ⬗ ⬘ ⬙ ⬚ ⬛⬜⬝ ⬞ ⬥ ⬦ ⬧ ⬨ ⭕⭠ ⭡ ⭢ ⭣ ⭥
      ⭦ ⭧ ⭨ ⭩ ⭮ ⭯ ⮌ ⮍ ⮎ ⮏ ⮐ ⮑ ⮒ ⮓ ⮕ ⮬ ⮭ ⮮ ⮯ ⮺ ⮻ ⮼ ⯀ ⯁ ⯅ ⯆ ⯇ ⯈ ⯊ ⯋ ⯑ ⯒
      ⯾ ⯿ ⱼ ⱽ ꟲ ꟳ ꟴ ꟹ                        
             � 🬀 🬁 🬂 🬃 🬄 🬅 🬆 🬇 🬈 🬉 🬊 🬋 🬌 🬍 🬎 🬏 🬐 🬑 🬒 🬓 🬔 🬕 🬖 🬗
      🬘 🬙 🬚 🬛 🬜 🬝 🬞 🬟 🬠 🬡 🬢 🬣 🬤 🬥 🬦 🬧 🬨 🬩 🬪 🬫 🬬 🬭 🬮 🬯 🬰 🬱 🬲 🬳 🬴 🬵 🬶 🬷
      🬸 🬹 🬺 🬻 🬼 🬽 🬾 🬿 🭀 🭁 🭂 🭃 🭄 🭅 🭆 🭇 🭈 🭉 🭊 🭋 🭌 🭍 🭎 🭏 🭐 🭑 🭒 🭓 🭔 🭕 🭖 🭗
      🭘 🭙 🭚 🭛 🭜 🭝 🭞 🭟 🭠 🭡 🭢 🭣 🭤 🭥 🭦 🭧 🭨 🭩 🭪 🭫 🭬 🭭 🭮 🭯 🮌 🮍 🮎 🮏 🮐 🮑 🮒 🮔
      🮕 🮖 🮗 🮘 🮙 🮚 🮛 🮜 🮝 🮞 🮟 🮠 🮡 🮢 🮣 🮤 🮥 🮦 🮧 🮨 🮩 🮪 🮫 🮬 🮭 🮮 🮯 🮰 🮱 🮲 🮳 🮴
      🮵 🮶 🮷 🮸 🮹 🮺 🮻 🮼 🮽 🮾 🮿 🯀 🯁 🯂 🯃 🯄 🯅 🯆 🯇 🯈 🯉 🯊 🯰 🯱 🯲 🯳 🯴 🯵 🯶 🯷 🯸 🯹