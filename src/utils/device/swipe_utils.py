import logging
import time

import numpy as np

from src.core.area import Region
from src.utils.device.interfaces import DeviceController
from src.utils.ocr.extract import crop_image

logger = logging.getLogger("BA-Scanner")

# A scroll of exactly a row pitch lines the slot frames up again and only the icons
# differ, so the mean diff stays under 0.05 (0.037-0.042 on synthetic grids). The grid
# also counts as moved when over 5% of its pixels changed by more than 40 on some
# channel: such a scroll changes 14-19% of a synthetic grid, capture noise (sigma <= 5)
# none, a cursor or a selection frame that moved 0.1-1.4%.
STRONG_DIFF = 40
STRONG_SHARE = 0.05

# ponytail: 60 drags of 2.5+ rows reach the top from ~750 items down, further fails loudly
MAX_DRAGS_TO_TOP = 60


def swipe_with_verification(
    device: DeviceController,
    grid_region: Region,
    max_attempts: int = 3,
) -> bool:
    """
    Scroll the grid towards its end with one drag, retrying drags the game ignored.

    Returns:
        bool: True if the grid moved. False if it is at its end: max_attempts drags
        did not move it, but a drag back up did, so the drags do reach the game.

    Raises:
        RuntimeError: The grid moved in neither direction, or a screenshot failed.
    """
    for attempt in range(1, max_attempts + 1):
        if _drag_moves_grid(device, grid_region):
            return True

        logger.warning(
            f"[bold yellow]Swipe: [/bold yellow] Attempt {attempt}/{max_attempts} did not scroll."
        )

    if _drag_moves_grid(device, grid_region, up=True):
        logger.info("Grid did not scroll further but scrolled back up: end of the grid.")
        return False

    raise RuntimeError(
        "Grid did not scroll in either direction: drags are not reaching the game "
        "(or the whole list fits on one screen), previous results kept"
    )


def scroll_to_top(
    device: DeviceController,
    grid_region: Region,
    max_drags: int = MAX_DRAGS_TO_TOP,
    confirmations: int = 2,
) -> None:
    """
    Drag the grid back up until `confirmations` drags in a row no longer move it.
    A single still drag could be one the game ignored (often the first input after
    focusing it), and the scan would then start mid-list.
    """
    # ponytail: 2 still drags in a row, ~4.5 s extra per grid; raise it if ignored drags come in pairs
    logger.info("[bold yellow]Swipe: [/bold yellow] Scrolling the grid to its top...")
    still = 0
    for _ in range(max_drags):
        still = 0 if _drag_moves_grid(device, grid_region, up=True) else still + 1
        if still >= confirmations:
            return

    raise RuntimeError(
        f"Grid still moving after {max_drags} drags up, could not reach its top, "
        "previous results kept"
    )


def _drag_moves_grid(
    device: DeviceController, grid_region: Region, up: bool = False
) -> bool:
    """
    One slow drag over the grid, True if it changed the grid.
    Drags from 80% down the grid height to 10% (towards the end of the list),
    or the other way round with up=True (towards its top).
    """
    low_y = grid_region.y + int(grid_region.height * 0.80)
    high_y = grid_region.y + int(grid_region.height * 0.10)
    start_y, end_y = (high_y, low_y) if up else (low_y, high_y)
    swipe_x = grid_region.x + (grid_region.width // 2)

    before = _capture_grid(device, grid_region)
    if device.swipe(swipe_x, start_y, swipe_x, end_y, duration_ms=2000) is False:
        # ADB reports a failed "input swipe", no point retrying blind
        raise RuntimeError("Swipe command failed, previous results kept")
    time.sleep(2.5)  # Wait for the scroll animation
    after = _capture_grid(device, grid_region)

    return _screens_are_different(before, after)


def _capture_grid(device: DeviceController, grid_region: Region) -> np.ndarray:
    image = device.capture_screenshot()
    if image is None:
        # Can't tell whether the grid moved, guessing could end the scan early
        raise RuntimeError(
            "Screenshot failed while scrolling the grid, previous results kept"
        )
    return crop_image(image, grid_region)


def _screens_are_different(
    before_crop: np.ndarray,
    after_crop: np.ndarray,
    threshold: float = 0.05,
) -> bool:
    """
    Compare the full grid region to detect if swipe actually changed content.
    """
    # if shapes don't match, assume it changed (or screen resized)
    if before_crop.shape != after_crop.shape:
        return True

    diff = np.abs(before_crop.astype(float) - after_crop.astype(float))
    diff_ratio = np.mean(diff) / 255.0
    channel_max = diff.max(axis=2) if diff.ndim == 3 else diff
    strong_ratio = np.mean(channel_max > STRONG_DIFF)

    logger.info(
        f"[bold yellow]Swipe: [/bold yellow] diff_ratio = {diff_ratio:.4f}  (threshold = {threshold}), "
        f"strongly changed = {strong_ratio:.4f}  (threshold = {STRONG_SHARE})"
    )

    return diff_ratio > threshold or strong_ratio > STRONG_SHARE
