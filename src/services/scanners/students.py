import concurrent.futures
import logging
import time

import numpy as np
from rich.markup import escape

from locations import screens
from locations.search import StudentSearchPattern
from src.core.config import Config
from src.enums.ExtractionMode import ExtractionMode
from src.services.workers import student_ocr_worker
from src.utils.data.io import write_json
from src.utils.data.student_skill_helper import map_student_data_to_character
from src.utils.device.interfaces import DeviceController
from src.utils.ocr.extract import extract_from_region

logger = logging.getLogger("BA-Scanner")

# ponytail: hard cap so a first name that never OCRs the same again can't loop
# forever (~2.7 MB per screenshot); raise it once the roster gets near
MAX_STUDENTS = 400
# A page still showing the last name gets this many more captures, 0.5 s apart,
# before NEXT is tapped again (a second tap on a late page would skip a student)
RECAPTURES = 4
# Pages in a row whose name can't be read: something covers the game (a popup)
MAX_UNREADABLE = 3


def get_student_info(
    device: DeviceController,
    ocr_workers: int = 2,
) -> bool:
    """
    Capture every student page, tapping NEXT until the first student comes
    round again, then OCR and save them. True only if the results were written.

    Raises:
        RuntimeError: A capture failed or NEXT did not change the page
        (the previous results are kept).
    """
    first_name = None
    captured_images: list[np.ndarray] = []
    unreadable = 0
    image, current_name = _capture_page(device)

    while True:
        unreadable = 0 if current_name else unreadable + 1
        if unreadable >= MAX_UNREADABLE:
            # Else a popup would get NEXT tapped blindly up to MAX_STUDENTS times
            raise RuntimeError(
                f"Student name unreadable on {unreadable} pages in a row, "
                "previous results kept."
            )

        if not first_name:
            # An empty read can never match, so the first readable name marks the loop
            first_name = current_name
            logger.info(
                f"[bold]First student name[/bold] set to: [cyan]{first_name}[/cyan]"
            )

        elif current_name == first_name:
            # Pages only count once NEXT changed the name, so this is a real wrap
            logger.info("Encountered the first student again. Ending capture loop.")
            break

        captured_images.append(image)
        if len(captured_images) >= MAX_STUDENTS:
            logger.warning(
                f"Captured {MAX_STUDENTS} students without meeting "
                f"{first_name!r} again. Ending capture loop."
            )
            break

        image, current_name = _next_page(device, current_name)

    results = process_ocr_results(captured_images, ocr_workers)
    if not results:
        logger.error("OCR could not read any student name.")
        return False

    logger.info(
        f"[bold yellow]Extracted[/bold yellow] {len(results)} student records. Formatting & saving..."
    )

    final_data = {"characters": to_characters(results)}

    write_json(Config.scanned_students, final_data)
    logger.info(
        f"[bold yellow]Saved[/bold yellow] "
        f"{len(final_data['characters'])} students → \n"
        f":open_file_folder: [link {Config.scanned_students}]"
        f"{escape(str(Config.scanned_students.as_uri()))}"
    )
    return True


def to_characters(results: list[dict]) -> list[dict]:
    """OCR results as scanned_students.json "characters", one per name."""
    characters = []
    seen_names = set()

    for r in results:
        name, current_data = map_student_data_to_character(r)
        if name in seen_names:
            # Same unreadable page captured twice, or two students read alike
            logger.warning(f"Dropped a second page read as {escape(name)}.")
            continue
        seen_names.add(name)
        characters.append({"name": name, "current": current_data})
    return characters


def _capture_page(device: DeviceController) -> tuple[np.ndarray, str]:
    """A screenshot and the student name on it ("" if unreadable)."""
    image = device.capture_screenshot()
    if image is None:
        raise RuntimeError("Failed to capture a student page, previous results kept.")

    # Lightweight name check ONLY for loop control
    name = extract_from_region(
        image, StudentSearchPattern.STUDENT_NAME.value, mode=ExtractionMode.NAME
    )
    return image, name or ""


def _next_page(device: DeviceController, name: str) -> tuple[np.ndarray, str]:
    """
    Tap NEXT and return the next page once its name differs from `name`.
    A late page is re-captured first, NEXT is tapped again only if it never came.
    """
    next_button = screens.StudentInfo.BUTTONS.NEXT
    for attempt in range(2):
        if attempt:
            logger.warning(f"Still on {escape(name)} after NEXT, tapping it again.")
        device.tap(int(next_button.x), int(next_button.y))

        for _ in range(1 + RECAPTURES):
            time.sleep(0.5 * Config.WAIT_TIME_MULTIPLIER)
            image, new_name = _capture_page(device)
            if new_name and new_name != name:
                return image, new_name

        if not new_name or not name:
            # Can't tell whether the page changed: keep it rather than risk
            # skipping a student with a second tap (the caller counts these)
            return image, new_name

    raise RuntimeError(
        f"NEXT never changed the page from {name} (a one-student roster or list "
        "filter? clear it), previous results kept."
    )


def process_ocr_results(captured_images: list, ocr_workers: int) -> list[dict]:
    if not captured_images:
        logger.warning("⚠️ No students captured.")
        return []

    logger.info(
        f"[bold yellow]Processing[/bold yellow] {len(captured_images)} screenshots with {ocr_workers} OCR workers..."
    )

    results = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=ocr_workers)
    try:
        futures = [executor.submit(student_ocr_worker, p) for p in captured_images]
        for page, future in enumerate(futures, 1):  # Capture order, so roster order survives
            try:
                data = future.result()
            except Exception as e:  # noqa: BLE001
                logger.error(f"OCR worker failed: {e}")
                continue
            if data and data.get("Name"):
                results.append(data)
            else:
                logger.warning(f"Dropped student page {page}: its name could not be read.")
    except BaseException:
        # A Ctrl+C/F2 must not wait for every queued page to be OCR'd
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    executor.shutdown()

    return results
