"""Regression coverage for issue #62's failing This Is error handlers."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from backend import main
from backend.ai_client import AIClient
from backend.database import DatabaseManager
from backend.schemas import CreatePlaylistRequest


class ThisIsFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tracks = [
            {"id": "low", "title": "Low", "artist": "King Gizzard", "album": "A", "play_count": 1},
            {"id": "high", "title": "High", "artist": "King Gizzard", "album": "B", "play_count": 20},
            {"id": "middle", "title": "Middle", "artist": "King Gizzard", "album": "C", "play_count": 5},
        ]
        self.provider = SimpleNamespace(
            provider_type="groq", api_key="test-key", model="test-model",
            base_url="https://example.invalid", generate=AsyncMock(),
        )
        factory = patch("backend.ai_client.get_ai_provider", return_value=self.provider)
        factory.start()
        self.addCleanup(factory.stop)
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        shuffle = patch("random.shuffle")
        shuffle.start()
        self.addCleanup(shuffle.stop)
        self.client = AIClient()

    async def curate(self, include_reasoning=True, num_tracks=2):
        return await self.client.curate_this_is(
            "King Gizzard and the Lizard Wizard", self.tracks, num_tracks,
            include_reasoning=include_reasoning,
        )

    async def test_invalid_responses_fall_back_to_most_played_tracks(self):
        original = deepcopy(self.tracks)
        for response in ("not JSON", "", '{"track_ids": "bad"}', '{"track_ids": []}'):
            for include_reasoning in (True, False):
                with self.subTest(response=response, reasoning=include_reasoning):
                    self.provider.generate.return_value = response
                    result = await self.curate(include_reasoning)
                    ids = result[0] if include_reasoning else result
                    self.assertEqual(ids, ["high", "middle"])
                    if include_reasoning:
                        self.assertIn("AI response validation failed", result[1])
                        self.assertIn("play count", result[1])
        self.assertEqual(self.tracks, original)

    async def test_network_and_provider_errors_preserve_original_cause(self):
        request = httpx.Request("POST", "https://example.invalid")
        errors = (
            (httpx.ConnectError("connection failed", request=request), "Network error"),
            (httpx.ReadTimeout("timed out", request=request), "Network error"),
            (RuntimeError("provider failed"), "provider failed"),
        )
        for error, expected in errors:
            with self.subTest(error=type(error).__name__):
                self.provider.generate.side_effect = error
                ids, reason = await self.curate()
                self.assertEqual(ids, ["high", "middle"])
                self.assertIn(expected, reason)

    async def test_http_error_branches_return_fallback_instead_of_name_error(self):
        for code, body in ((429, "quota exhausted"), (502, "<html>upstream unavailable</html>")):
            with self.subTest(status=code):
                response = httpx.Response(code, text=body, request=httpx.Request("POST", "https://example.invalid"))
                self.provider.generate.side_effect = httpx.HTTPStatusError(
                    "provider rejected request", request=response.request, response=response
                )
                ids, reason = await self.curate()
                self.assertEqual(ids, ["high", "middle"])
                self.assertIn(str(code), reason)

    async def test_successful_ai_selection_keeps_its_order_and_reasoning(self):
        self.provider.generate.return_value = '{"track_ids": [0, 2], "reasoning": "AI selection"}'
        self.assertEqual(await self.curate(), (["low", "middle"], "AI selection"))

    async def test_keyless_openrouter_still_works_without_calling_ai(self):
        self.provider.provider_type = "openrouter"
        self.provider.api_key = None
        self.client.api_key = None
        ids, reason = await self.curate()
        self.assertEqual(ids, ["high", "middle"])
        self.assertIn("No AI API key", reason)
        self.provider.generate.assert_not_awaited()

    async def test_short_libraries_return_only_available_tracks(self):
        self.provider.generate.return_value = "invalid JSON"
        ids, _ = await self.curate(num_tracks=25)
        self.assertEqual(ids, ["high", "middle", "low"])

    async def test_create_playlist_succeeds_when_ai_response_is_invalid(self):
        self.provider.generate.return_value = "invalid JSON"
        nav = SimpleNamespace(
            get_artists=AsyncMock(return_value=[{"id": "artist", "name": "King Gizzard"}]),
            get_tracks_by_artist=AsyncMock(return_value=self.tracks),
            get_library_stats=AsyncMock(return_value={}),
            create_playlist=AsyncMock(return_value="mock-playlist"),
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(
            main, "get_navidrome_client", return_value=nav
        ), patch.object(main, "get_ai_client", return_value=self.client):
            db = DatabaseManager(str(Path(directory) / "playlists.db"))
            result = await main.create_playlist(
                CreatePlaylistRequest(artist_ids=["artist"], playlist_length=2), db
            )
            self.assertEqual(result["songs"], ["High", "Middle"])
            self.assertEqual(result["navidrome_playlist_id"], "mock-playlist")
            self.assertIn("Fallback curation", result["reasoning"])
            self.assertEqual(nav.create_playlist.call_args.kwargs["track_ids"], ["high", "middle"])


if __name__ == "__main__":
    unittest.main()
