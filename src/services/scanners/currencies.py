import logging
import re

from locations.search import SearchPattern
from src.core.config import Config
from src.enums.ExtractionMode import ExtractionMode
from src.utils.data.io import update_count
from src.utils.device.interfaces import DeviceController
from src.utils.ocr.extract import extract_from_region

logger = logging.getLogger("BA-Scanner")

AP_READ = re.compile(r"(\d+)\s*/\s*(\d+)")  # Remaining/Max
AMOUNT_READ = re.compile(r"\d+([.,]\d+)*")  # Thousand separators, OCR may read "," as "."


def get_currencies(device: DeviceController) -> bool:
    image = device.capture_screenshot()

    if image is None:
        return False

    currencies = [SearchPattern.AP, SearchPattern.CREDIT, SearchPattern.PYROXENE]
    owned_currencies_file = Config.scanned_currencies

    # Check all three before writing, a misread must not replace the last good values
    values, unreadable = {}, []
    for currency in currencies:
        how_many = (
            extract_from_region(image, currency.value, mode=ExtractionMode.NUMBER)
            or ""
        ).strip()
        logger.info(
            f"[bold yellow]Detected[/bold yellow] [bold]Currency[/bold] {currency.name}: [cyan]{how_many}[/cyan]"
        )

        if currency.name == "AP":
            AP = AP_READ.fullmatch(how_many)
            value = {"Remaining": AP[1], "Max": AP[2]} if AP else None
        else:
            value = how_many if AMOUNT_READ.fullmatch(how_many) else None

        if value is None:
            unreadable.append(currency.name)
        values[currency.name.title()] = value

    if unreadable:
        logger.error(
            f"[bold red]Error:[/bold red] Couldn't read {', '.join(unreadable)} "
            "on the lobby, the currencies were not saved."
        )
        return False

    for name, value in values.items():
        update_count(owned_currencies_file, name, value)

    return True
