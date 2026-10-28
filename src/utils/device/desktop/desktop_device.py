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

set_dpi_awareness()  # Before pyautogui is imported, see set_dpi_awareness

import pyautogui  # noqa: E402

pyautogui.FAILSAFE = True  # Mouse into a screen corner = emergency stop
FAILSAFE_MSG = "Mouse moved to a screen corner (pyautogui failsafe)."
SETTLE_S = 2  # After a wait, a fixed window must pass twice this far apart

logger = logging.getLogger("BA-Scanner")


class DesktopDevice(DeviceController):
    def __init__(self, window_name="Blue Archive", read_only=False):
        self.window_name = window_name
        # read_only: screenshots only, never a click, a drag or a focus change
        self.read_only = read_only
        self.wm: WindowManager | None = None
        self._client_size = None  # Window size of the last capture
        self._bars_ok = False  # Its bars were checked black, see _find_game_area

    def connect(self, retries=0):
        """Find the game window, there is nothing else to connect to."""
        try:
            self.wm = WindowManager(self.window_name, allow_focus=not self.read_only)
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
                raise  # Game gone or never focused: stop rather than scan blank data
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

    def _to_screen(self, x, y):
        """
        Screen point for a 1280x720 coordinate. Never returns a point another
        window would get the click on, waits instead (a toast, a popup).
        """
        if self.read_only:
            raise RuntimeError("Read-only device: the scanner must not send input.")
        deadline = time.monotonic() + FOCUS_WAIT_S
        warned = False
        while True:
            self.wm.activate()
            sx, sy = self.wm.scale_coords(x, y)
            if self.wm.owns_point(sx, sy):
                return sx, sy
            if time.monotonic() > deadline:
                raise DeviceUnavailableError(
                    f"'{self.window_name}' is covered or off-screen at ({sx}, {sy})."
                )
            if not warned:
                logger.warning(
                    f"'{self.window_name}' is covered or off-screen at ({sx}, {sy}), waiting."
                )
                warned = True
            time.sleep(0.5)

    def tap(self, x, y, duration_ms=100):
        sx, sy = self._to_screen(x, y)
        try:
            pyautogui.click(sx, sy)
        except pyautogui.FailSafeException as e:
            raise DeviceUnavailableError(FAILSAFE_MSG) from e
        return True

    def swipe(self, x1, y1, x2, y2, duration_ms=500):
        sx1, sy1 = self._to_screen(x1, y1)
        sx2, sy2 = self._to_screen(x2, y2)
        try:
            pyautogui.moveTo(sx1, sy1)
            pyautogui.mouseDown()
            try:
                pyautogui.moveTo(sx2, sy2, duration=duration_ms / 1000)
            finally:
                pyautogui.mouseUp()
        except pyautogui.FailSafeException as e:
            raise DeviceUnavailableError(FAILSAFE_MSG) from e
        return True
