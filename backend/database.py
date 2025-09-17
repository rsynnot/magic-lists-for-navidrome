import sqlite3
import aiosqlite
from typing import List, Optional
from datetime import datetime
import json

from .schemas import Playlist

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
    
    async def create_playlist(self, artist_id: str, playlist_name: str, songs: Optional[List[str]] = None) -> Playlist:
        """Create a new playlist in the database"""
        await self.init_db()
        
        songs_json = json.dumps(songs or [])
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO playlists (artist_id, playlist_name, songs)
                VALUES (?, ?, ?)
            """, (artist_id, playlist_name, songs_json))
            
            playlist_id = cursor.lastrowid
            await db.commit()
            
            # Fetch the created playlist
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, created_at, updated_at
                FROM playlists WHERE id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=json.loads(row[3]),
                        created_at=row[4],
                        updated_at=row[5]
                    )
    
    async def get_playlist(self, playlist_id: int) -> Optional[Playlist]:
        """Get a playlist by ID"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, created_at, updated_at
                FROM playlists WHERE id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=json.loads(row[3]),
                        created_at=row[4],
                        updated_at=row[5]
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

# Dependency for FastAPI
async def get_db() -> DatabaseManager:
    """FastAPI dependency to get database manager"""
    return DatabaseManager()