"""Map the recommended element to a daily number without an LLM call."""
from datetime import date

# Earth uses 0 as this product's single-digit representation of 10.
NUMBERS = {"water": (1, 6), "fire": (2, 7), "wood": (3, 8), "metal": (4, 9), "earth": (5, 0)}


def generate(context: dict) -> int:
    """Alternate between the element's two numbers using the target date."""
    pair = NUMBERS[context["daily_reading"]["element"]]
    return pair[date.fromisoformat(context["date"]).toordinal() % 2]
