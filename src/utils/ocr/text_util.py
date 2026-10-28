import re

import Levenshtein


# ? Note: we leave this for some uses idk where/when
def is_close_to(text: str, target: str = "MAX", threshold: float = 0.8) -> bool:
    """
    Compares the given text to the target string (default "MAX")
    using the Levenshtein ratio. Returns True if the similarity is
    greater than or equal to the threshold, else False.

    Parameters:
      text: The string to compare.
      target: The reference string, default is "MAX".
      threshold: A float between 0 and 1 representing the minimum
                 similarity ratio required.

    Returns:
      bool: True if text is considered close to target, False otherwise.
    """
    normalized_text = text.strip().upper()

    # print("\n")
    similarity = Levenshtein.ratio(normalized_text, target)

    # For debugging
    # print(f"Similarity: {similarity:.2f}")

    return similarity >= threshold


def normalize_skill_value(value, max_level: int):
    """
    Convert a skill value to its numeric representation.
    Handles "MAX" (case-insensitive) and formats like "Lv.7".

    Args:
        value: The extracted skill value (could be a string like "MAX" or a numeric string).
        max_level: The maximum level for the skill slot or something can be indicated as MAX (e.g., 5 for EX skill, 10 for other skills).

    Returns:
        The normalized value.
    """
    if isinstance(value, str) and value.strip().upper() == "MAX":
        return max_level
    # Fallback to level_value to handle "Lv.X", plain numbers, etc.
    return level_value(value)


def level_value(value, default=0):
    """
    The N of a "Lv.N" read: its last group of digits, so an "L" OCR'd as 1 can't
    turn "Lv.50" into 150 ("1v.50." -> 50). Spaces inside a group are OCR gaps.
    """
    groups = re.findall(r"\d(?:[\d\s]*\d)?", str(value)) if value is not None else []
    return int(re.sub(r"\s", "", groups[-1])) if groups else default


def normalize_value(value, default=0):
    """
    Remove non-digit characters from a value and convert it to an int.
    Automatically handles strings like "Lv.7", "LV. 8", "T9", or plain "81".

    Args:
        value: The value as extracted (e.g., "T9" or "9").
        default: The default value to return if conversion fails.

    Returns:
        int: The numeric value.
    """
    if value is None:
        return default

    try:
        val_str = str(value).strip()
        # \D matches ANY non-digit character. Removing it leaves only numbers.
        numeric_str = re.sub(r"\D", "", val_str)
        return int(numeric_str) if numeric_str else default

    except (ValueError, TypeError):
        return default


# Letters OCR reads instead of a tier digit
TIER_LOOKALIKES = str.maketrans(
    {"B": "3", "O": "0", "o": "0", "S": "5", "l": "1", "I": "1"}
)


def get_tier_level(text: str) -> str | None:
    """
    Gear tier "1".."10" from an OCR read of its "Tn" label, None if it is not one.
    OCR may read the T as 7 or 1 ("T9" -> "79", "T10" -> "110") or drop it.
    """
    if (text or "").strip() in ("π", "刀"):  # How RapidOCR merges "T7" at 720p
        return "7"
    text = re.sub(r"[^0-9A-Za-z]", "", text or "")  # Spaces, brackets, dots
    has_t = text[:1] in ("T", "t")
    digits = text[1:] if has_t else text
    digits = digits.translate(TIER_LOOKALIKES)
    if not re.fullmatch(r"[0-9]+", digits):
        return None

    candidates = [digits]
    if not has_t and digits[0] in "71":
        candidates.append(digits[1:])  # The T read as a digit
    for tier in candidates:
        if tier and tier[0] != "0" and 1 <= int(tier) <= 10:
            return tier
    return None
