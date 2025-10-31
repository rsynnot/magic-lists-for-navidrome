import httpx
import os
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
import json
import random
from .recipe_manager import recipe_manager


class RediscoverWeekly:
    """Handles the Re-Discover Weekly feature logic"""
    
    def __init__(self, navidrome_client):
        self.navidrome_client = navidrome_client
        
    async def get_listening_history(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch listening history from Navidrome for the last N days.
        Uses the getNowPlaying and getScrobbles endpoints if available,
        or falls back to play count data from songs.
        """
        try:
            await self.navidrome_client._ensure_authenticated()
            
            # Try to get scrobbles/listening history
            # Note: This depends on Navidrome version and available endpoints
            params = self.navidrome_client._get_subsonic_params()
            
            # Calculate date range
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days_back)
            
            # Try getScrobbles endpoint (may not be available in all versions)
            try:
                params_scrobbles = params.copy()
                params_scrobbles["count"] = "1000"  # Get up to 1000 recent plays
                
                response = await self.navidrome_client.client.get(
                    f"{self.navidrome_client.base_url}/rest/getScrobbles.view",
                    params=params_scrobbles
                )
                
                if response.status_code == 200:
                    data = response.json()
                    subsonic_response = data.get("subsonic-response", {})
                    if subsonic_response.get("status") == "ok":
                        scrobbles = subsonic_response.get("scrobbles", {}).get("scrobble", [])
                        if scrobbles:
                            # Filter scrobbles by date range
                            filtered_scrobbles = []
                            for scrobble in scrobbles:
                                # Parse the timestamp (format may vary)
                                play_time_str = scrobble.get("time", "")
                                try:
                                    # Try different timestamp formats
                                    if "T" in play_time_str:
                                        play_time = datetime.fromisoformat(play_time_str.replace("Z", "+00:00"))
                                    else:
                                        # Unix timestamp
                                        play_time = datetime.fromtimestamp(int(play_time_str) / 1000)
                                    
                                    if start_date <= play_time <= end_date:
                                        filtered_scrobbles.append({
                                            "song_id": scrobble.get("id"),
                                            "title": scrobble.get("title"),
                                            "artist": scrobble.get("artist"),
                                            "album": scrobble.get("album"),
                                            "played_at": play_time.isoformat()
                                        })
                                except (ValueError, TypeError):
                                    continue
                            
                            return filtered_scrobbles
            except:
                # Scrobbles endpoint not available, continue with fallback
                pass
            
            # Fallback: Get all songs and use play count as proxy for recent activity
            # This is less accurate but works when scrobbles aren't available
            return await self._get_fallback_history()
            
        except Exception as e:
            raise Exception(f"Failed to get listening history: {e}")
    
    async def _get_fallback_history(self) -> List[Dict[str, Any]]:
        """
        Fallback method: Get songs with play counts as a proxy for listening history.
        This isn't perfect but provides some data when scrobbles aren't available.
        """
        # Get all artists first
        artists = await self.navidrome_client.get_artists()
        
        history = []
        # Limit to top artists to avoid overwhelming API calls
        for artist in artists[:50]:  # Process top 50 artists
            try:
                tracks = await self.navidrome_client.get_tracks_by_artist(artist["id"], library_id)
                for track in tracks:
                    play_count = track.get("play_count", 0)
                    if play_count > 0:
                        # Create synthetic history entries based on play count
                        # Assume plays were distributed over the last 30 days
                        history.append({
                            "song_id": track["id"],
                            "title": track["title"],
                            "artist": artist["name"],
                            "album": track.get("album", ""),
                            "play_count": play_count,
                            "synthetic": True  # Flag to indicate this is estimated data
                        })
            except Exception:
                continue  # Skip artists that fail
        
        return history
    
    async def analyze_listening_patterns(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze listening history to find patterns and identify candidate tracks
        for re-discovery.
        """
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        # Track statistics
        track_stats = defaultdict(lambda: {
            "total_plays": 0,
            "recent_plays": 0,  # Last 7 days
            "last_play": None,
            "artist": "",
            "title": "",
            "album": ""
        })
        
        # Process history
        for entry in history:
            song_id = entry["song_id"]
            track_stats[song_id]["artist"] = entry["artist"]
            track_stats[song_id]["title"] = entry["title"]
            track_stats[song_id]["album"] = entry.get("album", "")
            
            if entry.get("synthetic"):
                # Handle synthetic data from fallback method
                track_stats[song_id]["total_plays"] = entry.get("play_count", 0)
                # Assume no recent plays for synthetic data (conservative approach)
                track_stats[song_id]["recent_plays"] = 0
            else:
                # Real scrobble data
                track_stats[song_id]["total_plays"] += 1
                
                # Parse play time
                try:
                    play_time = datetime.fromisoformat(entry["played_at"].replace("Z", "+00:00"))
                    if not track_stats[song_id]["last_play"] or play_time > track_stats[song_id]["last_play"]:
                        track_stats[song_id]["last_play"] = play_time
                    
                    if play_time >= week_ago:
                        track_stats[song_id]["recent_plays"] += 1
                except:
                    continue
        
        return dict(track_stats)
    
    def score_tracks_for_rediscovery(self, track_stats: Dict[str, Any], min_gap_days: int = 7, max_per_artist: int = 3) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Score tracks for re-discovery based on:
        - Historical play count (higher = better)
        - Time since last play (longer = better)
        - No recent plays (configurable via min_gap_days)

        Args:
            track_stats: Dictionary of track statistics
            min_gap_days: Minimum days since last play to consider (default: 7)
            max_per_artist: Maximum tracks per artist (not used in scoring, but kept for API compatibility)
        """
        candidates = []
        now = datetime.now(timezone.utc)

        for song_id, stats in track_stats.items():
            # Only consider tracks with some historical plays (reduced threshold)
            if stats["total_plays"] < 1:
                continue

            # Skip tracks played recently (based on min_gap_days)
            if stats["recent_plays"] > 0:
                continue

            # Calculate days since last play
            days_since_last_play = min_gap_days  # Minimum for synthetic data
            if stats["last_play"]:
                days_since_last_play = (now - stats["last_play"]).days

            # Only consider tracks not played in the minimum gap period
            if days_since_last_play < min_gap_days:
                continue

            # Score: (historical play count) × (days since last play)
            # This favors both popular tracks and tracks that haven't been heard recently
            score = stats["total_plays"] * min(days_since_last_play, 90)  # Cap at 90 days

            candidates.append((song_id, score, stats))

        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates
    
    def _generate_analysis_summary(self, track_stats: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
        """Generate analysis summary for the user's listening patterns"""
        try:
            # Count plays by genre and artist in last 90 days
            genre_counts = {}
            artist_counts = {}
            
            for entry in history:
                genre = entry.get("genre", "Unknown")
                artist = entry.get("artist", "Unknown")
                
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
                artist_counts[artist] = artist_counts.get(artist, 0) + 1
            
            # Get top 5 genres and artists
            top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            top_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Format summary
            genre_list = ", ".join([genre for genre, _ in top_genres if genre != "Unknown"])
            artist_list = ", ".join([artist for artist, _ in top_artists if artist != "Unknown"])
            
            summary = f"Top Genres: {genre_list or 'Mixed'}. Top Artists: {artist_list or 'Various'}."
            return summary
            
        except Exception as e:
            return "Top Genres: Mixed. Top Artists: Various."
    
    def _calculate_rediscovery_scores(self, track_stats: Dict[str, Any], max_tracks: int = 25, max_per_artist: int = 3) -> List[Tuple[str, float, Dict[str, Any]]]:
        """Calculate rediscovery scores and apply recipe filters"""
        scored_tracks = []
        current_year = datetime.now(timezone.utc).year
        cutoff_year = current_year - 15  # Dynamic cutoff year
        
        # Debug counters (silent)
        debug_stats = {
            "total_tracks": len(track_stats),
            "filtered_days": 0,
            "filtered_play_count": 0,
            "passed_filters": 0
        }
        
        for song_id, stats in track_stats.items():
            try:
                # Calculate days since last play
                if stats.get("last_play"):
                    days_since_last_play = (datetime.now() - stats["last_play"]).days
                else:
                    days_since_last_play = 90  # Default for never played
                
                play_count = stats.get("total_plays", 0)
                year = stats.get("year", 2000)
                
                # Filtering for re-discovery candidates
                # 1. Days filter: 7-120 days (wider rediscovery window)
                if not (7 <= days_since_last_play <= 120):
                    debug_stats["filtered_days"] += 1
                    continue
                
                # 2. Play count filter: at least 1 play (must have been played before)
                if play_count < 1:
                    debug_stats["filtered_play_count"] += 1
                    continue
                
                # No year filter - rediscovery should include tracks from any era
                
                debug_stats["passed_filters"] += 1
                
                # Calculate rediscovery_score = play_count * days_since_last_play
                rediscovery_score = play_count * days_since_last_play
                
                # Add to candidate list
                scored_tracks.append((song_id, rediscovery_score, {
                    **stats,
                    "rediscovery_score": rediscovery_score,
                    "days_since_last_play": days_since_last_play
                }))
                
            except Exception as e:
                continue  # Skip problematic tracks
        
        # Filter results logged silently
        
        # Sort by rediscovery_score descending and take more candidates for AI selection
        scored_tracks.sort(key=lambda x: x[1], reverse=True)
        # Scale candidate limit based on desired playlist size (2.5x for 25 tracks = 62.5, for 50 tracks = 125)
        candidate_limit = min(int(max_tracks * 2.5), len(scored_tracks))
        return scored_tracks[:candidate_limit]
    
    def filter_artist_diversity(self, scored_tracks: List[Tuple[str, float, Dict[str, Any]]], max_per_artist: int = 3) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Filter tracks to ensure no artist dominates the playlist.
        Limits each artist to max_per_artist tracks.
        """
        artist_counts = Counter()
        filtered_tracks = []
        
        for song_id, score, stats in scored_tracks:
            artist = stats["artist"]
            
            if artist_counts[artist] < max_per_artist:
                filtered_tracks.append((song_id, score, stats))
                artist_counts[artist] += 1
        
        return filtered_tracks
    
    async def generate_rediscover_weekly(self, max_tracks: int = 20, use_ai: bool = True, variety_context: str = None, library_id: str = None) -> List[Dict[str, Any]]:
        """
        Main method to generate the Re-Discover Weekly playlist.
        Returns a list of track metadata for the final tracks.
        """
        try:
            # Step 1: Get listening history first to build analysis summary
            history = await self.get_listening_history(days_back=90)  # Use 90 days for analysis
            
            if not history:
                raise Exception("No listening history found in the last 90 days")
            
            # Step 2: Analyze patterns and create analysis summary
            track_stats = await self.analyze_listening_patterns(history)
            analysis_summary = self._generate_analysis_summary(track_stats, history)
            
            # Analysis summary logged silently
            
            # Initial recipe inputs (will be updated with candidates later)
            recipe_inputs = {
                "num_tracks": max_tracks,
                "analysis_summary": analysis_summary,
                "candidate_tracks_json": "[]"  # Placeholder for now
            }
            
            # Step 3: Score tracks for re-discovery with new rediscovery_score calculation
            # Scale max_per_artist based on playlist size (~12.5% of playlist, minimum 2)
            scaled_max_per_artist = max(2, max_tracks // 8)
            print(f"🎯 Generating {max_tracks}-track rediscover playlist (max {scaled_max_per_artist} per artist)")
            scored_tracks = self._calculate_rediscovery_scores(track_stats, max_tracks=max_tracks, max_per_artist=scaled_max_per_artist)
            
            if not scored_tracks:
                raise Exception("No tracks found for re-discovery")
            
            # Step 4: Apply artist diversity filtering before AI selection
            filtered_tracks = self.filter_artist_diversity(scored_tracks, max_per_artist=scaled_max_per_artist)
            # Artist diversity filtering applied silently
            
            # Step 5: Prepare candidate tracks for AI (filtered and sorted by rediscovery_score)
            candidate_tracks = filtered_tracks
            
            if not candidate_tracks:
                raise Exception("No suitable tracks found for re-discovery")
            
            print(f"🔍 Prepared {len(candidate_tracks)} rediscovery candidates for AI curation")
            
            # Step 6: Prepare candidate tracks JSON for recipe placeholder replacement
            ai_candidates = []
            for song_id, score, stats in candidate_tracks:
                # Try to get genre information if available
                genre = "Unknown"
                try:
                    if "genre" in stats:
                        genre = stats["genre"]
                    elif hasattr(self, 'all_tracks_cache'):
                        track_match = next((t for t in self.all_tracks_cache if t["id"] == song_id), None)
                        if track_match:
                            genre = track_match.get("genre", "Unknown")
                except:
                    genre = "Unknown"
                
                ai_candidates.append({
                    "id": song_id,
                    "title": stats["title"],
                    "artist": stats["artist"],
                    "album": stats["album"],
                    "genre": genre,
                    "year": stats.get("year", 2000),
                    "play_count": stats.get("total_plays", 0),
                    "days_since_last_play": stats["days_since_last_play"],
                    "rediscovery_score": round(score, 2)
                })
            
            # Step 6: Use AI curation if enabled
            if use_ai:
                # Update recipe inputs with actual candidate tracks
                import json
                recipe_inputs["candidate_tracks_json"] = json.dumps(ai_candidates, indent=2)
                
                # Apply recipe with all placeholders resolved
                final_recipe = recipe_manager.apply_recipe("re_discover", recipe_inputs, include_reasoning=True)

                # Recipe configuration applied silently
                
                # Use new recipe format for AI curation
                if "llm_config" in final_recipe:
                    # Import AI client here to avoid circular imports
                    from .ai_client import AIClient
                    ai_client = AIClient()
                    
                    try:
                        # Use the new recipe-based AI curation method
                        ai_result = await ai_client.curate_rediscover_weekly(
                            candidate_tracks=ai_candidates,
                            analysis_summary=analysis_summary,
                            num_tracks=max_tracks,
                            include_reasoning=True,
                            variety_context=variety_context
                        )
                        
                        if isinstance(ai_result, tuple):
                            curated_track_ids, reasoning = ai_result
                        else:
                            curated_track_ids = ai_result
                            reasoning = ""
                        
                        # Create final playlist with AI selections
                        playlist_tracks = []
                        id_to_candidate = {candidate["id"]: candidate for candidate in ai_candidates}
                        
                        for track_id in curated_track_ids:
                            if track_id in id_to_candidate:
                                candidate = id_to_candidate[track_id]
                                playlist_tracks.append({
                                    "id": track_id,
                                    "title": candidate["title"],
                                    "artist": candidate["artist"],
                                    "album": candidate["album"],
                                    "score": candidate["rediscovery_score"],
                                    "historical_plays": candidate["play_count"],
                                    "days_since_last_play": candidate["days_since_last_play"],
                                    "ai_curated": True,
                                    "ai_reasoning": reasoning if reasoning else "AI curation applied"
                                })
                        
                        if playlist_tracks:
                            return playlist_tracks
                            
                    except Exception as e:
                        # AI curation failed, fall back to algorithmic selection
                        print(f"❌ AI curation failed for Re-Discover Weekly: {e}")
                        import traceback
                        print(f"📋 Full traceback: {traceback.format_exc()}")
                        # Fall through to algorithmic selection
            
            # Step 7: Fallback to algorithmic selection
            top_tracks = candidate_tracks[:max_tracks]
            playlist_tracks = []
            for song_id, score, stats in top_tracks:
                playlist_tracks.append({
                    "id": song_id,
                    "title": stats["title"],
                    "artist": stats["artist"],
                    "album": stats["album"],
                    "score": round(score, 2),
                    "historical_plays": stats["total_plays"],
                    "days_since_last_play": (datetime.now() - stats["last_play"]).days if stats["last_play"] else "30+",
                    "ai_curated": False,
                    "ai_reasoning": "Algorithmic selection used (AI not available or failed)"
                })
            
            return playlist_tracks
            
        except Exception as e:
            raise Exception(f"Failed to generate Re-Discover Weekly: {e}")


class ReDiscoverV2Processor:
    """
    Re-Discover Weekly v2.0 - Uses OpenSubsonic API's played timestamps
    for temporal analysis and two-phase AI collaboration.
    """

    def __init__(self, navidrome_client, ai_client, db_manager):
        self.navidrome_client = navidrome_client
        self.ai_client = ai_client
        self.db = db_manager
        self.config = {
            "track_count": 25,
            "target_period_days_start": 90,
            "target_period_days_end": 30,
            "exclude_played_within_days": 30,
            "sample_size_percentage": 0.02,
            "sample_size_min": 500,
            "sample_size_max": 3000,
            "max_tracks_per_artist": 2,
            "min_target_period_tracks": 10,
            "genre_cache_hours": 24,
            "enable_fallback": True
        }

    async def generate_playlist(self, user_id: str, server_id: str, library_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Main entry point for Re-Discover Weekly v2.0 generation.
        Returns playlist data ready for Navidrome creation.
        """
        try:
            print(f"🎵 Re-Discover Weekly v2.0: Starting generation for user {user_id}, server {server_id}")

            # Phase 0: Context Gathering
            print("📊 Phase 0: Gathering context...")
            library_size = await self._get_library_size_cached(server_id)
            print(f"📊 Library size: {library_size} tracks")

            genres = await self._get_genres_cached(server_id)
            print(f"📊 Found {len(genres)} unique genres")

            sample_size = self._calculate_sample_size(library_size)
            print(f"📊 Calculated sample size: {sample_size} tracks")

            # Phase 1: Analyze & Strategize
            print("🔍 Phase 1: Analyzing listening patterns...")
            sample_tracks = await self._sample_library(sample_size, library_ids)
            print(f"🔍 Sampled {len(sample_tracks)} tracks from library")

            target_tracks = self._filter_to_target_period(sample_tracks)
            print(f"🔍 Found {len(target_tracks)} tracks in target period (30-90 days ago)")

            if len(target_tracks) < self.config["min_target_period_tracks"]:
                print(f"⚠️ Only {len(target_tracks)} target tracks found (minimum: {self.config['min_target_period_tracks']})")
                print("🔄 Triggering fallback strategy...")
                return await self._trigger_fallback(user_id, server_id, library_ids)

            analysis = self._analyze_target_period(target_tracks)
            theme_strategy = await self._llm_phase1_theme_detection(analysis, genres)

            # Phase 2: Search & Sequence
            search_results = await self._execute_searches(theme_strategy, library_ids)
            candidates = self._filter_and_enrich_candidates(search_results, target_tracks)
            final_tracks = await self._llm_phase2_sequencing(candidates, theme_strategy)

            # Phase 3: Create & Log
            playlist_data = await self._create_playlist_data(final_tracks, theme_strategy, user_id, server_id)
            await self._log_to_database_v2(playlist_data, theme_strategy, len(target_tracks))

            return playlist_data

        except Exception as e:
            raise Exception(f"Re-Discover Weekly v2.0 failed: {e}")

    async def _get_library_size_cached(self, server_id: str) -> int:
        """Get library size with caching."""
        cache_key = f"library_size:{server_id}"
        cached = await self.db.get_cache(cache_key)
        if cached:
            return int(cached)

        # Fetch from Navidrome
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getScanStatus.view",
                params=params
            )
            response.raise_for_status()
            data = response.json()
            count = data.get("subsonic-response", {}).get("scanStatus", {}).get("count", 0)

            # Cache for 24 hours
            await self.db.set_cache(cache_key, str(count), 86400)
            return count
        except:
            return 1000  # Fallback estimate

    async def _get_genres_cached(self, server_id: str) -> List[str]:
        """Get genres with caching."""
        cache_key = f"genres:{server_id}"
        cached = await self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        # Fetch from Navidrome
        try:
            genres = await self.navidrome_client.get_genres()
            genre_names = [g.get("value", g.get("name", "")) for g in genres if g.get("value", g.get("name", ""))]

            # Cache for 24 hours
            await self.db.set_cache(cache_key, json.dumps(genre_names), 86400)
            return genre_names
        except:
            return ["Rock", "Pop", "Electronic", "Jazz", "Classical"]  # Fallback

    def _calculate_sample_size(self, library_size: int) -> int:
        """Calculate optimal sample size based on library size."""
        percentage_based = int(library_size * self.config["sample_size_percentage"])
        return min(max(percentage_based, self.config["sample_size_min"]), self.config["sample_size_max"])

    async def _sample_library(self, sample_size: int, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Sample random tracks from the library using OpenSubsonic getRandomSongs."""
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            params["size"] = str(sample_size)

            # Add library filter if specified
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getRandomSongs.view",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs if isinstance(songs, list) else []

        except Exception as e:
            print(f"❌ Failed to sample library: {e}")
            return []

    def _filter_to_target_period(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter tracks to those played in the target period (30-90 days ago)."""
        now = datetime.now(timezone.utc)
        target_tracks = []
        tracks_with_timestamps = 0
        tracks_in_range = 0

        print(f"🔍 Filtering {len(tracks)} tracks for target period ({self.config['target_period_days_end']}-{self.config['target_period_days_start']} days ago)...")

        for track in tracks:
            played_str = track.get("played")
            if not played_str:
                continue

            tracks_with_timestamps += 1

            try:
                # Parse ISO 8601 timestamp
                if played_str.endswith("Z"):
                    played_str = played_str[:-1] + "+00:00"
                played = datetime.fromisoformat(played_str)

                days_ago = (now - played).days

                # Debug: log some examples
                if tracks_in_range < 3:  # Log first few matches
                    print(f"🔍 Track '{track.get('title', 'Unknown')}' played {days_ago} days ago")

                if self.config["target_period_days_end"] <= days_ago <= self.config["target_period_days_start"]:
                    # Add parsed timestamp for easier processing later
                    track["played_datetime"] = played
                    track["days_ago"] = days_ago
                    target_tracks.append(track)
                    tracks_in_range += 1

            except (ValueError, TypeError) as e:
                print(f"⚠️ Failed to parse timestamp '{played_str}' for track '{track.get('title', 'Unknown')}': {e}")
                continue  # Skip invalid timestamps

        print(f"🔍 Summary: {tracks_with_timestamps} tracks had timestamps, {tracks_in_range} in target range")
        return target_tracks

    def _analyze_target_period(self, target_tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the target period tracks to understand listening patterns."""
        if not target_tracks:
            return {"tracks_found": 0}

        # Extract genres (handle multi-genre format)
        genre_counts = Counter()
        for track in target_tracks:
            genres = track.get("genres", [])
            if isinstance(genres, list):
                for genre_obj in genres:
                    if isinstance(genre_obj, dict) and "name" in genre_obj:
                        genre_counts[genre_obj["name"]] += 1
            elif isinstance(genres, str):
                genre_counts[genres] += 1

        # Extract other patterns
        artist_counts = Counter(track.get("artist", "Unknown") for track in target_tracks)
        decades = Counter()
        for track in target_tracks:
            year = track.get("year", 2000)
            if year and isinstance(year, int):
                decade = (year // 10) * 10
                decades[decade] += 1

        play_counts = [track.get("playCount", 0) for track in target_tracks]

        return {
            "tracks_found": len(target_tracks),
            "top_genres": dict(genre_counts.most_common(5)),
            "top_artists": dict(artist_counts.most_common(5)),
            "top_decades": dict(decades.most_common(3)),
            "avg_play_count": sum(play_counts) / len(play_counts) if play_counts else 0,
            "date_range": {
                "oldest": min((t["played_datetime"] for t in target_tracks), default=None),
                "newest": max((t["played_datetime"] for t in target_tracks), default=None)
            }
        }

    async def _llm_phase1_theme_detection(self, analysis: Dict[str, Any], available_genres: List[str]) -> Dict[str, Any]:
        """Phase 1 AI: Analyze listening patterns and select curation strategy."""

        # Create recipe inputs
        recipe_inputs = {
            "tracks_found": analysis["tracks_found"],
            "top_genres": json.dumps(analysis.get("top_genres", {})),
            "top_artists": json.dumps(analysis.get("top_artists", {})),
            "top_decades": json.dumps(analysis.get("top_decades", {})),
            "avg_play_count": round(analysis.get("avg_play_count", 0), 1),
            "available_genres": json.dumps(available_genres[:20])  # Limit for token efficiency
        }

        try:
            # Apply recipe
            final_recipe = recipe_manager.apply_recipe("re_discover_phase1_v2", recipe_inputs)

            if "llm_config" in final_recipe:
                # Use the AI provider directly with the recipe instructions
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")

                model = self.ai_client.model or llm_config.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1500)

                print(f"🤖 Making Phase 1 AI call with model {model}...")

                ai_result = await self.ai_client.provider.generate(
                    system_prompt="You are an expert music curator analyzing listening patterns.",
                    user_prompt=model_instructions,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

                # Parse JSON response with the same cleaning logic
                try:
                    # Clean up the response and extract JSON
                    cleaned_content = ai_result.strip()

                    # Remove markdown code fences if present
                    if cleaned_content.startswith("```json"):
                        cleaned_content = cleaned_content[7:]  # Remove ```json
                    if cleaned_content.startswith("```"):
                        cleaned_content = cleaned_content[3:]   # Remove ```
                    if cleaned_content.endswith("```"):
                        cleaned_content = cleaned_content[:-3]  # Remove trailing ```

                    cleaned_content = cleaned_content.strip()

                    # Try to find JSON object - use greedy match to handle nested objects
                    import re
                    json_object_match = re.search(r'\{.*\}', cleaned_content, re.DOTALL)
                    if json_object_match:
                        json_str = json_object_match.group(0)
                    else:
                        json_str = cleaned_content

                    # Clean up the extracted JSON
                    lines = json_str.split('\n')
                    cleaned_lines = []

                    for line in lines:
                        # Remove // comments but preserve URLs
                        if '//' in line and 'http://' not in line and 'https://' not in line:
                            comment_pos = line.find('//')
                            line = line[:comment_pos].rstrip()

                        # Remove trailing commas before closing brackets
                        line = re.sub(r',(\s*[\]}])', r'\1', line)

                        if line.strip():
                            cleaned_lines.append(line)

                    final_json = '\n'.join(cleaned_lines).strip()
                    strategy = json.loads(final_json)

                    return strategy

                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse Phase 1 AI response as JSON: {e}")
                    print(f"🔍 Raw response: {ai_result}")
                    # Fall through to fallback strategy
        except Exception as e:
            print(f"❌ Phase 1 AI failed: {e}")

        # Fallback strategy
        return {
            "selected_mode": "A",
            "mode_rationale": "AI analysis failed, using fallback strategy",
            "theme_identified": "Mixed favorites",
            "primary_genres": list(analysis.get("top_genres", {}).keys())[:3],
            "primary_decade": "2000s",
            "mood_keywords": ["nostalgic", "favorite"],
            "search_strategy": {
                "include_genres": list(analysis.get("top_genres", {}).keys())[:3],
                "include_decades": ["2000s", "2010s"],
                "play_count_min": 2,
                "play_count_max": 15,
                "exclude_played_within_days": 30,
                "prioritize_starred": True
            },
            "reasoning": "Fallback strategy due to AI unavailability"
        }

    async def _execute_searches(self, theme_strategy: Dict[str, Any], library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Execute targeted searches based on AI strategy."""
        search_results = []
        strategy = theme_strategy.get("search_strategy", {})

        # Search by genres
        include_genres = strategy.get("include_genres", [])
        for genre in include_genres[:3]:  # Limit to top 3 genres
            try:
                tracks = await self.navidrome_client.get_tracks_by_genre(genre, library_ids)
                search_results.extend(tracks)
            except Exception as e:
                print(f"⚠️ Genre search failed for {genre}: {e}")

        # Search by decades (year ranges)
        include_decades = strategy.get("include_decades", [])
        for decade in include_decades[:2]:  # Limit to 2 decades
            try:
                # Handle decade strings like '2000s', '2010s', etc.
                if isinstance(decade, str) and decade.endswith('s'):
                    start_year = int(decade[:-1])  # Remove 's' and convert to int
                else:
                    start_year = int(decade)
                end_year = start_year + 9
                tracks = await self._search_by_year_range(start_year, end_year, library_ids)
                search_results.extend(tracks)
            except Exception as e:
                print(f"⚠️ Decade search failed for {decade}: {e}")

        # Include starred tracks if requested
        if strategy.get("prioritize_starred", False):
            try:
                starred = await self.navidrome_client.get_starred()
                search_results.extend(starred)
            except Exception as e:
                print(f"⚠️ Starred tracks search failed: {e}")

        return search_results

    async def _search_by_year_range(self, start_year: int, end_year: int, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for tracks in a specific year range."""
        # This is a simplified implementation - in practice you'd use more sophisticated search
        # For now, we'll use getRandomSongs with year filtering
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            params["size"] = "200"  # Reasonable sample size
            params["fromYear"] = str(start_year)
            params["toYear"] = str(end_year)

            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getRandomSongs.view",
                params=params
            )
            response.raise_for_status()
            data = response.json()

            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs if isinstance(songs, list) else []

        except Exception as e:
            print(f"❌ Year range search failed: {e}")
            return []

    def _filter_and_enrich_candidates(self, search_results: List[Dict[str, Any]], target_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter search results and calculate rediscovery scores."""
        candidates = []
        now = datetime.now(timezone.utc)
        exclude_before = now - timedelta(days=self.config["exclude_played_within_days"])

        # Create lookup for target tracks
        target_track_ids = {t["id"] for t in target_tracks}

        for track in search_results:
            track_id = track.get("id")
            if not track_id:
                continue

            # Skip if played too recently
            played_str = track.get("played")
            if played_str:
                try:
                    if played_str.endswith("Z"):
                        played_str = played_str[:-1] + "+00:00"
                    played = datetime.fromisoformat(played_str)
                    if played > exclude_before:
                        continue  # Played too recently
                except:
                    pass  # Continue if timestamp parsing fails

            # Calculate rediscovery score
            play_count = track.get("playCount", 0)
            days_since_play = 30  # Default

            if played_str:
                try:
                    if played_str.endswith("Z"):
                        played_str = played_str[:-1] + "+00:00"
                    played = datetime.fromisoformat(played_str)
                    days_since_play = (now - played).days
                except:
                    pass

            # Enhanced scoring: play_count * log(days_since_play + 1) * random_factor
            rediscovery_score = play_count * (1 + days_since_play ** 0.5) * random.uniform(0.8, 1.2)

            # Mark if this track was in the target period
            was_in_target_period = track_id in target_track_ids

            candidate = {
                **track,
                "rediscovery_score": rediscovery_score,
                "days_since_last_play": days_since_play,
                "was_in_target_period": was_in_target_period
            }
            candidates.append(candidate)

        # Sort by score and return top candidates
        candidates.sort(key=lambda x: x["rediscovery_score"], reverse=True)
        return candidates[:100]  # Return top 100 for AI selection

    async def _llm_phase2_sequencing(self, candidates: List[Dict[str, Any]], theme_strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Phase 2 AI: Sequence exactly 25 tracks for optimal playlist flow."""

        # Prepare AI input
        ai_candidates = []
        for track in candidates[:80]:  # Limit for token efficiency
            ai_candidates.append({
                "id": track["id"],
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "album": track.get("album", ""),
                "genres": [g.get("name", "") for g in track.get("genres", [])] if isinstance(track.get("genres"), list) else [],
                "year": track.get("year", 2000),
                "play_count": track.get("playCount", 0),
                "days_since_last_play": track.get("days_since_last_play", 30),
                "rediscovery_score": round(track.get("rediscovery_score", 0), 2),
                "was_in_target_period": track.get("was_in_target_period", False)
            })

        recipe_inputs = {
            "theme_strategy": json.dumps(theme_strategy),
            "candidate_tracks": json.dumps(ai_candidates),
            "num_tracks": self.config["track_count"]
        }

        try:
            # Use the proper AI curation method with indexing
            ai_result = await self.ai_client.curate_rediscover_weekly(
                candidate_tracks=ai_candidates,
                analysis_summary="",  # Could be enhanced with theme_strategy info
                num_tracks=self.config["track_count"],
                include_reasoning=True,
                variety_context=json.dumps(theme_strategy) if theme_strategy else None
            )

            if isinstance(ai_result, tuple):
                track_ids, reasoning = ai_result
            else:
                track_ids = ai_result
                reasoning = ""

            # Build final track list
            final_tracks = []
            for track_id in track_ids:
                # track_ids from curate_rediscover_weekly are actual Navidrome IDs (already mapped back)
                candidate = next((c for c in ai_candidates if c["id"] == track_id), None)
                if candidate:
                    final_tracks.append({
                        **candidate,
                        "ai_curated": True,
                        "ai_reasoning": reasoning
                    })

            if len(final_tracks) == self.config["track_count"]:
                return final_tracks

        except Exception as e:
            print(f"❌ Phase 2 AI failed: {e}")
            # Update theme strategy to reflect AI failure
            theme_strategy["reasoning"] = "Fallback strategy due to AI unavailability"

        # Fallback: Score-based selection
        top_candidates = candidates[:self.config["track_count"]]
        return [{
            **track,
            "ai_curated": False,
            "ai_reasoning": "Algorithmic selection (AI not available)"
        } for track in top_candidates]

    async def _create_playlist_data(self, tracks: List[Dict[str, Any]], theme_strategy: Dict[str, Any], user_id: str, server_id: str) -> Dict[str, Any]:
        """Create final playlist data structure."""
        return {
            "name": "Re-Discover Weekly",
            "tracks": tracks,
            "theme": theme_strategy.get("theme_identified", "Mixed"),
            "mode": theme_strategy.get("selected_mode", "A"),
            "reasoning": theme_strategy.get("reasoning", ""),
            "user_id": user_id,
            "server_id": server_id,
            "generated_at": datetime.now().isoformat()
        }

    async def _log_to_database_v2(self, playlist_data: Dict[str, Any], theme_strategy: Dict[str, Any], tracks_analyzed: int):
        """Log v2 playlist generation to database."""
        # TODO: Implement proper database logging for v2 playlists
        # For now, just log to console
        print(f"📊 V2 Playlist logged: {len(playlist_data['tracks'])} tracks, theme: {theme_strategy.get('theme_identified', 'Unknown')}, tracks analyzed: {tracks_analyzed}")

    async def _trigger_fallback(self, user_id: str, server_id: str, library_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fallback strategy when insufficient target period tracks are found."""
        try:
            # Try starred tracks approach
            starred_tracks = await self.navidrome_client.get_starred()
            if starred_tracks:
                # Filter starred tracks by played timestamp
                now = datetime.now(timezone.utc)
                exclude_before = now - timedelta(days=self.config["exclude_played_within_days"])

                valid_starred = []
                for track in starred_tracks[:50]:  # Limit for performance
                    played_str = track.get("played")
                    if played_str:
                        try:
                            if played_str.endswith("Z"):
                                played_str = played_str[:-1] + "+00:00"
                            played = datetime.fromisoformat(played_str)
                            if played < exclude_before:
                                valid_starred.append(track)
                        except:
                            continue

                if len(valid_starred) >= 10:
                    # Create fallback playlist
                    fallback_tracks = valid_starred[:self.config["track_count"]]
                    return {
                        "name": "Re-Discover Weekly",
                        "tracks": [{
                            **track,
                            "ai_curated": False,
                            "ai_reasoning": "Fallback: Using starred tracks (limited recent listening history)"
                        } for track in fallback_tracks],
                        "theme": "Starred Favorites",
                        "mode": "FALLBACK",
                        "reasoning": "Insufficient listening history in target period. Using starred tracks instead.",
                        "user_id": user_id,
                        "server_id": server_id,
                        "generated_at": datetime.now().isoformat(),
                        "is_fallback": True
                    }

        except Exception as e:
            print(f"⚠️ Starred tracks fallback failed: {e}")

        # Try a more basic fallback: use any tracks from the library
        try:
            print("🔄 Trying basic library fallback...")
            # Get a small sample of tracks from the library
            basic_tracks = await self._sample_library(min(100, self.config["track_count"] * 3), library_ids)

            if basic_tracks and len(basic_tracks) >= 10:
                # Sort by play count and take top tracks
                basic_tracks.sort(key=lambda x: x.get("playCount", 0), reverse=True)
                fallback_tracks = basic_tracks[:self.config["track_count"]]

                return {
                    "name": "Re-Discover Weekly",
                    "tracks": [{
                        **track,
                        "ai_curated": False,
                        "ai_reasoning": "Basic fallback: Using highest-played tracks (very limited listening history)"
                    } for track in fallback_tracks],
                    "theme": "Library Favorites",
                    "mode": "BASIC_FALLBACK",
                    "reasoning": "No recent listening history found. Using your most-played tracks instead.",
                    "user_id": user_id,
                    "server_id": server_id,
                    "generated_at": datetime.now().isoformat(),
                    "is_fallback": True
                }

        except Exception as e:
            print(f"⚠️ Basic library fallback also failed: {e}")

        # Ultimate fallback: Error message
        raise Exception("Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!")