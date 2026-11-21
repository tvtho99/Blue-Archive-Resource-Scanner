import logging
import time

from src.utils.device.interfaces import DeviceController, DeviceUnavailableError

from .window_manager import (
    FOCUS_WAIT_S,
    MIN_GAME_AREA,
    WindowManager,
    bars_are_black,
    game_area,
    set_dpi_awareness,
    to_base_resolution,
)

set_dpi_awareness()

SETTLE_S = 2  # After a wait, a fixed window must pass twice this far apart
READ_ONLY_MSG = (
    "The PC client is read-only: the scanner never clicks, drags or focuses the game. "
    "Go through the game yourself with python -m tools.manual_scan."
)

logger = logging.getLogger("BA-Scanner")


class DesktopDevice(DeviceController):
    """
    The PC client window, screenshots only. The game ships an anti-cheat and its
    terms forbid macros, so nothing here can click, drag or focus the game.
    """

    def __init__(self, window_name="Blue Archive"):
        self.window_name = window_name
        self.wm: WindowManager | None = None
        self._client_size = None  # Window size of the last capture
        self._bars_ok = False  # Its bars were checked black, see _find_game_area

    def connect(self, retries=0):
        """Find the game window, there is nothing else to connect to."""
        try:
            self.wm = WindowManager(self.window_name)
        except RuntimeError as e:
            logger.error(e)
            return False
        return True

    def capture_screenshot(self):
        """
        The game picture scaled to 1280x720, or None if the capture failed.
        While the window can't be scanned (too small, not letterboxed) asks the
        user to fix it and re-captures about every second, raising
        DeviceUnavailableError if it isn't fixed within FOCUS_WAIT_S.
        """
        deadline = None  # Set while waiting for the user to fix the window
        shown = None  # The instruction last logged
        passed = None  # Window size that passed once since the wait began
        while True:
            try:
                image = self.wm.get_screenshot()
            except DeviceUnavailableError:
                raise  # Game gone: stop rather than scan blank data
            except Exception as e:  # noqa: BLE001
                if deadline is None:
                    logger.error(f"Screenshot of '{self.window_name}' failed: {e}")
                    return None
                # The user may be resizing it or switching the screen mode
                logger.debug(f"Screenshot of '{self.window_name}' failed while waiting: {e}")
                image = None

            if image is not None:
                area, problem = self._find_game_area(image)
                if problem is None:
                    size = image.shape[:2]
                    if deadline is None or passed == size:
                        if deadline is not None:
                            logger.info("Game window is fine now, continuing.")
                        return to_base_resolution(
                            image[area.y : area.bottom, area.x : area.right]
                        )
                    # Passed once after a wait: look again, the user may still be
                    # dragging the border or closing the options
                    passed = size
                    time.sleep(SETTLE_S)
                    continue

                passed = None
                if problem != shown:  # A new instruction gets the full wait again
                    shown, deadline = problem, time.monotonic() + FOCUS_WAIT_S
                    logger.warning(f"{problem} Waiting up to {FOCUS_WAIT_S} s.")

            if time.monotonic() > deadline:
                raise DeviceUnavailableError(shown)
            time.sleep(1)

    def _find_game_area(self, image):
        """
        The game picture in a client-area capture, and what the user has to
        fix before it can be scanned (None if nothing).
        """
        h, w = image.shape[:2]
        area = game_area(w, h)
        if (w, h) != self._client_size:
            self._client_size, self._bars_ok = (w, h), False
            logger.info(
                f"Game area {area.width}x{area.height} at ({area.x}, {area.y}) in a {w}x{h} window"
            )

        if area.width < MIN_GAME_AREA.width or area.height < MIN_GAME_AREA.height:
            return area, (
                f"Game area is {area.width}x{area.height}, smaller than the "
                f"{MIN_GAME_AREA.width}x{MIN_GAME_AREA.height} minimum. "
                "Make the game window bigger (or use fullscreen)."
            )
        # ponytail: the bars are checked until they pass once per window size, so a
        # toast over a bar can't stop a scan later on. A picture that stops being
        # letterboxed without a resize, or an unletterboxed one whose edges were
        # dark when checked, goes unnoticed.
        if not self._bars_ok:
            if not bars_are_black(image, area):
                return area, (
                    f"Game window is {w}x{h} (not 16:9) and the picture is not letterboxed. "
                    "Set Screen Ratio to 16:9 in the game options, or resize the window to 16:9."
                )
            self._bars_ok = True
        return area, None

    def tap(self, x, y, duration_ms=100):
        raise DeviceUnavailableError(READ_ONLY_MSG)  # Stops a scan, see main.py

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        raise DeviceUnavailableError(READ_ONLY_MSG)
