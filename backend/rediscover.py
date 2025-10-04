import httpx
import os
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json
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
            end_date = datetime.now()
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
                tracks = await self.navidrome_client.get_tracks_by_artist(artist["id"])
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
        now = datetime.now()
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
        now = datetime.now()

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
    
    async def generate_rediscover_weekly(self, max_tracks: int = 20, use_ai: bool = True) -> List[Dict[str, Any]]:
        """
        Main method to generate the Re-Discover Weekly playlist.
        Returns a list of track metadata for the final tracks.
        """
        try:
            # Use recipe system to get strategy parameters
            recipe_inputs = {
                "candidate_tracks": "placeholder",
                "num_tracks": max_tracks,
                "analysis_summary": "placeholder"
            }
            
            recipe_result = recipe_manager.apply_recipe("re_discover", recipe_inputs, include_reasoning=True)
            recipe = recipe_result["recipe"]
            strategy = recipe["strategy_notes"]
            
            # Extract strategy parameters from recipe
            analysis_days = int(strategy["time_windows"]["analysis_period"].split()[0])
            min_gap_text = strategy["time_windows"]["minimum_gap"]
            min_gap_days = int(min_gap_text.split("+")[0]) if "+" in min_gap_text else 7
            max_per_artist = strategy["diversity_controls"]["max_per_artist"]
            
            # Step 1: Get listening history using recipe parameters
            history = await self.get_listening_history(days_back=analysis_days)
            
            if not history:
                raise Exception(f"No listening history found in the last {analysis_days} days")
            
            # Step 2: Analyze patterns
            track_stats = await self.analyze_listening_patterns(history)
            
            # Step 3: Score tracks for re-discovery using recipe strategy
            scored_tracks = self.score_tracks_for_rediscovery(
                track_stats, 
                min_gap_days=min_gap_days,
                max_per_artist=max_per_artist
            )
            
            if not scored_tracks:
                raise Exception("No tracks found for re-discovery")
            
            # Step 4: Filter for artist diversity and prepare larger candidate pool for AI
            diverse_tracks = self.filter_artist_diversity(scored_tracks, max_per_artist=max_per_artist)
            
            # Prepare a larger candidate pool for AI (3-5x the target tracks)
            candidate_pool_size = min(max_tracks * 4, len(diverse_tracks), 100)  # Cap at 100 tracks
            candidate_tracks = diverse_tracks[:candidate_pool_size]

            # If we have fewer candidates than desired, try to get more by relaxing filters
            if len(candidate_tracks) < max_tracks * 2:  # Ensure at least 2x target for good AI selection
                # Try again with more lenient filters
                lenient_candidates = []
                for song_id, stats in track_stats.items():
                    # More lenient: include any track with play count > 0
                    if stats["total_plays"] < 1:
                        continue

                    # Allow tracks played up to 3 days ago instead of min_gap_days
                    if stats["recent_plays"] > 0:
                        continue

                    days_since_last_play = 3  # Reduced threshold
                    if stats["last_play"]:
                        days_since_last_play = (datetime.now() - stats["last_play"]).days

                    if days_since_last_play < 3:
                        continue

                    score = stats["total_plays"] * min(days_since_last_play, 90)
                    lenient_candidates.append((song_id, score, stats))

                # Sort and apply diversity filter
                lenient_candidates.sort(key=lambda x: x[1], reverse=True)
                lenient_diverse = self.filter_artist_diversity(lenient_candidates, max_per_artist=max_per_artist + 1)

                # Combine with existing tracks (avoid duplicates)
                existing_ids = {track[0] for track in candidate_tracks}
                additional_tracks = [track for track in lenient_diverse if track[0] not in existing_ids]

                # Add additional tracks to candidate pool
                candidate_tracks.extend(additional_tracks)
            
            # Prepare analysis summary for AI
            total_history_tracks = len(set(track_stats.keys()))
            avg_score = sum(score for _, score, _ in candidate_tracks) / len(candidate_tracks) if candidate_tracks else 0
            
            analysis_summary = f"""Algorithmic Analysis Results:
- Analyzed {len(history)} listening events from the last {analysis_days} days
- Found {total_history_tracks} unique tracks in listening history
- Applied scoring formula: play_count × days_since_last_play (capped at 90 days)
- Filtered for minimum {min_gap_days} days since last play
- Applied artist diversity limit of {max_per_artist} tracks per artist
- Generated {len(candidate_tracks)} high-quality rediscovery candidates
- Average algorithmic score: {avg_score:.1f}
- Candidate pool represents top scoring tracks with good artist diversity"""

            # Step 5: Use AI to curate final selection from candidates
            if use_ai and len(candidate_tracks) >= max_tracks:
                # Import AI client here to avoid circular imports
                from .ai_client import AIClient
                ai_client = AIClient()
                
                # Prepare candidate tracks for AI with relevant metadata
                ai_candidates = []
                for song_id, score, stats in candidate_tracks:
                    ai_candidates.append({
                        "id": song_id,
                        "title": stats["title"],
                        "artist": stats["artist"],
                        "album": stats["album"],
                        "historical_plays": stats["total_plays"],
                        "days_since_last_play": (datetime.now() - stats["last_play"]).days if stats["last_play"] else "30+",
                        "rediscover_score": round(score, 2)
                    })
                
                try:
                    # Get AI curation with reasoning
                    ai_result = await ai_client.curate_rediscover_weekly(
                        candidate_tracks=ai_candidates,
                        analysis_summary=analysis_summary,
                        num_tracks=max_tracks,
                        include_reasoning=True
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
                                "score": candidate["rediscover_score"],
                                "historical_plays": candidate["historical_plays"],
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
            
            # Step 6: Fallback to algorithmic selection
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