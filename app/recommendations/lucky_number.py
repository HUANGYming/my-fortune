from datetime import date

NUMBERS = {"water": (1, 6), "fire": (2, 7), "wood": (3, 8), "metal": (4, 9), "earth": (5, 0)}


def generate(context: dict) -> int:
    pair = NUMBERS[context["daily_reading"]["element"]]
    return pair[date.fromisoformat(context["date"]).toordinal() % 2]
