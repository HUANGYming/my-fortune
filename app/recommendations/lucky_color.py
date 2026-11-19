from datetime import date
from app.models import Color

PALETTES = {
    "wood": (("Green", "#228B22"), ("Jade", "#00A86B")),
    "fire": (("Red", "#C62828"), ("Purple", "#7B1FA2")),
    "earth": (("Yellow", "#FBC02D"), ("Brown", "#795548")),
    "metal": (("Gold", "#D4AF37"), ("White", "#FFFFFF")),
    "water": (("Blue", "#1565C0"), ("Black", "#212121")),
}


def generate(context: dict) -> Color:
    palette = PALETTES[context["daily_reading"]["element"]]
    name, hex_value = palette[date.fromisoformat(context["date"]).toordinal() % len(palette)]
    return Color(name=name, hex=hex_value)
