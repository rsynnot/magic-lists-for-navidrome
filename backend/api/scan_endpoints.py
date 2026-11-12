"""
FastAPI endpoints for library scanning operations

This module provides REST API endpoints for:
- Starting library scans
- Monitoring scan progress
- Cancelling active scans
- Viewing scan history
- Getting collection statistics

All endpoints include proper error handling, logging, and OpenAPI documentation.
"""

import logging
import time
import json
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import asyncio
from threading import Thread

from ..database import DatabaseManager, get_db
from ..navidrome_client import NavidromeClient
from ..schemas import ScanStatus, StartScanRequest
from ..services.library_scanner import get_library_scanner
from ..services.chroma_service import get_chroma_service

# Global navidrome client instance (same pattern as main.py)
navidrome_client = None

def get_navidrome_client():
    """Get or create Navidrome client instance"""
    global navidrome_client
    if navidrome_client is None:
        navidrome_client = NavidromeClient()
    return navidrome_client

logger = logging.getLogger(__name__)

# Global registry for active streaming scan tasks
active_scan_tasks: Dict[str, asyncio.Task] = {}

# Response models for OpenAPI documentation
class ScanStartResponse(BaseModel):
    """Response model for starting a scan"""
    session_id: str = Field(..., description="Unique session identifier for tracking the scan")
    status: str = Field(..., description="Initial scan status")
    message: str = Field(..., description="Human-readable status message")
    estimated_tracks: Optional[int] = Field(None, description="Estimated number of tracks to process")
    mode: str = Field(..., description="Scan mode: local or remote")

class ScanStatusResponse(BaseModel):
    """Response model for scan status"""
    session_id: str = Field(..., description="Session identifier")
    status: str = Field(..., description="Current scan status")
    progress_percentage: float = Field(..., description="Completion percentage (0-100)")
    total_tracks: int = Field(..., description="Total tracks to process")
    processed_tracks: int = Field(..., description="Successfully processed tracks")
    failed_tracks: int = Field(..., description="Failed track count")
    skipped_tracks: int = Field(..., description="Skipped tracks (already analyzed)")
    current_file: Optional[str] = Field(None, description="Currently processing file")
    started_at: Optional[str] = Field(None, description="Scan start timestamp")
    completed_at: Optional[str] = Field(None, description="Scan completion timestamp")
    estimated_time_remaining: Optional[str] = Field(None, description="Estimated time to completion")
    errors: List[str] = Field(default_factory=list, description="List of error messages")

class CollectionStatsResponse(BaseModel):
    """Response model for collection statistics"""
    total_embeddings: int = Field(..., description="Total number of stored embeddings")
    collection_name: str = Field(..., description="ChromaDB collection name")
    persist_directory: str = Field(..., description="Storage directory path")

router = APIRouter()

@router.post(
    "/start",
    response_model=ScanStartResponse,
    summary="Start Library Scan",
    description="Start a background scan of the music library to extract audio features and build similarity database"
)
async def start_scan(
    request: StartScanRequest,
    background_tasks: BackgroundTasks,
    navidrome_client: NavidromeClient = Depends()
):
    """
    Start a library scan to analyze audio files and extract features.

    The scan runs in the background and can be monitored using the status endpoint.
    """
    try:
        scanner = get_library_scanner()

        # Check if there's already an active scan
        active_scans = scanner.get_active_scans()
        if active_scans:
            raise HTTPException(
                status_code=409,
                detail="A scan is already in progress. Please wait for it to complete or cancel it first."
            )

        # Get music directory
        import os
        if request.music_directory:
            music_directory = request.music_directory
        else:
            # Use MUSIC_PATH environment variable or default Docker path
            music_directory = os.getenv("MUSIC_PATH", "/music")
            logger.info(f"Using music directory from environment: {music_directory}")

        # Validate music directory
        if not music_directory or not os.path.exists(music_directory):
            raise HTTPException(
                status_code=400,
                detail=f"Music directory does not exist: {music_directory}"
            )

        if not os.path.isdir(music_directory):
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a directory: {music_directory}"
            )

        # Start the scan
        session_id = await scanner.start_scan(
            music_directory=music_directory,
            navidrome_client=navidrome_client,
            max_tracks=request.max_tracks,
            mode=request.mode
        )

        logger.info(f"Started library scan session {session_id} for directory: {request.music_directory}")

        return ScanStartResponse(
            session_id=session_id,
            status="started",
            message="Library scan started successfully",
            mode="local",
            estimated_tracks=None  # Will be updated as scan progresses
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start scan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")

@router.get(
    "/status/{session_id}",
    response_model=ScanStatusResponse,
    summary="Get Scan Status",
    description="Get the current status and progress of a library scan session"
)
async def get_scan_status(session_id: str):
    """Get the status of a specific scan session"""
    try:
        scanner = get_library_scanner()
        status = scanner.get_scan_status(session_id)

        if not status:
            raise HTTPException(status_code=404, detail=f"Scan session {session_id} not found")

        return ScanStatusResponse(**status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scan status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scan status: {str(e)}")

@router.delete(
    "/cancel/{session_id}",
    summary="Cancel Scan",
    description="Cancel a running library scan session"
)
async def cancel_scan(session_id: str):
    """Cancel a running scan session"""
    try:
        scanner = get_library_scanner()

        if scanner.cancel_scan(session_id):
            logger.info(f"Cancelled scan session {session_id}")
            return {"message": f"Scan session {session_id} cancelled successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Could not cancel scan session {session_id}. It may not be running or may have already completed."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel scan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel scan: {str(e)}")

@router.get(
    "/active",
    summary="List Active Scans",
    description="Get a list of all currently active scan sessions"
)
async def get_active_scans():
    """Get all active scan sessions"""
    try:
        scanner = get_library_scanner()
        active_scans = scanner.get_active_scans()
        return {"active_scans": active_scans}

    except Exception as e:
        logger.error(f"Failed to get active scans: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active scans: {str(e)}")

@router.get(
    "/stats",
    response_model=CollectionStatsResponse,
    summary="Get Collection Statistics",
    description="Get statistics about the main audio embedding collection (excludes test collection)"
)
async def get_collection_stats():
    """Get statistics about the stored audio embeddings from main collection only"""
    try:
        chroma_service = get_chroma_service()

        # Ensure we're getting stats from the main collection
        current_collection = chroma_service.collection_name
        chroma_service.switch_collection("audio_embeddings")

        try:
            stats = chroma_service.get_collection_stats()

            if "error" in stats:
                raise HTTPException(status_code=500, detail=f"Failed to get collection stats: {stats['error']}")

            return CollectionStatsResponse(**stats)
        finally:
            # Switch back to whatever collection was active
            if current_collection != "audio_embeddings":
                chroma_service.switch_collection(current_collection)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get collection stats: {str(e)}")

@router.delete(
    "/collection",
    summary="Clear Collection",
    description="Clear all audio embeddings from the collection (irreversible operation)"
)
async def clear_collection():
    """Clear all embeddings from the ChromaDB collection"""
    try:
        chroma_service = get_chroma_service()

        if chroma_service.clear_collection():
            logger.info("Cleared audio embedding collection")
            return {"message": "Audio embedding collection cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear collection")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear collection: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear collection: {str(e)}")

@router.get(
    "/system/resources",
    summary="Get System Resources",
    description="Get current system resource usage (CPU, memory)"
)
async def get_system_resources():
    """Get current system resource usage"""
    try:
        scanner = get_library_scanner()
        resources = scanner.get_system_resources()
        return {"system_resources": resources}

    except Exception as e:
        logger.error(f"Failed to get system resources: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system resources: {str(e)}")

@router.get(
    "/history",
    summary="Get Scan History",
    description="Get history of completed library scans"
)
async def get_scan_history(db: DatabaseManager = Depends(get_db)):
    """Get history of completed scans"""
    try:
        history = await db.get_scan_history(limit=20)  # Get last 20 scans
        return {"scan_history": history}

    except Exception as e:
        logger.error(f"Failed to get scan history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scan history: {str(e)}")

@router.delete(
    "/history",
    summary="Clear Scan History",
    description="Clear all scan history records (irreversible operation)"
)
async def clear_scan_history(db: DatabaseManager = Depends(get_db)):
    """Clear all scan history"""
    try:
        if await db.clear_scan_history():
            logger.info("Cleared scan history")
            return {"message": "Scan history cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear scan history")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear scan history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear scan history: {str(e)}")

@router.get(
    "/partial-status",
    summary="Check for Partial Scan",
    description="Check if there's a partial/incomplete scan that can be resumed"
)
async def get_partial_scan_status(navidrome_client: NavidromeClient = Depends()):
    """Check for partial scan status"""
    try:
        scanner = get_library_scanner()

        # Check for active scans first
        active_scans = scanner.get_active_scans()
        if active_scans:
            return {
                "has_partial": False,
                "reason": "active_scan_in_progress",
                "active_scan": active_scans[0]  # Return first active scan
            }

        # Check processing status cache for partial scan
        processing_status = await scanner._get_processing_status(navidrome_client)

        last_processed_index = processing_status.get('last_processed_index', -1)
        completed_tracks = processing_status.get('completed_tracks', [])
        last_updated = processing_status.get('last_updated')

        if last_processed_index >= 0 and completed_tracks:
            # Get scan history for additional details
            db = await get_db()
            recent_scans = await db.get_scan_history(limit=5)

            # Find the most recent scanning session
            partial_session = None
            for scan in recent_scans:
                if scan.get('status') == 'scanning':
                    partial_session = scan
                    break

            return {
                "has_partial": True,
                "session_id": partial_session.get('session_id') if partial_session else None,
                "last_processed_index": last_processed_index,
                "completed_tracks_count": len(completed_tracks),
                "total_tracks": partial_session.get('total_tracks') if partial_session else None,
                "progress_percentage": (len(completed_tracks) / (partial_session.get('total_tracks') or len(completed_tracks))) * 100 if partial_session and partial_session.get('total_tracks') else 0,
                "last_updated": last_updated,
                "started_at": partial_session.get('started_at') if partial_session else None,
                "current_file": completed_tracks[-1] if completed_tracks else None
            }

        return {"has_partial": False}

    except Exception as e:
        logger.error(f"Failed to get partial scan status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get partial scan status: {str(e)}")

@router.delete(
    "/partial",
    summary="Cancel Partial Scan",
    description="Cancel any partial scan and clear its processing state"
)
async def cancel_partial_scan(navidrome_client: NavidromeClient = Depends()):
    """Cancel a partial scan and clear processing state"""
    try:
        scanner = get_library_scanner()

        # Check if there's a partial scan
        partial_status = await get_partial_scan_status(navidrome_client)
        if not partial_status.get('has_partial'):
            raise HTTPException(status_code=404, detail="No partial scan found")

        # Clear processing status cache
        cache_key = scanner._get_cache_key(navidrome_client)
        status_path = scanner._get_processing_status_path(cache_key)

        if status_path.exists():
            try:
                status_path.unlink()  # Delete the separate processing status file
                logger.info(f"Cleared processing status for partial scan")
            except Exception as e:
                logger.error(f"Failed to clear processing status cache: {e}")

        # Note: Scan history is not updated to avoid duplicates.
        # The cache clearing is sufficient to allow fresh scans.

        return {"message": "Partial scan cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel partial scan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel partial scan: {str(e)}")

@router.delete(
    "/stream-cancel/{scan_id}",
    summary="Cancel Streaming Scan",
    description="Cancel a running streaming scan (test or full scan)"
)
async def cancel_stream_scan(scan_id: str):
    """Cancel a running streaming scan"""
    try:
        if scan_id not in active_scan_tasks:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found or already completed")

        # Cancel the task
        task = active_scan_tasks[scan_id]
        task.cancel()

        # Remove from registry
        del active_scan_tasks[scan_id]

        logger.info(f"Cancelled streaming scan {scan_id}")
        return {"message": f"Scan {scan_id} cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel streaming scan {scan_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel scan: {str(e)}")

@router.post(
    "/test",
    summary="Run Test Scan",
    description="Run a test scan with only 10 tracks to estimate full library scan time"
)
async def run_test_scan():
    """Run a test scan with 10 tracks to estimate full scan time"""
    try:
        # Get Navidrome client and scanner
        navidrome_client = get_navidrome_client()
        scanner = get_library_scanner()

        # Get all tracks from Navidrome using paginated method
        tracks = await scanner._get_all_tracks_from_navidrome(navidrome_client, force_refresh=True)
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found in Navidrome")

        logger.info(f"Starting test scan with {len(tracks)} total tracks from Navidrome")

        # Get music directory from environment
        import os
        music_directory = os.getenv("MUSIC_PATH", "/music")
        logger.info(f"Using music directory: {music_directory}")

        # Get scanner and run test scan
        scanner = get_library_scanner()
        result = await scanner.scan_library(tracks, test_mode=True, music_directory=music_directory)

        # After scan completes, fetch the latest history to include the new scan
        db = await get_db()
        history = await db.get_scan_history(limit=5)  # Get latest 5 scans
        result["latest_history"] = history

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Test scan failed: {str(e)}")

@router.post(
    "/full",
    summary="Run Full Library Scan",
    description="Run a complete scan of the entire music library"
)
async def run_full_scan():
    """Run a full scan of the entire music library"""
    try:
        # Get Navidrome client and scanner
        navidrome_client = get_navidrome_client()
        scanner = get_library_scanner()

        # Get all tracks from Navidrome using paginated method
        tracks = await scanner._get_all_tracks_from_navidrome(navidrome_client, force_refresh=True)
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found in Navidrome")

        logger.info(f"Starting full scan with {len(tracks)} total tracks from Navidrome")

        # Get music directory from environment
        import os
        music_directory = os.getenv("MUSIC_PATH", "/music")
        logger.info(f"Using music directory: {music_directory}")

        # Get scanner and run full scan
        scanner = get_library_scanner()
        result = await scanner.scan_library(tracks, test_mode=False, music_directory=music_directory)

        # After scan completes, fetch the latest history to include the new scan
        db = await get_db()
        history = await db.get_scan_history(limit=5)  # Get latest 5 scans
        result["latest_history"] = history

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Full scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Full scan failed: {str(e)}")
@router.get(
    "/test-stream",
    summary="Run Test Scan with Streaming Progress",
    description="Run a test scan with streaming progress updates via Server-Sent Events"
)
async def run_test_scan_stream(library_id: Optional[str] = Query(None, description="Library ID to scan (optional)")):
    """Run a test scan with real-time progress streaming via SSE"""

    logger.info(f"📡 Test scan stream started with library_id: {library_id}")

    # Generate unique scan ID
    scan_id = str(uuid.uuid4())

    # Shared list for events
    events = []

    async def event_generator():
        try:
            # Send started event with scan_id
            yield f"event: started\ndata: {json.dumps({'type': 'started', 'scan_id': scan_id, 'timestamp': int(time.time())})}\n\n"

            # Start scan in background
            scan_task = asyncio.create_task(_run_test_scan_background(events, scan_id, library_id))
            active_scan_tasks[scan_id] = scan_task

            try:
                # Yield events as they arrive
                last_event_count = 0
                while True:
                    # Check for new events
                    if len(events) > last_event_count:
                        for i in range(last_event_count, len(events)):
                            event = events[i]
                            if event is None:  # Sentinel value = scan complete
                                # Get final result
                                result = await scan_task
                                # Send completed event
                                tracks_scanned = result.get('summary', {}).get('tracks_scanned', 0)
                                scan_total = result.get('summary', {}).get('scan_total', tracks_scanned)
                                completed_data = {
                                    'type': 'completed',
                                    'processed': tracks_scanned,
                                    'total': scan_total,  # Total tracks that were targeted for scanning
                                    'duration': result.get('duration_seconds', 0)
                                }
                                yield f"event: completed\ndata: {json.dumps(completed_data)}\n\n"
                                return

                            event_type = event.get('type', 'progress')
                            if event_type == 'progress':
                                logger.info(f"📡 SSE sending event: {event_type}")
                            yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                        last_event_count = len(events)

                    # Wait a bit before checking again
                    await asyncio.sleep(0.05)  # Check more frequently

                    # Check if scan is done and no more events
                    if scan_task.done() and len(events) == last_event_count:
                        break

            finally:
                # Clean up task reference
                active_scan_tasks.pop(scan_id, None)

        except Exception as e:
            logger.error(f"Test scan stream failed: {e}", exc_info=True)
            error_data = {'type': 'error', 'message': str(e)}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            # Clean up on error
            active_scan_tasks.pop(scan_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

async def _run_test_scan_background(events, scan_id: str, library_id: Optional[str] = None):
    """Run test scan in background and append events to list"""
    try:
        # Get Navidrome client and scanner
        navidrome_client = get_navidrome_client()
        scanner = get_library_scanner()

        # Get tracks from Navidrome (filtered by library if specified)
        tracks = await scanner._get_all_tracks_from_navidrome(navidrome_client, force_refresh=True, library_id=library_id)
        if library_id:
            logger.info(f"Starting test scan stream with {len(tracks)} tracks from library {library_id}")
        else:
            logger.info(f"Starting test scan stream with {len(tracks)} total tracks from Navidrome")

        if not tracks:
            events.append({'type': 'error', 'message': 'No tracks found in Navidrome'})
            events.append(None)
            return {}

        # Get music directory from environment
        import os
        music_directory = os.getenv("MUSIC_PATH", "/music")

        def progress_callback(event):
            """Callback to receive progress events from scanner"""
            events.append(event)

        # Run test scan with streaming callback
        result = await scanner.scan_library(
            tracks,
            test_mode=True,
            music_directory=music_directory,
            progress_callback=progress_callback,
            library_id=library_id
        )

        # Send sentinel
        events.append(None)
        return result

    except asyncio.CancelledError:
        logger.info(f"Test scan {scan_id} was cancelled")
        events.append({'type': 'cancelled', 'message': 'Scan was cancelled by user'})
        events.append(None)
        raise
    except Exception as e:
        logger.error(f"Test scan background failed: {e}", exc_info=True)
        events.append({'type': 'error', 'message': str(e)})
        events.append(None)
        return {}

@router.get(
    "/full-stream",
    summary="Run Full Library Scan with Streaming Progress",
    description="Run a complete scan with streaming progress updates via Server-Sent Events"
)
async def run_full_scan_stream(library_id: Optional[str] = Query(None, description="Library ID to scan (optional)")):
    """Run a full scan with real-time progress streaming via SSE"""

    logger.info(f"📡 Full scan stream started with library_id: {library_id}")

    # Generate unique scan ID
    scan_id = str(uuid.uuid4())

    # Queue for streaming events
    event_queue = asyncio.Queue()

    async def event_generator():
        try:
            # Send started event with scan_id
            yield f"event: started\ndata: {json.dumps({'type': 'started', 'scan_id': scan_id, 'timestamp': int(time.time())})}\n\n"

            # Start scan in background
            scan_task = asyncio.create_task(_run_full_scan_background(event_queue, scan_id, library_id))
            active_scan_tasks[scan_id] = scan_task

            try:
                # Yield events as they arrive
                while True:
                    try:
                        # Wait for event with timeout
                        event = await asyncio.wait_for(event_queue.get(), timeout=2.0)

                        if event is None:  # Sentinel value = scan complete
                            break

                        event_type = event.get('type', 'progress')
                        if event_type == 'progress':
                            logger.info(f"📡 SSE sending event: {event_type}")
                        yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        # Check if scan is done
                        if scan_task.done():
                            break
                        continue

                # Get final result
                result = await scan_task

                # Send completed event
                completed_data = {
                    'type': 'completed',
                    'processed': result.get('summary', {}).get('tracks_scanned', 0),
                    'total': result.get('summary', {}).get('total_input_tracks', 0),
                    'duration': result.get('duration_seconds', 0)
                }
                yield f"event: completed\ndata: {json.dumps(completed_data)}\n\n"

            finally:
                # Clean up task reference
                active_scan_tasks.pop(scan_id, None)

        except Exception as e:
            logger.error(f"Full scan stream failed: {e}", exc_info=True)
            error_data = {'type': 'error', 'message': str(e)}
            yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
            # Clean up on error
            active_scan_tasks.pop(scan_id, None)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

async def _run_full_scan_background(event_queue: asyncio.Queue, scan_id: str, library_id: Optional[str] = None):
    """Run full scan in background and emit events to queue"""
    try:
        # Get the correct event loop for this asyncio task
        loop = asyncio.get_running_loop()

        # Get Navidrome client and scanner
        navidrome_client = get_navidrome_client()
        scanner = get_library_scanner()

        # Get tracks from Navidrome (filtered by library if specified)
        tracks = await scanner._get_all_tracks_from_navidrome(navidrome_client, force_refresh=True, library_id=library_id)
        if not tracks:
            await event_queue.put({'type': 'error', 'message': 'No tracks found in Navidrome'})
            await event_queue.put(None)
            return {}

        if library_id:
            logger.info(f"Starting full scan stream with {len(tracks)} tracks from library {library_id}")
        else:
            logger.info(f"Starting full scan stream with {len(tracks)} total tracks from Navidrome")

        # Get music directory from environment
        import os
        music_directory = os.getenv("MUSIC_PATH", "/music")

        def progress_callback(event):
            """Callback to receive progress events from scanner"""
            # Put event on queue
            try:
                asyncio.run_coroutine_threadsafe(event_queue.put(event), loop)
            except Exception as e:
                logger.error(f"Failed to put event on queue: {e}")

        # Run full scan with streaming callback
        result = await scanner.scan_library(
            tracks,
            test_mode=False,
            music_directory=music_directory,
            progress_callback=progress_callback,
            library_id=library_id
        )

        # Send sentinel
        await event_queue.put(None)
        return result

    except asyncio.CancelledError:
        logger.info(f"Full scan {scan_id} was cancelled")
        await event_queue.put({'type': 'cancelled', 'message': 'Scan was cancelled by user'})
        await event_queue.put(None)
        raise
    except Exception as e:
        logger.error(f"Full scan background failed: {e}", exc_info=True)
        await event_queue.put({'type': 'error', 'message': str(e)})
        await event_queue.put(None)
        return {}
