"""Per-listing local time. Every listing stores an IANA timezone; 'now' is evaluated in it."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

from . import settings

COMMON_TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix", "America/Anchorage",
    "Pacific/Honolulu", "America/Toronto", "America/Vancouver", "America/Mexico_City", "America/Sao_Paulo", "America/Bogota",
    "America/Argentina/Buenos_Aires", "Europe/London", "Europe/Dublin", "Europe/Lisbon", "Europe/Paris", "Europe/Berlin",
    "Europe/Madrid", "Europe/Rome", "Europe/Amsterdam", "Europe/Zurich", "Europe/Stockholm", "Europe/Warsaw", "Europe/Athens",
    "Europe/Istanbul", "Europe/Moscow", "Africa/Cairo", "Africa/Lagos", "Africa/Johannesburg", "Africa/Nairobi", "Asia/Dubai",
    "Asia/Karachi", "Asia/Kolkata", "Asia/Dhaka", "Asia/Bangkok", "Asia/Jakarta", "Asia/Singapore", "Asia/Kuala_Lumpur",
    "Asia/Manila", "Asia/Hong_Kong", "Asia/Shanghai", "Asia/Taipei", "Asia/Seoul", "Asia/Tokyo", "Australia/Perth",
    "Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane", "Pacific/Auckland", "UTC",
]
_ALL = available_timezones()


def valid(tz: str) -> bool:
    return tz in _ALL


def local_now(tz: str | None) -> datetime:
    """Naive wall-clock 'now' in the given zone, so it compares with stored naive listing times."""
    zone = tz if tz and valid(tz) else settings.DEFAULT_TZ
    return datetime.now(ZoneInfo(zone)).replace(tzinfo=None, second=0, microsecond=0)
