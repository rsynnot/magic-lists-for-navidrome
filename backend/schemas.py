from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Artist(BaseModel):
    """Schema for Navidrome artist"""
    id: str
    name: str
    album_count: int = 0
    song_count: int = 0

class CreatePlaylistRequest(BaseModel):
    """Request schema for creating a playlist"""
    artist_ids: List[str]
    playlist_name: Optional[str] = None  # Optional, will auto-generate if not provided

class Playlist(BaseModel):
    """Schema for a stored playlist"""
    id: int
    artist_id: str
    playlist_name: str
    songs: List[str] = []
    created_at: str
    updated_at: str

class Song(BaseModel):
    """Schema for a song"""
    id: str
    title: str
    artist: str
    album: str
    duration: Optional[int] = None
    track_number: Optional[int] = None

class PlaylistResponse(BaseModel):
    """Response schema for playlist operations"""
    playlist: Playlist
    message: str

class RediscoverTrack(BaseModel):
    """Schema for a Re-Discover Weekly track"""
    id: str
    title: str
    artist: str
    album: str
    score: float
    historical_plays: int
    days_since_last_play: str

class RediscoverWeeklyResponse(BaseModel):
    """Response schema for Re-Discover Weekly"""
    tracks: List[RediscoverTrack]
    total_tracks: int
    message: str