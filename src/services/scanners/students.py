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


def get_student_info(
    device: DeviceController,
    ocr_workers: int = 2,
) -> bool:
    first_name = None
    iteration = 0
    captured_images: list[np.ndarray] = []

    while True:
        iteration += 1
        image = device.capture_screenshot()
        if image is None:
            logger.error("Failed to capture screenshot.")
            return False

        # Lightweight name check ONLY for loop termination
        current_name = extract_from_region(
            image, StudentSearchPattern.STUDENT_NAME.value, mode=ExtractionMode.NAME
        )

        if not first_name:
            # An empty read can never match, so the first readable name marks the loop
            first_name = current_name
            logger.info(
                f"[bold]First student name[/bold] set to: [cyan]{first_name}[/cyan]"
            )

        elif current_name == first_name:
            logger.info("Encountered the first student again. Ending capture loop.")
            break

        captured_images.append(image)
        if len(captured_images) >= MAX_STUDENTS:
            logger.warning(
                f"Captured {MAX_STUDENTS} students without meeting "
                f"{first_name!r} again. Ending capture loop."
            )
            break

        # Tap Next
        device.tap(
            int(screens.StudentInfo.BUTTONS.NEXT.x),
            int(screens.StudentInfo.BUTTONS.NEXT.y),
        )
        time.sleep(0.5 * Config.WAIT_TIME_MULTIPLIER)

        if Config.DEBUG and iteration >= 2:
            break

    results = process_ocr_results(captured_images, ocr_workers)
    if not results:
        logger.error("OCR could not read any student name.")
        return False

    logger.info(
        f"[bold yellow]Extracted[/bold yellow] {len(results)} student records. Formatting & saving..."
    )

    final_data = {"characters": []}
    seen_names = set()

    for r in results:
        name, current_data = map_student_data_to_character(r)
        if name in seen_names:
            # Same page captured twice (a missed NEXT tap) or an empty first read
            continue
        seen_names.add(name)
        final_data["characters"].append({"name": name, "current": current_data})

    write_json(Config.scanned_students, final_data)
    logger.info(
        f"[bold yellow]Saved[/bold yellow] "
        f"{len(final_data['characters'])} students → \n"
        f":open_file_folder: [link {Config.scanned_students}]"
        f"{escape(str(Config.scanned_students.as_uri()))}"
    )
    return True


def process_ocr_results(captured_images: list, ocr_workers: int) -> list[dict]:
    if not captured_images:
        logger.warning("⚠️ No students captured.")
        return []

    logger.info(
        f"[bold yellow]Processing[/bold yellow] {len(captured_images)} screenshots with {ocr_workers} OCR workers..."
    )

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=ocr_workers) as executor:
        futures = [executor.submit(student_ocr_worker, p) for p in captured_images]
        for future in futures:  # Capture order, so roster order survives
            try:
                data = future.result()
            except Exception as e:  # noqa: BLE001
                logger.error(f"OCR worker failed: {e}")
                continue
            if data and data.get("Name"):
                results.append(data)

    return results
