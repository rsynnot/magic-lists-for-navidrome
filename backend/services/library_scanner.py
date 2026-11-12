"""
Library scanner service for analyzing music collections and storing audio embeddings.

This service provides:
- Recursive scanning of music directories
- Audio file discovery and validation
- Batch processing with progress tracking
- Integration with ChromaDB for embedding storage
- Scan session management and status tracking
"""

import os
import logging
import asyncio
import uuid
import json
import hashlib
import gc
import csv
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Set
from concurrent.futures import ThreadPoolExecutor
import psutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .audio_analyzer import get_audio_analyzer
from .chroma_service import get_chroma_service
from .audio_analysis_cache import get_audio_analysis_cache
from .chroma_ingestion_service import get_chroma_ingestion_service
from ..database import get_db
from ..navidrome_client import NavidromeClient

logger = logging.getLogger(__name__)

class ScanSession:
    """Represents a library scanning session"""

    def __init__(self, session_id: str, music_directory: str, max_tracks: Optional[int] = None, library_id: Optional[str] = None):
        self.session_id = session_id
        self.music_directory = music_directory
        self.max_tracks = max_tracks
        self.library_id = library_id  # NEW: track which library is being scanned
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.status = "initialized"  # initialized, scanning, completed, failed, cancelled
        self.total_files = 0
        self.processed_files = 0
        self.failed_files = 0
        self.skipped_files = 0
        self.current_file = ""
        self.errors: List[str] = []
        self.failed_tracks: List[Dict[str, Any]] = []  # NEW: detailed failure information
        self.jsonl_files_created: List[str] = []  # NEW: list of created JSONL files

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "progress_percentage": (self.processed_files / self.total_files * 100) if self.total_files > 0 else 0,
            "total_tracks": self.total_files,
            "processed_tracks": self.processed_files,
            "failed_tracks": self.failed_files,
            "skipped_tracks": self.skipped_files,
            "current_file": self.current_file,
            "library_id": self.library_id,
            "started_at": self.start_time.isoformat().replace('+00:00', 'Z'),
            "completed_at": self.end_time.isoformat().replace('+00:00', 'Z') if self.end_time else None,
            "estimated_time_remaining": None,  # TODO: implement time estimation
            "errors": self.errors
        }

class LibraryScanner:
    """Service for scanning music libraries and extracting audio features"""

    def __init__(self):
        self.audio_analyzer = get_audio_analyzer()
        self.chroma_service = get_chroma_service()
        self.cache_service = get_audio_analysis_cache()
        self.ingestion_service = get_chroma_ingestion_service()
        self.active_sessions: Dict[str, ScanSession] = {}
        # Match thread pool workers to batch size for optimal concurrency
        # Use environment variable to control both batch size and worker count
        self.batch_size = int(os.getenv('BATCH_SIZE', '5'))
        self.executor = ThreadPoolExecutor(max_workers=self.batch_size)

    async def start_scan(self, music_directory: str, navidrome_client: NavidromeClient,
                        progress_callback: Optional[Callable] = None, max_tracks: Optional[int] = None,
                        mode: str = "full") -> str:
        """
        Start a new library scan session

        Args:
            music_directory: Root directory to scan for audio files
            navidrome_client: Navidrome client for getting track metadata
            progress_callback: Optional callback for progress updates
            max_tracks: Optional limit on number of tracks to process
            mode: Scan mode - "scan" (analysis only), "ingest" (ChromaDB ingestion), "full" (both phases)

        Returns:
            Session ID for tracking the scan
        """
        session_id = str(uuid.uuid4())
        session = ScanSession(session_id, music_directory, max_tracks)
        self.active_sessions[session_id] = session

        logger.info(f"Starting library scan session {session_id} for directory: {music_directory}")

        # Start scan in background with exception handling
        async def _scan_with_exception_handling():
            try:
                await self._scan_library(session, navidrome_client, progress_callback, max_tracks, mode)
            except Exception as e:
                logger.error(f"💥 Background scan task crashed for session {session_id}: {e}")
                session.status = "failed"
                session.end_time = datetime.now(timezone.utc)
                session.errors.append(f"Background task crashed: {str(e)}")
                logger.error(f"Stack trace for crashed scan {session_id}:", exc_info=True)

        asyncio.create_task(_scan_with_exception_handling())

        return session_id

    async def _get_music_path_for_library(self, library_id: str) -> Optional[str]:
        """Get the music path for a library ID from database mappings"""
        try:
            from ..database import get_db
            db = await get_db()
            return await db.get_music_path_for_library(library_id)
        except Exception as e:
            logger.error(f"Failed to get music path for library {library_id}: {e}")
            return None

    async def scan_library(self, navidrome_tracks: List[Dict], test_mode: bool = False, music_directory: Optional[str] = None, progress_callback: Optional[Callable] = None, library_id: Optional[str] = None) -> Dict:
        """
        Main library scanning function - runs all 3 phases sequentially.

        Args:
            navidrome_tracks: List of track dictionaries from Navidrome
            test_mode: If True, scan only 10 tracks to test_collection
            music_directory: Override music directory (optional)
            progress_callback: Callback for progress updates (optional)
            library_id: Library ID to associate with scanned tracks (optional)

        Returns:
            Complete scan report
        """
        if test_mode:
            logger.info("🧪 Starting TEST library scan (10 tracks to test_collection)")
        else:
            logger.info("🚀 Starting FULL library scan")
        logger.info("=" * 50)

        # Get music directory from parameter or environment
        if not music_directory:
            music_directory = os.getenv("MUSIC_PATH", "/music")
            logger.info(f"Using music directory from environment: {music_directory}")
        
        # Create a temporary session for this scan
        session_id = str(uuid.uuid4())

        # If library_id is provided, look up the correct music path
        if library_id:
            try:
                actual_music_directory = await self._get_music_path_for_library(library_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid library_id format: {library_id}")
                actual_music_directory = None
            if actual_music_directory:
                music_directory = actual_music_directory
                logger.info(f"Using mapped music directory for library {library_id}: {music_directory}")
            else:
                logger.warning(f"No mapping found for library {library_id}, using default path: {music_directory}")

        # Ensure we have a valid music directory
        if not music_directory:
            music_directory = os.getenv("MUSIC_PATH", "/music")

        session = ScanSession(session_id, music_directory, library_id=library_id)

        try:
            # ===== TEST MODE SETUP - BEFORE FILTERING =====
            # IMPORTANT: Must switch collections BEFORE filtering so track_exists() checks the right collection
            if test_mode:
                # Setup test collection (delete/recreate) - this creates a fresh empty collection
                await self.setup_test_collection()

                # Switch ChromaDB service to test collection BEFORE any filtering
                self.chroma_service.switch_collection("test_collection")
                logger.info("🔄 Switched to test_collection for filtering and analysis")
            else:
                # Ensure we're using main collection
                self.chroma_service.switch_collection("audio_embeddings")
                logger.info("🔄 Using main audio_embeddings collection")

            # Discover all audio files on disk
            logger.info(f"📁 Discovering audio files in {music_directory}...")
            all_audio_files = await self._discover_audio_files(music_directory)
            logger.info(f"📁 Found {len(all_audio_files)} audio files on disk")

            # Match tracks to files
            logger.info(f"🔍 Matching {len(navidrome_tracks)} Navidrome tracks to disk files...")
            matched_file_paths = await self._match_tracks_to_files(navidrome_tracks, all_audio_files, music_directory)

            # ===== PHASE 1: PRE-FLIGHT FILTERING =====
            logger.info("=" * 50)
            logger.info("PHASE 1: Pre-Flight Filtering")
            logger.info("=" * 50)

            filter_results = await self.filter_tracks_for_scan(navidrome_tracks, matched_file_paths)
            self._log_filter_results(filter_results)

            tracks_to_scan = filter_results["to_scan"]

            # ===== TEST MODE: LIMIT TO 10 TRACKS =====
            if test_mode:
                original_count = len(tracks_to_scan)
                tracks_to_scan = self.select_test_tracks(tracks_to_scan, count=10)
                logger.info(f"🎯 Test mode: Limited from {original_count} to {len(tracks_to_scan)} tracks")
                logger.info(f"🎯 Test collection is empty, so all {len(tracks_to_scan)} tracks will be scanned")

            # Send preflight complete event
            if progress_callback:
                progress_callback({
                    'type': 'preflight_complete',
                    'total_tracks': filter_results["total_input"],
                    'tracks_to_scan': len(tracks_to_scan)
                })

            if len(tracks_to_scan) == 0:
                logger.info("✅ No tracks need scanning!")
                return {
                    "test_mode": test_mode,
                    "summary": {
                        "total_input_tracks": filter_results["total_input"],
                        "tracks_scanned": 0,
                        "successfully_ingested": 0,
                        "failed_analysis": 0,
                        "failed_ingestion": 0
                    },
                    "filtering": filter_results["filtered_out"],
                    "failed_tracks": []
                }

            # ===== PHASE 2: ANALYSIS & JSONL EXPORT =====
            logger.info("=" * 50)
            logger.info("PHASE 2: Analysis & JSONL Export")
            logger.info("=" * 50)

            # Update session totals AFTER test mode limiting
            session.total_files = len(tracks_to_scan)

            start_time = time.time()

            analysis_results = await self.analyze_tracks(
                tracks_to_scan,
                matched_file_paths,
                session,
                progress_callback
            )

            logger.info(f"📊 Analysis results: {analysis_results['processed']} processed, {analysis_results['failed']} failed")
            logger.info(f"📁 Created {len(analysis_results['jsonl_files'])} JSONL files")

            # ===== PHASE 3: CHROMADB INGESTION =====
            logger.info("=" * 50)
            logger.info("PHASE 3: ChromaDB Ingestion")
            logger.info("=" * 50)

            ingestion_results = await self.ingest_embeddings(
                analysis_results["jsonl_files"]
            )

            total_time = time.time() - start_time

            # ===== GENERATE REPORT =====
            report = self.generate_completion_report(
                filter_results,
                analysis_results,
                ingestion_results
            )

            # Add test mode flag and timing to report
            report["test_mode"] = test_mode
            report["total_time_seconds"] = total_time

            # ===== TEST MODE: CALCULATE ETA =====
            if test_mode:
                # Calculate ETA for full library
                full_library_count = len(filter_results["to_scan"])  # Original count before limiting
                avg_time_per_track = total_time / len(tracks_to_scan) if tracks_to_scan else 0
                estimated_full_time = avg_time_per_track * full_library_count

                report["test_results"] = {
                    "tracks_tested": len(tracks_to_scan),
                    "time_per_track_seconds": avg_time_per_track,
                    "full_library_estimate_seconds": estimated_full_time,
                    "full_library_estimate_formatted": self._format_time(estimated_full_time)
                }

                logger.info("=" * 50)
                logger.info("🧪 TEST SCAN RESULTS")
                logger.info("=" * 50)
                logger.info(f"✅ Scanned {len(tracks_to_scan)} tracks in {self._format_time(total_time)}")
                logger.info(f"⏱️ Average time per track: {avg_time_per_track:.2f}s")
                logger.info(f"📊 Full library ({full_library_count} tracks) estimated: {self._format_time(estimated_full_time)}")
                logger.info("=" * 50)

            # ===== SAVE TO DATABASE FIRST =====
            # Save scan results to database BEFORE setting session status
            try:
                db = await get_db()
                end_time = datetime.now(timezone.utc)

                scan_data = {
                    'session_id': session_id,
                    'music_directory': music_directory,
                    'status': 'completed',
                    'total_tracks': len(tracks_to_scan),
                    'processed_tracks': report["summary"]["tracks_scanned"],
                    'failed_tracks': report["summary"]["failed_analysis"],
                    'skipped_tracks': 0,
                    'duration_seconds': int(total_time),
                    'started_at': (end_time - timedelta(seconds=total_time)).isoformat(),
                    'completed_at': end_time.isoformat(),
                    'max_tracks': 10 if test_mode else None,  # Mark test scans with max_tracks=10
                    'errors': []
                }

                logger.info(f"💾 Saving scan results to database (test_mode={test_mode})")
                result = await db.save_scan_history(scan_data)
                logger.info(f"✅ Saved scan session to history, row ID: {result}")

                # Add database ID to report for frontend reference
                report["scan_history_id"] = result

            except Exception as db_error:
                logger.error(f"Failed to save scan history: {db_error}")
                # Don't fail the scan if database save fails

            # ===== NOW SET SESSION STATUS =====
            session.status = "completed"
            session.end_time = datetime.now(timezone.utc)

            # Log summary
            self._log_completion_summary(report)

            # Reset to main collection after test scan
            if test_mode:
                self.chroma_service.switch_collection("audio_embeddings")
                logger.info("🔄 Switched back to main collection")

            return report

        except Exception as e:
            logger.error(f"💥 Scan failed: {e}")

            # Set session status to failed
            session.status = "failed"
            session.end_time = datetime.now(timezone.utc)
            session.errors.append(str(e))

            # Still try to save failed scan to database
            try:
                db = await get_db()
                end_time = datetime.now(timezone.utc)

                scan_data = {
                    'session_id': session_id,
                    'music_directory': music_directory,
                    'status': 'failed',
                    'total_tracks': len(navidrome_tracks),
                    'processed_tracks': 0,
                    'failed_tracks': 0,
                    'skipped_tracks': 0,
                    'duration_seconds': 0,
                    'started_at': end_time.isoformat(),  # Failed immediately
                    'completed_at': end_time.isoformat(),
                    'max_tracks': 10 if test_mode else None,
                    'errors': [str(e)]
                }

                logger.info(f"💾 Saving failed scan results to database (test_mode={test_mode})")
                result = await db.save_scan_history(scan_data)
                logger.info(f"✅ Saved failed scan session to history, row ID: {result}")

            except Exception as db_error:
                logger.error(f"Failed to save failed scan history: {db_error}")

            return {
                "summary": {
                    "total_input_tracks": len(navidrome_tracks),
                    "tracks_scanned": 0,
                    "successfully_ingested": 0,
                    "failed_analysis": 0,
                    "failed_ingestion": 0
                },
                "error": str(e)
            }

    async def _get_chromadb_navidrome_ids(self) -> Set[str]:
        """Get all navidrome_ids currently stored in ChromaDB"""
        try:
            chroma_service = get_chroma_service()
            all_embeddings = chroma_service.get_all_embeddings()

            navidrome_ids = set()
            for embedding_data in all_embeddings:
                metadata = embedding_data.get("metadata", {})
                navidrome_id = metadata.get("navidrome_id", "")
                if navidrome_id:
                    navidrome_ids.add(navidrome_id)

            logger.info(f"📊 Found {len(navidrome_ids)} navidrome_ids in ChromaDB")
            return navidrome_ids

        except Exception as e:
            logger.error(f"Failed to get navidrome_ids from ChromaDB: {e}")
            return set()

    async def _filter_navidrome_tracks_for_scan(self, track_metadata: Dict[str, Dict[str, Any]], navidrome_client: NavidromeClient) -> Dict[str, Dict[str, Any]]:
        """Filter Navidrome tracks by size, duration, and existing embeddings"""
        logger.info(f"🔍 Starting filtering of {len(track_metadata)} Navidrome tracks")

        # Get existing navidrome_ids from ChromaDB
        existing_navidrome_ids = await self._get_chromadb_navidrome_ids()

        # Get limits from environment
        max_duration_minutes = int(os.getenv('MAX_TRACK_DURATION_MINUTES', '15'))
        max_file_size_mb = int(os.getenv('MAX_FILE_SIZE_MB', '65'))

        filtered_tracks = {}
        skipped_size = 0
        skipped_duration = 0
        skipped_embedded = 0

        for relative_path, track in track_metadata.items():
            navidrome_id = track.get("id", "")
            duration_seconds = track.get("duration", 0)
            path = track.get("path", "")

            # Skip if already embedded
            if navidrome_id and navidrome_id in existing_navidrome_ids:
                skipped_embedded += 1
                logger.debug(f"⏭️ Skipping {track.get('title', 'Unknown')} - already embedded (ID: {navidrome_id})")
                continue

            # Skip if duration exceeds limit
            if duration_seconds:
                duration_minutes = duration_seconds / 60
                if duration_minutes > max_duration_minutes:
                    skipped_duration += 1
                    logger.debug(f"⏭️ Skipping {track.get('title', 'Unknown')} - duration {duration_minutes:.1f}min exceeds {max_duration_minutes}min")
                    continue

            # For size check, we can't check file size without the actual file path
            # This will be checked during processing when we find the disk file
            # But we can estimate based on bitrate if available, or skip this check here

            # Track passes filters
            filtered_tracks[relative_path] = track

        logger.info(f"📊 Filtering complete: {len(filtered_tracks)} tracks to process")
        logger.info(f"📊 Skipped: {skipped_embedded} already embedded, {skipped_duration} too long, {skipped_size} too large")

        return filtered_tracks

    async def _match_tracks_to_disk_files(self, track_metadata: Dict[str, Dict[str, Any]], all_audio_files: List[str], music_directory: str) -> List[str]:
        """Match filtered Navidrome tracks to disk files using hierarchical fuzzy matching"""
        logger.info(f"🔍 Matching {len(track_metadata)} tracks to {len(all_audio_files)} disk files using hierarchical approach")

        matched_files = []
        matched_tracks = set()

        # Build hierarchical file index: artist_dir -> album_dir -> [files]
        file_index = self._build_file_index(all_audio_files, music_directory)

        for relative_path, track in track_metadata.items():
            navidrome_path = track.get("path", "")
            track_title = track.get("title", "")
            track_artist = track.get("artist", "")

            # Find matching disk file using hierarchical search
            matched_file = self._find_file_for_track(track, navidrome_path, file_index, music_directory)

            if matched_file:
                if matched_file not in matched_files:
                    matched_files.append(matched_file)
                    matched_tracks.add(relative_path)
                    logger.debug(f"✅ Matched '{track_title}' by '{track_artist}' -> '{Path(matched_file).name}'")
            else:
                logger.warning(f"❌ No match found for '{track_title}' by '{track_artist}' (Navidrome path: {navidrome_path})")

        logger.info(f"📊 Matched {len(matched_files)} disk files to {len(track_metadata)} Navidrome tracks")
        return matched_files

    async def _match_tracks_to_files(self, navidrome_tracks: List[Dict], all_audio_files: List[str], music_directory: str) -> Dict[str, str]:
        """
        Match Navidrome tracks to disk files and return mapping of track_id -> file_path.

        Args:
            navidrome_tracks: List of track dictionaries from Navidrome
            all_audio_files: List of all audio file paths on disk
            music_directory: Root music directory

        Returns:
            Dict mapping track_id to matched file path
        """
        matched_file_paths = {}

        # Build hierarchical file index: artist_dir -> album_dir -> [files]
        file_index = self._build_file_index(all_audio_files, music_directory)

        for track in navidrome_tracks:
            track_id = track.get("id", "")
            navidrome_path = track.get("path", "")
            track_title = track.get("title", "")
            track_artist = track.get("artist", "")

            # Find matching disk file using hierarchical search
            matched_file = self._find_file_for_track(track, navidrome_path, file_index, music_directory)

            if matched_file:
                matched_file_paths[track_id] = matched_file
                logger.debug(f"✅ Matched '{track_title}' by '{track_artist}' -> '{Path(matched_file).name}'")
            else:
                logger.debug(f"❌ No match found for '{track_title}' by '{track_artist}' (Navidrome path: {navidrome_path})")

        logger.info(f"📊 Created mapping for {len(matched_file_paths)} tracks out of {len(navidrome_tracks)} total tracks")
        return matched_file_paths

    def _build_file_index(self, all_audio_files: List[str], music_directory: str) -> Dict[str, Dict[str, List[str]]]:
        """Build hierarchical index of files by artist/album directories"""
        file_index = {}

        for file_path in all_audio_files:
            try:
                # Get relative path from music directory
                rel_path = os.path.relpath(file_path, music_directory)
                parts = rel_path.split(os.sep)

                if len(parts) >= 2:  # At least artist/album/filename
                    artist_dir = parts[0]
                    album_dir = parts[1] if len(parts) > 2 else ""
                    filename = parts[-1]

                    # Initialize artist directory
                    if artist_dir not in file_index:
                        file_index[artist_dir] = {}

                    # Initialize album directory
                    if album_dir not in file_index[artist_dir]:
                        file_index[artist_dir][album_dir] = []

                    # Add file to album directory
                    file_index[artist_dir][album_dir].append(file_path)

                else:
                    # Files not in artist/album structure - add to root
                    if "" not in file_index:
                        file_index[""] = {"": []}
                    if "" not in file_index[""]:
                        file_index[""][""] = []
                    file_index[""][""].append(file_path)

            except (ValueError, OSError):
                # Handle files that can't be relativized
                if "" not in file_index:
                    file_index[""] = {"": []}
                if "" not in file_index[""]:
                    file_index[""][""] = []
                file_index[""][""].append(file_path)

        return file_index

    def _find_file_for_track(self, track: Dict[str, Any], navidrome_path: str, file_index: Dict[str, Dict[str, List[str]]], music_directory: str) -> Optional[str]:
        """Find disk file for Navidrome track using hierarchical search"""

        # Parse Navidrome path to extract expected location
        path_parts = navidrome_path.strip('/').split('/') if navidrome_path else []
        expected_artist = path_parts[0] if len(path_parts) > 0 else ""
        expected_album = path_parts[1] if len(path_parts) > 1 else ""
        expected_filename = path_parts[-1] if path_parts else ""

        track_title = track.get("title", "")
        track_artist = track.get("artist", "")

        # 1. Try exact path match
        if navidrome_path:
            exact_path = os.path.join(music_directory, navidrome_path)
            if os.path.exists(exact_path) and os.path.isfile(exact_path):
                return exact_path

        # 2. Try exact filename match in expected album directory
        if expected_artist in file_index and expected_album in file_index[expected_artist]:
            album_files = file_index[expected_artist][expected_album]
            exact_match = self._find_exact_filename_match(expected_filename, album_files)
            if exact_match:
                return exact_match

        # 3. Try fuzzy match in expected album directory
        if expected_artist in file_index and expected_album in file_index[expected_artist]:
            album_files = file_index[expected_artist][expected_album]
            fuzzy_match = self._find_fuzzy_match(track_title, track_artist, album_files)
            if fuzzy_match:
                return fuzzy_match

        # 4. Try exact filename match in expected artist directory (any album)
        if expected_artist in file_index:
            artist_files = []
            for album_files in file_index[expected_artist].values():
                artist_files.extend(album_files)

            exact_match = self._find_exact_filename_match(expected_filename, artist_files)
            if exact_match:
                return exact_match

        # 5. Try fuzzy match in expected artist directory
        if expected_artist in file_index:
            artist_files = []
            for album_files in file_index[expected_artist].values():
                artist_files.extend(album_files)

            fuzzy_match = self._find_fuzzy_match(track_title, track_artist, artist_files)
            if fuzzy_match:
                return fuzzy_match

        # 6. Try exact filename match across all files
        all_files = []
        for artist_data in file_index.values():
            for album_files in artist_data.values():
                all_files.extend(album_files)

        exact_match = self._find_exact_filename_match(expected_filename, all_files)
        if exact_match:
            return exact_match

        # 7. Try fuzzy match across all files (fallback)
        fuzzy_match = self._find_fuzzy_match(track_title, track_artist, all_files)
        if fuzzy_match:
            return fuzzy_match

        return None

    def _find_exact_filename_match(self, expected_filename: str, file_list: List[str]) -> Optional[str]:
        """Find exact filename match in file list"""
        if not expected_filename:
            return None

        expected_stem = Path(expected_filename).stem.lower()
        for file_path in file_list:
            file_stem = Path(file_path).stem.lower()
            if file_stem == expected_stem:
                return file_path

        return None

    def _find_fuzzy_match(self, track_title: str, track_artist: str, file_list: List[str]) -> Optional[str]:
        """Find fuzzy match in file list using simplified approach"""
        if not track_title:
            return None

        # Create title variations
        title_variations = [
            track_title.lower(),
            self._normalize_filename(track_title),
            track_title.lower().strip(),
        ]

        for file_path in file_list:
            file_stem = Path(file_path).stem

            # Create file variations
            file_variations = [
                file_stem.lower(),
                self._normalize_filename(file_stem),
                file_stem.lower().strip(),
            ]

            # Try without track numbers
            no_track_num = re.sub(r'^\d+[-\s\.]*', '', file_stem.lower())
            if no_track_num != file_stem.lower():
                file_variations.extend([
                    no_track_num,
                    self._normalize_filename(no_track_num)
                ])

            # Check for any reasonable match (simplified logic)
            for title_var in title_variations:
                for file_var in file_variations:
                    # Exact match
                    if title_var == file_var:
                        return file_path

                    # One contains the other
                    if title_var in file_var or file_var in title_var:
                        return file_path

                    # Word overlap check (simplified)
                    title_words = set(title_var.split())
                    file_words = set(file_var.split())

                    if title_words and file_words:
                        intersection = title_words.intersection(file_words)
                        if len(intersection) >= 1:  # At least one word matches
                            union = title_words.union(file_words)
                            overlap_ratio = len(intersection) / len(union)
                            if overlap_ratio >= 0.3:  # 30% word overlap
                                return file_path

        return None

    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename for better matching"""
        import re

        # Convert to lowercase
        normalized = filename.lower()

        # Remove track numbers at start (01., 1-, etc.)
        normalized = re.sub(r'^\d+[-\s\.]*', '', normalized)

        # Remove artist prefixes (Artist - Title pattern)
        # Split on common separators and take the last part (usually the title)
        parts = re.split(r'\s*[-–]\s*', normalized)
        if len(parts) > 1:
            # If it looks like "Artist - Title", take the title part
            normalized = parts[-1].strip()
        else:
            normalized = parts[0].strip()

        # Remove common suffixes in parentheses/brackets
        normalized = re.sub(r'\s*\[.*?\]|\(.*?\)', '', normalized)

        # Replace multiple spaces with single space
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized.strip()

    def _calculate_match_score(self, title1: str, title2: str, artist: str = "") -> float:
        """Calculate match score between two normalized titles"""
        # Exact match
        if title1 == title2:
            return 100.0

        # One contains the other
        if title1 in title2 or title2 in title1:
            return 80.0

        # Word-based matching
        words1 = set(title1.split())
        words2 = set(title2.split())

        if not words1 or not words2:
            return 0.0

        # Calculate word overlap
        intersection = words1.intersection(words2)
        union = words1.union(words2)

        if intersection:
            overlap_score = (len(intersection) / len(union)) * 60.0

            # Bonus for longer matches
            if len(intersection) >= 2:
                overlap_score += 10.0

            return overlap_score

        # No word overlap - check for partial matches
        partial_score = 0.0
        for word1 in words1:
            for word2 in words2:
                # Check for substring matches
                if len(word1) > 3 and len(word2) > 3:
                    if word1 in word2 or word2 in word1:
                        partial_score += 20.0
                        break

        return min(partial_score, 40.0)  # Cap partial matches

    async def filter_tracks_for_scan(
        self,
        navidrome_tracks: List[Dict],
        matched_file_paths: Dict[str, str]  # track_id -> filesystem path
    ) -> Dict:
        """
        Filter tracks that don't need to be scanned.

        Args:
            navidrome_tracks: All tracks from Navidrome
            matched_file_paths: Mapping of track_id to matched file path

        Returns:
            {
                "to_scan": [list of tracks to process],
                "filtered_out": {
                    "already_scanned": 0,
                    "too_long": 0,
                    "too_large": 0,
                    "missing_files": 0,
                    "total": 0
                },
                "total_input": 2500
            }
        """
        to_scan = []
        filtered_out = {
            "already_scanned": 0,
            "too_long": 0,
            "too_large": 0,
            "missing_files": 0,
            "total": 0
        }

        # Configuration from environment
        max_file_size_mb = int(os.getenv('MAX_FILE_SIZE_MB', '65'))
        max_duration_min = int(os.getenv('MAX_TRACK_DURATION_MINUTES', '15'))

        for track in navidrome_tracks:
            track_id = track.get("id")
            if not track_id:
                logger.warning(f"Track missing ID: {track}")
                filtered_out["missing_files"] += 1
                continue

            # Check 1: Missing file
            if track_id not in matched_file_paths:
                filtered_out["missing_files"] += 1
                continue

            file_path = matched_file_paths[track_id]

            # Check 2: File size
            try:
                file_size_bytes = os.path.getsize(file_path)
                if file_size_bytes is not None:
                    file_size_mb = file_size_bytes / (1024 * 1024)
                    if file_size_mb > max_file_size_mb:
                        filtered_out["too_large"] += 1
                        logger.info(f"⏭️ Skipping {os.path.basename(file_path)} - file size {file_size_mb:.1f}MB exceeds limit of {max_file_size_mb}MB")
                        continue
            except (OSError, IOError, TypeError) as e:
                logger.warning(f"Could not check file size for {file_path}: {e}")
                # Continue processing if we can't check file size

            # Check 3: Duration
            duration_seconds = track.get("duration")
            if duration_seconds is not None and duration_seconds > 0:
                duration_minutes = duration_seconds / 60
                if duration_minutes > max_duration_min:
                    filtered_out["too_long"] += 1
                    logger.debug(f"⏭️ Skipping {track.get('title', 'Unknown')} - duration {duration_minutes:.1f}min exceeds limit of {max_duration_min}min")
                    continue

            # Check 4: Already scanned (exists in ChromaDB)
            if self.chroma_service.track_exists(track_id):
                filtered_out["already_scanned"] += 1
                logger.debug(f"⏭️ Skipping {track.get('title', 'Unknown')} - already exists in ChromaDB (track_id: {track_id})")
                continue

            # Passed all checks
            to_scan.append(track)

        # Calculate total filtered out
        filtered_out["total"] = (
            filtered_out["already_scanned"] +
            filtered_out["too_long"] +
            filtered_out["too_large"] +
            filtered_out["missing_files"]
        )

        return {
            "to_scan": to_scan,
            "filtered_out": filtered_out,
            "total_input": len(navidrome_tracks)
        }

    async def analyze_tracks(
        self,
        tracks_to_scan: List[Dict],
        matched_file_paths: Dict[str, str],
        session: ScanSession,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        Analyze tracks and write embeddings to JSONL files.

        Args:
            tracks_to_scan: Filtered tracks from Phase 1
            matched_file_paths: Track ID to file path mapping
            session: Scan session for progress tracking
            progress_callback: Optional callback for progress updates

        Returns:
            {
                "processed": 1195,
                "failed": 5,
                "jsonl_files": ["batch_0.jsonl", "batch_1.jsonl", ...],
                "failed_tracks": [...]
            }
        """
        logger.info(f"🎵 Starting analysis of {len(tracks_to_scan)} tracks")

        # Send initial progress event (1%) to show analysis has started
        if progress_callback:
            event_data = {
                'type': 'processing',
                'filename': 'Starting analysis...',
                'processed': 0,
                'total': len(tracks_to_scan)
            }
            logger.debug("📤 Sending initial analysis progress event (1%)")
            progress_callback(event_data)

        # Configuration
        batch_size = int(os.getenv('BATCH_SIZE', '5'))  # Concurrent processing threads
        chroma_write_batch = int(os.getenv('CHROMA_WRITE_BATCH', '100'))  # Tracks per JSONL file

        embeddings_buffer = []
        batch_number = 0
        jsonl_files = []
        processed_count = 0

        # Process tracks in batches
        for i in range(0, len(tracks_to_scan), batch_size):
            # Check for cancellation
            current_task = asyncio.current_task()
            if current_task and current_task.cancelled():
                logger.info("Scan cancelled during analysis phase")
                raise asyncio.CancelledError("Scan was cancelled")

            batch = tracks_to_scan[i:i + batch_size]

            # Log batch start with worker count
            batch_num = i // batch_size + 1
            logger.info(f"🔄 Starting batch {batch_num}: {len(batch)} tracks with {self.batch_size} workers")

            # Send progress event for first track in batch
            if progress_callback and batch:
                first_track = batch[0]
                filename = first_track.get("title", "Unknown")
                if first_track.get("album"):
                    filename = f"{filename} - {first_track.get('album')}"
                event_data = {
                    'type': 'processing',
                    'filename': filename,
                    'processed': i,
                    'total': len(tracks_to_scan)
                }
                logger.debug(f"📤 Sending batch start event: {event_data['filename']}")
                progress_callback(event_data)

            # Process batch concurrently
            tasks = [
                self._process_single_track(track, matched_file_paths, session)
                for track in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            for track, result in zip(batch, results):
                if isinstance(result, Exception):
                    # Track failed - collect error details
                    session.failed_tracks.append({
                        "track_id": track["id"],
                        "title": track.get("title", "Unknown"),
                        "artist": track.get("artist", "Unknown"),
                        "album": track.get("album", "Unknown"),
                        "file_path": matched_file_paths.get(track["id"], "unknown"),
                        "error": str(result),
                        "error_type": type(result).__name__
                    })
                    session.failed_files += 1
                    logger.warning(f"❌ Failed to process {track.get('title', 'Unknown')}: {result}")
                elif result is not None:
                    # Track succeeded - add to buffer
                    embeddings_buffer.append(result)
                    processed_count += 1
                    session.processed_files += 1

                # Write JSONL when buffer is full
                if len(embeddings_buffer) >= chroma_write_batch:
                    file_path = await self._write_embeddings_batch(
                        embeddings_buffer,
                        batch_number
                    )
                    jsonl_files.append(file_path)
                    session.jsonl_files_created.append(file_path)
                    batch_number += 1

                    # Aggressive garbage collection after JSONL write
                    embeddings_buffer = []  # Clear buffer
                    logger.debug("🗑️ Forcing garbage collection after JSONL write")
                    gc.collect()  # Force garbage collection
                    await asyncio.sleep(0.1)  # Let GC complete

            # Update progress
            progress = (i + len(batch)) / len(tracks_to_scan) * 100

            # Send progress event for streaming
            if progress_callback and batch:
                # Get filename from the last track in the batch
                last_track = batch[-1]
                filename = last_track.get("title", "Unknown")
                if last_track.get("album"):
                    filename = f"{filename} - {last_track.get('album')}"
                if progress_callback:
                    event_data = {
                        'type': 'processing',
                        'filename': filename,
                        'processed': i + len(batch),
                        'total': len(tracks_to_scan)
                    }
                    logger.debug(f"📤 Sending processing event: {event_data['processed']}/{event_data['total']}")
                    progress_callback(event_data)

            # Log CPU and memory usage with progress
            mem = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=0.1)  # Quick CPU check
            logger.info(f"📊 Progress: {progress:.1f}% | CPU: {cpu_percent:.1f}% | Memory: {mem.percent:.1f}% ({mem.used / (1024**3):.2f}GB used)")

            # Throttle processing to prevent CPU overload (using already measured cpu_percent)
            if cpu_percent > 80:
                logger.warning(f"🌡️ CPU hot ({cpu_percent:.1f}%), cooling down...")
                await asyncio.sleep(2.0)  # Longer cooldown for high CPU
            else:
                await asyncio.sleep(0.5)  # Standard cooldown between batches

            if progress_callback:
                # Send progress event with frontend-expected field names
                progress_callback({
                    'type': 'progress',
                    'processed': session.processed_files,
                    'total': session.total_files,
                    'percentage': (session.processed_files / session.total_files * 100) if session.total_files > 0 else 0,
                    'status': session.status,
                    'current_file': session.current_file
                })

        # Write remaining embeddings
        if embeddings_buffer:
            file_path = await self._write_embeddings_batch(
                embeddings_buffer,
                batch_number
            )
            jsonl_files.append(file_path)
            session.jsonl_files_created.append(file_path)

            # Aggressive garbage collection after final JSONL write
            embeddings_buffer = []  # Clear buffer
            logger.debug("🗑️ Forcing garbage collection after final JSONL write")
            gc.collect()  # Force garbage collection
            await asyncio.sleep(0.1)  # Let GC complete

        logger.info(f"✅ Analysis complete: {processed_count} processed, {len(session.failed_tracks)} failed")

        return {
            "processed": processed_count,
            "failed": len(session.failed_tracks),
            "jsonl_files": jsonl_files,
            "failed_tracks": session.failed_tracks
        }

    async def _process_single_track(
        self,
        track: Dict,
        matched_file_paths: Dict[str, str],
        session: ScanSession
    ) -> Optional[Dict]:
        """
        Process a single track with librosa.

        Returns:
            Embedding dict or None if failed
        """
        track_id = track["id"]
        file_path = matched_file_paths.get(track_id)

        if not file_path:
            raise ValueError(f"No file path found for track {track_id}")

        # LOG BEFORE PROCESSING
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        logger.info(f"🎵 Loading: {os.path.basename(file_path)} ({file_size_mb:.1f}MB)")

        try:
            # Extract embedding with librosa
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor, self.audio_analyzer.analyze_file, file_path
            )
            embedding, reason = result

            if embedding is None:
                raise ValueError(f"Analysis failed: {reason}")

            logger.info(f"✅ Processed: {os.path.basename(file_path)}")

            # Build embedding dict for JSONL
            embedding_data = {
                "track_id": track_id,
                "title": track.get("title"),
                "artist": track.get("artist"),
                "album": track.get("album"),
                "duration": track.get("duration"),
                "embedding": embedding,  # This will be converted to list by JSON serialization
                "file_path": file_path,
                "file_size_mb": file_size_mb,
                "library_id": session.library_id,  # NEW: include library_id for ChromaDB filtering
                "processed_at": datetime.now(timezone.utc).isoformat()
            }

            return embedding_data

        except Exception as e:
            logger.error(f"❌ FAILED: {os.path.basename(file_path)} - {e}")
            # Re-raise to let gather() handle it
            raise

    async def _write_embeddings_batch(
        self,
        embeddings_batch: List[Dict],
        batch_number: int
    ) -> str:
        """
        Write a batch of embeddings to JSONL file.

        Args:
            embeddings_batch: List of embedding dicts
            batch_number: Sequential batch number

        Returns:
            Path to created JSONL file
        """
        # Use cache directory for JSONL files
        cache_dir = Path("./cache/audio_analysis")
        cache_dir.mkdir(parents=True, exist_ok=True)

        output_file = f"embeddings_batch_{batch_number:03d}.jsonl"
        output_path = cache_dir / output_file

        with open(output_path, 'w') as f:
            for embedding in embeddings_batch:
                # Convert numpy arrays to lists for JSON serialization
                serializable_item = {}
                for key, value in embedding.items():
                    if hasattr(value, 'tolist'):  # Check if it's a numpy array
                        serializable_item[key] = value.tolist()
                    else:
                        serializable_item[key] = value
                json.dump(serializable_item, f)
                f.write('\n')

        logger.info(f"✍️ Wrote {len(embeddings_batch)} embeddings to {output_file}")
        return str(output_path)

    async def setup_test_collection(self):
        """
        Prepare test collection - delete if exists, create fresh.
        Always ensures test_collection is clean and ready for testing.
        """
        test_collection_name = "test_collection"

        # Ensure ChromaDB service is initialized
        self.chroma_service._ensure_initialized()

        client = self.chroma_service.client
        if not client:
            logger.error("❌ ChromaDB client not initialized, cannot setup test collection")
            raise Exception("ChromaDB client not initialized")

        # Step 1: Check if collection exists and delete it
        try:
            # Check if collection exists first
            existing_collections = client.list_collections()
            collection_names = [col.name for col in existing_collections]

            if test_collection_name in collection_names:
                logger.info(f"🗑️ Found existing test_collection, deleting...")
                client.delete_collection(test_collection_name)
                logger.info("🗑️ Deleted existing test_collection")
            else:
                logger.info("ℹ️ No existing test_collection found")
        except Exception as e:
            logger.warning(f"⚠️ Issue checking/deleting test_collection: {e}")
            # Try to delete anyway in case it exists
            try:
                client.delete_collection(test_collection_name)
                logger.info("🗑️ Force deleted test_collection")
            except Exception as force_delete_error:
                logger.debug(f"Force delete failed (collection probably doesn't exist): {force_delete_error}")

        # Step 2: Create fresh test collection
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"✨ Creating fresh test_collection (attempt {attempt + 1}/{max_retries})")
                new_collection = client.create_collection(
                    name=test_collection_name,
                    metadata={"type": "test", "created_at": datetime.now(timezone.utc).isoformat()}
                )
                logger.info(f"✨ Created fresh test_collection: {new_collection.name}")

                # Verify collection exists and is empty
                test_collection = client.get_collection(test_collection_name)
                initial_count = test_collection.count()
                logger.info(f"✅ Verified test_collection exists, initial count: {initial_count}")

                if initial_count > 0:
                    logger.warning(f"⚠️ New test_collection has {initial_count} tracks, clearing...")
                    # Clear any existing tracks
                    all_ids = test_collection.get(include=[])['ids']
                    if all_ids:
                        test_collection.delete(ids=all_ids)
                        logger.info(f"🧹 Cleared {len(all_ids)} existing tracks from test_collection")

                return  # Success

            except Exception as e:
                logger.warning(f"❌ Failed to create test_collection (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"❌ Failed to create test_collection after {max_retries} attempts", exc_info=True)
                    raise
                # Wait a bit before retrying
                await asyncio.sleep(0.5)

    def select_test_tracks(self, all_tracks: List[Dict], count: int = 10) -> List[Dict]:
        """
        Select tracks for test scan.

        Strategy: Take first N tracks that would be scanned
        (after filtering, so they're representative of actual work)

        Args:
            all_tracks: All available tracks
            count: Number of tracks to select (default 10)

        Returns:
            List of selected tracks
        """
        # Take first N tracks (simplest approach)
        selected = all_tracks[:count]

        logger.info(f"🎯 Selected {len(selected)} tracks for test scan")
        return selected

    def _format_time(self, seconds: float) -> str:
        """Format seconds into human-readable time."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def _log_filter_results(self, filter_results: Dict):
        """Log the results of pre-flight filtering."""
        filtered = filter_results["filtered_out"]
        total_input = filter_results["total_input"]
        total_filtered = filtered["total"]
        to_scan = len(filter_results["to_scan"])

        logger.info("🔍 Pre-flight filtering:")
        logger.info(f"  - Input tracks: {total_input}")
        logger.info(f"  - Already scanned: {filtered['already_scanned']}")
        logger.info(f"  - Too long (>{os.getenv('MAX_TRACK_DURATION_MINUTES', '15')}min): {filtered['too_long']}")
        logger.info(f"  - Too large (>{os.getenv('MAX_AUDIO_FILE_SIZE_MB', '100')}MB): {filtered['too_large']}")
        logger.info(f"  - Missing files: {filtered['missing_files']}")
        logger.info(f"  - Total filtered out: {total_filtered}")
        logger.info(f"  ✅ Tracks to scan: {to_scan}")

    async def ingest_embeddings(self, jsonl_files: List[str], progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Ingest JSONL files into ChromaDB.
        
        Args:
            jsonl_files: List of JSONL file paths to ingest
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dict with ingestion results
        """
        import numpy as np
        from pathlib import Path
        
        logger.info(f"📥 Starting ingestion of {len(jsonl_files)} JSONL files")
        logger.info(f"📥 Current ChromaDB collection: {self.chroma_service.collection_name}")
        logger.info(f"📥 Collection object: {self.chroma_service.collection}")
        
        # Verify collection is ready
        if not self.chroma_service.collection:
            logger.error("❌ No collection available for ingestion!")
            return {"total_ingested": 0, "total_failed": len(jsonl_files) * 10}  # Estimate
        
        total_ingested = 0
        total_failed = 0
        
        for jsonl_file in jsonl_files:
            try:
                # Ensure file path exists
                file_path = Path(jsonl_file)
                if not file_path.exists():
                    logger.error(f"JSONL file not found: {jsonl_file}")
                    continue
                    
                logger.info(f"📄 Reading JSONL file: {file_path}")
                
                with open(file_path, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        try:
                            data = json.loads(line)
                            track_id = data.get("track_id")
                            embedding = data.get("embedding")
                            
                            if not track_id or not embedding:
                                total_failed += 1
                                logger.warning(f"Line {line_num}: Missing track_id or embedding")
                                continue
                            
                            # Convert embedding list to numpy array
                            if isinstance(embedding, list):
                                embedding = np.array(embedding, dtype=np.float32)
                            elif not isinstance(embedding, np.ndarray):
                                total_failed += 1
                                logger.error(f"Line {line_num}: Embedding is not a list or array: {type(embedding)}")
                                continue
                            
                            # Build metadata from JSONL data (metadata is NOT nested, it's at top level)
                            metadata = {
                                "title": data.get("title", ""),
                                "artist": data.get("artist", ""),
                                "album": data.get("album", ""),
                                "duration": data.get("duration", 0),
                                "genre": data.get("genre", ""),
                                "year": data.get("year", 0),
                                "navidrome_id": track_id,  # Use track_id as navidrome_id
                                "file_path": data.get("file_path", ""),
                                "library_id": data.get("library_id", "")  # NEW: include library_id from JSONL
                            }
                            
                            # Store in ChromaDB (current collection - test or main)
                            try:
                                success = self.chroma_service.store_embedding(track_id, embedding, metadata)
                                if success:
                                    total_ingested += 1
                                    logger.debug(f"✅ Ingested {track_id} ({metadata.get('title')}) to {self.chroma_service.collection_name}")
                                else:
                                    total_failed += 1
                                    logger.error(f"❌ Failed to store {track_id} - store_embedding returned False")
                            except Exception as store_error:
                                total_failed += 1
                                logger.error(f"❌ Exception storing {track_id}: {store_error}", exc_info=True)
                                
                        except json.JSONDecodeError as e:
                            total_failed += 1
                            logger.error(f"Line {line_num}: JSON decode error: {e}")
                        except Exception as e:
                            total_failed += 1
                            logger.error(f"Line {line_num}: Ingestion error: {e}")
                            
            except Exception as e:
                logger.error(f"Failed to read JSONL file {jsonl_file}: {e}")
                
        logger.info(f"✅ Ingestion complete: {total_ingested} ingested, {total_failed} failed")
        
        return {
            "total_ingested": total_ingested,
            "total_failed": total_failed
        }

    def generate_completion_report(
        self,
        filter_results: Dict,
        analysis_results: Dict,
        ingestion_results: Dict
    ) -> Dict:
        """
        Generate a comprehensive completion report.
        
        Args:
            filter_results: Results from filtering phase
            analysis_results: Results from analysis phase
            ingestion_results: Results from ingestion phase
            
        Returns:
            Dict with complete scan summary
        """
        # Calculate the effective scan total (what was actually targeted)
        # For test scans: 10, For full scans: filtered count
        scan_total = analysis_results["processed"] + analysis_results["failed"]  # Total attempted

        return {
            "summary": {
                "total_input_tracks": filter_results["total_input"],
                "scan_total": scan_total,  # Tracks actually targeted for scanning
                "tracks_scanned": analysis_results["processed"],
                "successfully_ingested": ingestion_results["total_ingested"],
                "failed_analysis": analysis_results["failed"],
                "failed_ingestion": ingestion_results["total_failed"]
            },
            "filtering": filter_results["filtered_out"],
            "failed_tracks": analysis_results.get("failed_tracks", [])
        }

    def _log_completion_summary(self, report: Dict):
        """Log the completion summary."""
        summary = report.get("summary", {})
        
        logger.info("=" * 50)
        logger.info("📊 SCAN COMPLETION SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Total input tracks: {summary.get('total_input_tracks', 0)}")
        logger.info(f"Tracks scanned: {summary.get('tracks_scanned', 0)}")
        logger.info(f"Successfully ingested: {summary.get('successfully_ingested', 0)}")
        logger.info(f"Failed analysis: {summary.get('failed_analysis', 0)}")
        logger.info(f"Failed ingestion: {summary.get('failed_ingestion', 0)}")
        logger.info("=" * 50)

    async def _ingest_cached_batches(self, session: ScanSession, progress_callback: Optional[Callable] = None):
        """Ingest cached audio analysis batches into ChromaDB"""
        try:
            logger.info("Starting Phase 2: ChromaDB ingestion from cached batches")

            # Get ingestion progress
            progress_info = self.ingestion_service.get_ingestion_progress()
            logger.info(f"Cache progress: {progress_info['cache_progress']}")

            # Ingest all cached batches
            ingestion_result = self.ingestion_service.ingest_all_cached_batches()

            logger.info(f"Phase 2 complete: {ingestion_result['successful_batches']}/{ingestion_result['total_batches']} batches ingested, {ingestion_result['total_ingested']} embeddings")

            session.status = "completed"
            session.end_time = datetime.now(timezone.utc)

            if progress_callback:
                progress_callback({
                    'type': 'progress',
                    'processed': session.processed_files,
                    'total': session.total_files,
                    'percentage': (session.processed_files / session.total_files * 100) if session.total_files > 0 else 0,
                    'status': session.status,
                    'current_file': session.current_file
                })

        except Exception as e:
            logger.error(f"Phase 2 ingestion failed: {e}")
            session.status = "failed"
            session.errors.append(f"Ingestion failed: {str(e)}")
            session.end_time = datetime.now(timezone.utc)
            raise

    def _init_memory_logger(self, session: ScanSession):
        """Initialize CSV memory logger"""
        csv_path = Path("backend/memory_watchdog.csv")
        if not csv_path.exists():
            with open(csv_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    'timestamp',
                    'session_id',
                    'batch_number',
                    'batch_size',
                    'memory_percent_before',
                    'memory_used_gb_before',
                    'memory_percent_after',
                    'memory_used_gb_after',
                    'processed_files',
                    'total_files'
                ])
        logger.info(f"Initialized memory watchdog CSV: {csv_path}")

    async def _scan_library(self, session: ScanSession, navidrome_client: NavidromeClient,
                            progress_callback: Optional[Callable] = None, max_tracks: Optional[int] = None,
                            mode: str = "full"):
        """Internal method to perform the actual scanning"""
        logger.info(f"🔍 _scan_library called with mode: '{mode}'")
        try:
            # Handle different scan modes
            if mode == "ingest":
                # Phase 2: Ingest cached embeddings into ChromaDB
                session.status = "ingesting"
                await self._ingest_cached_batches(session, progress_callback)
                return
            elif mode == "scan":
                # Phase 1: Audio analysis and caching
                session.status = "scanning"
            elif mode == "full":
                # Both phases: scan then ingest
                session.status = "scanning"
            else:
                raise ValueError(f"Invalid scan mode: {mode}. Must be 'scan', 'ingest', or 'full'")

            # ===== PHASE 1: PRE-FLIGHT FILTERING =====
            logger.info("=" * 50)
            logger.info("PHASE 1: Pre-Flight Filtering")
            logger.info("=" * 50)

            # Get track metadata from Navidrome
            track_metadata = await self._get_track_metadata(navidrome_client, session.music_directory, force_refresh=False)
            navidrome_tracks = list(track_metadata.values())

            # Discover all audio files on disk
            all_audio_files = await self._discover_audio_files(session.music_directory)

            # Match tracks to files
            logger.info(f"🔍 Matching {len(navidrome_tracks)} Navidrome tracks to disk files...")
            matched_file_paths = await self._match_tracks_to_files(navidrome_tracks, all_audio_files, session.music_directory)

            # Apply unified pre-filtering
            logger.info(f"🔍 Applying unified pre-filtering...")
            filter_results = await self.filter_tracks_for_scan(navidrome_tracks, matched_file_paths)

            # Log results
            self._log_filter_results(filter_results)

            if len(filter_results["to_scan"]) == 0:
                logger.info("✅ No tracks need scanning!")
                session.status = "completed"
                session.end_time = datetime.now(timezone.utc)
                return {
                    "summary": {
                        "total_input_tracks": filter_results["total_input"],
                        "tracks_scanned": 0,
                        "successfully_ingested": 0,
                        "failed_analysis": 0,
                        "failed_ingestion": 0
                    },
                    "filtering": filter_results["filtered_out"],
                    "failed_tracks": []
                }

            # ===== PHASE 2: ANALYSIS & JSONL EXPORT =====
            logger.info("=" * 50)
            logger.info("PHASE 2: Analysis & JSONL Export")
            logger.info("=" * 50)

            analysis_results = await self.analyze_tracks(
                filter_results["to_scan"],
                matched_file_paths,
                session,
                progress_callback
            )

            logger.info(f"📊 Analysis results: {analysis_results['processed']} processed, {analysis_results['failed']} failed")
            logger.info(f"📁 Created {len(analysis_results['jsonl_files'])} JSONL files")

            # ===== PHASE 3: CHROMADB INGESTION =====
            logger.info("=" * 50)
            logger.info("PHASE 3: ChromaDB Ingestion")
            logger.info("=" * 50)

            ingestion_results = await self.ingest_embeddings(
                analysis_results["jsonl_files"],
                progress_callback
            )

            # ===== GENERATE REPORT =====
            report = self.generate_completion_report(
                filter_results,
                analysis_results,
                ingestion_results
            )

            # Log summary
            self._log_completion_summary(report)

            session.status = "completed"
            session.end_time = datetime.now(timezone.utc)

            return report

            # Save completed scan to database
            scan_data = None
            try:
                db = await get_db()
                duration_seconds = int((session.end_time - session.start_time).total_seconds()) if session.end_time else None

                scan_data = {
                    'session_id': str(session.session_id),
                    'music_directory': str(session.music_directory),
                    'status': str(session.status),
                    'total_tracks': int(session.total_files),
                    'processed_tracks': int(session.processed_files),
                    'failed_tracks': int(session.failed_files),
                    'skipped_tracks': int(session.skipped_files),
                    'duration_seconds': duration_seconds,
                    'started_at': str(session.start_time.isoformat()),
                    'completed_at': str(session.end_time.isoformat()) if session.end_time else None,
                    'max_tracks': session.max_tracks,
                    'errors': session.errors
                }

                logger.info(f"Saving scan history for session {session.session_id}")
                result = await db.save_scan_history(scan_data)
                logger.info(f"Successfully saved scan session {session.session_id} to history, row ID: {result}")
            except Exception as db_error:
                logger.error(f"Failed to save scan history for session {session.session_id}: {db_error}")
                logger.error(f"Scan data was: {scan_data}")

            # Log memory usage summary
            final_mem = psutil.virtual_memory()
            logger.info(f"📊 Scan completed - Memory summary: Peak usage not tracked, final: {final_mem.percent:.1f}% ({final_mem.used/(1024**3):.2f}GB)")
            logger.info(f"Completed scan session {session.session_id}: {session.processed_files} processed, {session.failed_files} failed")

        except Exception as e:
            session.status = "failed"
            session.end_time = datetime.now(timezone.utc)
            session.errors.append(str(e))
            logger.error(f"Scan session {session.session_id} failed: {e}")

            # Save failed scan to database
            try:
                db = await get_db()
                duration_seconds = int((session.end_time - session.start_time).total_seconds()) if session.end_time else None

                scan_data = {
                    'session_id': str(session.session_id),
                    'music_directory': str(session.music_directory),
                    'status': str(session.status),
                    'total_tracks': int(session.total_files),
                    'processed_tracks': int(session.processed_files),
                    'failed_tracks': int(session.failed_files),
                    'skipped_tracks': int(session.skipped_files),
                    'duration_seconds': duration_seconds,
                    'started_at': str(session.start_time.isoformat()),
                    'completed_at': str(session.end_time.isoformat()) if session.end_time else None,
                    'max_tracks': session.max_tracks,
                    'errors': session.errors
                }

                logger.info(f"Saving failed scan history for session {session.session_id}")
                result = await db.save_scan_history(scan_data)
                logger.info(f"Successfully saved failed scan session {session.session_id} to history, row ID: {result}")
            except Exception as db_error:
                logger.error(f"Failed to save failed scan history for session {session.session_id}: {db_error}")

        finally:
            if progress_callback:
                progress_callback({
                    'type': 'progress',
                    'processed': session.processed_files,
                    'total': session.total_files,
                    'percentage': (session.processed_files / session.total_files * 100) if session.total_files > 0 else 0,
                    'status': session.status,
                    'current_file': session.current_file
                })

    async def _discover_audio_files(self, directory: str) -> List[str]:
        """Discover all supported audio files in directory"""
        audio_files = []
        supported_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma'}

        def scan_dir(path: str):
            """Recursively scan directory for audio files"""
            try:
                for entry in os.scandir(path):
                    if entry.is_file():
                        if Path(entry.name).suffix.lower() in supported_extensions:
                            audio_files.append(entry.path)
                    elif entry.is_dir() and not entry.name.startswith('.'):
                        try:
                            scan_dir(entry.path)
                        except OSError as e:
                            logger.warning(f"OSError accessing subdirectory {entry.path}: {e}. Skipping.")
            except PermissionError:
                logger.warning(f"Permission denied accessing: {path}")
            except OSError as e:
                logger.warning(f"OSError accessing {path}: {e}. Skipping this directory.")

        # Run scan in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, scan_dir, directory)

        return audio_files

    def _validate_track_paths(self, session: ScanSession, track_metadata: Dict[str, Dict[str, Any]]) -> None:
        """
        Validate that sample tracks from Navidrome exist on disk.
        This catches path configuration issues early before processing all files.
        """
        if not track_metadata:
            raise ValueError("No track metadata available from Navidrome. Cannot validate paths.")

        # Check first 3 tracks as samples
        sample_tracks = list(track_metadata.values())[:3]
        missing_tracks = []

        for track in sample_tracks:
            track_path = track.get('path', '')
            if not track_path:
                missing_tracks.append(f"{track.get('title', 'Unknown')} (no path)")
                continue

            full_path = os.path.join(session.music_directory, track_path)
            if not os.path.exists(full_path):
                # Try multiple fallback strategies to find the track
                track_title = track.get('title', '')
                found_alternative = False

                if track_title:
                    # Strategy 1: Look for exact title match anywhere in music directory
                    try:
                        for root, dirs, files in os.walk(session.music_directory):
                            for file in files:
                                if (track_title.lower() in file.lower() and
                                    file.endswith(('.mp3', '.flac', '.m4a', '.ogg', '.wav'))):
                                    found_alternative = True
                                    logger.info(f"✅ Found track '{track_title}' with alternative path: {os.path.join(root, file)}")
                                    break
                            if found_alternative:
                                break
                    except Exception as e:
                        logger.warning(f"Error during title search: {e}")

                    # Strategy 2: Fuzzy filename matching - check if key parts match
                    if not found_alternative:
                        navidrome_filename = os.path.basename(track_path)
                        # Remove common prefixes like "01-02 - " to get core title
                        core_title = navidrome_filename
                        # Remove track numbers and separators
                        import re
                        core_title = re.sub(r'^\d+[-\s]*', '', core_title)  # Remove leading numbers
                        core_title = core_title.replace('.mp3', '').replace('.flac', '').strip()

                        try:
                            for root, dirs, files in os.walk(session.music_directory):
                                for file in files:
                                    if not file.endswith(('.mp3', '.flac', '.m4a', '.ogg', '.wav')):
                                        continue

                                    file_core = file.replace('.mp3', '').replace('.flac', '').replace('.m4a', '').replace('.ogg', '').replace('.wav', '').strip()
                                    file_core = re.sub(r'^\d+[-\s]*', '', file_core)  # Remove leading numbers

                                    # Check if core titles match (case insensitive)
                                    if core_title.lower() == file_core.lower():
                                        found_alternative = True
                                        logger.info(f"✅ Found track '{track_title}' with fuzzy match. Navidrome: '{core_title}', File: '{file_core}' at {os.path.join(root, file)}")
                                        break
                                if found_alternative:
                                    break
                        except Exception as e:
                            logger.warning(f"Error during fuzzy matching: {e}")

                if not found_alternative:
                    missing_tracks.append(f"{track.get('title', 'Unknown')} at {full_path}")
                else:
                    logger.info(f"Track '{track_title}' found with alternative matching, continuing with scan")

        if missing_tracks:
            error_msg = f"Path validation failed: {len(missing_tracks)}/{len(sample_tracks)} sample tracks not found on disk. " \
                        f"This usually means Navidrome's music library paths are out of sync with your file system. " \
                        f"Please rescan your music library in Navidrome to update the file paths. " \
                        f"Missing tracks: {', '.join(missing_tracks)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"✅ Path validation passed: {len(sample_tracks)} sample tracks found on disk")

    async def _get_track_metadata(self, navidrome_client: NavidromeClient, music_directory: str, force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        """Get track metadata from Navidrome for correlation"""
        try:
            # Get all tracks from Navidrome using search API (more reliable than genre-based approach)
            tracks = await self._get_all_tracks_from_navidrome(navidrome_client, force_refresh)

            # Create lookup by relative path from music directory root
            metadata_lookup = {}

            for track in tracks:
                path = track.get("path")
                if path:
                    # Normalize path separators and create lookup key
                    normalized_path = path.replace('\\', '/').lstrip('/')
                    metadata_lookup[normalized_path] = track

            logger.info(f"Loaded metadata for {len(metadata_lookup)} tracks from Navidrome using path-based lookup")
            
            # Debug: Log first few paths to understand the format
            if tracks:
                logger.debug(f"Sample Navidrome paths:")
                for i, track in enumerate(tracks[:3]):
                    logger.debug(f"  {i+1}. Path: '{track.get('path')}' -> Title: '{track.get('title')}' by '{track.get('artist')}'")
            
            return metadata_lookup

        except Exception as e:
            logger.error(f"Failed to get track metadata from Navidrome: {e}")
            return {}

    def _get_cache_key(self, navidrome_client: NavidromeClient) -> str:
        """Generate a cache key based on Navidrome server and library configuration"""
        # Create a hash of server URL and library IDs to identify unique cache
        cache_data = {
            "server_url": navidrome_client.base_url,
            "username": navidrome_client.username
        }
        cache_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_string.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the cache file path for a given cache key"""
        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / f"navidrome_tracks_{cache_key}.json"

    def _get_processing_status_path(self, cache_key: str) -> Path:
        """Get the processing status cache file path"""
        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / f"processing_status_{cache_key}.json"

    async def _load_track_cache(self, navidrome_client: NavidromeClient) -> Optional[Dict[str, Any]]:
        """Load track cache if it exists and is valid"""
        try:
            cache_key = self._get_cache_key(navidrome_client)
            cache_path = self._get_cache_path(cache_key)

            if not cache_path.exists():
                logger.info("No track cache found, will fetch from Navidrome")
                return None

            # Check if cache is recent (less than 24 hours old)
            cache_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
            cache_age = datetime.now(timezone.utc) - cache_mtime

            if cache_age > timedelta(hours=24):
                logger.info(f"Track cache is {cache_age.total_seconds()/3600:.1f} hours old, refreshing")
                return None

            # Load and validate cache
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Validate cache structure
            if not isinstance(cache_data, dict) or 'tracks' not in cache_data:
                logger.warning("Invalid cache structure, will refresh")
                return None

            tracks = cache_data['tracks']
            if not isinstance(tracks, list):
                logger.warning("Invalid tracks data in cache, will refresh")
                return None

            # Validate track data integrity
            if tracks:
                sample_track = tracks[0]
                required_fields = ['id', 'title', 'artist', 'path']
                if not all(field in sample_track for field in required_fields):
                    logger.warning("Cache tracks missing required fields, will refresh")
                    return None

            # Validate processing status if present
            processing_status = cache_data.get('processing_status')
            if processing_status:
                if not isinstance(processing_status, dict):
                    logger.warning("Invalid processing status in cache, will refresh")
                    return None

            logger.info(f"Loaded {len(tracks)} tracks from cache (age: {cache_age.total_seconds()/3600:.1f} hours)")
            return cache_data

        except Exception as e:
            logger.warning(f"Failed to load track cache: {e}")
            return None

    async def _save_track_cache(self, navidrome_client: NavidromeClient, tracks: List[Dict[str, Any]]) -> bool:
        """Save tracks to cache file"""
        try:
            cache_key = self._get_cache_key(navidrome_client)
            cache_path = self._get_cache_path(cache_key)

            cache_data = {
                "server_url": navidrome_client.base_url,
                "username": navidrome_client.username,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "track_count": len(tracks),
                "tracks": tracks,
                "processing_status": {
                    "last_processed_index": -1,
                    "completed_tracks": [],
                    "failed_tracks": [],
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
            }

            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved {len(tracks)} tracks to cache: {cache_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save track cache: {e}")
            return False

    async def _update_processing_status(self, navidrome_client: NavidromeClient,
                                       last_processed_index: int,
                                       completed_track_path: Optional[str] = None,
                                       failed_track_path: Optional[str] = None,
                                       session_id: Optional[str] = None) -> bool:
        """Update processing status in separate cache file"""
        try:
            cache_key = self._get_cache_key(navidrome_client)
            status_path = self._get_processing_status_path(cache_key)

            # Load current status or create new
            if status_path.exists():
                with open(status_path, 'r', encoding='utf-8') as f:
                    status = json.load(f)
            else:
                status = {
                    "last_processed_index": -1,
                    "completed_tracks": [],
                    "failed_tracks": [],
                    "last_updated": None
                }

            # Update status
            status['last_processed_index'] = last_processed_index
            status['last_updated'] = datetime.now(timezone.utc).isoformat()

            if session_id:
                status['session_id'] = session_id

            if completed_track_path:
                if completed_track_path not in status['completed_tracks']:
                    status['completed_tracks'].append(completed_track_path)

            if failed_track_path:
                if failed_track_path not in status['failed_tracks']:
                    status['failed_tracks'].append(failed_track_path)

            # Save updated status
            with open(status_path, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")
            return False

    async def _get_processing_status(self, navidrome_client: NavidromeClient) -> Dict[str, Any]:
        """Get current processing status from separate cache file"""
        try:
            cache_key = self._get_cache_key(navidrome_client)
            status_path = self._get_processing_status_path(cache_key)

            if not status_path.exists():
                return {
                    "last_processed_index": -1,
                    "completed_tracks": [],
                    "failed_tracks": [],
                    "last_updated": None
                }

            with open(status_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Failed to get processing status: {e}")
            return {
                "last_processed_index": -1,
                "completed_tracks": [],
                "failed_tracks": [],
                "last_updated": None
            }

    async def _get_all_tracks_from_navidrome_paginated(self, navidrome_client: NavidromeClient, max_tracks: Optional[int] = None, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all tracks from Navidrome using search API with pagination support"""
        try:
            await navidrome_client._ensure_authenticated()

            all_tracks = []
            offset = 0
            batch_size = 1000  # Reasonable batch size for pagination
            total_fetched = 0

            while True:
                # Use search3 API to get tracks in batches
                params = navidrome_client._get_subsonic_params()
                params["query"] = ""  # Empty query = all tracks
                params["artistCount"] = 0
                params["albumCount"] = 0
                params["songCount"] = batch_size
                params["songOffset"] = offset
                if library_id:
                    params["musicFolderId"] = library_id
                    logger.info(f"🔍 Filtering tracks by library: {library_id}, params: {params}")

                response = await navidrome_client.client.get(
                    f"{navidrome_client.base_url}/rest/search3.view",
                    params=params
                )
                response.raise_for_status()

                data = response.json()

                # Handle Subsonic API response format
                subsonic_response = data.get("subsonic-response", {})
                if subsonic_response.get("status") != "ok":
                    error = subsonic_response.get("error", {})
                    raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

                search_result = subsonic_response.get("searchResult3", {})
                songs = search_result.get("song", [])

                if library_id:
                    logger.info(f"🔍 Fetched {len(songs)} songs for library {library_id} (offset: {offset})")
                else:
                    logger.info(f"🔍 Fetched {len(songs)} songs (offset: {offset})")

                if not songs:
                    # No more tracks to fetch
                    break

                # Convert to consistent track format
                batch_tracks = []
                for song in songs:
                    track = {
                        "id": song.get("id"),
                        "title": song.get("title"),
                        "artist": song.get("artist"),
                        "album": song.get("album"),
                        "year": song.get("year"),
                        "genre": song.get("genre"),
                        "play_count": song.get("playCount", 0),
                        "local_library_likes": song.get("starred") is not None,
                        "duration": song.get("duration"),
                        "track_number": song.get("track"),
                        "path": song.get("path")  # Relative path from music folder root
                    }
                    batch_tracks.append(track)

                all_tracks.extend(batch_tracks)
                total_fetched += len(batch_tracks)
                offset += batch_size

                logger.info(f"Fetched batch {offset//batch_size}: {len(batch_tracks)} tracks (total: {total_fetched})")

                # Safety check to prevent infinite loops
                if len(songs) < batch_size:
                    break

                # Respect max_tracks limit if specified
                if max_tracks and total_fetched >= max_tracks:
                    all_tracks = all_tracks[:max_tracks]
                    break

            logger.info(f"Retrieved {len(all_tracks)} tracks from Navidrome using paginated search API")
            return all_tracks

        except Exception as e:
            logger.error(f"Failed to get all tracks from Navidrome: {e}")
            return []

    async def _get_all_tracks_from_navidrome(self, navidrome_client: NavidromeClient, force_refresh: bool = False, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all tracks from Navidrome using search API with caching support"""
        logger.info(f"🔍 _get_all_tracks_from_navidrome called with force_refresh={force_refresh}")

        # Try to load from cache first (unless force_refresh is True)
        if not force_refresh:
            logger.info("🔍 Checking cache (force_refresh=False)")
            cache_data = await self._load_track_cache(navidrome_client)
            if cache_data:
                logger.info(f"🔍 Loaded {len(cache_data['tracks'])} tracks from cache")
                return cache_data['tracks']
        else:
            logger.info("🔍 Skipping cache check (force_refresh=True)")

        # Cache miss, invalid, or force refresh - fetch from Navidrome
        logger.info("Fetching tracks from Navidrome (cache miss or force refresh)")
        tracks = await self._get_all_tracks_from_navidrome_paginated(navidrome_client, library_id=library_id)

        # Save to cache for future use (unless force_refresh)
        if tracks and not force_refresh:
            await self._save_track_cache(navidrome_client, tracks)

        return tracks

    async def _process_batch(self, session: ScanSession, batch: List[str],
                            track_metadata: Dict[str, Dict[str, Any]],
                            navidrome_client: NavidromeClient,
                            progress_callback: Optional[Callable] = None,
                            mode: str = "full"):
        """Process a batch of audio files"""
        logger.info(f"📦 Processing batch of {len(batch)} tracks...")

        # Log thread pool status
        logger.debug(f"📦 Thread pool status: active_threads={len(self.executor._threads) if hasattr(self.executor, '_threads') else 'unknown'}, "
                    f"max_workers={self.executor._max_workers}")

        tasks = []

        for file_path in batch:
            task = asyncio.create_task(self._process_file(session, file_path, track_metadata, navidrome_client, mode))
            tasks.append(task)

        # Wait for all files in batch to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results and update session counters
        batch_cache_data = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Exception was already handled in _process_file
                continue
            elif result is not None:
                batch_cache_data.append(result)
                session.processed_files += 1
                # Update processing status
                await self._update_processing_status(navidrome_client, session.processed_files - 1, batch[i], None)
            else:
                # Failed result was already counted in _process_file
                pass

        # Write batch to cache if we have data
        if batch_cache_data:
            batch_number = (session.processed_files - len(batch_cache_data)) // self.batch_size + 1
            self.cache_service.write_batch(batch_cache_data, batch_number)
            logger.info(f"📦 Cached batch {batch_number} with {len(batch_cache_data)} embeddings")

        logger.info(f"📦 Batch completed: {session.processed_files}/{session.total_files} tracks processed")

        # Aggressive memory cleanup after batch processing
        # ChromaDB maintains in-memory indexes that grow with each batch,
        # so we need thorough cleanup to prevent memory accumulation
        gc.collect()

        # Force garbage collection multiple times for thorough cleanup
        for _ in range(3):
            gc.collect()

        # Lower GC thresholds to trigger collection more frequently
        gc.set_threshold(700, 10, 10)

        # Check memory usage and adjust batch size if needed (more conservative thresholds)
        mem_after = psutil.virtual_memory()
        if mem_after.percent > 40:  # If memory > 40%, reduce batch size (conservative to avoid 55% restarts)
            old_batch_size = self.batch_size
            self.batch_size = max(1, self.batch_size // 2)  # Minimum batch size of 1
            if self.batch_size != old_batch_size:
                logger.warning(f"⚠️ High memory usage ({mem_after.percent:.1f}%), reducing batch size from {old_batch_size} to {self.batch_size}")
        elif mem_after.percent < 25 and self.batch_size < 10:  # If memory low, can increase batch size
            old_batch_size = self.batch_size
            self.batch_size = min(10, self.batch_size * 2)  # Maximum batch size of 10
            if self.batch_size != old_batch_size:
                logger.info(f"✅ Memory usage low ({mem_after.percent:.1f}%), increasing batch size to {self.batch_size}")

            if progress_callback:
                # Send progress event with frontend-expected field names
                await progress_callback({
                    'type': 'progress',
                    'processed': session.processed_files,
                    'total': session.total_files,
                    'percentage': (session.processed_files / session.total_files * 100) if session.total_files > 0 else 0,
                    'status': session.status,
                    'current_file': session.current_file
                })

    async def _process_file(self, session: ScanSession, file_path: str,
                            track_metadata: Dict[str, Dict[str, Any]], navidrome_client: NavidromeClient,
                            mode: str = "full") -> Optional[Dict[str, Any]]:
        """Process a single audio file"""
        try:
            session.current_file = file_path
            logger.info(f"🔍 Analyzing track: {os.path.basename(file_path)} (using direct file access)")

            # Log memory and system resources before processing
            mem_before = psutil.virtual_memory()
            cpu_before = psutil.cpu_percent(interval=None)
            logger.debug(f"🔍 Memory before file processing: {mem_before.percent:.1f}% used ({mem_before.used / (1024**3):.2f}GB), CPU: {cpu_before:.1f}%")

            # Analyze audio file
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor, self.audio_analyzer.analyze_file, file_path
            )
            embedding, reason = result

            # Log memory and system resources after processing
            mem_after = psutil.virtual_memory()
            cpu_after = psutil.cpu_percent(interval=None)
            logger.debug(f"🔍 Memory after file processing: {mem_after.percent:.1f}% used ({mem_after.used / (1024**3):.2f}GB), CPU: {cpu_after:.1f}%")

            if embedding is None:
                if reason in ["skipped_size", "skipped_memory", "skipped_short"]:
                    session.skipped_files += 1
                    logger.info(f"⏭️ Skipped: {os.path.basename(file_path)} - {reason.replace('_', ' ')}")
                else:
                    session.failed_files += 1
                    session.errors.append(f"Failed to analyze: {file_path}")
                return

            # Calculate relative path from music directory root
            relative_path = "unknown"
            try:
                music_dir_path = Path(session.music_directory).resolve()
                file_path_obj = Path(file_path).resolve()
                relative_path = str(file_path_obj.relative_to(music_dir_path))
                # Normalize path separators for cross-platform compatibility
                relative_path = relative_path.replace('\\', '/').lstrip('/')
            except (ValueError, OSError) as e:
                logger.warning(f"Could not calculate relative path for {file_path}: {e}")
                relative_path = f"unknown_{hash(file_path)}"

            # Create consistent track ID using file path hash
            track_id = f"file_{hash(file_path)}"

            # Duplicate checking is now done in pre-filtering phase

            # Now do the expensive metadata lookup only if we need to process the track
            track_meta = track_metadata.get(relative_path)

            if not track_meta:
                # Fallback to filename-based matching if path matching fails
                logger.info(f"No path match found for {relative_path}, trying filename fallback")
                track_meta = self._find_track_metadata_by_filename(file_path, track_metadata)
                if track_meta:
                    logger.info(f"✅ Found metadata match: {track_meta.get('title')} by {track_meta.get('artist')}")
                else:
                    logger.warning(f"❌ No metadata match found for {os.path.basename(file_path)}")

            # Duration check moved to pre-filtering stage

            # Prepare metadata for storage
            metadata = {
                "file_path": file_path,
                "relative_path": relative_path,
                "file_name": Path(file_path).name,
                "title": track_meta.get("title", Path(file_path).stem) if track_meta else Path(file_path).stem,
                "artist": track_meta.get("artist", "Unknown Artist") if track_meta else "Unknown Artist",
                "album": track_meta.get("album", "Unknown Album") if track_meta else "Unknown Album",
                "genre": track_meta.get("genre", "") if track_meta else "",
                "year": track_meta.get("year", 0) if track_meta else 0,
                "duration": track_meta.get("duration", 0) if track_meta else 0,
                "navidrome_id": track_meta.get("id", "") if track_meta else "",
                "analyzed_at": datetime.now().isoformat()
            }

            # Return cache data for batch processing
            cache_data = {
                "track_id": track_id,
                "embedding": embedding,
                "metadata": metadata
            }

            logger.info(f"✅ Completed: {os.path.basename(file_path)} - embedding ready for caching")
            return cache_data

        except Exception as e:
            session.failed_files += 1
            session.errors.append(f"Error processing {file_path}: {str(e)}")
            logger.error(f"Error processing file {file_path}: {e}")
            return None

        # Aggressive memory cleanup after processing each file
        gc.collect()

        # Additional memory management for long-running scans
        mem_current = psutil.virtual_memory()
        if mem_current.percent > 45:  # More frequent cleanup when memory gets high
            gc.set_threshold(500, 5, 5)  # Even more aggressive GC
        else:
            gc.set_threshold(700, 10, 10)  # Normal thresholds

    def _find_track_metadata_by_filename(self, file_path: str, track_metadata: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Fallback method to find track metadata using filename-based matching"""
        file_name = Path(file_path).stem.lower()
        file_basename = Path(file_path).name.lower()

        # Strategy 1: Direct lookup by filename (in case path lookup failed)
        if file_name in track_metadata:
            logger.debug(f"Found direct filename match for: {file_name}")
            return track_metadata[file_name]

        # Strategy 2: Try matching against Navidrome titles directly
        for key, meta in track_metadata.items():
            title = meta.get("title", "").lower().strip()
            artist = meta.get("artist", "").lower().strip()
            
            # Clean filename for comparison - remove common separators and normalize
            clean_file_name = file_name.replace("-", " ").replace("_", " ").replace(".", " ").replace("  ", " ").strip()
            clean_title = title.replace("-", " ").replace("_", " ").replace(".", " ").replace("  ", " ").strip()
            
            # Exact title match
            if clean_file_name == clean_title:
                logger.debug(f"Found exact title match: '{clean_file_name}' -> '{clean_title}'")
                return meta
            
            # Contains match (filename contains title or title contains filename)
            if clean_file_name in clean_title or clean_title in clean_file_name:
                logger.debug(f"Found contains match: '{clean_file_name}' <-> '{clean_title}'")
                return meta
                
            # Fuzzy match - check if most words match
            file_words = set(clean_file_name.split())
            title_words = set(clean_title.split())
            
            if file_words and title_words:
                # Calculate similarity based on word overlap
                overlap = len(file_words.intersection(title_words))
                similarity = overlap / max(len(file_words), len(title_words))
                
                if similarity > 0.7:  # 70% word overlap
                    logger.debug(f"Found fuzzy match ({similarity:.2f}): '{clean_file_name}' -> '{clean_title}'")
                    return meta

        logger.debug(f"No metadata match found for file: {file_name}")
        return None

    def get_scan_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a scan session"""
        session = self.active_sessions.get(session_id)
        return session.to_dict() if session else None

    def cancel_scan(self, session_id: str) -> bool:
        """Cancel a running scan session"""
        session = self.active_sessions.get(session_id)
        if session and session.status in ["initialized", "scanning"]:
            session.status = "cancelled"
            session.end_time = datetime.now(timezone.utc)

            logger.info(f"Cancelled scan session {session_id}, previous status was {session.status}, now set to cancelled")

            # Note: Database save will happen when the scan task completes
            # We can't save here because this method is called from sync context

            return True
        logger.warning(f"Could not cancel scan {session_id}: session not found or status is {session.status if session else 'None'}")
        return False

    def get_active_scans(self) -> List[Dict[str, Any]]:
        """Get all active scan sessions"""
        return [session.to_dict() for session in self.active_sessions.values()
                if session.status in ["initialized", "scanning"]]

    def cleanup_completed_scans(self, max_age_hours: int = 24):
        """Clean up old completed scan sessions"""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

        to_remove = []
        for session_id, session in self.active_sessions.items():
            if session.end_time and session.end_time.timestamp() < cutoff_time:
                to_remove.append(session_id)

        for session_id in to_remove:
            del self.active_sessions[session_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old scan sessions")

    def get_system_resources(self) -> Dict[str, Any]:
        """Get current system resource usage"""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": psutil.virtual_memory().used / (1024**3),
            "memory_available_gb": psutil.virtual_memory().available / (1024**3),
            "active_scans": len(self.get_active_scans())
        }

    async def _save_scan_state(self, session: ScanSession):
        """Save scan state for crash recovery"""
        try:
            db = await get_db()
            state_data = {
                'session_id': str(session.session_id),
                'music_directory': str(session.music_directory),
                'status': str(session.status),
                'total_tracks': int(session.total_files),
                'processed_tracks': int(session.processed_files),
                'failed_tracks': int(session.failed_files),
                'skipped_tracks': int(session.skipped_files),
                'current_file': str(session.current_file),
                'started_at': str(session.start_time.isoformat()),
                'max_tracks': session.max_tracks,
                'errors': session.errors[:10],  # Limit error history
                'last_saved': str(datetime.now(timezone.utc).isoformat())
            }

            # Save to a special crash recovery table or use existing scan history
            # For now, we'll update the scan history table with current state
            result = await db.save_scan_history(state_data)
            logger.debug(f"💾 Saved scan state for session {session.session_id}: {session.processed_files}/{session.total_files} processed")
            return result
        except Exception as e:
            logger.warning(f"Failed to save scan state for session {session.session_id}: {e}")
            return None


# Global service instance
_library_scanner = None

def get_library_scanner() -> LibraryScanner:
    """Get the global library scanner instance"""
    global _library_scanner
    if _library_scanner is None:
        _library_scanner = LibraryScanner()
    return _library_scanner