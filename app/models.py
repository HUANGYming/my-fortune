from datetime import date, datetime
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Zodiac(str, Enum):
    RAT = "Rat"
    OX = "Ox"
    TIGER = "Tiger"
    RABBIT = "Rabbit"
    DRAGON = "Dragon"
    SNAKE = "Snake"
    HORSE = "Horse"
    GOAT = "Goat"
    MONKEY = "Monkey"
    ROOSTER = "Rooster"
    DOG = "Dog"
    PIG = "Pig"


class Patron(StrictModel):
    patron_id: str
    birth_date: date | None = None
    birth_hour: int | None = Field(default=None, ge=0, le=23)
    gender: Literal["male", "female"] | None = None
    birth_minute: int | None = Field(default=None, ge=0, le=59)
    birth_timezone: str | None = None
    longitude: float | None = Field(default=None, ge=-180, le=180)



class CatalogEntry(StrictModel):
    id: str
    name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Color(StrictModel):
    name: str
    hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class Fortune(StrictModel):
    patron_id: str
    fortune_date: date
    lucky_zodiac: Zodiac
    lucky_number: int = Field(ge=0, le=9)
    lucky_color: Color
    lucky_item: CatalogEntry
    lucky_dining: CatalogEntry
    generated_at: datetime
    model: str
    prompt_version: str
    rules_version: str = "legacy-v1"
    personalization: str = "unknown"
