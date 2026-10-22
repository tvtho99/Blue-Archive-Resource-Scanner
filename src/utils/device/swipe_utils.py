import logging
import time

import numpy as np

from src.core.area import Region
from src.utils.device.interfaces import DeviceController
from src.utils.ocr.extract import crop_image

logger = logging.getLogger("BA-Scanner")


def swipe_with_verification(
    device: DeviceController,
    grid_region: Region,
    max_attempts: int = 3,
) -> bool:
    """
    Swipe with screenshot verification to ensure it actually scrolled.
    A swipe the game ignored is retried, so False means the grid is at its end.
    """

    # Swipe from 80% down the grid height to 10% down the grid height
    start_y = grid_region.y + int(grid_region.height * 0.80)
    end_y = grid_region.y + int(grid_region.height * 0.10)
    swipe_x = grid_region.x + (grid_region.width // 2)

    for attempt in range(1, max_attempts + 1):
        # Capture before swipe
        before = device.capture_screenshot()
        if before is None:
            return False

        # Perform swipe
        device.swipe(swipe_x, start_y, swipe_x, end_y, duration_ms=2000)

        # Wait for animation
        time.sleep(2.5)

        # Capture after swipe
        after = device.capture_screenshot()
        if after is None:
            return False

        # Verify screen changed using full grid region
        if _screens_are_different(
            crop_image(before, grid_region), crop_image(after, grid_region)
        ):
            return True

        logger.warning(
            f"[bold yellow]Swipe: [/bold yellow] Attempt {attempt}/{max_attempts} did not scroll."
        )

    logger.info("Grid did not scroll after all retries, treating it as the end.")
    return False


def _screens_are_different(
    before_crop: np.ndarray,
    after_crop: np.ndarray,
    threshold: float = 0.05,
) -> bool:
    """
    Compare the full grid region to detect if swipe actually changed content.
    """
    if before_crop is None or after_crop is None:
        return False

    # if shapes don't match, assume it changed (or screen resized)
    if before_crop.shape != after_crop.shape:
        return True

    diff = np.abs(before_crop.astype(float) - after_crop.astype(float))
    diff_ratio = np.mean(diff) / 255.0

    logger.info(
        f"[bold yellow]Swipe: [/bold yellow] diff_ratio = {diff_ratio:.4f}  (threshold = {threshold})"
    )

    return diff_ratio > threshold
