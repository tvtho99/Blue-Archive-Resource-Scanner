"""OCR helpers that don't need the OCR engine: gear tiers, UE stars, white text."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from locations.search import StudentSearchPattern
from src.enums.ExtractionMode import ExtractionMode
from src.utils.ocr.extract import extract_from_region
from src.utils.ocr.preprocessor import preprocess_image_for_ocr
from src.utils.ocr.text_util import get_tier_level, level_value, normalize_skill_value

STAR_DIR = Path(__file__).resolve().parents[1] / "assets" / "images" / "star"
UE_STARS = StudentSearchPattern.UNIQUE_EQUIPMENT_STAR_QUANTITY.value
NAVY, LIGHT, WHITE = (70, 45, 30), (235, 235, 235), (255, 255, 255)


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("Lv.50", 50),
        ("LV. 81", 81),
        ("81", 81),
        ("1v.50", 50),  # The L read as 1 must not make it 150
        ("1v.50.", 50),  # Also with a trailing dot
        ("Lv.1 0", 10),  # A space inside the number
        ("Lv.5O", 5),  # No trailing digits: same as before
        ("", 0),
        (None, 0),
        (1, 1),  # The default when the read is missing
    ],
)
def test_level_value(text, level):
    assert level_value(text) == level


def test_skill_level_ignores_an_l_read_as_1():
    assert normalize_skill_value("1v.7", 10) == 7
    assert normalize_skill_value("MAX", 5) == 5


@pytest.mark.parametrize(
    ("text", "tier"),
    [
        ("T1", "1"),
        ("T9", "9"),
        ("T10", "10"),
        ("(T8)", "8"),
        ("T 7", "7"),
        ("T9.", "9"),
        ("7", "7"),  # T not read at all
        ("10", "10"),
        # T read as 7 or 1
        ("77", "7"),
        ("79", "9"),
        ("17", "7"),
        ("12", "2"),
        ("72", "2"),
        ("110", "10"),
        ("710", "10"),
        # Letters for digits, only when that gives a tier
        ("B", "3"),
        ("TB", "3"),
        ("1O", "10"),
        ("T1O", "10"),
        ("S", "5"),
        ("Tl", "1"),
        ("TI", "1"),
        # Not a tier
        ("", None),
        ("T", None),
        ("T0", None),
        ("0", None),
        ("T11", None),
        ("99", None),
        ("123", None),
        ("Lv.7", None),
        ("π", "7"),  # T7 merged into one glyph
        ("刀", "7"),
    ],
)
def test_get_tier_level(text, tier):
    assert get_tier_level(text) == tier


def ue_frame(stars, bg, x_offset):
    """1280x720 frame with the repo's n-star UE crop drawn into the UE region."""
    frame = np.empty((720, 1280, 3), np.float32)
    frame[:] = bg
    if stars:
        path = STAR_DIR / f"{stars}_blue_star.png"
        crop = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        h, w = crop.shape[:2]
        x, y = UE_STARS.x + x_offset, UE_STARS.y
        alpha = crop[:, :, 3:] / 255
        frame[y : y + h, x : x + w] = (
            crop[:, :, :3] * alpha + frame[y : y + h, x : x + w] * (1 - alpha)
        )
    return np.round(frame).astype(np.uint8)


def as_scanned(frame):
    """
    The frame natively, sub-pixel shifted, and scaled up then back down to
    1280x720 with INTER_AREA as the desktop capture does.
    """
    yield "native", frame
    for dx, dy in ((0.5, 0.5), (0.25, 0.75)):
        shift = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(
            frame, shift, (1280, 720), borderMode=cv2.BORDER_REPLICATE
        )
        yield f"shift {dx},{dy}", shifted
    for scale, interpolation in (
        (2, cv2.INTER_CUBIC),
        (2, cv2.INTER_LINEAR),
        (1.5, cv2.INTER_CUBIC),
        (1.25, cv2.INTER_LINEAR),
        (1366 / 1280, cv2.INTER_CUBIC),
    ):
        size = (round(1280 * scale), round(720 * scale))
        big = cv2.resize(frame, size, interpolation=interpolation)
        small = cv2.resize(big, (1280, 720), interpolation=cv2.INTER_AREA)
        yield f"x{scale:.2f}/{interpolation}", small


@pytest.mark.parametrize("bg", [NAVY, LIGHT])
@pytest.mark.parametrize("stars", [1, 2, 3, 4])
def test_ue_star_count_survives_resampling(stars, bg):
    # The 1-3 star crops are 60 px wide, so they fit the 93 px region at two spots
    for x_offset in (0, 30) if stars < 4 else (0,):
        for label, frame in as_scanned(ue_frame(stars, bg, x_offset)):
            got = extract_from_region(frame, UE_STARS, mode=ExtractionMode.UE_STAR)
            assert got == stars, (label, x_offset)


@pytest.mark.parametrize("bg", [NAVY, LIGHT, WHITE])
def test_no_ue_stars_count_zero(bg):
    frame = ue_frame(0, bg, 0)
    assert extract_from_region(frame, UE_STARS, mode=ExtractionMode.UE_STAR) == 0


@pytest.mark.parametrize(
    ("mode", "faint_is_text"),
    [(ExtractionMode.NAME, False), (ExtractionMode.UE_LEVEL, True)],
)
def test_white_text_keeps_near_white_strokes(mode, faint_is_text):
    # Scaling a bigger game picture to 1280x720 leaves white text below 255
    crop = np.full((40, 150, 3), 40, np.uint8)
    crop[10:30, 10:20] = 255  # A stroke that stayed pure white
    crop[10:30, 40:50] = 240  # A blended one
    crop[10:30, 70:80] = (255, 245, 238)  # A slightly tinted one
    crop[10:30, 100:110] = 228  # Faint: small UE level text, or bright art by a name
    crop[10:30, 130:140] = 205  # Light background, never text

    binary = preprocess_image_for_ocr(crop, mode)
    assert binary.shape == (80, 300)  # Small crops are doubled
    ink = [binary[20:60, 2 * x : 2 * x + 20].mean() > 200 for x in range(10, 150, 30)]
    assert ink == [True, True, True, faint_is_text, False]
