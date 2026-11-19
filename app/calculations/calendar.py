import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import astronomy
from lunar_python import Solar

CALENDAR_ZONE = timezone(timedelta(hours=8))


def solar(value: datetime):
    return Solar.fromYmdHms(value.year, value.month, value.day, value.hour, value.minute, value.second)


def resolve_instant(wall: datetime, zone_name: str, *, unknown_hour: bool = False) -> datetime:
    zone = ZoneInfo(zone_name)
    candidates = sorted({wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                         for fold in (0, 1)
                         if wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                         .astimezone(zone).replace(tzinfo=None) == wall})
    if len(candidates) == 1:
        return candidates[0]
    if unknown_hour:
        if candidates:
            return candidates[0]
        # Match upstream compatible policy for synthetic unknown-hour endpoints.
        return max(wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc) for fold in (0, 1))
    raise ValueError("Ambiguous or nonexistent birth time in the supplied timezone")


def true_solar_time(instant: datetime, zone_name: str, longitude: float) -> tuple[datetime, dict]:
    clock = instant.astimezone(ZoneInfo(zone_name))
    time = astronomy.Time.Make(instant.year, instant.month, instant.day,
                               instant.hour, instant.minute, instant.second)
    equator = astronomy.EquatorFromVector(astronomy.RotateVector(
        astronomy.Rotation_EQJ_EQD(time), astronomy.GeoVector(astronomy.Body.Sun, time, True)))
    apparent = (astronomy.SiderealTime(time) - equator.ra + 12) * 60
    mean = instant.hour * 60 + instant.minute + instant.second / 60
    equation = (apparent - mean + 2160) % 1440 - 720
    offset = clock.utcoffset().total_seconds() / 60
    correction = longitude * 4 - offset + equation
    local = clock.replace(tzinfo=None)
    corrected = local + timedelta(minutes=math.floor(correction + 0.5))
    return corrected, {"clockTime": local.strftime('%H:%M'), "trueSolarTime": corrected.strftime('%H:%M'),
                       "longitude": longitude, "correctionMinutes": round(correction, 1),
                       "equationOfTimeMinutes": round(equation, 3), "timezone": zone_name,
                       "utcOffsetMinutes": offset, "dayOffset": (corrected.date()-local.date()).days}
