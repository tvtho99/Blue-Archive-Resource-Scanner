from collections.abc import Iterable
from typing import Any

from rapidfuzz import fuzz, process


def find_closest(
    query: str, choices: Iterable[str], threshold: float = 0.8
) -> str | None:
    """Return the closest match or None if below threshold."""
    if not query or not choices:
        return None
    match = process.extractOne(
        query, choices, scorer=fuzz.ratio, score_cutoff=threshold * 100
    )
    return match[0] if match else None


def match_scanned(
    scanned: dict[str, Any], names: Iterable[str], threshold: float = 0.8
) -> dict[str, Any]:
    """
    Map known names to scanned (OCR) values. Each scanned name goes to its one
    closest known name, so a known item that was not scanned stays unmatched
    instead of borrowing the value of a similarly named one.
    When several scanned names land on the same known name, the closest wins.
    """
    choices = list(dict.fromkeys(names))
    best: dict[str, tuple[float, Any]] = {}
    for scanned_name, value in scanned.items():
        if not scanned_name:
            continue
        match = process.extractOne(
            scanned_name, choices, scorer=fuzz.ratio, score_cutoff=threshold * 100
        )
        if match and match[1] > best.get(match[0], (-1.0, None))[0]:
            best[match[0]] = (match[1], value)
    return {name: value for name, (_, value) in best.items()}
