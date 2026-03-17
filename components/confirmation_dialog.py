"""Centered quit confirmation dialog."""
from textual.screen import ModalScreen
from textual.containers import Container, Vertical
from textual.widgets import Static, Label
from textual.binding import Binding


class ConfirmationDialog(ModalScreen[bool]):
    """A centered modal dialog for confirming quit action."""

    BINDINGS = [
        Binding("y", "confirm_yes", "Yes", show=False),
        Binding("Y", "confirm_yes", "Yes", show=False),
        Binding("n", "confirm_no", "No", show=False),
        Binding("N", "confirm_no", "No", show=False),
        Binding("enter", "confirm_yes", "Confirm", show=False),
        Binding("escape", "confirm_no", "Cancel", show=False),
    ]

    CSS = """
    ConfirmationDialog {
        align: center middle;
    }

    #dialog {
        width: 50;
        height: 9;
        border: thick #ffd700;
        background: #1a1a1a;
        padding: 1 2;
    }

    #message {
        width: 100%;
        content-align: center middle;
        color: #ffd700;
    }

    #options {
        width: 100%;
        height: 3;
        content-align: center middle;
        margin-top: 1;
        color: #ffffff;
    }
    """

    def __init__(self, message: str = "Quit application?", gamepad_handler=None):
        super().__init__()
        self.message = message
        self._gamepad_handler = gamepad_handler
        self._saved_confirm_cb = None
        self._saved_back_cb = None
        self._saved_back_btn_cb = None

    def compose(self):
        """Compose the dialog layout."""
        with Vertical(id="dialog"):
            yield Label(self.message, id="message")
            yield Label("[Y]es  [N]o", id="options", markup=False)

    def _get_gamepad_handler(self):
        """Return the gamepad handler from the app or the constructor parameter."""
        gp = getattr(self.app, "gamepad_handler", None)
        if gp is None:
            gp = self._gamepad_handler
        return gp

    def on_mount(self):
        """Register gamepad callbacks when dialog is shown.
        Saves any existing callbacks for the actions we override so they can be
        restored on dismiss (the underlying mode does not get on_mode_resume).
        """
        gp = self._get_gamepad_handler()
        if gp is None:
            return
        from gamepad.actions import GP
        self._saved_confirm_cb = gp.get_button_callback(GP.CONFIRM)
        self._saved_back_cb = gp.get_button_callback(GP.BACK)
        self._saved_back_btn_cb = gp.get_button_callback(GP.BACK_BTN)
        gp.set_button_callback(GP.CONFIRM, self._gp_yes)
        gp.set_button_callback(GP.BACK, self._gp_no)
        gp.set_button_callback(GP.BACK_BTN, self._gp_no)

    def on_unmount(self):
        """Restore the displaced gamepad callbacks when dialog is dismissed."""
        gp = self._get_gamepad_handler()
        if gp is None:
            return
        from gamepad.actions import GP
        if self._saved_confirm_cb is not None:
            gp.set_button_callback(GP.CONFIRM, self._saved_confirm_cb)
        else:
            gp.set_button_callback(GP.CONFIRM, lambda: None)
        if self._saved_back_cb is not None:
            gp.set_button_callback(GP.BACK, self._saved_back_cb)
        else:
            gp.set_button_callback(GP.BACK, lambda: None)
        if self._saved_back_btn_cb is not None:
            gp.set_button_callback(GP.BACK_BTN, self._saved_back_btn_cb)
        else:
            gp.set_button_callback(GP.BACK_BTN, lambda: None)

    def _gp_yes(self):
        """Gamepad confirm: dismiss with True."""
        self.dismiss(True)

    def _gp_no(self):
        """Gamepad cancel: dismiss with False."""
        self.dismiss(False)

    def action_confirm_yes(self):
        """User confirmed."""
        self.dismiss(True)

    def action_confirm_no(self):
        """User cancelled."""
        self.dismiss(False)
