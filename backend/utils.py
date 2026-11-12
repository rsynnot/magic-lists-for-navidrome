"""
Utility functions for the application
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_next_refresh(frequency: str) -> datetime:
    """Calculate the next refresh time based on frequency"""
    now = datetime.now()

    # The cron runs at 1:01 AM and 1:01 PM local time
    # We need to find the next occurrence of these times

    def next_cron_time():
        """Find the next 1:01 AM or 1:01 PM"""
        # Today at 1:01 AM
        today_1am = now.replace(hour=1, minute=1, second=0, microsecond=0)
        # Today at 1:01 PM
        today_1pm = now.replace(hour=13, minute=1, second=0, microsecond=0)

        if now < today_1am:
            return today_1am
        elif now < today_1pm:
            return today_1pm
        else:
            # Next occurrence is tomorrow at 1:01 AM
            return today_1am + timedelta(days=1)

    if frequency == "daily":
        # Next day at 1:00 AM (daily refresh)
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "weekly":
        # Next Monday at 1:00 AM
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0:
            # It's Monday, check if we've passed 1:00 AM
            monday_1am = now.replace(hour=1, minute=0, second=0, microsecond=0)
            if now >= monday_1am:
                days_until_monday = 7  # Next Monday
        next_monday = now + timedelta(days=days_until_monday)
        return next_monday.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "monthly":
        # 1st of next month at 1:00 AM
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=1, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=1, minute=0, second=0, microsecond=0)
        return next_month
    else:
        return now  # Fallback