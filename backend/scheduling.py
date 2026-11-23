"""Server timezone handling for playlist refresh schedules."""

import os
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tzlocal import get_localzone


def get_server_timezone() -> tzinfo:
    """Return the TZ environment setting, or the server's local timezone."""
    timezone_name = os.getenv("TZ", "").strip()
    if not timezone_name:
        return get_localzone()

    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"Invalid TZ setting: {timezone_name!r}. "
            "Use an IANA timezone such as America/New_York or Australia/Melbourne."
        ) from exc


def server_now() -> datetime:
    """Return server wall time for the existing timezone-naive schedule records."""
    return datetime.now(get_server_timezone()).replace(tzinfo=None)
