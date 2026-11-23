"""Regression tests for server-level timezone scheduling."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend import main, scheduling
from backend.database import DatabaseManager


def clock_at(instant: str):
    """Freeze the clock at a UTC instant while retaining timezone conversion."""
    value = datetime.fromisoformat(instant)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return value.astimezone(tz)

    return patch.object(scheduling, "datetime", FrozenDatetime)


class ServerTimezoneTests(unittest.TestCase):
    def test_invalid_timezone_is_rejected(self):
        with patch.dict(os.environ, {"TZ": "Not/A_Timezone"}):
            with self.assertRaisesRegex(ValueError, "Invalid TZ setting"):
                scheduling.get_server_timezone()

    def test_unset_timezone_preserves_system_default(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
            scheduling, "get_localzone", return_value=ZoneInfo("Australia/Melbourne")
        ):
            self.assertEqual(str(scheduling.get_server_timezone()), "Australia/Melbourne")

    def test_server_clock_uses_tz_even_when_host_clock_differs(self):
        with patch.dict(os.environ, {"TZ": "America/New_York"}), clock_at(
            "2026-01-16T06:01:00+00:00"
        ):
            self.assertEqual(scheduling.server_now(), datetime(2026, 1, 16, 1, 1))
            self.assertIsNone(scheduling.server_now().tzinfo)

    def test_cron_stays_at_local_times_in_winter_and_summer(self):
        for zone in ("UTC", "America/New_York", "Australia/Melbourne", "Asia/Kathmandu"):
            for month in (1, 7):
                with self.subTest(zone=zone, month=month), patch.dict(os.environ, {"TZ": zone}):
                    tz = scheduling.get_server_timezone()
                    scheduler = AsyncIOScheduler(timezone=tz)
                    with patch.object(main, "scheduler", scheduler):
                        main.schedule_playlist_refresh()
                    trigger = scheduler.get_job("playlist_refresh").trigger
                    midnight = datetime(2026, month, 15, tzinfo=tz)
                    morning = trigger.get_next_fire_time(None, midnight)
                    afternoon = trigger.get_next_fire_time(morning, morning)
                    self.assertEqual((morning.hour, morning.minute), (1, 1))
                    self.assertEqual((afternoon.hour, afternoon.minute), (13, 1))
                    self.assertEqual(str(trigger.timezone), zone)

    def test_cron_adjusts_offset_across_dst_without_restart(self):
        for zone, before, after in (
            ("America/New_York", (2026, 3, 7), (2026, 3, 9)),
            ("America/New_York", (2026, 10, 31), (2026, 11, 2)),
            ("Australia/Melbourne", (2026, 4, 4), (2026, 4, 6)),
            ("Australia/Melbourne", (2026, 10, 3), (2026, 10, 5)),
        ):
            with self.subTest(zone=zone, before=before), patch.dict(os.environ, {"TZ": zone}):
                tz = scheduling.get_server_timezone()
                scheduler = AsyncIOScheduler(timezone=tz)
                with patch.object(main, "scheduler", scheduler):
                    main.schedule_playlist_refresh()
                trigger = scheduler.get_job("playlist_refresh").trigger
                first = trigger.get_next_fire_time(None, datetime(*before, tzinfo=tz))
                second = trigger.get_next_fire_time(None, datetime(*after, tzinfo=tz))
                self.assertEqual((first.hour, first.minute), (1, 1))
                self.assertEqual((second.hour, second.minute), (1, 1))
                self.assertNotEqual(first.utcoffset(), second.utcoffset())

    def test_all_refresh_frequencies_use_server_date(self):
        # UTC is already January 1; New York is still December 31.
        with patch.dict(os.environ, {"TZ": "America/New_York"}), clock_at(
            "2026-01-01T02:00:00+00:00"
        ):
            self.assertEqual(main.calculate_next_refresh("daily"), datetime(2026, 1, 1, 1))
            self.assertEqual(main.calculate_next_refresh("weekly"), datetime(2026, 1, 5, 1))
            self.assertEqual(main.calculate_next_refresh("monthly"), datetime(2026, 1, 1, 1))


class ServerTimezoneIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_uses_configured_timezone(self):
        health = type("Health", (), {"run_checks": AsyncMock(return_value={"checks": []})})()
        with patch.dict(os.environ, {"TZ": "America/New_York"}), patch.object(
            main, "HealthCheckService", return_value=health
        ), patch.object(main, "scheduler", None):
            await main.startup_event()
            try:
                self.assertEqual(str(main.scheduler.timezone), "America/New_York")
                job = main.scheduler.get_job("playlist_refresh")
                self.assertEqual(str(job.trigger.timezone), "America/New_York")
            finally:
                await main.shutdown_event()

    async def test_due_checks_and_repeated_refreshes_use_same_clock(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"TZ": "America/New_York"}
        ):
            db = DatabaseManager(str(Path(directory) / "schedules.db"))
            # Cross the spring DST change between successive daily refreshes.
            with clock_at("2026-03-07T17:00:00+00:00"):
                next_refresh = main.calculate_next_refresh("daily")
            row = await db.create_scheduled_playlist("this_is", "test-playlist", "daily", next_refresh)
            for utc_instant, expected_local_date in (
                ("2026-03-08T06:01:00+00:00", 8),
                ("2026-03-09T05:01:00+00:00", 9),
            ):
                with self.subTest(instant=utc_instant), clock_at(utc_instant):
                    refresh = AsyncMock()
                    with patch.object(main, "DatabaseManager", return_value=db), patch.object(
                        main, "refresh_this_is_playlist", refresh
                    ):
                        await main.refresh_scheduled_playlists()
                    refresh.assert_awaited_once()
                    self.assertEqual(scheduling.server_now().day, expected_local_date)
                    await db.update_scheduled_playlist_next_refresh(
                        row.id, main.calculate_next_refresh("daily")
                    )
                    self.assertEqual(await db.get_scheduled_playlists_due(scheduling.server_now()), [])


if __name__ == "__main__":
    unittest.main()
