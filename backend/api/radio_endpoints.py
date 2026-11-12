"""
Song Radio API endpoints for creating playlists based on track similarity

This module provides REST API endpoints for:
- Creating radio playlists based on seed tracks
- Finding similar tracks using audio embeddings
- Integrating with AI for playlist curation
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from ..services.chroma_service import get_chroma_service
from ..navidrome_client import NavidromeClient
from ..ai_client import AIClient
from ..recipe_manager import recipe_manager
from ..database import DatabaseManager, get_db

logger = logging.getLogger(__name__)

router = APIRouter()


def calculate_next_refresh(frequency: str):
    """Calculate the next refresh time based on frequency"""
    from datetime import datetime, timedelta
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



def filter_seed_artist_dominance(
    candidates: List[Dict],
    seed_artist: str,
    max_seed_artist_percentage: float = 0.20
) -> List[Dict]:
    """
    Remove excess seed artist tracks to maintain diversity.

    Strategy:
    a. Count total candidates
    b. Count seed artist instances in the list
    c. Calculate 20% of total candidates
    d. Remove seed artist tracks from BOTTOM (least similar) up
       until seed artist count <= 20%

    Args:
        candidates: Already sorted by similarity (best first)
        seed_artist: Artist of seed track
        max_seed_artist_percentage: Max % from seed artist (default 20%)

    Returns:
        Filtered candidates (still sorted, seed artist capped)
    """
    # a. Count total candidates
    total_count = len(candidates)

    # c. Calculate max allowed seed artist tracks (20% of total)
    max_seed_tracks = int(total_count * max_seed_artist_percentage)

    logger.info(f"🎯 Filtering seed artist from {total_count} candidates:")
    logger.info(f"   Seed artist: {seed_artist}")
    logger.info(f"   Max allowed: {max_seed_tracks} tracks ({max_seed_artist_percentage*100}%)")

    # b. Count seed artist instances
    seed_artist_normalized = seed_artist.lower()

    # Find all seed artist track indices
    seed_artist_indices = [
        i for i, c in enumerate(candidates)
        if c.get('artist', '').lower() == seed_artist_normalized
    ]

    seed_artist_count = len(seed_artist_indices)
    logger.info(f"   Found: {seed_artist_count} tracks by {seed_artist}")

    # If already within limit, no filtering needed
    if seed_artist_count <= max_seed_tracks:
        logger.info(f"   ✅ Already within limit, no filtering needed")
        return candidates

    # d. Calculate how many to remove and remove from BOTTOM
    tracks_to_remove = seed_artist_count - max_seed_tracks
    logger.info(f"   ❌ Need to remove {tracks_to_remove} tracks by {seed_artist}")

    # Keep the FIRST max_seed_tracks (most similar)
    # Remove the REST (least similar, from bottom)
    indices_to_keep = set(seed_artist_indices[:max_seed_tracks])
    indices_to_remove = set(seed_artist_indices[max_seed_tracks:])

    logger.info(f"   Keeping {len(indices_to_keep)} most similar {seed_artist} tracks")
    logger.info(f"   Removing {len(indices_to_remove)} least similar {seed_artist} tracks")

    # Build filtered list (exclude removed indices)
    filtered_candidates = [
        c for i, c in enumerate(candidates)
        if i not in indices_to_remove
    ]

    # Verify final count
    remaining_seed_count = sum(
        1 for c in filtered_candidates
        if c.get('artist', '').lower() == seed_artist_normalized
    )

    logger.info(f"   ✅ After filtering: {remaining_seed_count} tracks by {seed_artist}")
    logger.info(f"   ✅ Total candidates remaining: {len(filtered_candidates)}")
    logger.info(f"   ✅ Other artists: {len(filtered_candidates) - remaining_seed_count}")

    return filtered_candidates


def format_candidates_for_ai(candidates: List[Dict], num_tracks: int) -> tuple[List[Dict], List[str]]:
    """
    Format candidates for AI with rich metadata using index-based approach.

    Args:
        candidates: Scored and ranked candidates
        num_tracks: Target number of tracks for playlist (for logging only)

    Returns:
        Tuple of (formatted indexed candidates, track_id_map)
    """
    formatted = []
    track_id_map = []  # Map index -> actual track ID
    
    for idx, track in enumerate(candidates):
        # Store the actual track ID in our mapping
        track_id_map.append(track['track_id'])
        
        # Create indexed track (no complex IDs sent to AI)
        formatted.append({
            'index': idx,
            'title': track['title'],
            'artist': track['artist'],
            'album': track.get('album', 'Unknown'),
            'year': track.get('year'),
            'genre': track.get('genre'),
            'similarity': track['similarity_score'],  # ← KEY for AI
            'duration_seconds': track.get('duration')
        })

    logger.info(f"📤 Formatted {len(formatted)} candidates for AI using index-based approach")
    return formatted, track_id_map


async def curate_with_ai(
    seed_track: Dict,
    candidates: List[Dict],
    track_id_map: List[str],
    num_tracks: int,
    recipe: Dict,
    ai_client: AIClient,
    additional_instructions: str = ""
) -> tuple[List[str], str]:
    """
    Send candidates to AI for curation using index-based approach.

    Args:
        seed_track: Seed track metadata
        candidates: Formatted candidate list (index-based, no complex IDs)
        track_id_map: Mapping from indices to actual track IDs
        num_tracks: Target playlist size
        recipe: Recipe configuration
        ai_client: AI client instance
        additional_instructions: Optional context for refreshing an existing playlist

    Returns:
        Tuple of (selected track indices, reasoning)
    """
    if ai_client.provider.provider_type == "openrouter" and not ai_client.api_key:
        return track_id_map[:num_tracks], "Playlist created using acoustic similarity ranking."

    # Build prompt
    system_prompt = recipe['system_prompt']
    user_prompt = apply_recipe_placeholders(recipe, seed_track, candidates, num_tracks)
    if additional_instructions:
        user_prompt += "\n\n" + additional_instructions

    logger.info(f"🤖 Sending {len(candidates)} candidates to AI for curation")

    try:
        # Call AI
        content = await ai_client.provider.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=recipe['config']['temperature'],
            max_tokens=recipe['config']['max_tokens']
        )

        # Parse response
        content = content.strip()

        # Remove markdown code fences if present
        if content.startswith('```'):
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)
        track_indices = result.get('track_ids', [])
        reasoning = result.get('reasoning', '')

        valid_indices = list(dict.fromkeys(
            idx for idx in track_indices if type(idx) is int and 0 <= idx < len(track_id_map)
        ))
        if len(valid_indices) < num_tracks:
            raise ValueError("AI returned too few unique candidate tracks")
        mapped_track_ids = [track_id_map[idx] for idx in valid_indices[:num_tracks]]

        logger.info(f"✅ AI selected {len(mapped_track_ids)} tracks (requested: {num_tracks})")
        logger.info(f"💬 Reasoning: {reasoning}")

        return mapped_track_ids, reasoning

    except Exception as e:
        logger.error(f"❌ AI curation failed: {e}")

        # Fallback: Use top N by similarity
        logger.info(f"⚠️ Falling back to similarity-based selection")
        fallback_track_ids = track_id_map[:num_tracks] if track_id_map else []
        return fallback_track_ids, "Playlist created using acoustic similarity ranking."


def apply_recipe_placeholders(
    recipe: Dict,
    seed_track: Dict,
    candidates: List[Dict],
    num_tracks: int
) -> str:
    """
    Replace placeholders in recipe template with actual values.

    Args:
        recipe: Recipe dictionary
        seed_track: Seed track metadata
        candidates: Formatted candidate list
        num_tracks: Target playlist size

    Returns:
        User prompt with placeholders replaced
    """
    template = recipe['user_prompt_template']

    # Create replacements
    replacements = {
        '{{SEED_TRACK_NAME}}': seed_track.get('title', 'Unknown'),
        '{{SEED_TRACK_ARTIST}}': seed_track.get('artist', 'Unknown'),
        '{{DESIRED_TRACK_COUNT}}': str(num_tracks),
        '{{CANDIDATE_COUNT}}': str(len(candidates)),
        '{{MAX_INDEX}}': str(len(candidates) - 1) if candidates else '0',
        '{{CANDIDATES_JSON}}': json.dumps(candidates, indent=2)
    }

    # Apply replacements
    prompt = template
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)

    logger.info(f"✅ Applied {len(replacements)} placeholder replacements")

    return prompt


class RadioRequest(BaseModel):
    """Request schema for creating a radio playlist"""
    seed_track_id: str
    num_tracks: int = Field(default=25, ge=2, le=100)
    playlist_name: Optional[str] = None
    library_id: Optional[str] = None
    refresh_frequency: str = "none"  # "none", "daily", "weekly", "monthly"

class RadioResponse(BaseModel):
    """Response schema for radio playlist creation"""
    playlist_id: str
    name: str
    seed_track: Dict[str, Any]
    total_tracks: int
    similar_tracks: List[Dict[str, Any]]
    navidrome_playlist_id: Optional[str] = None
    reasoning: Optional[str] = None

@router.post(
    "/create",
    response_model=RadioResponse,
    summary="Create Song Radio Playlist",
    description="Create a radio playlist based on a seed track using audio similarity"
)
async def create_radio_playlist(
    request: RadioRequest,
    db = Depends(get_db),
    navidrome_client: NavidromeClient = Depends(),
    ai_client: AIClient = Depends()
):
    """
    Create a radio playlist based on audio similarity to a seed track.

    Simplified flow:
    1. Get seed track embedding
    2. Query ChromaDB for 3x candidates (75 for 25-track playlist)
    3. Score and rank by similarity
    4. Format for AI with rich metadata
    5. AI curates best 25 tracks
    6. Build playlist in Navidrome

    Args:
        request: RadioRequest containing seed_track_id and num_tracks
        navidrome_client: Navidrome client for playlist creation
        ai_client: AI client for playlist curation

    Returns:
        RadioResponse with playlist info and similar tracks

    Raises:
        HTTPException: 404 if seed track not analyzed, 500 for other errors
    """
    try:
        logger.info(f"🎵 Creating {request.num_tracks}-track radio for seed: {request.seed_track_id}")

        chroma_service = get_chroma_service()

        # Load recipe
        recipe = recipe_manager.get_recipe("song_radio")

        # 1. Get seed track
        seed_result = chroma_service.get_embedding(request.seed_track_id)
        if not seed_result:
            raise HTTPException(
                status_code=404,
                detail=f"Seed track {request.seed_track_id} has not been analyzed. Please run a library scan first."
            )

        seed_embedding, seed_metadata = seed_result
        seed_track = {
            "id": request.seed_track_id,
            "title": seed_metadata.get("title", "Unknown"),
            "artist": seed_metadata.get("artist", "Unknown"),
            "album": seed_metadata.get("album", "Unknown"),
            "genre": seed_metadata.get("genre", "Unknown")
        }

        # 2. Retrieve MANY candidates (10x target)
        candidate_multiplier = recipe['config']['candidate_multiplier']
        n_candidates = request.num_tracks * candidate_multiplier  # 250 for 25-track playlist

        # Get library_id from seed track metadata for filtering
        seed_library_id = seed_metadata.get("library_id") or request.library_id

        raw_candidates = chroma_service.find_similar_tracks(
            query_embedding=seed_embedding,
            n_results=n_candidates,
            exclude_track_ids=[request.seed_track_id],
            library_id=seed_library_id
        )

        logger.info(f"🔍 Retrieved {len(raw_candidates)} candidates (target: {request.num_tracks})")

        candidate_count = min(request.num_tracks - 1, len(raw_candidates))
        if not candidate_count:
            raise HTTPException(status_code=422, detail="Analyze more tracks in this library to create a Song Radio playlist.")

        formatted_candidates, track_id_map = format_candidates_for_ai(
            raw_candidates,
            candidate_count
        )

        # 6. AI curation
        selected_track_ids, reasoning = await curate_with_ai(
            seed_track,
            formatted_candidates,
            track_id_map,
            candidate_count,
            recipe,
            ai_client
        )

        # 7. Build playlist
        # selected_track_ids are already mapped to actual Navidrome IDs

        # Add seed track first
        playlist_track_ids = [request.seed_track_id] + selected_track_ids

        # Generate playlist name
        playlist_name = request.playlist_name
        if not playlist_name:
            playlist_name = f"Song Radio: {seed_track['title']} - {seed_track['artist']}"

        # Create in Navidrome
        navidrome_playlist_id = await navidrome_client.create_playlist(
            name=playlist_name,
            track_ids=playlist_track_ids,
            comment=reasoning
        )

        # Store playlist in local database
        candidates_by_id = {track['track_id']: track for track in raw_candidates}
        selected_tracks = [candidates_by_id[track_id] for track_id in selected_track_ids]
        track_titles = [seed_track['title']] + [track['title'] for track in selected_tracks]
        await db.create_playlist(
            artist_id=f"song_radio_{request.seed_track_id}",
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=len(playlist_track_ids),
            library_ids=[seed_library_id] if seed_library_id else None
        )

        # Handle scheduling if not "none"
        if request.refresh_frequency not in ["none", "never"]:
            next_refresh = calculate_next_refresh(request.refresh_frequency)

            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="song_radio",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )

        # Prepare response
        response = RadioResponse(
            playlist_id=f"radio_{request.seed_track_id}_{len(playlist_track_ids)}",
            name=playlist_name,
            seed_track=seed_track,
            total_tracks=len(playlist_track_ids),
            similar_tracks=[
                {
                    "id": track["track_id"],
                    "title": track["title"],
                    "artist": track["artist"],
                    "album": track["album"],
                    "genre": track["genre"],
                    "similarity_score": track["similarity_score"]
                }
                for track in selected_tracks
            ],
            navidrome_playlist_id=navidrome_playlist_id,
            reasoning=reasoning
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create radio playlist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create radio playlist: {str(e)}")

@router.get(
    "/analyzed-tracks",
    summary="Get Analyzed Tracks",
    description="Get list of tracks that have been analyzed and have embeddings stored"
)
async def get_analyzed_tracks(library_id: Optional[str] = Query(None)):
    """
    Get all tracks that have been analyzed and stored in ChromaDB.

    Args:
        library_id: Optional library ID to filter tracks by

    Returns:
        List of analyzed tracks with metadata
    """
    try:
        chroma_service = get_chroma_service()

        # Get all embeddings from ChromaDB
        all_embeddings = chroma_service.get_all_embeddings()

        if not all_embeddings:
            return {"tracks": []}

        # Filter by library_id if provided
        if library_id:
            filtered_embeddings = []
            for embedding_data in all_embeddings:
                metadata = embedding_data.get("metadata", {})
                if metadata.get("library_id") == library_id:
                    filtered_embeddings.append(embedding_data)
            all_embeddings = filtered_embeddings

        # Format the response
        tracks = []
        for embedding_data in all_embeddings:
            metadata = embedding_data.get("metadata", {})
            tracks.append({
                "id": embedding_data.get("id", ""),
                "title": metadata.get("title", ""),
                "artist": metadata.get("artist", ""),
                "album": metadata.get("album", ""),
                "genre": metadata.get("genre", ""),
                "year": metadata.get("year", 0),
                "duration": metadata.get("duration", 0)
            })

        logger.info(f"Retrieved {len(tracks)} analyzed tracks from ChromaDB" + (f" for library {library_id}" if library_id else ""))
        return {"tracks": tracks}

    except Exception as e:
        logger.error(f"Failed to get analyzed tracks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analyzed tracks: {str(e)}")

@router.get(
    "/search-tracks",
    summary="Search Analyzed Tracks",
    description="Search for analyzed tracks by title or artist with autocomplete support"
)
async def search_analyzed_tracks(
    q: str = Query(..., min_length=3, description="Search query for track title or artist (minimum 3 characters)"),
    limit: int = Query(50, description="Maximum number of results to return")
):
    print(f"DEBUG: Search endpoint called with q='{q}', limit={limit}")  # Debug print
    """
    Search analyzed tracks by title or artist.
    Gets full metadata from Navidrome for all analyzed tracks and filters server-side.
    Only returns tracks that have been analyzed and are available for radio playlists.

    Args:
        q: Search query (minimum 3 characters)
        limit: Maximum number of results to return

    Returns:
        List of matching tracks with full metadata from Navidrome
    """
    try:
        # First, get all analyzed track IDs from ChromaDB
        chroma_service = get_chroma_service()
        all_embeddings = chroma_service.get_all_embeddings()

        if not all_embeddings:
            return {"tracks": []}

        # Create a set of analyzed track IDs for fast lookup
        analyzed_track_ids = set()
        for embedding_data in all_embeddings:
            track_id = embedding_data.get("id", "")
            if track_id:
                analyzed_track_ids.add(track_id)

        logger.info(f"Searching {len(analyzed_track_ids)} analyzed tracks for '{q}'")
        logger.info(f"Sample analyzed track IDs: {list(analyzed_track_ids)[:5]}")

        # Get all tracks from Navidrome (for searching seed tracks)
        navidrome_client = NavidromeClient()
        await navidrome_client._ensure_authenticated()

        # Use search3 API with empty query to get all songs
        search_params = {
            "u": navidrome_client.username,
            "t": navidrome_client._subsonic_token,
            "s": navidrome_client._subsonic_salt,
            "v": "1.16.0",
            "c": "magiclists",
            "query": "",  # Empty query to get all songs
            "artistCount": "0",
            "albumCount": "0",
            "songCount": "10000",  # Get a large number to cover most libraries
            "f": "json"  # Request JSON format instead of XML
        }

        response = await navidrome_client.client.get(
            f"{navidrome_client.base_url}/rest/search3.view",
            params=search_params
        )
        response.raise_for_status()

        data = response.json()
        subsonic_response = data.get("subsonic-response", {})

        if subsonic_response.get("status") != "ok":
            raise HTTPException(status_code=500, detail="Navidrome API error")

        search_result = subsonic_response.get("searchResult3", {})
        navidrome_songs = search_result.get("song", [])

        logger.info(f"Retrieved {len(navidrome_songs)} total tracks from Navidrome for search")

        logger.info(f"Retrieved {len(navidrome_songs)} total songs from Navidrome")
        logger.info(f"Sample Navidrome song IDs: {[song.get('id') for song in navidrome_songs[:5]]}")

        # Debug: Show first few songs regardless of analysis
        logger.debug(f"First 3 Navidrome songs: {navidrome_songs[:3]}")
        
        # Filter to only include analyzed tracks and search server-side
        matching_tracks = []
        query_lower = q.lower()

        for song in navidrome_songs:
            song_id = song.get("id", "")
            
            # Only include tracks that have been analyzed
            if song_id not in analyzed_track_ids:
                continue

            # Check if query matches title or artist (case-insensitive)
            title = song.get("title", "").lower()
            artist = song.get("artist", "").lower()
            
            if query_lower in title or query_lower in artist:
                matching_tracks.append({
                    "id": song_id,
                    "title": song.get("title", ""),
                    "artist": song.get("artist", ""),
                    "album": song.get("album", ""),
                    "genre": song.get("genre", ""),
                    "year": int(song.get("year", 0)),
                    "duration": int(song.get("duration", 0))
                })

                # Stop if we have enough results
                if len(matching_tracks) >= limit:
                    break

        # Sort alphabetically by title, then artist
        matching_tracks.sort(key=lambda x: (x["title"].lower(), x["artist"].lower()))

        logger.info(f"Found {len(matching_tracks)} analyzed tracks matching query '{q}'")
        return {"tracks": matching_tracks}

    except Exception as e:
        logger.error(f"Failed to search tracks: {e}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to search tracks: {str(e)}")

@router.get(
    "/similar/{track_id}",
    summary="Find Similar Tracks",
    description="Find tracks similar to a given track ID"
)
async def find_similar_tracks(
    track_id: str,
    num_tracks: int = 10,
    library_id: Optional[str] = None
):
    """
    Find tracks similar to the specified track.

    Args:
        track_id: ID of the track to find similar tracks for
        num_tracks: Number of similar tracks to return

    Returns:
        List of similar tracks with metadata
    """
    try:
        chroma_service = get_chroma_service()

        # Get seed track embedding
        seed_result = chroma_service.get_embedding(track_id)
        if not seed_result:
            raise HTTPException(
                status_code=404,
                detail=f"Track {track_id} has not been analyzed. Please run a library scan first."
            )

        seed_embedding, seed_metadata = seed_result

        # Find similar tracks (filter by library if specified)
        track_library_id = seed_metadata.get("library_id") or library_id

        similar_tracks = chroma_service.find_similar_tracks(
            query_embedding=seed_embedding,
            n_results=num_tracks,
            exclude_track_ids=[track_id],
            library_id=track_library_id
        )

        return {
            "seed_track": {
                "id": track_id,
                "title": seed_metadata.get("title", ""),
                "artist": seed_metadata.get("artist", ""),
                "album": seed_metadata.get("album", ""),
                "genre": seed_metadata.get("genre", "")
            },
            "similar_tracks": [
                {
                    "id": track["track_id"],
                    "title": track["title"],
                    "artist": track["artist"],
                    "album": track["album"],
                    "genre": track["genre"],
                    "similarity_score": track["similarity_score"]
                }
                for track in similar_tracks
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to find similar tracks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to find similar tracks: {str(e)}")
