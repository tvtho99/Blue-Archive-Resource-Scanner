import cv2
import numpy as np

# Blue UE star row in the 1280x720 UNIQUE_EQUIPMENT_STAR_QUANTITY crop. Measured on
# assets/images/star/*_blue_star.png natively, sub-pixel shifted and scaled up
# 1.07-2.5x and back with INTER_AREA: 1-4 stars span 16-19, 33-35, 49-52 and 65-67 px.
UE_STAR_WIDTH = 17.5
UE_STAR_PITCH = 16.5
MAX_UE_STARS = 4


def count_blue_stars_adaptive(cropped_image, debug=False):
    """
    Count the blue UE stars in a crop of the 1280x720 frame.
    Neighbouring stars touch and resampling splits or merges their blobs, so the
    count comes from the width of the star row, which resampling barely changes.
    """
    if cropped_image is None or cropped_image.size == 0:
        return 0

    # Blue including the pale highlights, but not the dark navy UI text
    hsv = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([85, 40, 120]), np.array([135, 255, 255]))

    # ponytail: assumes nothing else blue in the crop, a blue icon there widens the row
    columns = np.flatnonzero(np.count_nonzero(mask, axis=0) >= 3)  # Not thin specks
    width = int(columns[-1] - columns[0] + 1) if columns.size else 0
    stars = round((width - UE_STAR_WIDTH) / UE_STAR_PITCH) + 1 if width else 0
    stars = min(MAX_UE_STARS, max(0, stars))

    if debug:
        print(f"Blue star row {width} px wide -> {stars} stars")

    return stars


def count_stars(crop_img):
    """
    Counts stars by detecting connected yellow/blue blobs.
    Works well even if the stars are pixelated or slightly different shapes.
    """
    if crop_img is None or crop_img.size == 0:
        return 0

    # Convert to grayscale
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)

    # Threshold to make it a pure black and white mask
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)

    # This removes tiny single-pixel specks that aren't actually stars
    kernel = np.ones((2, 2), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    # RETR_EXTERNAL only gets the outer shapes
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    star_count = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)

        # Ignore anything too small (noise) or too large (UI artifacts)
        if 5 < area < 500:
            star_count += 1

    return star_count
