import sqlite3
import aiosqlite
import os
from typing import List, Optional, Dict
from datetime import datetime
import json

from .schemas import Playlist, ScheduledPlaylist

class DatabaseManager:
    """SQLite database manager for storing playlists"""
    
    def __init__(self, db_path: str = "magiclists.db"):
        self.db_path = db_path
    
    async def init_db(self):
        """Initialize the database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_id TEXT NOT NULL,
                    playlist_name TEXT NOT NULL,
                    songs TEXT, -- JSON array of song titles
                    reasoning TEXT, -- AI reasoning/description
                    navidrome_playlist_id TEXT, -- Link to Navidrome playlist
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add reasoning column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN reasoning TEXT")
            except:
                # Column already exists or other error - ignore
                pass
            
            # Add navidrome_playlist_id column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN navidrome_playlist_id TEXT")
            except:
                # Column already exists or other error - ignore
                pass

            # Add library_ids column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN library_ids TEXT")  # JSON array of library IDs
            except:
                # Column already exists or other error - ignore
                pass
            
            # Add last_refreshed column if it doesn't exist (for tracking refreshes)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN last_refreshed TIMESTAMP")
            except:
                # Column already exists or other error - ignore
                pass
            
            # Add playlist_length column if it doesn't exist (for storing original length)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN playlist_length INTEGER")
            except:
                # Column already exists or other error - ignore
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_type TEXT NOT NULL,
                    navidrome_playlist_id TEXT NOT NULL,
                    refresh_frequency TEXT NOT NULL,
                    next_refresh TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_type TEXT NOT NULL,
                    navidrome_playlist_id TEXT NOT NULL,
                    refresh_frequency TEXT NOT NULL,
                    next_refresh TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create the app_config table for storing application configuration
            await db.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Create the library_analytics table for tracking library size
            await db.execute("""
                CREATE TABLE IF NOT EXISTS library_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    song_count INTEGER NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create the user_preferences table for storing user settings like selected library
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,  -- For future multi-user support
                    selected_library_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create the playlist_history_v2 table for Re-Discover Weekly v2.0 logging
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_history_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    navidrome_server_id TEXT NOT NULL,
                    mode_used TEXT NOT NULL,
                    primary_theme TEXT,
                    tracks_analyzed_count INTEGER NOT NULL,
                    track_ids_json TEXT NOT NULL,  -- JSON array of track IDs
                    track_count INTEGER NOT NULL,
                    reasoning TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create the api_cache table for caching API responses
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL UNIQUE,
                    cache_value TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index on cache_key for faster lookups
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_cache_key ON api_cache(cache_key)
            """)

            # Create index on expires_at for cleanup
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache(expires_at)
            """)

            await db.commit()
    
    async def create_playlist(self, artist_id: str, playlist_name: str, songs: Optional[List[str]] = None, reasoning: Optional[str] = None, navidrome_playlist_id: Optional[str] = None, playlist_length: Optional[int] = None, library_ids: Optional[List[str]] = None) -> Optional[Playlist]:
        """Create a new playlist in the database"""
        await self.init_db()
        
        songs_json = json.dumps(songs or [])
        library_ids_json = json.dumps(library_ids or [])

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO playlists (artist_id, playlist_name, songs, reasoning, navidrome_playlist_id, playlist_length, library_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (artist_id, playlist_name, songs_json, reasoning, navidrome_playlist_id, playlist_length, library_ids_json))
            
            playlist_id = cursor.lastrowid
            await db.commit()
            
            # Fetch the created playlist
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, reasoning, navidrome_playlist_id, created_at, updated_at, playlist_length, library_ids
                FROM playlists WHERE id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=json.loads(row[3]),
                        reasoning=row[4],
                        navidrome_playlist_id=row[5],
                        created_at=row[6],
                        updated_at=row[7],
                        library_ids=json.loads(row[9]) if row[9] else []
                    )
                return None
    
    async def get_playlist(self, playlist_id: int) -> Optional[Playlist]:
        """Get a playlist by ID"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, reasoning, navidrome_playlist_id, created_at, updated_at, playlist_length, library_ids
                FROM playlists WHERE id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=json.loads(row[3]),
                        reasoning=row[4],
                        navidrome_playlist_id=row[5],
                        created_at=row[6],
                        updated_at=row[7],
                        library_ids=json.loads(row[9]) if row[9] else []
                    )
        return None
    
    async def get_playlists_by_artist(self, artist_id: str) -> List[Playlist]:
        """Get all playlists for a specific artist"""
        await self.init_db()
        
        playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, created_at, updated_at
                FROM playlists WHERE artist_id = ?
                ORDER BY created_at DESC
            """, (artist_id,)) as cursor:
                rows = await cursor.fetchall()
                
                for row in rows:
                    playlist = Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=json.loads(row[3]),
                        created_at=row[4],
                        updated_at=row[5]
                    )
                    playlists.append(playlist)
        
        return playlists
    
    async def get_all_playlists_with_schedule_info(self) -> List[Dict]:
        """Get all playlists with their scheduling information"""
        await self.init_db()
        
        playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 
                    p.id, 
                    p.artist_id, 
                    p.playlist_name, 
                    p.songs, 
                    p.reasoning,
                    p.navidrome_playlist_id,
                    p.created_at, 
                    p.updated_at,
                    p.last_refreshed,
                    p.playlist_length,
                    sp.refresh_frequency,
                    sp.next_refresh,
                    sp.playlist_type
                FROM playlists p
                LEFT JOIN scheduled_playlists sp ON p.navidrome_playlist_id = sp.navidrome_playlist_id
                ORDER BY p.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
                
                for row in rows:
                    playlist_data = {
                        "id": row[0],
                        "artist_id": row[1],
                        "playlist_name": row[2],
                        "songs": json.loads(row[3]),
                        "reasoning": row[4],
                        "navidrome_playlist_id": row[5],
                        "created_at": row[6],
                        "updated_at": row[7],
                        "last_refreshed": row[8],
                        "playlist_length": row[9],
                        "refresh_frequency": row[10],
                        "next_refresh": row[11],
                        "playlist_type": row[12]
                    }
                    playlists.append(playlist_data)
        
        return playlists
    
    async def get_playlist_by_id_with_schedule_info(self, playlist_id: int) -> Optional[Dict]:
        """Get a specific playlist with its scheduling information"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 
                    p.id, 
                    p.artist_id, 
                    p.playlist_name, 
                    p.songs, 
                    p.reasoning,
                    p.created_at, 
                    p.updated_at,
                    p.navidrome_playlist_id,
                    sp.refresh_frequency,
                    sp.next_refresh,
                    sp.playlist_type
                FROM playlists p
                LEFT JOIN scheduled_playlists sp ON p.navidrome_playlist_id = sp.navidrome_playlist_id
                WHERE p.id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return {
                        "id": row[0],
                        "artist_id": row[1],
                        "playlist_name": row[2],
                        "songs": json.loads(row[3]),
                        "reasoning": row[4],
                        "created_at": row[5],
                        "updated_at": row[6],
                        "navidrome_playlist_id": row[7],
                        "refresh_frequency": row[8],
                        "next_refresh": row[9],
                        "playlist_type": row[10]
                    }
        
        return None
    
    async def delete_playlist(self, playlist_id: int) -> bool:
        """Delete a playlist from the database"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM playlists WHERE id = ?
            """, (playlist_id,))
            
            await db.commit()
            return cursor.rowcount > 0
    
    async def delete_scheduled_playlist_by_navidrome_id(self, navidrome_playlist_id: str) -> bool:
        """Delete a scheduled playlist by Navidrome playlist ID"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM scheduled_playlists WHERE navidrome_playlist_id = ?
            """, (navidrome_playlist_id,))
            
            await db.commit()
            return cursor.rowcount > 0
    
    async def update_playlist_songs(self, playlist_id: int, songs: List[str]) -> bool:
        """Update the songs in a playlist"""
        await self.init_db()
        
        songs_json = json.dumps(songs)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE playlists 
                SET songs = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (songs_json, playlist_id))
            
            await db.commit()
            return cursor.rowcount > 0
    
    async def create_scheduled_playlist(self, playlist_type: str, navidrome_playlist_id: str,
                                      refresh_frequency: str, next_refresh: datetime) -> ScheduledPlaylist:
        """Create a new scheduled playlist"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO scheduled_playlists (playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh)
                VALUES (?, ?, ?, ?)
            """, (playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh.isoformat()))

            scheduled_id = cursor.lastrowid
            await db.commit()

            # Fetch the created scheduled playlist
            async with db.execute("""
                SELECT id, playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh, created_at, updated_at
                FROM scheduled_playlists WHERE id = ?
            """, (scheduled_id,)) as cursor:
                row = await cursor.fetchone()

                if row:
                    return ScheduledPlaylist(
                        id=row[0],
                        playlist_type=row[1],
                        navidrome_playlist_id=row[2],
                        refresh_frequency=row[3],
                        next_refresh=row[4],
                        created_at=row[5],
                        updated_at=row[6]
                    )

        # This should never happen, but handle it gracefully
        raise Exception("Failed to create scheduled playlist")
    
    async def get_scheduled_playlists_due(self, current_time: datetime, grace_hours: int = 168) -> List[ScheduledPlaylist]:
        """Get all scheduled playlists that are due for refresh, including overdue ones within grace period
        
        Args:
            current_time: Current timestamp to check against
            grace_hours: Hours to look back for missed refreshes (default 7 days = 168 hours)
        """
        await self.init_db()
        
        # Calculate grace period cutoff (7 days ago by default)
        from datetime import timedelta
        grace_cutoff = current_time - timedelta(hours=grace_hours)
        
        scheduled_playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh, created_at, updated_at
                FROM scheduled_playlists 
                WHERE next_refresh <= ? AND next_refresh >= ?
                ORDER BY next_refresh ASC
            """, (current_time.isoformat(), grace_cutoff.isoformat())) as cursor:
                rows = await cursor.fetchall()
                
                for row in rows:
                    scheduled_playlist = ScheduledPlaylist(
                        id=row[0],
                        playlist_type=row[1],
                        navidrome_playlist_id=row[2],
                        refresh_frequency=row[3],
                        next_refresh=row[4],
                        created_at=row[5],
                        updated_at=row[6]
                    )
                    scheduled_playlists.append(scheduled_playlist)
        
        return scheduled_playlists
    
    async def update_scheduled_playlist_next_refresh(self, scheduled_id: int, next_refresh: datetime) -> bool:
        """Update the next refresh time for a scheduled playlist"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE scheduled_playlists 
                SET next_refresh = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (next_refresh.isoformat(), scheduled_id))
            
            await db.commit()
            return cursor.rowcount > 0
    
    async def update_playlist_last_refreshed(self, navidrome_playlist_id: str) -> bool:
        """Update the last_refreshed timestamp for a playlist"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE playlists 
                SET last_refreshed = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE navidrome_playlist_id = ?
            """, (navidrome_playlist_id,))
            
            await db.commit()
            return cursor.rowcount > 0
    
    async def update_playlist_content(self, navidrome_playlist_id: str, songs: List[str], reasoning: Optional[str] = None) -> bool:
        """Update the songs and reasoning for a playlist during refresh"""
        await self.init_db()
        
        songs_json = json.dumps(songs)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE playlists 
                SET songs = ?, reasoning = ?, last_refreshed = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE navidrome_playlist_id = ?
            """, (songs_json, reasoning, navidrome_playlist_id))
            
            await db.commit()
            return cursor.rowcount > 0
    
    async def get_config(self, key: str) -> Optional[str]:
        """Get a configuration value by key"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT value FROM app_config WHERE key = ?
            """, (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    
    async def set_config(self, key: str, value: str) -> bool:
        """Set a configuration value"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)
            """, (key, value))
            await db.commit()
            return True
    
    async def get_or_create_user_id(self) -> str:
        """Get or create a unique user ID for analytics tracking"""
        import uuid
        
        user_id = await self.get_config("user_id")
        if not user_id:
            # Generate a new unique user ID
            user_id = str(uuid.uuid4())
            await self.set_config("user_id", user_id)
        
        return user_id
    
    async def should_track_library_size(self) -> bool:
        """Check if we should track library size (90+ days since last tracking)"""
        await self.init_db()
        
        from datetime import datetime, timedelta
        
        # Get the last tracking timestamp
        last_tracked = await self.get_config("last_library_tracking")
        if not last_tracked:
            return True  # Never tracked before
        
        try:
            last_tracked_date = datetime.fromisoformat(last_tracked)
            cutoff_date = datetime.now() - timedelta(days=90)
            return last_tracked_date < cutoff_date
        except:
            return True  # Invalid timestamp, track again
    
    async def record_library_size(self, song_count: int) -> bool:
        """Record library size for analytics"""
        await self.init_db()
        
        user_id = await self.get_or_create_user_id()
        current_time = datetime.now()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Insert the library analytics record
            await db.execute("""
                INSERT INTO library_analytics (user_id, song_count, recorded_at)
                VALUES (?, ?, ?)
            """, (user_id, song_count, current_time.isoformat()))
            
            # Update the last tracking timestamp
            await db.execute("""
                INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)
            """, ("last_library_tracking", current_time.isoformat()))
            
            await db.commit()
            return True

    async def get_user_preference(self, user_id: str, key: str) -> Optional[str]:
        """Get a user preference value"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT value FROM user_preferences WHERE user_id = ? AND key = ?
            """, (user_id, key)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_user_preference(self, user_id: str, key: str, value: str) -> bool:
        """Set a user preference value"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_preferences (user_id, key, value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, key, value))
            await db.commit()
            return True

    async def get_selected_library_id(self, user_id: str) -> Optional[str]:
        """Get the user's selected library ID"""
        return await self.get_user_preference(user_id, "selected_library_id")

    async def set_selected_library_id(self, user_id: str, library_id: str) -> bool:
        """Set the user's selected library ID"""
        return await self.set_user_preference(user_id, "selected_library_id", library_id)

    async def get_cache(self, cache_key: str) -> Optional[str]:
        """Get a cached value by key, checking expiration"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT cache_value FROM api_cache
                WHERE cache_key = ? AND expires_at > datetime('now')
            """, (cache_key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_cache(self, cache_key: str, cache_value: str, ttl_seconds: int) -> bool:
        """Set a cached value with TTL (time to live in seconds)"""
        await self.init_db()

        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO api_cache (cache_key, cache_value, expires_at)
                VALUES (?, ?, ?)
            """, (cache_key, cache_value, expires_at.isoformat()))
            await db.commit()
            return True

    async def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries. Returns number of entries deleted."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM api_cache WHERE expires_at <= datetime('now')
            """)
            deleted_count = cursor.rowcount
            await db.commit()
            return deleted_count

# Dependency for FastAPI
async def get_db() -> DatabaseManager:
    """FastAPI dependency to get database manager"""
    # Get database path from environment variable with smart defaults
    # Docker: /app/data/magiclists.db (set in docker-compose.yml)
    # Standalone: ./magiclists.db (current directory)
    default_path = "/app/data/magiclists.db" if os.path.exists("/app/data") else "./magiclists.db"
    db_path = os.getenv("DATABASE_PATH", default_path)
    return DatabaseManager(db_path)