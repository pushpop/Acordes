# ABOUTME: Lets a Tambor dialog take over the gamepad while it is open and hand it back on closing.
# ABOUTME: Mixed into modal screens; without a gamepad handler it only closes the screen.

from typing import Callable, Dict

from gamepad.actions import GP


class GamepadDialog:
    """Gamepad control for a modal screen.

    The screen sets gamepad_handler, calls take_gamepad() when mounted and closes
    itself with close_dialog(). B and the View button run the cancel callback, and
    Start closes the dialog before doing what it does everywhere else.
    """

    gamepad_handler = None
    _saved_gamepad_callbacks = None

    def take_gamepad(self, buttons: Dict[str, Callable], cancel: Callable):
        """Replace the gamepad callbacks of whatever is underneath with the dialog's own."""
        handler = self.gamepad_handler
        if handler is None:
            return
        self._saved_gamepad_callbacks = handler.save_callbacks()
        handler.clear_callbacks()
        for action, callback in {**buttons, GP.BACK: cancel, GP.BACK_BTN: cancel}.items():
            handler.set_button_callback(action, self._while_on_top(callback))
        handler.set_button_callback(GP.START, lambda: self._leave_on_start(cancel))

    def _while_on_top(self, callback: Callable) -> Callable:
        """Ignore the button while another screen, such as a question, covers this one."""
        def run():
            if self.app.screen is self:
                callback()
        return run

    def _leave_on_start(self, cancel: Callable):
        """Close this dialog, and any question on top of it, then run the usual Start action."""
        async def leave():
            if self.app.screen is not self:
                # The question hands the gamepad back as it closes, so wait for that
                await self.app.screen.dismiss(False)
            cancel()
            self.gamepad_handler.fire_global_button(GP.START)

        self.run_worker(leave(), exclusive=True)

    def release_gamepad(self):
        """Give the gamepad back to whatever had it before this dialog."""
        if self._saved_gamepad_callbacks is not None:
            self.gamepad_handler.restore_callbacks(self._saved_gamepad_callbacks)
            self._saved_gamepad_callbacks = None

    def close_dialog(self):
        """Hand the gamepad back and close the screen."""
        self.release_gamepad()
        self.app.pop_screen()
