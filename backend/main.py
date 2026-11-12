from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, Response
from fastapi import Query
import os
import uvicorn
import os
import json
import logging
import logging.handlers
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# Load environment variables first
load_dotenv()

# Get log level from environment (ERROR=minimal, INFO=normal, DEBUG=verbose)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging for scheduler activities with rotation
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'scheduler.log',
            maxBytes=5*1024*1024,  # 5MB per file
            backupCount=2,         # Keep 2 old files (total ~10MB)
            encoding='utf-8'
        ),
        logging.StreamHandler()  # Also log to console
    ]
)

# Create a specific logger for scheduler activities
scheduler_logger = logging.getLogger('scheduler')
logger = logging.getLogger(__name__)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

from .navidrome_client import NavidromeClient
from .ai_client import AIClient
from .database import DatabaseManager, get_db
from .services.chroma_service import get_chroma_service
from .ai_client import AIClient
from .recipe_manager import recipe_manager
from .schemas import (
    Playlist,
    CreatePlaylistRequest,
    CreateGenrePlaylistRequest,
    CreateRediscoverPlaylistRequest,
    RediscoverWeeklyResponse,
    RediscoverWeeklyV2Response,
    ScheduledPlaylist,
)
from .rediscover import RediscoverWeekly, ReDiscoverV2Processor
from .track_scoring import filter_tracks_for_this_is_playlist
# SYSTEM CHECK FEATURE - START
from .services.health_check_service import HealthCheckService
from .services.library_mapping_service import LibraryMappingService
# SYSTEM CHECK FEATURE - END

# Song Radio API endpoints
from .api.scan_endpoints import router as scan_router
from .api.radio_endpoints import curate_with_ai, format_candidates_for_ai, router as radio_router

app = FastAPI(title="MagicLists Navidrome MVP")

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup"""
    global scheduler, system_check_passed, system_check_results
    
    # Detect local timezone offset
    local_offset = time.timezone if not time.daylight else time.altzone
    local_tz_offset = timedelta(seconds=-local_offset)
    
    # Create scheduler with local timezone awareness
    scheduler = AsyncIOScheduler()
    scheduler.start()
    
    # Log timezone information
    utc_now = datetime.utcnow()
    local_now = utc_now + local_tz_offset
    scheduler_logger.info(f"⏰ System Timezone Detection - UTC: {utc_now.strftime('%H:%M:%S')} | Local: {local_now.strftime('%H:%M:%S')} | Offset: {local_tz_offset}")
    scheduler_logger.info("✅ Scheduler started successfully")
    # Auto-start the cron job
    await start_scheduler_job()
    scheduler_logger.info("✅ Cron job auto-started on application startup")

    # Calculate time to next cron run
    now = datetime.now()
    candidates = [
        now.replace(hour=1, minute=1, second=0, microsecond=0),
        now.replace(hour=13, minute=1, second=0, microsecond=0)
    ]
    next_run = None
    for candidate in candidates:
        if candidate > now:
            next_run = candidate
            break
    if next_run is None:
        # Both today are past, next is tomorrow 1:01 AM
        next_run = (now + timedelta(days=1)).replace(hour=1, minute=1, second=0, microsecond=0)
    time_to_next = next_run - now
    hours, remainder = divmod(int(time_to_next.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    scheduler_logger.info(f"⏰ Time to next run: {hours}h:{minutes}m")
    
    # SYSTEM CHECK FEATURE - START
    # Run system checks on startup
    try:
        health_service = HealthCheckService()
        system_check_results = await health_service.run_checks(is_startup=True)
        system_check_passed = system_check_results.get("all_passed", False)
        
        if system_check_passed:
            scheduler_logger.info("✅ System health checks passed on startup")
        else:
            scheduler_logger.warning("⚠️ System health checks failed on startup - user will be redirected to system check page")
            
        # Log individual check results with enhanced AI provider logging
        for check in system_check_results.get("checks", []):
            status_emoji = "✅" if check["status"] == "success" else "⚠️" if check["status"] == "warning" else "ℹ️" if check["status"] == "info" else "❌"
            
            # Enhanced logging for AI Provider checks
            if "AI Provider" in check["name"]:
                ai_provider = os.getenv("AI_PROVIDER", "openrouter")
                if check["status"] == "success":
                    # Extract model from success message (e.g., "service reachable (model: llama3.2)")
                    if "model:" in check["message"]:
                        model_part = check["message"].split("model: ")[1].rstrip(")")
                        scheduler_logger.info(f"🤖 AI Provider: {ai_provider.title()} with model '{model_part}' - Ready")
                    else:
                        scheduler_logger.info(f"🤖 AI Provider: {ai_provider.title()} - Ready")
                elif check["status"] == "warning":
                    if "not set" in check["message"]:
                        scheduler_logger.info(f"🤖 AI Provider: {ai_provider.title()} - No API key (using fallback algorithms)")
                    else:
                        scheduler_logger.warning(f"🤖 AI Provider: {ai_provider.title()} - {check['message']}")
                elif check["status"] == "error":
                    scheduler_logger.error(f"🤖 AI Provider: {ai_provider.title()} - {check['message']}")
            else:
                # Standard logging for other checks
                scheduler_logger.info(f"{status_emoji} {check['name']}: {check['status']}")
            
    except Exception as e:
        scheduler_logger.error(f"❌ Failed to run system checks on startup: {e}")
        system_check_passed = False
        system_check_results = {
            "all_passed": False,
            "checks": [{
                "name": "System Check Service",
                "status": "error", 
                "message": f"Failed to run health checks: {str(e)}",
                "suggestion": "Check application logs and restart the service"
            }]
        }
    # SYSTEM CHECK FEATURE - END

@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup scheduler on app shutdown"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler_logger.info("🛑 Scheduler shutdown completed")

# Mount static files
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
import os

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")

# Include API routers
app.include_router(scan_router, prefix="/api/scan", tags=["scan"])
app.include_router(radio_router, prefix="/api/radio", tags=["radio"])

# Initialize clients (lazy loading)
navidrome_client = None
ai_client = None

# Initialize scheduler (will be started on app startup)
scheduler = None

# SYSTEM CHECK FEATURE - START
# App state to track system check results
system_check_passed = False
system_check_results = None
# SYSTEM CHECK FEATURE - END

def get_navidrome_client():
    global navidrome_client
    if navidrome_client is None:
        navidrome_client = NavidromeClient()
    return navidrome_client

def get_ai_client():
    global ai_client
    if ai_client is None:
        ai_client = AIClient()
    return ai_client

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main HTML page"""
    # SYSTEM CHECK FEATURE - START
    # Redirect to system check if checks haven't passed
    if not system_check_passed:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/system-check", status_code=302)
    # SYSTEM CHECK FEATURE - END
    
    return templates.TemplateResponse("index.html", {"request": request})

# SYSTEM CHECK FEATURE - START
@app.get("/system-check", response_class=HTMLResponse)
async def system_check_page(request: Request):
    """Serve the system check page"""
    return templates.TemplateResponse("index.html", {"request": request})
# SYSTEM CHECK FEATURE - END

@app.get("/api/artists")
async def get_artists(library_id: List[str] = Query(None)):
    """Get list of artists from Navidrome"""
    try:
        client = get_navidrome_client()
        artists = await client.get_artists(library_id)
        return artists
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch artists: {error_msg}")

@app.get("/api/genres")
async def get_genres(library_id: List[str] = Query(None), db: DatabaseManager = Depends(get_db)):
    """Get list of genres from Navidrome with caching"""
    try:
        client = get_navidrome_client()

        # Create cache key
        import hashlib
        library_ids = library_id or []
        library_ids_hash = hashlib.md5(",".join(sorted(library_ids)).encode()).hexdigest()
        server_id = client.base_url or "unknown_server"

        print(f"🎵 get_genres called with library_ids: {library_ids}, hash: {library_ids_hash[:8]}...")

        # DISABLE CACHE TEMPORARILY FOR DEBUGGING
        print(f"🚫 Genre cache disabled for debugging")
        cached_data = None

        # Cache miss or invalid - rebuild cache
        print("🔄 Building fresh genre cache...")
        cache_data = await client.build_genre_cache(library_ids if library_ids else None, db)
        print(f"📊 Built cache with {len(cache_data['libraries'])} libraries: {list(cache_data['libraries'].keys())}")

        # Return formatted response
        result = await _format_genre_cache_response(cache_data, library_ids)
        print(f"📋 Returning {len(result)} genres from fresh build: {[g['name'] for g in result[:3]]}...")
        return result

    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch genres: {error_msg}")

async def _format_genre_cache_response(cache_data: Dict[str, Any], requested_library_ids: List[str]) -> List[Dict[str, Any]]:
    """Format cached genre data into the expected API response format"""
    try:
        genres_dict = {}

        # Aggregate genres from requested libraries
        libraries_to_check = requested_library_ids if requested_library_ids else list(cache_data["libraries"].keys())
        print(f"🔍 Formatting cache response for libraries: {libraries_to_check}")

        for lib_id in libraries_to_check:
            if lib_id in cache_data["libraries"]:
                lib_data = cache_data["libraries"][lib_id]
                print(f"📊 Library {lib_id}: {len(lib_data['genres'])} genres")
                for genre_name, count in lib_data["genres"].items():
                    if genre_name in genres_dict:
                        genres_dict[genre_name] += count
                    else:
                        genres_dict[genre_name] = count

        # Convert to list format expected by frontend
        genres = [{"name": name, "songCount": count} for name, count in genres_dict.items() if count > 0]
        genres.sort(key=lambda x: x["name"])

        print(f"📋 Formatted {len(genres)} total genres: {[g['name'] for g in genres[:3]]}...")
        return genres

    except Exception as e:
        print(f"❌ Error formatting genre cache response: {e}")
        return []

@app.get("/api/libraries")
async def get_libraries():
    """Get list of music libraries from Navidrome"""
    try:
        client = get_navidrome_client()
        libraries = await client.get_music_folders()
        return libraries
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch libraries: {error_msg}")

@app.get("/api/libraries/{library_id}/stats")
async def get_library_stats(library_id: str):
    """Get statistics for a specific library"""
    try:
        from .services.library_scanner import get_library_scanner
        scanner = get_library_scanner()
        client = get_navidrome_client()

        # Try to get total tracks from cache first (much faster and accurate)
        cache_data = await scanner._load_track_cache(client)
        total_tracks = 0
        if cache_data and 'track_count' in cache_data:
            total_tracks = cache_data['track_count']
            logger.info(f"📊 Using cached track count for library stats: {total_tracks} tracks")
        else:
            # Fallback to API call if no cache
            logger.warning("No track cache available, falling back to Navidrome API for library stats")
            total_tracks = await client.get_library_song_count(library_id)

        # Get artists count for this library
        artists = await client.get_artists(library_ids=[library_id])
        total_artists = len(artists)

        # Get genres count (genres are global, not per library)
        genres = await client.get_genres()
        total_genres = len(genres)

        return {
            "library_id": library_id,
            "total_tracks": total_tracks,
            "total_artists": total_artists,
            "total_genres": total_genres
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to get library stats for {library_id}: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Failed to get library statistics: {error_msg}")

@app.get("/api/music-folders")
async def get_music_folders():
    """Get list of music folders/libraries from Navidrome (legacy endpoint)"""
    return await get_libraries()

@app.get("/api/tracks")
async def get_tracks(library_ids: List[str] = Query(None)):
    """Get all tracks from Navidrome, optionally filtered by library IDs"""
    try:
        client = get_navidrome_client()
        tracks = await client.get_tracks(library_ids=library_ids)
        return {"tracks": tracks}
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch tracks: {error_msg}")

@app.get("/api/tracks/count")
async def get_tracks_count(library_ids: List[str] = Query(None)):
    """Get cached track count for libraries (used for UI display to avoid expensive API calls)"""
    try:
        from .services.library_scanner import get_library_scanner
        scanner = get_library_scanner()
        client = get_navidrome_client()

        # Try to get cached track count
        cache_data = await scanner._load_track_cache(client)
        if cache_data and 'track_count' in cache_data:
            total_tracks = cache_data['track_count']
            logger.info(f"📊 Returning cached track count: {total_tracks} tracks")
            return {"total_tracks": total_tracks, "cached": True}

        # Fallback to Navidrome API if no cache
        logger.warning("No track cache available, falling back to Navidrome API")
        tracks = await client.get_tracks(library_ids=library_ids)
        return {"total_tracks": len(tracks), "cached": False}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to get track count: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Failed to get track count: {error_msg}")

@app.post("/api/cache/invalidate")
async def invalidate_track_cache():
    """Invalidate the track metadata cache (useful when library changes)"""
    try:
        from .services.library_scanner import get_library_scanner
        import os
        scanner = get_library_scanner()
        client = get_navidrome_client()

        # Remove cache file
        cache_key = scanner._get_cache_key(client)
        cache_path = scanner._get_cache_path(cache_key)

        if cache_path.exists():
            cache_path.unlink()
            logger.info(f"🗑️ Invalidated track cache: {cache_path}")
            return {"message": "Cache invalidated successfully"}
        else:
            return {"message": "No cache file found to invalidate"}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to invalidate cache: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {error_msg}")

@app.get("/api/starred")
async def get_starred_tracks(library_ids: List[str] = Query(None)):
    """Get starred tracks from Navidrome (used as sample tracks for radio)"""
    try:
        client = get_navidrome_client()
        tracks = await client.get_starred(library_ids=library_ids)
        return tracks
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch starred tracks: {error_msg}")


# SYSTEM CHECK FEATURE - START
@app.get("/api/health-check")
async def get_health_check():
    """Get system health check results"""
    global system_check_passed, system_check_results
    
    try:
        # Run fresh health checks
        health_service = HealthCheckService()
        fresh_results = await health_service.run_checks()
        
        # Update app state with fresh results
        system_check_passed = fresh_results.get("all_passed", False)
        system_check_results = fresh_results
        
        # Log the result
        if system_check_passed:
            scheduler_logger.info("✅ System health checks passed via API")
        else:
            scheduler_logger.warning("⚠️ System health checks failed via API")
        
        return fresh_results
        
    except Exception as e:
        scheduler_logger.error(f"❌ Failed to run health checks via API: {e}")
        error_results = {
            "all_passed": False,
            "checks": [{
                "name": "System Check Service",
                "status": "error",
                "message": f"Failed to run health checks: {str(e)}",
                "suggestion": "Check application logs and restart the service"
            }]
        }
        return error_results
# SYSTEM CHECK FEATURE - END
@app.post("/api/create_playlist", response_model=Playlist)
async def create_playlist(
    request: CreatePlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated 'This Is' playlist for a single artist"""
    try:
        # Debug: Log what we received
        scheduler_logger.info(f"DEBUG: include_mentions value = {request.include_mentions}")
        
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()
        
        # Get artist info
        all_artists = await nav_client.get_artists()
        selected_artists = [a for a in all_artists if a["id"] in request.artist_ids]
        
        if not selected_artists:
            raise HTTPException(status_code=404, detail="Artists not found")
        
        # Limit to single artist only - use first artist from the request
        if request.artist_ids:
            first_artist_id = request.artist_ids[0]
            selected_artists = [a for a in all_artists if a["id"] == first_artist_id]
            artist_names = [a["name"] for a in selected_artists]
        else:
            raise HTTPException(status_code=400, detail="At least one artist must be selected")

        # Generate playlist name if not provided - for single artist
        playlist_name = request.playlist_name or f"This is {artist_names[0]}"
        
        # Get tracks for only the first artist
        all_tracks = []
        
        # Check if we should include artist mentions (features, collaborations, etc.)
        if request.include_mentions:
            scheduler_logger.info(f"🔍 Searching for artist mentions (including collaborations)")
            tracks = await nav_client.search_artist_mentions(artist_names[0], request.library_ids)
        else:
            scheduler_logger.info(f"🎯 Using exact artist match only")
            tracks = await nav_client.get_tracks_by_artist(first_artist_id, request.library_ids)
        
        if tracks:
            all_tracks.extend(tracks)
        
        if not all_tracks:
            raise HTTPException(status_code=404, detail="No tracks found for the selected artists")
        
        # NEW: Apply smart filtering for "This Is" playlists to optimize LLM payload
        library_stats = await nav_client.get_library_stats()
        
        filtered_tracks, filter_metadata = filter_tracks_for_this_is_playlist(
            source_tracks=all_tracks,
            target_playlist_size=request.playlist_length,
            library_stats=library_stats
        )
        
        # Log filtering results for analytics/debugging
        if filter_metadata['filtered']:
            scheduler_logger.info(f"🎯 Smart filtering applied: {filter_metadata['source_count']} → {filter_metadata['sent_count']} tracks (multiplier: {filter_metadata['threshold_multiplier']}x)")
            scheduler_logger.info(f"📊 Score range: {filter_metadata['score_range']['highest']:.1f} - {filter_metadata['score_range']['lowest']:.1f} (cutoff: {filter_metadata['score_range']['cutoff']:.1f})")
        else:
            scheduler_logger.info(f"✅ No filtering needed: {filter_metadata['source_count']} tracks below threshold")
        
        # Use filtered tracks for LLM processing
        tracks_for_llm = filtered_tracks
        
        # Use AI to curate the playlist (always include reasoning for new recipe format)
        curation_result = await ai_client_instance.curate_this_is(
            artist_name=', '.join(artist_names),
            tracks_json=tracks_for_llm,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        
        # Handle both old and new return formats
        if isinstance(curation_result, tuple):
            curated_track_ids, reasoning = curation_result
        else:
            curated_track_ids = curation_result
            reasoning = ""

        # Check for validation failures or empty results
        if not curated_track_ids:
            if reasoning and "Playlist generation failed" in reasoning:
                # This is a validation failure - don't create playlist
                scheduler_logger.error(f"❌ Playlist creation aborted: {reasoning}")
                raise HTTPException(status_code=400, detail=f"Playlist generation failed: {reasoning}")
            else:
                # This is an empty result without explanation
                scheduler_logger.error(f"❌ AI curation returned no tracks for {', '.join(artist_names)}")
                raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        # Log the AI reasoning for debugging (truncated)
        if reasoning:
            reasoning_preview = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            scheduler_logger.info(f"🎵 AI curation applied for {', '.join(artist_names)} (reasoning length: {len(reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ No AI reasoning provided for {', '.join(artist_names)}")

        # Create playlist in Navidrome with AI reasoning as comment
        comment_to_use = reasoning if reasoning else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=curated_track_ids,
            comment=comment_to_use
        )
        
        # Get track titles for database storage - PRESERVE AI CURATION ORDER
        # Note: Use all_tracks for mapping since AI might reference tracks from full set
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
        for track_id in curated_track_ids:  # Iterate in AI-curated order
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])
        
        
        # Store playlist in local database (using the first artist_id for now)
        playlist = await db.create_playlist(
            artist_id=request.artist_ids[0],
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )
        
        # Handle scheduling if not "none" or "never"
        if request.refresh_frequency not in ["none", "never"]:
            next_refresh = calculate_next_refresh(request.refresh_frequency)
            
            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="this_is",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )
            
            # Schedule the refresh job
            schedule_playlist_refresh()
            scheduler_logger.info(f"📅 Scheduled {request.refresh_frequency} refresh for This Is playlist: {playlist_name}")
        
        # Add Navidrome playlist ID to response
        playlist_dict = playlist.dict() if hasattr(playlist, 'dict') else playlist.__dict__
        playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
        playlist_dict["refresh_frequency"] = request.refresh_frequency
        
        if request.refresh_frequency != "none":
            playlist_dict["next_refresh"] = calculate_next_refresh(request.refresh_frequency).isoformat()
        
        return playlist_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playlist: {str(e)}")

@app.post("/api/create_playlist_with_reasoning")
async def create_playlist_with_reasoning(
    request: CreatePlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated 'This Is' playlist with AI reasoning explanation"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()
        
        # Get artist info - use first artist from the array
        artists = await nav_client.get_artists()
        if not request.artist_ids or len(request.artist_ids) == 0:
            raise HTTPException(status_code=400, detail="At least one artist must be selected")
        first_artist_id = request.artist_ids[0]
        artist = next((a for a in artists if a["id"] == first_artist_id), None)
        
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")
        
        artist_name = artist["name"]
        
        # Generate playlist name if not provided
        playlist_name = getattr(request, 'playlist_name', None) or f"This is  {artist_name}"
        
        # Get tracks for the artist
        tracks = await nav_client.get_tracks_by_artist(first_artist_id)
        
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found for this artist")
        
        # Use AI to curate the playlist WITH reasoning
        curated_track_ids, reasoning = await ai_client_instance.curate_this_is(
            artist_name=artist_name,
            tracks_json=tracks,
            num_tracks=20,
            include_reasoning=True
        )

        # Create playlist in Navidrome with AI reasoning as comment
        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=curated_track_ids,
            comment=reasoning if reasoning else None
        )
        
        # Get track titles for database storage
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in tracks}
        for track_id in curated_track_ids:
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])
        
        # Store playlist in local database
        playlist = await db.create_playlist(
            artist_id=first_artist_id,
            playlist_name=playlist_name,
            songs=track_titles,
            navidrome_playlist_id=navidrome_playlist_id,
            library_ids=request.library_ids if hasattr(request, 'library_ids') else []
        )
        
        # Add Navidrome playlist ID and AI reasoning to response
        playlist_dict = playlist.dict() if hasattr(playlist, 'dict') else playlist.__dict__
        playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
        playlist_dict["ai_reasoning"] = reasoning
        
        return playlist_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playlist with reasoning: {str(e)}")

@app.post("/api/create_genre_playlist")
async def create_genre_playlist(
    request: CreateGenrePlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated 'Genre Mix' playlist for a specific genre"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        # Generate playlist name if not provided
        playlist_name = request.playlist_name or f"Genre Mix: {request.genre}"

        # Get tracks for the genre
        scheduler_logger.info(f"🎵 Request: genre='{request.genre}', library_ids={request.library_ids}")
        all_tracks = await nav_client.get_tracks_by_genre(request.genre, request.library_ids)
        scheduler_logger.info(f"🎵 Found {len(all_tracks)} total tracks for genre '{request.genre}'")

        if not all_tracks:
            raise HTTPException(status_code=404, detail=f"No tracks found for genre: {request.genre}")

        # NEW: Apply smart filtering for "Genre Mix" playlists to optimize LLM payload
        library_stats = await nav_client.get_library_stats()

        filtered_tracks, filter_metadata = filter_tracks_for_this_is_playlist(
            source_tracks=all_tracks,
            target_playlist_size=request.playlist_length,
            library_stats=library_stats
        )

        # Log filtering results for analytics/debugging
        if filter_metadata['filtered']:
            scheduler_logger.info(f"🎯 Smart filtering applied: {filter_metadata['source_count']} → {filter_metadata['sent_count']} tracks (multiplier: {filter_metadata['threshold_multiplier']}x)")
            scheduler_logger.info(f"📊 Score range: {filter_metadata['score_range']['highest']:.1f} - {filter_metadata['score_range']['lowest']:.1f} (cutoff: {filter_metadata['score_range']['cutoff']:.1f})")
        else:
            scheduler_logger.info(f"✅ No filtering needed: {filter_metadata['source_count']} tracks below threshold")

        # Use filtered tracks for LLM processing
        tracks_for_llm = filtered_tracks

        # Use AI to curate the playlist (always include reasoning for new recipe format)
        curation_result = await ai_client_instance.curate_genre_mix(
            genre=request.genre,
            tracks_json=tracks_for_llm,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )

        # Handle both old and new return formats
        if isinstance(curation_result, tuple):
            curated_track_ids, reasoning = curation_result
        else:
            curated_track_ids = curation_result
            reasoning = ""

        # Check for validation failures or empty results
        if not curated_track_ids:
            if reasoning and "Playlist generation failed" in reasoning:
                # This is a validation failure - don't create playlist
                scheduler_logger.error(f"❌ Playlist creation aborted: {reasoning}")
                raise HTTPException(status_code=400, detail=f"Playlist generation failed: {reasoning}")
            else:
                # This is an empty result without explanation
                scheduler_logger.error(f"❌ AI curation returned no tracks for {request.genre}")
                raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        # Log the AI reasoning for debugging (truncated)
        if reasoning:
            reasoning_preview = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            scheduler_logger.info(f"🎵 AI curation applied for {request.genre} (reasoning length: {len(reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ No AI reasoning provided for {request.genre}")

        # Create playlist in Navidrome with AI reasoning as comment
        comment_to_use = reasoning if reasoning else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=curated_track_ids,
            comment=comment_to_use
        )

        # Get track titles for database storage
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
        for track_id in curated_track_ids:  # Iterate in AI-curated order
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])


        # Store playlist in local database (using genre as identifier)
        playlist = await db.create_playlist(
            artist_id=request.genre,  # Using genre as artist_id for now
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        if not playlist:
            scheduler_logger.error(f"❌ Failed to store genre playlist in database: {playlist_name}")
            raise HTTPException(status_code=500, detail="Failed to store playlist in database")

        # Handle scheduling if not "none" or "never"
        if request.refresh_frequency not in ["none", "never"]:
            next_refresh = calculate_next_refresh(request.refresh_frequency)

            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="genre_mix",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )

        # Add Navidrome playlist ID and other fields to response for consistency
        playlist_dict = {
            "id": playlist.id,
            "artist_id": playlist.artist_id,
            "playlist_name": playlist.playlist_name,
            "name": playlist_name,  # Add name field for frontend consistency
            "songs": playlist.songs,
            "reasoning": playlist.reasoning,
            "navidrome_playlist_id": navidrome_playlist_id,
            "library_ids": playlist.library_ids,
            "created_at": playlist.created_at,
            "updated_at": playlist.updated_at,
            "refresh_frequency": request.refresh_frequency
        }
        
        if request.refresh_frequency != "none":
            playlist_dict["next_refresh"] = calculate_next_refresh(request.refresh_frequency).isoformat()

        return playlist_dict

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create genre playlist: {str(e)}")

@app.get("/api/rediscover-weekly", response_model=RediscoverWeeklyResponse)
async def get_rediscover_weekly():
    """Generate Re-Discover Weekly playlist based on listening history"""
    try:
        # Get Navidrome client
        nav_client = get_navidrome_client()
        
        # Create RediscoverWeekly instance
        rediscover = RediscoverWeekly(nav_client)
        
        # Generate the playlist with AI curation
        tracks = await rediscover.generate_rediscover_weekly(use_ai=True)
        
        # Extract AI curation info for response
        ai_curated = tracks[0].get("ai_curated", False) if tracks else False
        message = f"Generated Re-Discover Weekly with {len(tracks)} tracks"
        if ai_curated:
            message += " (AI curated)"
        else:
            message += " (algorithmic selection)"
        
        return RediscoverWeeklyResponse(
            tracks=tracks,
            total_tracks=len(tracks),
            message=message
        )
        
    except Exception as e:
        error_msg = str(e)
        if "No listening history found" in error_msg:
            raise HTTPException(status_code=404, detail="No listening history found. Make sure you've played some music in Navidrome.")
        elif "No tracks found for re-discovery" in error_msg:
            raise HTTPException(status_code=404, detail="No tracks found for re-discovery. Try listening to more music first.")
        elif "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to generate Re-Discover Weekly: {error_msg}")

@app.get("/api/rediscover-weekly-v2", response_model=RediscoverWeeklyV2Response)
async def get_rediscover_weekly_v2(library_ids: Optional[List[str]] = Query(None), db: DatabaseManager = Depends(get_db)):
    """Generate Re-Discover Weekly v2.0 playlist using temporal analysis and two-phase AI"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client = get_ai_client()

        # Get user and server IDs
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"  # Use base URL as server identifier

        # Create ReDiscoverV2Processor instance
        processor = ReDiscoverV2Processor(nav_client, ai_client, db)

        # Generate the playlist
        result = await processor.generate_playlist(user_id, server_id, library_ids)

        return RediscoverWeeklyV2Response(**result)

    except Exception as e:
        error_msg = str(e)
        if "Insufficient listening history" in error_msg:
            raise HTTPException(status_code=404, detail="Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!")
        elif "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to generate Re-Discover Weekly v2.0: {error_msg}")

@app.post("/api/create-rediscover-playlist-v2")
async def create_rediscover_playlist_v2(
    request: CreateRediscoverPlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create a Re-Discover Weekly v2.0 playlist in Navidrome"""
    try:
        scheduler_logger.info(f"🎵 Starting Re-Discover v2.0 playlist creation with length {request.playlist_length}, library_id: {request.library_id}")

        # Get clients
        nav_client = get_navidrome_client()
        ai_client = get_ai_client()

        # Get user and server IDs
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"

        # Create ReDiscoverV2Processor instance
        processor = ReDiscoverV2Processor(nav_client, ai_client, db)

        # Generate the playlist
        playlist_data = await processor.generate_playlist(user_id, server_id, [request.library_id])
        tracks = playlist_data.get("tracks", [])

        if not tracks:
            scheduler_logger.error("❌ No tracks generated for Re-Discover Weekly v2.0")
            raise HTTPException(status_code=404, detail="No tracks found for Re-Discover Weekly v2.0")

        scheduler_logger.info(f"✅ Generated {len(tracks)} tracks for Re-Discover Weekly v2.0")

        # Extract AI reasoning if available
        ai_reasoning = playlist_data.get("reasoning", "")
        ai_curated = any(track.get("ai_curated", False) for track in tracks)

        # If AI curated, get reasoning from the tracks instead of Phase 1
        if ai_curated:
            track_reasoning = next((track.get("ai_reasoning", "") for track in tracks if track.get("ai_curated", False) and track.get("ai_reasoning")), "")
            if track_reasoning:
                ai_reasoning = track_reasoning

        scheduler_logger.info(f"🎵 AI curated: {ai_curated}, reasoning length: {len(ai_reasoning)}")

        # Log the AI reasoning for debugging (truncated)
        if ai_reasoning and ai_curated:
            reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
            scheduler_logger.info(f"🎵 AI curation applied for Re-Discover Weekly v2.0 (reasoning length: {len(ai_reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ Re-Discover Weekly v2.0 used fallback strategy")

        # Create playlist name based on refresh frequency
        frequency_names = {
            "daily": "Re-Discover Daily ✨",
            "weekly": "Re-Discover Weekly ✨",
            "monthly": "Re-Discover Monthly ✨",
            "never": "Re-Discover ✨"
        }
        playlist_name = frequency_names.get(request.refresh_frequency, "Re-Discover Weekly ✨")
        if playlist_data.get("is_fallback"):
            playlist_name += " (Fallback)"
        scheduler_logger.info(f"📝 Creating playlist: {playlist_name}")

        # Extract track IDs
        track_ids = [track["id"] for track in tracks]
        scheduler_logger.info(f"🎵 Track IDs: {track_ids[:5]}... (total: {len(track_ids)})")

        # Create playlist in Navidrome with reasoning as comment
        comment_to_use = ai_reasoning if ai_reasoning else f"Theme: {playlist_data.get('theme', 'Mixed')}"
        comment_preview = comment_to_use[:200] + "..." if len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating Re-Discover v2.0 playlist with comment (length: {len(comment_to_use)}): {comment_preview}")

        scheduler_logger.info("🎵 Calling nav_client.create_playlist...")
        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=track_ids,
            comment=comment_to_use
        )
        scheduler_logger.info(f"✅ Navidrome playlist created: {navidrome_playlist_id}")

        # Get track titles for database storage
        track_titles = [track.get("title", "Unknown") for track in tracks]
        scheduler_logger.info(f"📊 Storing {len(track_titles)} track titles in database")

        # Store playlist in local database (using a synthetic artist_id for rediscover playlists)
        playlist_record = await db.create_playlist(
            artist_id="rediscover_v2",
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=ai_reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=len(tracks),
            library_ids=[request.library_id]
        )
        scheduler_logger.info(f"💾 Database playlist created: {playlist_record}")

        # Set up scheduling if requested
        if request.refresh_frequency != "never":
            scheduler_logger.info(f"⏰ Setting up {request.refresh_frequency} refresh schedule")
            scheduled_playlist = await db.create_scheduled_playlist(
                playlist_type="rediscover_weekly_v2",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )
            scheduler_logger.info(f"✅ Scheduled playlist created: {scheduled_playlist}")
        else:
            scheduler_logger.info("⏰ No scheduling requested (refresh_frequency='never')")

        return {
            "message": f"Re-Discover Weekly v2.0 playlist created successfully with {len(tracks)} tracks",
            "playlist_id": navidrome_playlist_id,
            "track_count": len(tracks),
            "theme": playlist_data.get("theme", "Mixed"),
            "mode": playlist_data.get("mode", "Unknown"),
            "is_fallback": playlist_data.get("is_fallback", False)
        }

    except HTTPException:
        raise
    except Exception as e:
        scheduler_logger.error(f"❌ Failed to create Re-Discover Weekly v2.0 playlist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Re-Discover Weekly v2.0 playlist: {str(e)}")

@app.post("/api/create-rediscover-playlist")
async def create_rediscover_playlist(
    request: CreateRediscoverPlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create a Re-Discover Weekly playlist in Navidrome"""
    try:
        scheduler_logger.info(f"🎵 Starting Re-Discover playlist creation with length {request.playlist_length}, library_id: {request.library_id}")

        # Get Navidrome client
        nav_client = get_navidrome_client()

        # Create RediscoverWeekly instance
        rediscover = RediscoverWeekly(nav_client)

        # Generate the playlist tracks with user-specified length and AI curation
        scheduler_logger.info("🎵 Generating rediscover tracks...")
        tracks = await rediscover.generate_rediscover_weekly(max_tracks=request.playlist_length, use_ai=True, library_id=request.library_id, variety_context="")
        scheduler_logger.info(f"🎵 Generated {len(tracks) if tracks else 0} tracks")
        
        if not tracks:
            scheduler_logger.error("❌ No tracks generated for Re-Discover Weekly")
            raise HTTPException(status_code=404, detail="No tracks found for Re-Discover Weekly")

        scheduler_logger.info(f"✅ Generated {len(tracks)} tracks for Re-Discover Weekly")

        # Extract AI reasoning if available
        ai_reasoning = ""
        ai_curated = False
        if tracks:
            first_track = tracks[0]
            ai_reasoning = first_track.get("ai_reasoning", "")
            ai_curated = first_track.get("ai_curated", False)
            scheduler_logger.info(f"🎵 AI curated: {ai_curated}, reasoning length: {len(ai_reasoning)}")
        
        # Log the AI reasoning for debugging (truncated)
        if ai_reasoning and ai_curated:
            reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
            scheduler_logger.info(f"🎵 AI curation applied for Re-Discover Weekly (reasoning length: {len(ai_reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ Re-Discover Weekly used algorithmic selection (no AI reasoning)")
        
        # Create playlist name based on frequency
        frequency_names = {
            "daily": "Re-Discover Daily ✨",
            "weekly": "Re-Discover Weekly ✨",
            "monthly": "Re-Discover Monthly ✨",
            "never": "Re-Discover ✨"
        }
        playlist_name = frequency_names.get(request.refresh_frequency, "Re-Discover Weekly ✨")
        scheduler_logger.info(f"📝 Creating playlist: {playlist_name}")

        # Extract track IDs
        track_ids = [track["id"] for track in tracks]
        scheduler_logger.info(f"🎵 Track IDs: {track_ids[:5]}... (total: {len(track_ids)})")

        # Create playlist in Navidrome with AI reasoning as comment if available
        comment_to_use = ai_reasoning if (ai_reasoning and ai_curated) else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating Re-Discover playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        scheduler_logger.info("🎵 Calling nav_client.create_playlist...")
        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=track_ids,
            comment=comment_to_use
        )
        scheduler_logger.info(f"✅ Navidrome playlist created: {navidrome_playlist_id}")
        
        # Get track titles for database storage
        track_titles = [track["title"] for track in tracks]
        scheduler_logger.info(f"📊 Storing {len(track_titles)} track titles in database")

        # Store playlist in local database (using a synthetic artist_id for rediscover playlists)
        scheduler_logger.info("💾 Creating playlist in database...")
        playlist = await db.create_playlist(
            artist_id="rediscover",
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=ai_reasoning if ai_curated else "Algorithmic selection",
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=[request.library_id]
        )
        scheduler_logger.info(f"✅ Database playlist created: {playlist}")
        
        # Handle scheduling if not "never"
        if request.refresh_frequency != "never":
            next_refresh = calculate_next_refresh(request.refresh_frequency)
            
            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="rediscover",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )
            
            # Schedule the refresh job
            schedule_playlist_refresh()
            scheduler_logger.info(f"📅 Scheduled {request.refresh_frequency} refresh for playlist: {playlist_name}")
        else:
            scheduler_logger.info(f"📅 No scheduling for playlist: {playlist_name} (refresh frequency: never)")
        
        # Add Navidrome playlist ID to response
        playlist_dict = playlist.dict() if hasattr(playlist, 'dict') else playlist.__dict__
        playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
        playlist_dict["tracks"] = tracks
        playlist_dict["refresh_frequency"] = request.refresh_frequency
        playlist_dict["next_refresh"] = calculate_next_refresh(request.refresh_frequency).isoformat()
        
        return playlist_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Re-Discover Weekly playlist: {str(e)}")

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


def schedule_playlist_refresh():
    """Schedule the playlist refresh job to run every 12 hours in local time"""
    if not scheduler.get_job('playlist_refresh'):
        # Detect local timezone offset to convert desired local times to UTC
        local_offset = time.timezone if not time.daylight else time.altzone
        local_tz_offset = timedelta(seconds=-local_offset)
        
        # TEST MODE: Uncomment the lines below to test at 8:15-8:17 PM today
        # Comment out the production times and uncomment test times
        TEST_MODE = os.getenv("SCHEDULER_TEST_MODE", "false").lower() == "true"
        
        if TEST_MODE:
            # Test times: 8:20 PM today (for testing)
            local_time_test = timedelta(hours=20, minutes=20)
            utc_time_test = (local_time_test - local_tz_offset).total_seconds() / 3600
            utc_hour_test = int(utc_time_test) % 24
            utc_minute_test = int((utc_time_test * 60) % 60)

            scheduler.add_job(
                refresh_scheduled_playlists,
                'cron',
                hour=utc_hour_test,  # Run at converted UTC hour
                minute=f'{utc_minute_test}-{utc_minute_test + 2}',  # Run for 3 minutes (8:20-8:22)
                id='playlist_refresh',
                replace_existing=True
            )
            scheduler_logger.info(f"🧪 TEST MODE: Playlist refresh job scheduled - Local time 8:20 PM → UTC hour {utc_hour_test}:{utc_minute_test:02d}-{utc_minute_test+2:02d}")
        else:
            # Production times: 1:01 AM and 1:01 PM
            local_time_1am = timedelta(hours=1, minutes=1)
            local_time_1pm = timedelta(hours=13, minutes=1)

            # Convert to UTC by subtracting the offset
            utc_time_1am = (local_time_1am - local_tz_offset).total_seconds() / 3600
            utc_time_1pm = (local_time_1pm - local_tz_offset).total_seconds() / 3600

            # Handle day wrapping
            utc_hour_1am = int(utc_time_1am) % 24
            utc_hour_1pm = int(utc_time_1pm) % 24
            utc_minute = int((utc_time_1am * 60) % 60)

            scheduler.add_job(
                refresh_scheduled_playlists,
                'cron',
                hour=f'{utc_hour_1am},{utc_hour_1pm}',  # Run at converted UTC hours
                minute=utc_minute,
                id='playlist_refresh',
                replace_existing=True
            )
            scheduler_logger.info(f"🔄 Playlist refresh job scheduled - Local times 1:01 AM & 1:01 PM → UTC hours {utc_hour_1am}:{utc_minute:02d} & {utc_hour_1pm}:{utc_minute:02d}")

async def refresh_scheduled_playlists():
    """Check for and refresh scheduled playlists that are due"""
    try:
        current_time = datetime.now()
        
        # Only log heartbeat in DEBUG mode, always log when tasks are found
        if LOG_LEVEL == "DEBUG":
            scheduler_logger.debug(f"🔄 Scheduler auto-run initiated at {current_time.strftime('%H:%M:%S')}")
        
        if LOG_LEVEL == "DEBUG":
            scheduler_logger.debug("🔍 Checking for playlists due for refresh...")
        else:
            scheduler_logger.info("🔍 Checking for playlists due for refresh...")
        
        # Get database path from environment variable with smart defaults
        # Docker: /app/data/magiclists.db (set in docker-compose.yml)
        # Standalone: ./magiclists.db (current directory)
        default_path = "/app/data/magiclists.db" if os.path.exists("/app/data") else "./magiclists.db"
        db_path = os.getenv("DATABASE_PATH", default_path)
        db = DatabaseManager(db_path)
        current_time = datetime.now()
        
        # Get playlists due for refresh (including 7-day catch-up window)
        scheduled_playlists = await db.get_scheduled_playlists_due(current_time, grace_hours=168)
        
        if not scheduled_playlists:
            if LOG_LEVEL == "DEBUG":
                scheduler_logger.debug("✅ No playlists due for refresh at this time")
            return
        
        # Group by navidrome_playlist_id to prevent duplicate processing
        # Only process the most recent overdue refresh for each playlist
        unique_playlists = {}
        for playlist in scheduled_playlists:
            playlist_id = playlist.navidrome_playlist_id
            if playlist_id not in unique_playlists:
                unique_playlists[playlist_id] = playlist
            else:
                # Keep the more recent one (closer to current time)
                existing = datetime.fromisoformat(unique_playlists[playlist_id].next_refresh)
                current = datetime.fromisoformat(playlist.next_refresh)
                if current > existing:
                    unique_playlists[playlist_id] = playlist
        
        final_playlists = list(unique_playlists.values())
        
        scheduler_logger.info(f"📋 Found {len(final_playlists)} playlist(s) due for refresh (deduplicated from {len(scheduled_playlists)} total)")
        
        for scheduled_playlist in final_playlists:
            # Check if this is a catch-up refresh
            scheduled_time = datetime.fromisoformat(scheduled_playlist.next_refresh)
            if scheduled_time < current_time:
                overdue_hours = (current_time - scheduled_time).total_seconds() / 3600
                scheduler_logger.info(f"🕐 Catching up on overdue playlist {scheduled_playlist.navidrome_playlist_id} (missed by {overdue_hours:.1f} hours)")
            
            if scheduled_playlist.playlist_type == "rediscover":
                await refresh_rediscover_playlist(scheduled_playlist, db)
            elif scheduled_playlist.playlist_type == "this_is":
                await refresh_this_is_playlist(scheduled_playlist, db)
            elif scheduled_playlist.playlist_type == "genre_mix":
                await refresh_genre_mix_playlist(scheduled_playlist, db)
            elif scheduled_playlist.playlist_type == "song_radio":
                await refresh_song_radio_playlist(scheduled_playlist, db)
                
    except Exception as e:
        scheduler_logger.error(f"❌ Error checking scheduled playlists: {e}")

async def refresh_rediscover_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a specific Re-Discover Weekly playlist"""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for playlist ID: {scheduled_playlist.navidrome_playlist_id} (frequency: {scheduled_playlist.refresh_frequency})")
        
        # Get clients
        nav_client = get_navidrome_client()
        
        # Get original playlist to find user's preferred length
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return
        
        # Get original playlist length (MUST respect user's choice)
        original_length = original_playlist.get("playlist_length", 20)
        scheduler_logger.info(f"🎯 Using original playlist length: {original_length}")
        
        # Get previous playlist songs for variety context
        previous_songs = original_playlist.get("songs", [])[:10]
        variety_instruction = f"REFRESH CHALLENGE: The current playlist opens with these tracks in this order: {', '.join(previous_songs[:5])}. Your goal is to create a FRESH arrangement that tells a different musical story. You may include some of the same excellent tracks if they're rediscovery-worthy, but avoid replicating the same opening sequence or overall flow. Think creatively about re-ordering, substituting, or finding better transitions to ensure a genuinely refreshed listening experience." if previous_songs else ""
        
        # Get AI client for v2.0 processor
        ai_client = get_ai_client()

        # Get user and server IDs for v2.0 processor
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"

        # Create ReDiscoverV2Processor instance (improved fallback handling)
        processor = ReDiscoverV2Processor(nav_client, ai_client, db)

        # Prepare library IDs for v2.0 processor
        library_ids = [scheduled_playlist.library_id] if hasattr(scheduled_playlist, 'library_id') and scheduled_playlist.library_id else None

        # Log refresh context for debugging
        scheduler_logger.info(f"🔄 Re-Discover v2.0 refresh context - Previous tracks: {len(previous_songs)}, Library IDs: {library_ids}")

        # Generate new tracks using v2.0 processor with improved fallback handling
        result = await processor.generate_playlist(user_id, server_id, library_ids)

        # Extract tracks from v2.0 result format
        tracks = result.get("tracks", [])

        # Ensure tracks have the expected format for the rest of the refresh logic
        # The v2.0 tracks should already have ai_curated and ai_reasoning fields
        
        # The rediscover.generate_rediscover_weekly() method now uses the new recipe system internally
        
        if tracks:
            scheduler_logger.info(f"🎵 Generated {len(tracks)} new tracks for refresh")
            
            # VALIDATE: Ensure we got the expected number of tracks
            if len(tracks) != original_length:
                scheduler_logger.warning(f"⚠️ Generated {len(tracks)} tracks but user requested {original_length}")
            else:
                scheduler_logger.info(f"✅ Generated exact number of requested tracks: {len(tracks)}")
            
            # Extract AI reasoning if available
            ai_reasoning = ""
            ai_curated = False
            if tracks:
                first_track = tracks[0]
                ai_reasoning = first_track.get("ai_reasoning", "")
                ai_curated = first_track.get("ai_curated", False)
            
            # Log the AI reasoning for scheduled refresh (truncated)
            if ai_reasoning and ai_curated:
                reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
                scheduler_logger.info(f"🎵 AI curation applied for scheduled Re-Discover refresh (reasoning length: {len(ai_reasoning)} chars): {reasoning_preview}")
            else:
                scheduler_logger.info(f"⚠️ Scheduled Re-Discover refresh used algorithmic selection")
            
            # Update the existing playlist in Navidrome with reasoning
            track_ids = [track["id"] for track in tracks]
            comment_to_use = ai_reasoning if (ai_reasoning and ai_curated) else "Re-Discover Weekly v2.0 - Automatically refreshed"
            await nav_client.update_playlist(
                playlist_id=scheduled_playlist.navidrome_playlist_id,
                track_ids=track_ids,
                comment=comment_to_use
            )
            
            # Update the local database with new songs and reasoning
            track_titles = [track["title"] for track in tracks]
            reasoning_to_store = ai_reasoning if ai_curated else "Algorithmic selection"
            await db.update_playlist_content(
                navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                songs=track_titles,
                reasoning=reasoning_to_store
            )
            
            # Calculate next refresh time
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            
            # Update the scheduled playlist record
            await db.update_scheduled_playlist_next_refresh(
                scheduled_playlist.id, 
                next_refresh
            )
            
            scheduler_logger.info(f"✅ Successfully refreshed playlist {scheduled_playlist.navidrome_playlist_id}. Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            scheduler_logger.warning(f"⚠️ No tracks generated for playlist {scheduled_playlist.navidrome_playlist_id}")
        
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing playlist {scheduled_playlist.navidrome_playlist_id}: {e}")

async def refresh_this_is_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a specific This Is playlist"""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for This Is playlist ID: {scheduled_playlist.navidrome_playlist_id} (frequency: {scheduled_playlist.refresh_frequency})")
        
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()
        
        # Find the original playlist to get artist info
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return
        
        # Get artist IDs from the original playlist (we'll need to store this better in future)
        # For now, we'll use the artist_id field, but this limits us to single artists for refresh
        artist_id = original_playlist["artist_id"]
        
        # Get all artists to find the name
        all_artists = await nav_client.get_artists()
        artist = next((a for a in all_artists if a["id"] == artist_id), None)
        
        if not artist:
            scheduler_logger.error(f"❌ Could not find artist data for ID: {artist_id}")
            return
        
        artist_name = artist["name"]
        
        # FRESH DATA: Re-fetch ALL tracks for the artist (gets latest play counts, dates)
        tracks = await nav_client.get_tracks_by_artist(artist_id)
        
        if tracks:
            scheduler_logger.info(f"🎵 Found {len(tracks)} tracks for artist: {artist_name} (fresh data)")
            
            # ENFORCE original playlist length (MUST respect user's choice)
            original_length = original_playlist.get("playlist_length", 25)
            scheduler_logger.info(f"🎯 ENFORCING original playlist length: {original_length}")
            
            # Check if we have enough tracks
            if len(tracks) < original_length:
                scheduler_logger.warning(f"⚠️ Artist only has {len(tracks)} tracks, but user requested {original_length}. Using all available tracks.")
                original_length = len(tracks)
            
            # Get previous playlist songs for STRONG variety enforcement
            previous_songs = original_playlist.get("songs", [])
            variety_instruction = f"REFRESH CONSTRAINT: This is a REFRESH, not a copy. Previous playlist had these tracks: {', '.join(previous_songs[:10])}. Create a completely different track selection and arrangement. Prioritize tracks NOT in the previous list. Tell a fresh musical story. Avoid identical opening sequences." if previous_songs else "Create a fresh, engaging playlist arrangement."
            
            # Prepare tracks with variety instruction - use a more direct approach
            tracks_for_ai = tracks.copy()
            
            # Use AI to curate a FRESH playlist with STRONG variety enforcement
            curation_result = await ai_client_instance.curate_this_is(
                artist_name=artist_name,
                tracks_json=tracks_for_ai,
                num_tracks=original_length,
                include_reasoning=True,
                variety_context=variety_instruction
            )
            
            # Handle both old and new return formats
            if isinstance(curation_result, tuple):
                curated_track_ids, reasoning = curation_result
            else:
                curated_track_ids = curation_result
                reasoning = ""
            
            if curated_track_ids:
                # VALIDATE: Ensure we got the right number of tracks
                if len(curated_track_ids) < original_length and len(tracks) >= original_length:
                    scheduler_logger.warning(f"⚠️ AI returned only {len(curated_track_ids)} tracks but user requested {original_length}. Using fallback to fill gap.")
                    # Fill the gap with remaining tracks
                    used_ids = set(curated_track_ids)
                    remaining_tracks = [t for t in tracks if t["id"] not in used_ids]
                    additional_needed = original_length - len(curated_track_ids)
                    additional_tracks = remaining_tracks[:additional_needed]
                    curated_track_ids.extend([t["id"] for t in additional_tracks])
                
                scheduler_logger.info(f"🎯 Final track count: {len(curated_track_ids)} (requested: {original_length})")
                
                # Update the existing playlist in Navidrome with new reasoning
                await nav_client.update_playlist(
                    playlist_id=scheduled_playlist.navidrome_playlist_id,
                    track_ids=curated_track_ids,
                    comment=reasoning if reasoning else None
                )
                
                # Update the local database with new songs and reasoning
                track_titles = []
                track_id_to_title = {track["id"]: track["title"] for track in tracks}
                for track_id in curated_track_ids:
                    if track_id in track_id_to_title:
                        track_titles.append(track_id_to_title[track_id])
                
                await db.update_playlist_content(
                    navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                    songs=track_titles,
                    reasoning=reasoning
                )
                
                # Calculate next refresh time
                next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
                
                # Update the scheduled playlist record
                await db.update_scheduled_playlist_next_refresh(
                    scheduled_playlist.id, 
                    next_refresh
                )
                
                scheduler_logger.info(f"✅ Successfully refreshed This Is playlist {scheduled_playlist.navidrome_playlist_id}. Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                scheduler_logger.warning(f"⚠️ No curated tracks generated for This Is playlist {scheduled_playlist.navidrome_playlist_id}")
        else:
            scheduler_logger.warning(f"⚠️ No tracks found for artist {artist_name} in playlist {scheduled_playlist.navidrome_playlist_id}")
        
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing This Is playlist {scheduled_playlist.navidrome_playlist_id}: {e}")

async def refresh_genre_mix_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a specific Genre Mix playlist"""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for Genre Mix playlist ID: {scheduled_playlist.navidrome_playlist_id} (frequency: {scheduled_playlist.refresh_frequency})")

        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        # Find the original playlist to get genre and preferences
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)

        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return

        # Get genre and preferences from original playlist
        genre = original_playlist["artist_id"]  # Genre is stored as artist_id for genre mix
        original_length = original_playlist.get("playlist_length", 25)
        library_ids = original_playlist.get("library_ids", [])

        scheduler_logger.info(f"🎵 Refreshing Genre Mix: {genre} (length: {original_length}, libraries: {library_ids})")

        # Get fresh tracks for the genre
        all_tracks = await nav_client.get_tracks_by_genre(genre, library_ids)

        if all_tracks:
            scheduler_logger.info(f"🎵 Found {len(all_tracks)} tracks for genre: {genre} (fresh data)")

            # ENFORCE original playlist length (MUST respect user's choice)
            scheduler_logger.info(f"🎯 ENFORCING original playlist length: {original_length}")

            # Check if we have enough tracks
            if len(all_tracks) < original_length:
                scheduler_logger.warning(f"⚠️ Genre only has {len(all_tracks)} tracks, but user requested {original_length}. Using all available tracks.")
                original_length = len(all_tracks)

            # Get previous playlist songs for variety context
            previous_songs = original_playlist.get("songs", [])
            variety_instruction = f"REFRESH CONSTRAINT: This is a REFRESH, not a copy. Previous playlist had these tracks: {', '.join(previous_songs[:10])}. Create a completely different track selection and arrangement. Prioritize tracks NOT in the previous list. Tell a fresh musical story. Avoid identical opening sequences." if previous_songs else "Create a fresh, engaging playlist arrangement."

            # Apply smart filtering for Genre Mix playlists
            library_stats = await nav_client.get_library_stats()
            filtered_tracks, filter_metadata = filter_tracks_for_this_is_playlist(
                source_tracks=all_tracks,
                target_playlist_size=original_length,
                library_stats=library_stats
            )

            # Log filtering results
            if filter_metadata['filtered']:
                scheduler_logger.info(f"🎯 Smart filtering applied: {filter_metadata['source_count']} → {filter_metadata['sent_count']} tracks (multiplier: {filter_metadata['threshold_multiplier']}x)")
                scheduler_logger.info(f"📊 Score range: {filter_metadata['score_range']['highest']:.1f} - {filter_metadata['score_range']['lowest']:.1f} (cutoff: {filter_metadata['score_range']['cutoff']:.1f})")
            else:
                scheduler_logger.info(f"✅ No filtering needed: {filter_metadata['source_count']} tracks below threshold")

            # Use AI to curate a FRESH playlist with variety enforcement
            curation_result = await ai_client_instance.curate_genre_mix(
                genre=genre,
                tracks_json=filtered_tracks,
                num_tracks=original_length,
                include_reasoning=True,
                variety_context=variety_instruction
            )

            # Handle both old and new return formats
            if isinstance(curation_result, tuple):
                curated_track_ids, reasoning = curation_result
            else:
                curated_track_ids = curation_result
                reasoning = ""

            if curated_track_ids:
                # VALIDATE: Ensure we got the right number of tracks
                if len(curated_track_ids) < original_length and len(all_tracks) >= original_length:
                    scheduler_logger.warning(f"⚠️ AI returned only {len(curated_track_ids)} tracks but user requested {original_length}. Using fallback to fill gap.")
                    # Fill the gap with remaining tracks
                    used_ids = set(curated_track_ids)
                    remaining_tracks = [t for t in all_tracks if t["id"] not in used_ids]
                    additional_needed = original_length - len(curated_track_ids)
                    additional_tracks = remaining_tracks[:additional_needed]
                    curated_track_ids.extend([t["id"] for t in additional_tracks])

                scheduler_logger.info(f"🎯 Final track count: {len(curated_track_ids)} (requested: {original_length})")

                # Update the existing playlist in Navidrome with new reasoning
                await nav_client.update_playlist(
                    playlist_id=scheduled_playlist.navidrome_playlist_id,
                    track_ids=curated_track_ids,
                    comment=reasoning if reasoning else None
                )

                # Update the local database with new songs and reasoning
                track_titles = []
                track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
                for track_id in curated_track_ids:
                    if track_id in track_id_to_title:
                        track_titles.append(track_id_to_title[track_id])

                await db.update_playlist_content(
                    navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                    songs=track_titles,
                    reasoning=reasoning
                )

                # Calculate next refresh time
                next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)

                # Update the scheduled playlist record
                await db.update_scheduled_playlist_next_refresh(
                    scheduled_playlist.id,
                    next_refresh
                )

                scheduler_logger.info(f"✅ Successfully refreshed Genre Mix playlist {scheduled_playlist.navidrome_playlist_id}. Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                scheduler_logger.warning(f"⚠️ No curated tracks generated for Genre Mix playlist {scheduled_playlist.navidrome_playlist_id}")
        else:
            scheduler_logger.warning(f"⚠️ No tracks found for genre {genre} in playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing Genre Mix playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


async def refresh_song_radio_playlist(scheduled_playlist: ScheduledPlaylist, db: DatabaseManager) -> None:
    """Refresh a Song Radio playlist using its saved seed track and length."""
    playlist_id = scheduled_playlist.navidrome_playlist_id
    try:
        playlists = await db.get_all_playlists_with_schedule_info()
        original = next((item for item in playlists if item.get("navidrome_playlist_id") == playlist_id), None)
        if not original or not original["artist_id"].startswith("song_radio_"):
            scheduler_logger.warning("No Song Radio seed found for playlist %s", playlist_id)
            return

        seed_track_id = original["artist_id"].removeprefix("song_radio_")
        chroma_service = get_chroma_service()
        seed_result = chroma_service.get_embedding(seed_track_id)
        if not seed_result:
            scheduler_logger.warning("Song Radio seed %s is no longer analyzed", seed_track_id)
            return

        seed_embedding, seed_metadata = seed_result
        seed_track = {**seed_metadata, "id": seed_track_id}
        recipe = recipe_manager.get_recipe("song_radio")
        original_length = original.get("playlist_length") or len(original["songs"]) or 25
        candidates = chroma_service.find_similar_tracks(
            query_embedding=seed_embedding,
            n_results=original_length * recipe["config"]["candidate_multiplier"],
            exclude_track_ids=[seed_track_id],
            library_id=seed_metadata.get("library_id"),
        )
        candidate_count = min(original_length - 1, len(candidates))
        if candidate_count < 1:
            scheduler_logger.warning("No similar tracks found while refreshing Song Radio playlist %s", playlist_id)
            return

        formatted_candidates, track_id_map = format_candidates_for_ai(candidates, candidate_count)
        nav_client = get_navidrome_client()
        previous_ids = await nav_client.get_playlist_track_ids(playlist_id)
        previous_indices = [idx for idx, track_id in enumerate(track_id_map) if track_id in previous_ids]
        selected_ids, reasoning = await curate_with_ai(
            seed_track,
            formatted_candidates,
            track_id_map,
            candidate_count,
            recipe,
            get_ai_client(),
            additional_instructions=(
                f"This is a refresh. Previously selected candidates have indices {previous_indices}. "
                "Vary the playlist while keeping it acoustically close to the seed."
            ),
        )
        updated = await nav_client.update_playlist(playlist_id, [seed_track_id, *selected_ids], reasoning)
        if not updated:
            scheduler_logger.error("Navidrome could not refresh Song Radio playlist %s", playlist_id)
            return

        titles_by_id = {track["track_id"]: track["title"] for track in candidates}
        titles = [seed_track.get("title", "Unknown")] + [titles_by_id[track_id] for track_id in selected_ids]
        await db.update_playlist_content(playlist_id, titles, reasoning)
        await db.update_scheduled_playlist_next_refresh(
            scheduled_playlist.id, calculate_next_refresh(scheduled_playlist.refresh_frequency)
        )
    except Exception:
        scheduler_logger.exception("Error refreshing Song Radio playlist %s", playlist_id)


@app.get("/api/playlists")
async def get_all_playlists(db: DatabaseManager = Depends(get_db)):
    """Get all playlists with scheduling information"""
    try:
        playlists = await db.get_all_playlists_with_schedule_info()
        # Add track count to each playlist
        for playlist in playlists:
            songs = playlist.get("songs", [])
            playlist["track_count"] = len(songs) if isinstance(songs, list) else 0
        return playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlists: {str(e)}")

@app.post("/api/fix-refresh-times")
async def fix_refresh_times(db: DatabaseManager = Depends(get_db)):
    """Fix all refresh times to use :00 instead of :01"""
    try:
        # Get all playlists with schedule info
        playlists = await db.get_all_playlists_with_schedule_info()
        updated_count = 0

        for playlist in playlists:
            if "next_refresh" in playlist and playlist["next_refresh"]:
                current_time = playlist["next_refresh"]
                if ":01:" in current_time:
                    # Replace :01: with :00:
                    fixed_time = current_time.replace(":01:", ":00:")
                    # Update in database
                    await db.update_scheduled_playlist_next_refresh(playlist["id"], datetime.fromisoformat(fixed_time))
                    updated_count += 1

        return {"message": f"Updated {updated_count} refresh times to use :00"}
    except Exception as e:
        logger.error(f"Error fixing refresh times: {e}")
        raise HTTPException(status_code=500, detail="Failed to fix refresh times")

# Library Mapping Endpoints
@app.get("/api/library-mappings")
async def get_library_mappings(db: DatabaseManager = Depends(get_db)):
    """Get all library mappings"""
    try:
        mappings = await db.get_library_mappings()
        return {"mappings": mappings}
    except Exception as e:
        logger.error(f"Error getting library mappings: {e}")
        raise HTTPException(status_code=500, detail="Failed to get library mappings")

@app.get("/api/library-paths")
async def get_library_paths():
    """Get configured music library paths from environment"""
    try:
        music_paths_env = os.getenv("MUSIC_LIBRARY_PATHS", "")
        if not music_paths_env:
            # Fallback to single MUSIC_PATH for backward compatibility
            music_path = os.getenv("MUSIC_PATH", "/music")
            paths = [music_path]
        else:
            # Split comma-separated paths
            paths = [p.strip() for p in music_paths_env.split(",") if p.strip()]
        
        logger.info(f"Returning {len(paths)} configured library paths")
        return {"paths": paths}
    except Exception as e:
        logger.error(f"Error getting library paths: {e}")
        raise HTTPException(status_code=500, detail="Failed to get library paths")

@app.put("/api/library-mappings/{library_id}")
async def update_library_mapping(
    library_id: str, 
    body: Dict[str, Any] = Body(...),
    db: DatabaseManager = Depends(get_db)
):
    """Update the music path for a library mapping"""
    try:
        music_path = body.get("music_path")
        library_name = body.get("library_name", "")
        
        if not music_path:
            raise HTTPException(status_code=400, detail="music_path is required")

        logger.info(f"Saving library mapping: library_id={library_id}, path={music_path}, name={library_name}")
        success = await db.upsert_library_mapping(library_id, library_name, music_path)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update mapping")

        logger.info(f"✅ Successfully saved library mapping for library_id={library_id}")
        return {"message": "Library mapping updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating library mapping: {e}")
        raise HTTPException(status_code=500, detail="Failed to update library mapping")

@app.delete("/api/library-mappings/{library_id}")
async def delete_library_mapping(library_id: str, db: DatabaseManager = Depends(get_db)):
    """Delete a library mapping"""
    try:
        logger.info(f"Deleting library mapping for library_id={library_id}")
        success = await db.delete_library_mapping(library_id)
        if not success:
            raise HTTPException(status_code=404, detail="Library mapping not found")

        logger.info(f"✅ Successfully deleted library mapping for library_id={library_id}")
        return {"message": "Library mapping deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting library mapping: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete library mapping")

@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete a playlist from both local database and Navidrome"""
    try:
        # First, get the specific playlist to find the Navidrome playlist ID
        # Use a direct query instead of fetching all playlists
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        # Delete from Navidrome if we have a playlist ID
        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        navidrome_deleted = False
        if navidrome_playlist_id:
            nav_client = get_navidrome_client()
            try:
                print(f"🗑️ Deleting playlist {playlist_id} from Navidrome (Navidrome ID: {navidrome_playlist_id})")
                deletion_result = await nav_client.delete_playlist(navidrome_playlist_id)
                print(f"✅ Navidrome deletion result: {deletion_result}")
                navidrome_deleted = True
            except Exception as e:
                print(f"❌ Warning: Failed to delete playlist from Navidrome: {e}")
                # Continue with local deletion even if Navidrome deletion fails
        else:
            print(f"⚠️ No Navidrome playlist ID found for local playlist {playlist_id}, skipping Navidrome deletion")
        
        # Delete from scheduled playlists if it exists
        if navidrome_playlist_id:
            await db.delete_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
        
        # Delete from local database
        success = await db.delete_playlist(playlist_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Playlist not found in database")
        
        return {"message": "Playlist deleted successfully", "navidrome_deleted": navidrome_deleted}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete playlist: {str(e)}")

@app.get("/api/recipes")
async def get_available_recipes():
    """Get information about available playlist generation recipes"""
    try:
        recipes_info = recipe_manager.list_available_recipes()
        return recipes_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load recipes: {str(e)}")

@app.get("/api/recipes/validate")
async def validate_recipes():
    """Validate all recipe files and return any errors"""
    try:
        registry = recipe_manager._load_registry()
        validation_results = {}
        
        for playlist_type, recipe_filename in registry.items():
            errors = recipe_manager.validate_recipe(recipe_filename)
            validation_results[playlist_type] = {
                "recipe_file": recipe_filename,
                "valid": len(errors) == 0,
                "errors": errors
            }
        
        return validation_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate recipes: {str(e)}")

@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and active jobs"""
    try:
        global scheduler
        if scheduler:
            jobs = list(scheduler.get_jobs())
            job_info = []
            for job in jobs:
                job_info.append({
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "func": job.func.__name__ if hasattr(job, 'func') else str(job.func)
                })
            
            return {
                "scheduler_running": scheduler.running,
                "active_jobs": len(jobs),
                "jobs": job_info,
                "scheduler_state": str(scheduler.state)
            }
        else:
            return {
                "scheduler_running": False,
                "error": "Scheduler not initialized"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")

@app.post("/api/scheduler/trigger")
async def trigger_scheduler_check():
    """Manually trigger the scheduler to check for playlists due for refresh"""
    try:
        scheduler_logger.info("🧪 Manual scheduler trigger requested via API")
        await refresh_scheduled_playlists()
        return {"message": "Scheduler check completed successfully"}
    except Exception as e:
        scheduler_logger.error(f"❌ Error in manual scheduler trigger: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduler: {str(e)}")

@app.post("/api/scheduler/start")
async def start_scheduler_job():
    """Manually start the recurring scheduler job"""
    try:
        schedule_playlist_refresh()
        global scheduler
        jobs = list(scheduler.get_jobs()) if scheduler else []
        scheduler_logger.info(f"🔄 Scheduler job registration requested. Active jobs: {len(jobs)}")
        return {
            "message": "Scheduler job started",
            "active_jobs": len(jobs),
            "jobs": [{"id": job.id, "next_run": job.next_run_time.isoformat() if job.next_run_time else None} for job in jobs]
        }
    except Exception as e:
        scheduler_logger.error(f"❌ Error starting scheduler job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler job: {str(e)}")

@app.get("/api/ai-model-info")
async def get_ai_model_info():
    """Get current AI model information for analytics"""
    try:
        ai_client_instance = get_ai_client()
        return {
            "provider": ai_client_instance.provider.provider_type,
            "model": ai_client_instance.model or "unknown",
            "has_api_key": bool(ai_client_instance.api_key)
        }
    except Exception as e:
        return {
            "provider": "unknown",
            "model": "unknown", 
            "has_api_key": False
        }

@app.post("/api/track-library-size")
async def track_library_size(db: DatabaseManager = Depends(get_db)):
    """Track library size for analytics (called post-launch)"""
    try:
        # Check if we should track (90+ days since last tracking)
        should_track = await db.should_track_library_size()
        if not should_track:
            return {"message": "Library size tracking not needed yet", "tracked": False}
        
        # Get Navidrome client and query library size
        nav_client = get_navidrome_client()
        song_count = await nav_client.get_total_song_count()
        
        # Get or create user ID and record the data
        user_id = await db.get_or_create_user_id()
        await db.record_library_size(song_count)
        
        scheduler_logger.info(f"📊 Library size tracked: {song_count} songs for user {user_id}")
        
        return {
            "message": "Library size tracked successfully",
            "tracked": True,
            "song_count": song_count,
            "user_id": user_id
        }
        
    except Exception as e:
        scheduler_logger.error(f"❌ Error tracking library size: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to track library size: {str(e)}")

@app.post("/api/admin/erase-chroma-db")
async def erase_chroma_db():
    """Erase all data from ChromaDB - DANGER ZONE operation"""
    try:
        logger.warning("🗑️ DANGER: Erase ChromaDB operation initiated")

        # Get ChromaDB service and erase all data
        chroma_service = get_chroma_service()
        collection = chroma_service.collection

        # Delete all documents from the collection
        count_before = collection.count()
        logger.info(f"📊 ChromaDB contains {count_before} documents before erase")

        # ChromaDB doesn't have a direct "delete all" method, so we need to delete in batches
        # Get all IDs and delete them
        results = collection.get(include=[])
        if results and results.get('ids'):
            ids_to_delete = results['ids']
            if ids_to_delete:
                # Delete in batches to avoid potential issues
                batch_size = 1000
                for i in range(0, len(ids_to_delete), batch_size):
                    batch_ids = ids_to_delete[i:i + batch_size]
                    collection.delete(ids=batch_ids)
                    logger.info(f"🗑️ Deleted batch of {len(batch_ids)} documents")

        count_after = collection.count()
        logger.warning(f"✅ ChromaDB erase completed. Documents before: {count_before}, after: {count_after}")

        return {
            "message": f"Successfully erased {count_before} documents from ChromaDB",
            "documents_deleted": count_before,
            "remaining_documents": count_after
        }

    except Exception as e:
        logger.error(f"❌ Error erasing ChromaDB: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to erase ChromaDB: {str(e)}")

# SPA ROUTING - Smart catch-all for client-side routing (MUST be last route)
@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_router(request: Request, path: str):
    """Handle SPA routing - serve app for known paths, redirect unknown paths"""
    # Known SPA paths - serve the app and let frontend handle routing
    spa_paths = ["this-is", "re-discover", "playlists", "terms", "genre-mix", "song-radio", "system-check", "sonic-analysis"]
    
    if path in spa_paths:
        # Apply same system check logic as root
        if not system_check_passed:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/system-check", status_code=302)
        return templates.TemplateResponse("index.html", {"request": request})
    
    # Unknown paths - redirect to home
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=302)

if __name__ == "__main__":
    # Custom logging config to filter out Umami heartbeat requests
    import uvicorn.config
    
    class FilteredUvicornFormatter(uvicorn.formatters.DefaultFormatter):
        def format(self, record):
            # Filter out GET / requests (Umami heartbeats) from access logs
            if hasattr(record, 'args') and record.args:
                # Look for GET / HTTP patterns in the log message
                message = str(record.args[2]) if len(record.args) > 2 else ""
                if 'GET / HTTP' in message:
                    return ""  # Return empty string to suppress this log
            return super().format(record)
    
    # Configure uvicorn with custom formatter
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["()"] = FilteredUvicornFormatter
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_config=log_config
    )