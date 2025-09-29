import httpx
import os
from typing import List, Dict, Any

class NavidromeClient:
    """Simple client for interacting with Navidrome Subsonic API"""
    
    def __init__(self):
        self.base_url = os.getenv("NAVIDROME_URL", "https://music.itsricky.com")
        self.api_key = os.getenv("NAVIDROME_API_KEY")
        self.username = os.getenv("NAVIDROME_USERNAME")
        self.password = os.getenv("NAVIDROME_PASSWORD")
        self.client = httpx.AsyncClient()
        self._auth_token = None
        self._subsonic_token = None
        self._subsonic_salt = None
        
    async def _ensure_authenticated(self):
        """Ensure we have valid authentication credentials"""
        if self.api_key:
            # Use provided static API key (future feature)
            self._auth_token = self.api_key
        elif self.username and self.password and not self._subsonic_token:
            # Login with username/password to get Subsonic credentials
            try:
                response = await self.client.post(
                    f"{self.base_url}/auth/login",
                    json={"username": self.username, "password": self.password}
                )
                response.raise_for_status()
                data = response.json()
                
                # Store both JWT token and Subsonic credentials
                self._auth_token = data.get("token")
                self._subsonic_token = data.get("subsonicToken")
                self._subsonic_salt = data.get("subsonicSalt")
                
                if not self._subsonic_token or not self._subsonic_salt:
                    raise Exception("No Subsonic credentials received from login response")
                    
            except httpx.RequestError as e:
                raise Exception(f"Network error during login: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise Exception("Invalid username or password")
                elif e.response.status_code == 403:
                    raise Exception("Access forbidden - check your credentials")
                else:
                    raise Exception(f"Login failed with status {e.response.status_code}: {e.response.text}")
            except Exception as e:
                raise Exception(f"Unexpected error during login: {e}")
        elif not self.username or not self.password:
            raise Exception("No authentication method available (need NAVIDROME_API_KEY or NAVIDROME_USERNAME/PASSWORD)")
        
    def _get_subsonic_params(self) -> Dict[str, str]:
        """Get Subsonic API parameters"""
        if self.api_key:
            # Future: use API key authentication if available
            return {
                "u": self.username,
                "t": self.api_key,
                "v": "1.16.1",
                "c": "MagicLists",
                "f": "json"
            }
        else:
            # Use Subsonic token authentication
            return {
                "u": self.username,
                "t": self._subsonic_token,
                "s": self._subsonic_salt,
                "v": "1.16.1",
                "c": "MagicLists",
                "f": "json"
            }
    
    async def get_artists(self) -> List[Dict[str, Any]]:
        """Fetch all artists from Navidrome using Subsonic API
        
        Returns:
            List of artists with format: {id, name}
        """
        try:
            await self._ensure_authenticated()
            
            params = self._get_subsonic_params()
            response = await self.client.get(
                f"{self.base_url}/rest/getArtists.view",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")
            
            artists_data = subsonic_response.get("artists", {})
            artists_list = []
            
            # Parse the indexed artist structure
            for index_group in artists_data.get("index", []):
                for artist in index_group.get("artist", []):
                    artists_list.append({
                        "id": artist.get("id"),
                        "name": artist.get("name")
                    })
            
            return artists_list
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching artists: {e}")
    
    async def get_tracks_by_artist(self, artist_id: str) -> List[Dict[str, Any]]:
        """Fetch tracks for a specific artist using Subsonic API
        
        Args:
            artist_id: The artist ID
            
        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()
            
            params = self._get_subsonic_params()
            params["id"] = artist_id
            
            response = await self.client.get(
                f"{self.base_url}/rest/getArtist.view",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")
            
            artist_data = subsonic_response.get("artist", {})
            tracks_list = []
            
            # Get tracks from albums
            for album in artist_data.get("album", []):
                album_id = album.get("id")
                album_name = album.get("name", "")
                album_year = album.get("year", 0)
                
                # Get songs from each album
                album_params = self._get_subsonic_params()
                album_params["id"] = album_id
                
                album_response = await self.client.get(
                    f"{self.base_url}/rest/getAlbum.view",
                    params=album_params
                )
                album_response.raise_for_status()
                album_data = album_response.json()
                
                album_subsonic = album_data.get("subsonic-response", {})
                if album_subsonic.get("status") == "ok":
                    album_info = album_subsonic.get("album", {})
                    for song in album_info.get("song", []):
                        tracks_list.append({
                            "id": song.get("id"),
                            "title": song.get("title"),
                            "album": album_name,
                            "year": album_year,
                            "play_count": song.get("playCount", 0)
                        })
            
            return tracks_list
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching tracks for artist {artist_id}: {e}")
    
    async def create_playlist(self, name: str, track_ids: List[str], comment: str = None) -> str:
        """Create a new playlist in Navidrome using Subsonic API
        
        Args:
            name: Name of the playlist
            track_ids: List of track IDs to add to playlist
            comment: Optional comment/description for the playlist
            
        Returns:
            playlist_id: The ID of the created playlist
        """
        try:
            await self._ensure_authenticated()
            
            # Create the playlist using Subsonic API
            params = self._get_subsonic_params()
            params["name"] = name
            if comment:
                params["comment"] = comment
                print(f"🔧 NavidromeClient: Adding comment to playlist '{name}': {comment[:100]}...")
            else:
                print(f"🔧 NavidromeClient: No comment provided for playlist '{name}'")
            
            response = await self.client.get(
                f"{self.base_url}/rest/createPlaylist.view",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")
            
            playlist_data = subsonic_response.get("playlist", {})
            playlist_id = playlist_data.get("id")
            
            if not playlist_id:
                raise Exception("Failed to get playlist ID from response")
            
            # Add tracks to the playlist if provided
            if track_ids:
                # Update playlist with songs using Subsonic API
                update_params = self._get_subsonic_params()
                update_params["playlistId"] = playlist_id
                update_params["songIdToAdd"] = track_ids
                
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=update_params
                )
                response.raise_for_status()
                
                update_data = response.json()
                update_subsonic = update_data.get("subsonic-response", {})
                if update_subsonic.get("status") != "ok":
                    error = update_subsonic.get("error", {})
                    raise Exception(f"Failed to add songs to playlist: {error.get('message', 'Unknown error')}")
                
            return playlist_id
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error creating playlist: {e}")
    
    async def update_playlist(self, playlist_id: str, track_ids: List[str], comment: str = None) -> bool:
        """Update an existing playlist by replacing all tracks
        
        Args:
            playlist_id: ID of the playlist to update
            track_ids: List of track IDs to replace current tracks with
            comment: Optional comment/description to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self._ensure_authenticated()
            
            # First, clear the existing playlist by updating it with no songs
            clear_params = self._get_subsonic_params()
            clear_params["playlistId"] = playlist_id
            if comment:
                clear_params["comment"] = comment
            
            response = await self.client.get(
                f"{self.base_url}/rest/updatePlaylist.view",
                params=clear_params
            )
            response.raise_for_status()
            
            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Failed to clear playlist: {error.get('message', 'Unknown error')}")
            
            # Then add the new tracks
            if track_ids:
                update_params = self._get_subsonic_params()
                update_params["playlistId"] = playlist_id
                update_params["songIdToAdd"] = track_ids
                
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=update_params
                )
                response.raise_for_status()
                
                update_data = response.json()
                update_subsonic = update_data.get("subsonic-response", {})
                if update_subsonic.get("status") != "ok":
                    error = update_subsonic.get("error", {})
                    raise Exception(f"Failed to add songs to playlist: {error.get('message', 'Unknown error')}")
            
            return True
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error updating playlist: {e}")
    
    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist from Navidrome
        
        Args:
            playlist_id: ID of the playlist to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self._ensure_authenticated()
            
            params = self._get_subsonic_params()
            params["playlistId"] = playlist_id
            
            response = await self.client.get(
                f"{self.base_url}/rest/deletePlaylist.view",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Failed to delete playlist: {error.get('message', 'Unknown error')}")
            
            return True
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error deleting playlist: {e}")
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()