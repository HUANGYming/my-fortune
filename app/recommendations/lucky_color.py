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
    preferred = context["profile"]["preferences"].get("preferred_colors", [])
    matches = [color for color in palette if color[0].lower() in [value.lower() for value in preferred]]
    choices = matches or palette
    name, hex_value = choices[date.fromisoformat(context["date"]).toordinal() % len(choices)]
    return Color(name=name, hex=hex_value)
