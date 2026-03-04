"""
ABOUTME: Textual screen for browsing and selecting factory presets
ABOUTME: Audio-first design: minimal UI updates, all resources to audio playback
"""

import time
from textual.screen import Screen
from textual.containers import Vertical
from textual.widgets import Static, Label
from textual.binding import Binding
from typing import Dict, Any, Optional, Callable, List


class PresetItem(Static):
    """A single preset row item."""

    DEFAULT_CSS = """
    PresetItem {
        layout: horizontal;
        width: 100%;
        height: 1;
        padding: 0;
        margin: 0;
    }

    PresetItem #preset-name {
        width: 100%;
        height: 1;
        padding: 0 2;
        margin: 0;
        content-align: left middle;
        color: $accent;
    }

    PresetItem.selected {
        background: $boost;
    }

    PresetItem.selected #preset-name {
        color: #ffff00;
        text-style: bold;
    }

    PresetItem.hidden {
        display: none;
    }
    """

    def __init__(self, name: str = "", category_id: str = "", preset_data: Dict[str, Any] = None):
        super().__init__()
        self.preset_name = name
        self.category_id = category_id
        self.preset_data = preset_data

    def compose(self):
        yield Label(self.preset_name, id="preset-name")

    def update_data(self, name: str, category_id: str, preset_data: Dict[str, Any]):
        """Update preset data without re-rendering."""
        self.preset_name = name
        self.category_id = category_id
        self.preset_data = preset_data
        label = self.query_one("#preset-name", Label)
        label.update(name)


class CategoryHeader(Static):
    """Category header widget."""

    DEFAULT_CSS = """
    CategoryHeader {
        layout: horizontal;
        width: 100%;
        height: 1;
        padding: 0;
        margin: 0;
    }

    CategoryHeader #cat-name {
        width: 100%;
        height: 1;
        padding: 0 2;
        margin: 0;
        content-align: left middle;
        color: #FFA500;
        text-style: bold;
    }

    CategoryHeader.hidden {
        display: none;
    }
    """

    def __init__(self, category_name: str = ""):
        super().__init__()
        self.category_name = category_name

    def compose(self):
        yield Label(self.category_name, id="cat-name")

    def update_data(self, category_name: str):
        """Update category name without re-rendering."""
        self.category_name = category_name
        label = self.query_one("#cat-name", Label)
        label.update(category_name)


class PresetBrowserScreen(Screen):
    """Audio-first preset browser: minimal UI updates, maximum audio resources."""

    # Class variable to persist state across modal open/close cycles
    _last_selected_index: int = 0
    _last_visible_start: int = 0

    CSS = """
    PresetBrowserScreen {
        align: center middle;
        background: $surface;
    }

    #browser-box {
        width: 55;
        height: auto;
        border: solid #FFA500;
        background: $panel;
    }

    #browser-header {
        width: 100%;
        height: auto;
        text-align: center;
        color: #00ff00;
        background: $boost;
        padding: 1 1;
        border-bottom: solid #FFA500;
        text-style: bold;
    }

    #presets-list-container {
        width: 100%;
        height: 28;
        padding: 0;
        margin: 0;
        layout: vertical;
        overflow: hidden;
    }

    #browser-footer {
        width: 100%;
        height: auto;
        padding: 1 1;
        margin: 0;
        border-top: solid #FFA500;
        color: #00aa00;
        text-align: center;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel_action", "Cancel", show=False),
        Binding("enter", "select_action", "Select", show=False),
        Binding("up", "navigate_up", "", show=False),
        Binding("down", "navigate_down", "", show=False),
    ]

    def __init__(
        self,
        presets_data: Dict[str, Dict[str, Any]],
        synth_engine: Optional[Any] = None,
        on_preset_selected: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the preset browser screen.

        Args:
            presets_data: Dict of categories from factory_presets.get_factory_presets()
            synth_engine: Reference to synth engine for all_notes_off()
            on_preset_selected: Callback when preset is selected (category_id, preset_name, preset_data)
            on_cancel: Callback when screen is cancelled
        """
        super().__init__()
        self.presets_data = presets_data
        self.synth_engine = synth_engine
        self.on_preset_selected = on_preset_selected
        self.on_cancel = on_cancel
        self.all_items: List[tuple] = []  # List of (type, data)
        self.all_presets: List[tuple] = []  # List of (category_id, preset_name, preset_data)
        self.selected_index = 0
        self.visible_start = 0
        self.max_visible = 27  # Fill entire list area (28 lines)
        self.widget_pool: List[Static] = []
        self._build_preset_list()

    def _build_preset_list(self):
        """Build a categorized list of presets with headers."""
        self.all_items = []
        self.all_presets = []
        category_order = ["bass", "leads", "pads", "plucked", "seq", "fx", "misc", "synth", "user"]
        category_names = {
            "bass": "🎸 BASS",
            "leads": "🎹 LEADS",
            "pads": "☁ PADS",
            "plucked": "🎵 PLUCKED",
            "seq": "🎶 SEQUENCER",
            "fx": "✨ FX",
            "misc": "🥁 MISC",
            "synth": "🌊 SYNTH",
            "user": "👤 USER",
        }

        for category_id in category_order:
            if category_id not in self.presets_data:
                continue
            category = self.presets_data[category_id]
            presets = category.get("presets", [])

            if not presets:
                continue

            # Add category header
            self.all_items.append(("header", (category_id, category_names.get(category_id, category_id.upper()))))

            # Add presets for this category
            for preset in presets:
                preset_name = preset.get("name", "Unnamed")
                self.all_items.append(("preset", (category_id, preset_name, preset)))
                self.all_presets.append((category_id, preset_name, preset))

    def compose(self):
        """Compose the screen layout - follows Tambor drum_editor pattern."""
        with Vertical(id="browser-box"):
            # Header
            yield Label("🎹 Factory Presets", id="browser-header")

            # Main list area - single column with fixed visible height
            with Vertical(id="presets-list-container"):
                # Create widget pool with flexible types (28 total widgets for 28 visible lines)
                # Roughly: 2-3 headers and 25-26 presets per viewport
                widget_types = (
                    [CategoryHeader("") for _ in range(1)] +
                    [PresetItem("", "", None) for _ in range(28)]
                )
                for widget in widget_types:
                    widget.add_class("hidden")
                    self.widget_pool.append(widget)
                    yield widget

            # Footer with instructions
            yield Label("[↑↓] Navigate  [ENTER] Apply  [ESC] Cancel", id="browser-footer")

    def on_mount(self) -> None:
        """Initialize the screen on mount."""
        # Restore last selected preset if still valid, otherwise find first preset
        if PresetBrowserScreen._last_selected_index > 0 and PresetBrowserScreen._last_selected_index < len(self.all_items):
            item_type, _ = self.all_items[PresetBrowserScreen._last_selected_index]
            if item_type == "preset":
                self.selected_index = PresetBrowserScreen._last_selected_index
                self.visible_start = PresetBrowserScreen._last_visible_start
            else:
                # Last index was a header, find next preset
                for idx in range(PresetBrowserScreen._last_selected_index, len(self.all_items)):
                    if self.all_items[idx][0] == "preset":
                        self.selected_index = idx
                        break
        else:
            # First time or invalid index, find first preset
            self.selected_index = 0
            self.visible_start = 0
            for idx, (item_type, _) in enumerate(self.all_items):
                if item_type == "preset":
                    self.selected_index = idx
                    break

        self._update_visible_items()

    def _update_visible_items(self):
        """Update widget pool to display visible items (minimal UI operations)."""
        # Ensure selected item is visible
        if self.selected_index < self.visible_start:
            self.visible_start = self.selected_index
        elif self.selected_index >= self.visible_start + self.max_visible:
            self.visible_start = self.selected_index - self.max_visible + 1

        # Update each widget in the pool - NO info panel updates
        visible_end = min(self.visible_start + self.max_visible, len(self.all_items))
        pool_idx = 0
        pool_headers = [i for i, w in enumerate(self.widget_pool) if isinstance(w, CategoryHeader)]
        pool_presets = [i for i, w in enumerate(self.widget_pool) if isinstance(w, PresetItem)]
        header_idx = 0
        preset_idx = 0

        for idx in range(self.visible_start, visible_end):
            if pool_idx >= len(self.widget_pool):
                break

            item_type, item_data = self.all_items[idx]

            # Find appropriate widget from pool based on item type
            if item_type == "header":
                cat_id, cat_name = item_data
                if header_idx < len(pool_headers):
                    widget = self.widget_pool[pool_headers[header_idx]]
                    header_idx += 1
                    widget.remove_class("hidden")
                    widget.update_data(cat_name)
                    widget.remove_class("selected")
                    pool_idx += 1
            else:  # preset
                cat_id, name, data = item_data
                if preset_idx < len(pool_presets):
                    widget = self.widget_pool[pool_presets[preset_idx]]
                    preset_idx += 1
                    widget.remove_class("hidden")
                    widget.update_data(name, cat_id, data)
                    if idx == self.selected_index:
                        widget.add_class("selected")
                    else:
                        widget.remove_class("selected")
                    pool_idx += 1

        # Hide unused widgets
        for i in range(pool_idx, len(self.widget_pool)):
            self.widget_pool[i].add_class("hidden")

    def _navigate_to_preset(self, new_index: int) -> bool:
        """Navigate to a preset, skipping headers."""
        new_index = new_index % len(self.all_items)
        item_type, _ = self.all_items[new_index]
        if item_type == "preset":
            self.selected_index = new_index
            # Persist the selected index for next time browser opens
            PresetBrowserScreen._last_selected_index = new_index
            PresetBrowserScreen._last_visible_start = self.visible_start
            self._update_visible_items()  # Minimal UI update only
            return True
        return False

    def _apply_current_preset(self):
        """Apply the currently selected preset with audio safety."""
        item_type, item_data = self.all_items[self.selected_index]
        if item_type != "preset":
            return

        cat_id, name, preset = item_data

        # Step 1: Cut all sounds immediately
        if self.synth_engine:
            self.synth_engine.all_notes_off()

        # Step 2: Small delay to let notes finish cutting (20ms)
        time.sleep(0.020)

        # Step 3: Apply preset to synth engine
        if self.on_preset_selected:
            self.on_preset_selected(cat_id, name, preset)

    def action_navigate_up(self) -> None:
        """Navigate to previous preset (minimal UI update only)."""
        if len(self.all_presets) == 0:
            return

        attempts = 0
        while attempts < len(self.all_items):
            new_index = (self.selected_index - 1) % len(self.all_items)
            if self._navigate_to_preset(new_index):
                return
            self.selected_index = new_index
            attempts += 1

    def action_navigate_down(self) -> None:
        """Navigate to next preset (minimal UI update only)."""
        if len(self.all_presets) == 0:
            return

        attempts = 0
        while attempts < len(self.all_items):
            new_index = (self.selected_index + 1) % len(self.all_items)
            if self._navigate_to_preset(new_index):
                return
            self.selected_index = new_index
            attempts += 1

    def action_select_action(self):
        """Apply the currently selected preset when ENTER is pressed."""
        if self.selected_index < 0 or self.selected_index >= len(self.all_items):
            return

        item_type, item_data = self.all_items[self.selected_index]
        if item_type != "preset":
            return

        # Apply the preset
        self._apply_current_preset()

        # Close the modal
        self.app.pop_screen()

    def action_cancel_action(self):
        """Cancel the screen."""
        if self.on_cancel:
            self.on_cancel()
        self.app.pop_screen()
