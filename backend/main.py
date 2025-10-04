from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
import uvicorn
import os
import logging
from typing import List
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# Load environment variables first
load_dotenv()

# Configure logging for scheduler activities
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
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

app = FastAPI(title="MagicLists Navidrome MVP")

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup"""
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler_logger.info("✅ Scheduler started successfully")

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
    return templates.TemplateResponse("index.html", {"request": request})

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
        
        # Get track titles for database storage
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
        for track_id in curated_track_ids:
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])
        
        # Store playlist in local database (using the first artist_id for now)
        playlist = await db.create_playlist(
            artist_id=request.artist_ids[0],
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id
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
            "monthly": "Re-Discover Monthly ✨"
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
            navidrome_playlist_id=navidrome_playlist_id
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
    """Schedule the playlist refresh job to run every hour"""
    if not scheduler.get_job('playlist_refresh'):
        scheduler.add_job(
            refresh_scheduled_playlists,
            'interval',
            hours=1,
            id='playlist_refresh',
            replace_existing=True
        )
        scheduler_logger.info("🔄 Playlist refresh job scheduled to run every hour")

async def refresh_scheduled_playlists():
    """Check for and refresh scheduled playlists that are due"""
    try:
        scheduler_logger.info("🔍 Checking for playlists due for refresh...")
        
        db = DatabaseManager()
        current_time = datetime.now()
        
        # Get playlists due for refresh
        scheduled_playlists = await db.get_scheduled_playlists_due(current_time)
        
        if not scheduled_playlists:
            scheduler_logger.info("✅ No playlists due for refresh at this time")
            return
        
        scheduler_logger.info(f"📋 Found {len(scheduled_playlists)} playlist(s) due for refresh")
        
        for scheduled_playlist in scheduled_playlists:
            if scheduled_playlist.playlist_type == "rediscover_weekly":
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
        
        # Create RediscoverWeekly instance
        rediscover = RediscoverWeekly(nav_client)

        # Generate new tracks with AI curation (use default length for scheduled refreshes)
        tracks = await rediscover.generate_rediscover_weekly(use_ai=True)
        
        if tracks:
            scheduler_logger.info(f"🎵 Generated {len(tracks)} new tracks for refresh")
            
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
        
        # Get tracks for the artist
        tracks = await nav_client.get_tracks_by_artist(artist_id)
        
        if tracks:
            scheduler_logger.info(f"🎵 Found {len(tracks)} tracks for artist: {artist_name}")
            
            # Use AI to curate a new playlist with reasoning (use default 25 for refreshes)
            curation_result = await ai_client_instance.curate_this_is(
                artist_name=artist_name,
                tracks_json=tracks,
                num_tracks=25,  # Default for refreshes, could be enhanced to store original length
                include_reasoning=True
            )
            
            # Handle both old and new return formats
            if isinstance(curation_result, tuple):
                curated_track_ids, reasoning = curation_result
            else:
                curated_track_ids = curation_result
                reasoning = ""
            
            if curated_track_ids:
                # Update the existing playlist in Navidrome with new reasoning
                await nav_client.update_playlist(
                    playlist_id=scheduled_playlist.navidrome_playlist_id,
                    track_ids=curated_track_ids,
                    comment=reasoning if reasoning else None
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
    uvicorn.run(app, host="0.0.0.0", port=8000)