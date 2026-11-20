"""Rotate within the product's ten-color palette by recommended element."""
from datetime import date
from app.models import Color

PALETTES = {
    "wood": (("Green", "#228B22"),),
    "fire": (("Red", "#C62828"), ("Purple", "#7B1FA2"),
             ("Orange", "#FF9800"), ("Pink", "#E91E63")),
    "earth": (("Yellow", "#FBC02D"), ("Brown", "#795548")),
    "metal": (("Gold", "#D4AF37"), ("Silver", "#C0C0C0")),
    "water": (("Blue", "#1565C0"),),
}


def generate(context: dict) -> Color:
    """Return a date-selected color name and hex value from the element's palette."""
    palette = PALETTES[context["daily_reading"]["element"]]
    name, hex_value = palette[date.fromisoformat(context["date"]).toordinal() % len(palette)]
    return Color(name=name, hex=hex_value)
