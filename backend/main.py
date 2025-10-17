from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
import uvicorn
import os
import logging
import logging.handlers
from typing import List
from datetime import datetime, timedelta
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

# Reduce httpx logging verbosity to avoid cluttering scheduler.log
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

from .navidrome_client import NavidromeClient
from .ai_client import AIClient
from .database import DatabaseManager, get_db
from .schemas import CreatePlaylistRequest, Playlist, RediscoverWeeklyResponse, CreateRediscoverPlaylistRequest, PlaylistWithScheduleInfo
from .recipe_manager import recipe_manager
from .rediscover import RediscoverWeekly
# SYSTEM CHECK FEATURE - START
from .services.health_check_service import HealthCheckService
# SYSTEM CHECK FEATURE - END

app = FastAPI(title="MagicLists Navidrome MVP")

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup"""
    global scheduler, system_check_passed, system_check_results
    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler_logger.info("✅ Scheduler started successfully")
    # Auto-start the cron job
    await start_scheduler_job()
    scheduler_logger.info("✅ Cron job auto-started on application startup")
    
    # SYSTEM CHECK FEATURE - START
    # Run system checks on startup
    try:
        health_service = HealthCheckService()
        system_check_results = await health_service.run_checks()
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
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")

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
async def get_artists():
    """Get list of artists from Navidrome"""
    try:
        client = get_navidrome_client()
        artists = await client.get_artists()
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
        playlist_name = request.playlist_name or f"This Is: {artist_names[0]}"
        
        # Get tracks for only the first artist
        all_tracks = []
        tracks = await nav_client.get_tracks_by_artist(first_artist_id)
        if tracks:
            all_tracks.extend(tracks)
        
        if not all_tracks:
            raise HTTPException(status_code=404, detail="No tracks found for the selected artists")
        
        # Use AI to curate the playlist (always include reasoning for new recipe format)
        curation_result = await ai_client_instance.curate_this_is(
            artist_name=', '.join(artist_names),
            tracks_json=all_tracks,
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
            playlist_length=request.playlist_length
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
        playlist_name = getattr(request, 'playlist_name', None) or f"This Is: {artist_name}"
        
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
            navidrome_playlist_id=navidrome_playlist_id
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

@app.post("/api/create-rediscover-playlist")
async def create_rediscover_playlist(
    request: CreateRediscoverPlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create a Re-Discover Weekly playlist in Navidrome"""
    try:
        # Get Navidrome client
        nav_client = get_navidrome_client()
        
        # Create RediscoverWeekly instance
        rediscover = RediscoverWeekly(nav_client)

        # Generate the playlist tracks with user-specified length and AI curation
        tracks = await rediscover.generate_rediscover_weekly(max_tracks=request.playlist_length, use_ai=True)
        
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found for Re-Discover Weekly")
        
        # Extract AI reasoning if available
        ai_reasoning = ""
        ai_curated = False
        if tracks:
            first_track = tracks[0]
            ai_reasoning = first_track.get("ai_reasoning", "")
            ai_curated = first_track.get("ai_curated", False)
        
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
        
        # Extract track IDs
        track_ids = [track["id"] for track in tracks]
        
        # Create playlist in Navidrome with AI reasoning as comment if available
        comment_to_use = ai_reasoning if (ai_reasoning and ai_curated) else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating Re-Discover playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=track_ids,
            comment=comment_to_use
        )
        
        # Get track titles for database storage
        track_titles = [track["title"] for track in tracks]
        
        # Store playlist in local database (using a synthetic artist_id for rediscover playlists)
        playlist = await db.create_playlist(
            artist_id="rediscover",
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=ai_reasoning if ai_curated else "Algorithmic selection",
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length
        )
        
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
    if frequency == "daily":
        # Next day at 1:00 AM
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "weekly":
        # Next Monday at 1:00 AM
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour >= 1:
            days_until_monday = 7  # If it's Monday after 1 AM, go to next Monday
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
    """Schedule the playlist refresh job to run every 12 hours"""
    if not scheduler.get_job('playlist_refresh'):
        scheduler.add_job(
            refresh_scheduled_playlists,
            'cron',
            hour='1,13',  # Run at 1 AM and 1 PM
            minute=1,     # Run at 1 minute past (1:01 AM and 1:01 PM)
            id='playlist_refresh',
            replace_existing=True
        )
        scheduler_logger.info("🔄 Playlist refresh job scheduled to run every 12 hours (1:01 AM and 1:01 PM)")

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
        
        # Create RediscoverWeekly instance  
        rediscover = RediscoverWeekly(nav_client)

        # Enhanced variety instruction with current playlist context for AI
        current_playlist_context = f"CURRENT PLAYLIST FLOW TO REFRESH: {', '.join(previous_songs[:10])}" if previous_songs else ""
        enhanced_variety_context = f"{variety_instruction}\n\nFor reference, here's the complete current playlist sequence: {current_playlist_context}".strip() if variety_instruction or current_playlist_context else None
        
        # Log refresh context for debugging
        scheduler_logger.info(f"🔄 Re-Discover refresh context - Previous tracks: {len(previous_songs)}, Enhanced variety: {bool(enhanced_variety_context)}")

        # Generate new tracks using NEW recipe system with fresh data analysis
        # Use the modern recipe-based approach like This Is playlists
        tracks = await rediscover.generate_rediscover_weekly(
            max_tracks=original_length,
            use_ai=True,
            variety_context=enhanced_variety_context
        )
        
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
            comment_to_use = ai_reasoning if (ai_reasoning and ai_curated) else None
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
        if navidrome_playlist_id:
            nav_client = get_navidrome_client()
            try:
                print(f"🗑️ Deleting playlist {playlist_id} from Navidrome (Navidrome ID: {navidrome_playlist_id})")
                deletion_result = await nav_client.delete_playlist(navidrome_playlist_id)
                print(f"✅ Navidrome deletion result: {deletion_result}")
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
        
        return {"message": "Playlist deleted successfully"}
        
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