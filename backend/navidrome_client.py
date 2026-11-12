import httpx
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Union, Optional

logger = logging.getLogger(__name__)

class NavidromeClient:
    """Simple client for interacting with Navidrome Subsonic API"""
    
    def __init__(self):
        self.base_url = os.getenv("NAVIDROME_URL")
        if not self.base_url:
            raise ValueError("NAVIDROME_URL environment variable is required")
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
            # Use Subsonic API authentication (Navidrome doesn't have separate auth endpoint)
            # We'll use password-based authentication for each request
            import hashlib
            import time
            
            # Generate salt and token for Subsonic API
            self._subsonic_salt = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
            salted_password = self.password + self._subsonic_salt
            self._subsonic_token = hashlib.md5(salted_password.encode()).hexdigest()
            
            # Test authentication with ping
            try:
                response = await self.client.get(
                    f"{self.base_url}/rest/ping.view",
                    params={
                        "u": self.username,
                        "t": self._subsonic_token,
                        "s": self._subsonic_salt,
                        "v": "1.16.0",
                        "c": "magiclists"
                    }
                )
                response.raise_for_status()
                
                # Check if response indicates successful authentication
                if 'status="ok"' not in response.text:
                    raise Exception("Authentication failed")
                    
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
        
    def _get_subsonic_params(self) -> Dict[str, Any]:
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
    
    async def get_artists(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Fetch all artists from Navidrome using Subsonic API

        Args:
            library_ids: Optional library ID(s) to filter artists (string, list of strings, or None)

        Returns:
            List of artists with format: {id, name}
        """
        try:
            await self._ensure_authenticated()

            # Normalize library_ids to a list
            if isinstance(library_ids, str):
                library_ids_list = [library_ids]
            elif isinstance(library_ids, list):
                library_ids_list = library_ids
            else:
                library_ids_list = []

            # If no specific libraries requested, use env var or fetch from all libraries
            if not library_ids_list:
                env_library_id = os.getenv("NAVIDROME_LIBRARY_ID")
                if env_library_id:
                    library_ids_list = [env_library_id]
                else:
                    # Fetch from all libraries
                    library_ids_list = None

            all_artists = []

            if library_ids_list:
                # Fetch from specific libraries
                for lib_id in library_ids_list:
                    print(f"🎵 Fetching artists from library ID: {lib_id}")
                    artists = await self._get_artists_from_library(lib_id)
                    all_artists.extend(artists)
            else:
                # Fetch from all libraries (no filter)
                print("🎵 Fetching artists from all libraries")
                artists = await self._get_artists_from_library(None)
                all_artists.extend(artists)

            # Remove duplicates based on artist ID
            unique_artists = []
            seen_ids = set()
            for artist in all_artists:
                if artist['id'] not in seen_ids:
                    unique_artists.append(artist)
                    seen_ids.add(artist['id'])

            print(f"✅ Retrieved {len(unique_artists)} unique artists from {len(library_ids_list) if library_ids_list else 'all'} libraries")
            return unique_artists

        except Exception as e:
            print(f"❌ Error in get_artists: {e}")
            raise

    async def _get_artists_from_library(self, library_id: Union[str, None]) -> List[Dict[str, Any]]:
        """Fetch artists from a specific library or all libraries"""
        try:
            params = self._get_subsonic_params()

            # Add library filter if specified
            if library_id:
                params["musicFolderId"] = library_id
                print(f"🎵 Using library ID: {library_id}")

            # Log the full request for debugging (minus auth details)
            log_params = {k: v for k, v in params.items() if k not in ['t', 's']}
            print(f"🌐 getArtists request: GET {self.base_url}/rest/getArtists.view with params: {log_params}")

            response = await self.client.get(
                f"{self.base_url}/rest/getArtists.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            print(f"📊 getArtists response status: {response.status_code}")

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                error_message = error.get('message', 'Unknown error')
                error_code = error.get('code', 0)

                print(f"❌ Subsonic API error: {error_message} (code: {error_code})")

                # Handle "Library not found" error
                if "Library not found" in error_message or "empty" in error_message.lower():
                    print("⚠️ Library not found error detected - attempting retry without library filter")

                    # Retry without library filter
                    retry_params = self._get_subsonic_params()
                    # Remove any library-specific parameters
                    retry_params.pop("musicFolderId", None)

                    print(f"🔄 Retry getArtists request: GET {self.base_url}/rest/getArtists.view with params: {retry_params}")

                    retry_response = await self.client.get(
                        f"{self.base_url}/rest/getArtists.view",
                        params=retry_params
                    )
                    retry_response.raise_for_status()

                    retry_data = retry_response.json()
                    retry_subsonic = retry_data.get("subsonic-response", {})

                    print(f"📊 Retry getArtists response status: {retry_response.status_code}")

                    if retry_subsonic.get("status") == "ok":
                        print("✅ Retry successful - multiple libraries detected, using all available libraries")
                        data = retry_data
                        subsonic_response = retry_subsonic
                    else:
                        retry_error = retry_subsonic.get("error", {})
                        raise Exception(f"Multiple libraries error: {retry_error.get('message', 'Unknown error')}")
                else:
                    raise Exception(f"Subsonic API error: {error_message}")

            # Ensure we have valid data to process
            if 'data' not in locals():
                raise Exception("No valid response data available")

            artists_data = subsonic_response.get("artists", {})
            artists_list = []

            # Parse the indexed artist structure
            for index_group in artists_data.get("index", []):
                for artist in index_group.get("artist", []):
                    artists_list.append({
                        "id": artist.get("id"),
                        "name": artist.get("name"),
                        "albumCount": artist.get("albumCount", 0)
                    })

            print(f"✅ Successfully fetched {len(artists_list)} artists from Navidrome")
            return artists_list

        except httpx.RequestError as e:
            print(f"🌐 Network error in getArtists: {e}")
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            print(f"🚨 HTTP error in getArtists: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            print(f"💥 Unexpected error in getArtists: {e}")
            raise Exception(f"Unexpected error fetching artists: {e}")

    async def get_music_folders(self) -> List[Dict[str, Any]]:
        """Get all available music folders/libraries using Subsonic API

        Returns:
            List of music folders with format: {id, name}
        """
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()

            print(f"🌐 getMusicFolders request: GET {self.base_url}/rest/getMusicFolders.view")

            response = await self.client.get(
                f"{self.base_url}/rest/getMusicFolders.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            music_folders_data = subsonic_response.get("musicFolders", {})
            folders = music_folders_data.get("musicFolder", [])

            # Ensure folders is a list (API might return single object)
            if isinstance(folders, dict):
                folders = [folders]

            result = []
            for folder in folders:
                result.append({
                    "id": str(folder.get("id", "")),
                    "name": folder.get("name", "Unknown Library")
                })

            print(f"📁 Found {len(result)} music folders: {[f['name'] for f in result]}")
            return result

        except Exception as e:
            print(f"💥 Error fetching music folders: {e}")
            raise Exception(f"Failed to fetch music folders: {e}")

    async def search_artist_mentions(self, artist_name: str, library_ids: Union[List[str], None] = None) -> List[Dict[str, Any]]:
        """Search for tracks that mention an artist in any field (title, featured artists, composers, etc.)

        Args:
            artist_name: The artist name to search for
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of tracks with format: {id, title, artist, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            all_tracks = []

            # If multiple libraries specified, fetch from each
            if library_ids and len(library_ids) > 1:
                for lib_id in library_ids:
                    print(f"🎵 Searching for mentions of '{artist_name}' in library {lib_id}")
                    tracks = await self._search_artist_mentions_in_library(artist_name, lib_id)
                    all_tracks.extend(tracks)
                # Remove duplicates based on track id
                seen_ids = set()
                unique_tracks = []
                for track in all_tracks:
                    if track["id"] not in seen_ids:
                        seen_ids.add(track["id"])
                        unique_tracks.append(track)
                all_tracks = unique_tracks
            else:
                # Single library or no library filter
                lib_id = library_ids[0] if library_ids else None
                all_tracks = await self._search_artist_mentions_in_library(artist_name, lib_id)

            print(f"✅ Found {len(all_tracks)} tracks mentioning '{artist_name}'")
            return all_tracks

        except Exception as e:
            print(f"❌ Error searching for mentions of '{artist_name}': {e}")
            raise

    async def _search_artist_mentions_in_library(self, artist_name: str, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for artist mentions in a specific library using multiple strategies"""
        all_tracks = {}  # Use dict to deduplicate by track ID
        
        library_filter = f" in library {library_id}" if library_id else ""
        logger.info(f"🎵 Starting artist mention search for '{artist_name}'{library_filter}")
        
        # Strategy 1: Search for full artist name in all fields (song titles, etc.)
        logger.info(f"  📍 Strategy 1: Full name search ('{artist_name}')")
        tracks = await self._search_query(artist_name, library_id)
        for track in tracks:
            all_tracks[track["id"]] = track
        logger.info(f"     Found {len(tracks)} tracks")
        
        # Strategy 2: Get a large sample of all tracks and filter by artist name in artist field (substring match)
        # This catches cases like "Hardsoul, Ron Carroll" or "Ron Carroll, Eric Kupper"
        logger.info(f"  📍 Strategy 2: Bulk fetch + artist field substring match")
        tracks = await self._get_all_tracks_sample(library_id, batch_count=5)
        matched_count = 0
        for track in tracks:
            track_artist = track.get("artist", "").lower()
            search_artist = artist_name.lower()
            
            # Check if artist name appears in the artist field (substring match)
            if search_artist in track_artist:
                all_tracks[track["id"]] = track
                matched_count += 1
        logger.info(f"     Found {matched_count} matching tracks via artist field")
        
        result_tracks = list(all_tracks.values())
        logger.info(f"✅ Found {len(result_tracks)} total unique tracks mentioning '{artist_name}'{library_filter}")
        return result_tracks

    async def _search_query(self, query: str, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Execute a search query and return all matching songs with pagination"""
        tracks = []
        offset = 0
        batch_size = 500
        max_iterations = 10  # Limit iterations to prevent hanging

        iteration_count = 0
        while iteration_count < max_iterations:
            iteration_count += 1
            params = self._get_subsonic_params()
            params["query"] = query
            params["count"] = batch_size
            params["offset"] = offset
            params["artistCount"] = "0"  # Don't return artists, just songs
            params["albumCount"] = "0"   # Don't return albums, just songs
            params["songCount"] = batch_size  # Return all matches as songs

            # Add library filter if specified
            if library_id:
                params["musicFolderId"] = library_id

            try:
                response = await self.client.get(
                    f"{self.base_url}/rest/search3.view",
                    params=params,
                    timeout=10.0  # Add timeout to prevent hanging
                )
                response.raise_for_status()
            except httpx.TimeoutException:
                logger.warning(f"     ⚠️ Search timeout for '{query}', stopping")
                break
            except Exception as e:
                logger.warning(f"     ⚠️ Search failed for '{query}': {e}")
                break

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                error_msg = error.get('message', 'Unknown error')
                logger.warning(f"     ⚠️ API error: {error_msg}")
                break

            search_result = subsonic_response.get("searchResult3", {})
            songs = search_result.get("song", [])

            if not songs:
                break

            # Convert to our format
            for song in songs:
                track = {
                    "id": song["id"],
                    "title": song["title"],
                    "album": song.get("album", ""),
                    "artist": song.get("artist", ""),
                    "year": song.get("year", 0),
                    "duration": song.get("duration", 0),
                    "genre": song.get("genre", ""),
                    "play_count": song.get("playCount", 0),
                    "path": song.get("path", ""),
                    "track_number": song.get("track", 0),
                    "disc_number": song.get("discNumber", 0),
                    "size": song.get("size", 0),
                    "bitrate": song.get("bitRate", 0),
                    "content_type": song.get("contentType", ""),
                    "created": song.get("created", ""),
                    "changed": song.get("changed", ""),
                    "starred": song.get("starred", False),
                    "user_rating": song.get("userRating", 0),
                    "average_rating": song.get("averageRating", 0),
                    "type": song.get("type", "music"),
                    "bookmark_position": song.get("bookmarkPosition", 0),
                    "played": song.get("played", ""),
                    "bpm": song.get("bpm", 0),
                    "comment": song.get("comment", ""),
                    "sort_name": song.get("sortName", ""),
                    "media_type": song.get("mediaType", ""),
                    "music_brainz_id": song.get("musicBrainzId", ""),
                    "replay_gain_track": song.get("replayGain", {}).get("trackGain", 0),
                    "replay_gain_album": song.get("replayGain", {}).get("albumGain", 0)
                }
                tracks.append(track)

            offset += batch_size

            # If we got fewer songs than batch size, we've reached the end
            if len(songs) < batch_size:
                break

        return tracks

    async def _get_all_tracks_sample(self, library_id: Optional[str] = None, batch_count: int = 5) -> List[Dict[str, Any]]:
        """Fetch a large sample of all tracks for filtering"""
        tracks = []
        offset = 0
        batch_size = 500
        iteration = 0

        while iteration < batch_count:
            iteration += 1
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query returns all tracks
            params["count"] = batch_size
            params["offset"] = offset
            params["artistCount"] = "0"
            params["albumCount"] = "0"
            params["songCount"] = batch_size

            if library_id:
                params["musicFolderId"] = library_id

            try:
                response = await self.client.get(
                    f"{self.base_url}/rest/search3.view",
                    params=params,
                    timeout=10.0
                )
                response.raise_for_status()
            except Exception as e:
                logger.warning(f"     ⚠️ Failed to fetch sample batch {iteration}: {e}")
                break

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                break

            search_result = subsonic_response.get("searchResult3", {})
            songs = search_result.get("song", [])

            if not songs:
                break

            for song in songs:
                track = {
                    "id": song["id"],
                    "title": song["title"],
                    "album": song.get("album", ""),
                    "artist": song.get("artist", ""),
                    "year": song.get("year", 0),
                    "duration": song.get("duration", 0),
                    "genre": song.get("genre", ""),
                    "play_count": song.get("playCount", 0),
                    "path": song.get("path", ""),
                    "track_number": song.get("track", 0),
                    "disc_number": song.get("discNumber", 0),
                    "size": song.get("size", 0),
                    "bitrate": song.get("bitRate", 0),
                    "content_type": song.get("contentType", ""),
                    "created": song.get("created", ""),
                    "changed": song.get("changed", ""),
                    "starred": song.get("starred", False),
                    "user_rating": song.get("userRating", 0),
                    "average_rating": song.get("averageRating", 0),
                    "type": song.get("type", "music"),
                    "bookmark_position": song.get("bookmarkPosition", 0),
                    "played": song.get("played", ""),
                    "bpm": song.get("bpm", 0),
                    "comment": song.get("comment", ""),
                    "sort_name": song.get("sortName", ""),
                    "media_type": song.get("mediaType", ""),
                    "music_brainz_id": song.get("musicBrainzId", ""),
                    "replay_gain_track": song.get("replayGain", {}).get("trackGain", 0),
                    "replay_gain_album": song.get("replayGain", {}).get("albumGain", 0)
                }
                tracks.append(track)

            offset += batch_size

        return tracks

    async def get_tracks_by_artist(self, artist_id: str, library_ids: Union[List[str], None] = None) -> List[Dict[str, Any]]:
        """Fetch tracks for a specific artist using Subsonic API

        Args:
            artist_id: The artist ID
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["id"] = artist_id

            # Add library filter if specified (use first library if multiple provided)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]
            
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
            
            # Get artist name for track metadata
            artist_name = artist_data.get("name", "Unknown Artist")
            
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
                            "artist": artist_name,  # Include artist name for AI processing
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

    async def get_tracks_by_genre(self, genre: str, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Fetch tracks for a specific genre using Subsonic getSongsByGenre API with pagination

        Args:
            genre: The genre name
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            all_tracks = []

            # If multiple libraries specified, fetch from each
            if library_ids and len(library_ids) > 1:
                for lib_id in library_ids:
                    print(f"🎵 Fetching tracks for genre '{genre}' from library {lib_id}")
                    tracks = await self._get_tracks_by_genre_from_library(genre, lib_id)
                    all_tracks.extend(tracks)
                # Remove duplicates based on track id
                seen_ids = set()
                unique_tracks = []
                for track in all_tracks:
                    if track["id"] not in seen_ids:
                        seen_ids.add(track["id"])
                        unique_tracks.append(track)
                all_tracks = unique_tracks
            else:
                # Single library or no library filter
                lib_id = library_ids[0] if library_ids else None
                all_tracks = await self._get_tracks_by_genre_from_library(genre, lib_id)

            print(f"✅ Collected {len(all_tracks)} tracks for genre '{genre}'")
            return all_tracks

        except Exception as e:
            print(f"❌ Error fetching tracks by genre '{genre}': {e}")
            raise

    async def _get_tracks_by_genre_from_library(self, genre: str, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch tracks for a genre from a specific library"""
        tracks = []
        total_fetched = 0
        offset = 0
        batch_size = 500  # Max allowed by API

        library_filter = f" in library {library_id}" if library_id else ""
        print(f"🎵 Starting genre track collection for '{genre}'{library_filter}")

        while True:
            params = self._get_subsonic_params()
            params["genre"] = genre
            params["count"] = batch_size
            params["offset"] = offset

            # Add library filter if specified
            if library_id:
                params["musicFolderId"] = library_id

            response = await self.client.get(
                f"{self.base_url}/rest/getSongsByGenre.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                error_msg = error.get('message', 'Unknown error')
                error_code = error.get('code', 0)

                # If getSongsByGenre is not supported, raise error
                if "not implemented" in error_msg.lower() or error_code == 0:
                    raise Exception(f"getSongsByGenre not supported by Navidrome server")
                else:
                    raise Exception(f"Subsonic API error: {error_msg}")

            songs_by_genre = subsonic_response.get("songsByGenre", {})
            songs = songs_by_genre.get("song", [])

            # If no songs returned, we've reached the end
            if not songs:
                break

            # Convert to our format
            for song in songs:
                track = {
                    "id": song["id"],
                    "title": song["title"],
                    "album": song.get("album", ""),
                    "artist": song.get("artist", ""),
                    "year": song.get("year", 0),
                    "duration": song.get("duration", 0),
                    "genre": song.get("genre", ""),
                    "play_count": song.get("playCount", 0),
                    "path": song.get("path", ""),
                    "track_number": song.get("track", 0),
                    "disc_number": song.get("discNumber", 0),
                    "size": song.get("size", 0),
                    "bitrate": song.get("bitRate", 0),
                    "content_type": song.get("contentType", ""),
                    "created": song.get("created", ""),
                    "changed": song.get("changed", ""),
                    "starred": song.get("starred", False),
                    "user_rating": song.get("userRating", 0),
                    "average_rating": song.get("averageRating", 0),
                    "type": song.get("type", "music"),
                    "bookmark_position": song.get("bookmarkPosition", 0),
                    "played": song.get("played", ""),
                    "bpm": song.get("bpm", 0),
                    "comment": song.get("comment", ""),
                    "sort_name": song.get("sortName", ""),
                    "media_type": song.get("mediaType", ""),
                    "music_brainz_id": song.get("musicBrainzId", ""),
                    "replay_gain_track": song.get("replayGain", {}).get("trackGain", 0),
                    "replay_gain_album": song.get("replayGain", {}).get("albumGain", 0)
                }
                tracks.append(track)

            total_fetched += len(songs)
            offset += batch_size

            # Safety check to prevent infinite loops
            if total_fetched >= 10000:  # Reasonable limit
                print(f"⚠️ Reached safety limit of 10000 tracks for genre '{genre}'{library_filter}")
                break

        # If no tracks found with getSongsByGenre, try fallback search
        if not tracks:
            print(f"⚠️ No tracks found with getSongsByGenre for '{genre}', trying fallback search")
            tracks = await self._fallback_genre_search(genre, library_id)

        print(f"✅ Collected {len(tracks)} tracks for genre '{genre}'{library_filter}")
        return tracks

    async def _get_genres_from_library(self, library_id: Union[str, None]) -> List[Dict[str, Any]]:
        """Fetch genres from a specific library by sampling tracks"""
        try:
            # Use search method to sample tracks from the library and extract genres
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all tracks
            params["artistCount"] = "0"
            params["albumCount"] = "0"
            params["songCount"] = "2000"  # Sample more tracks for better genre coverage

            if library_id:
                params["musicFolderId"] = library_id

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            search_result = subsonic_response.get("searchResult3", {})
            songs = search_result.get("song", [])

            # Extract genres from tracks
            genre_counts = {}
            for song in songs:
                genre = song.get("genre")
                if genre:
                    parsed_genres = self._parse_genre_string(genre)
                    for parsed_genre in parsed_genres:
                        genre_counts[parsed_genre] = genre_counts.get(parsed_genre, 0) + 1

            # Only include genres with at least one song
            genres = [{"name": name, "songCount": count} for name, count in genre_counts.items() if count > 0]
            print(f"📊 Retrieved {len(genres)} genres from library {library_id or 'all'} (sampled {len(songs)} tracks)")
            return genres

        except Exception as e:
            raise Exception(f"Error fetching genres from library: {e}")

    async def _fallback_genre_search(self, genre: str, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fallback method to find tracks by genre when getSongsByGenre fails"""
        try:
            tracks = []
            offset = 0
            batch_size = 500
            max_iterations = 10  # Limit iterations to prevent hanging
            iteration_count = 0

            while len(tracks) < 5000 and iteration_count < max_iterations:  # Limit to prevent too many results
                iteration_count += 1
                params = self._get_subsonic_params()
                params["query"] = ""  # Empty query to get all tracks
                params["count"] = batch_size
                params["offset"] = offset
                params["songCount"] = batch_size
                params["artistCount"] = "0"
                params["albumCount"] = "0"

                if library_id:
                    params["musicFolderId"] = library_id

                response = await self.client.get(
                    f"{self.base_url}/rest/search3.view",
                    params=params,
                    timeout=10.0  # Add timeout to prevent hanging
                )
                response.raise_for_status()

                data = response.json()
                subsonic_response = data.get("subsonic-response", {})
                if subsonic_response.get("status") != "ok":
                    error = subsonic_response.get("error", {})
                    raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

                search_result = subsonic_response.get("searchResult3", {})
                songs = search_result.get("song", [])

                if not songs:
                    break

                # Filter songs where genre contains the search term (case insensitive)
                for song in songs:
                    song_genre = song.get("genre", "")
                    if genre.lower() in song_genre.lower():
                        track = {
                            "id": song["id"],
                            "title": song["title"],
                            "album": song.get("album", ""),
                            "artist": song.get("artist", ""),
                            "year": song.get("year", 0),
                            "duration": song.get("duration", 0),
                            "genre": song_genre,
                            "play_count": song.get("playCount", 0),
                            "path": song.get("path", ""),
                            "track_number": song.get("track", 0),
                            "disc_number": song.get("discNumber", 0),
                            "size": song.get("size", 0),
                            "bitrate": song.get("bitRate", 0),
                            "content_type": song.get("contentType", ""),
                            "created": song.get("created", ""),
                            "changed": song.get("changed", ""),
                            "starred": song.get("starred", False),
                            "user_rating": song.get("userRating", 0),
                            "average_rating": song.get("averageRating", 0),
                            "type": song.get("type", "music"),
                            "bookmark_position": song.get("bookmarkPosition", 0),
                            "played": song.get("played", ""),
                            "bpm": song.get("bpm", 0),
                            "comment": song.get("comment", ""),
                            "sort_name": song.get("sortName", ""),
                            "media_type": song.get("mediaType", ""),
                            "music_brainz_id": song.get("musicBrainzId", ""),
                            "replay_gain_track": song.get("replayGain", {}).get("trackGain", 0),
                            "replay_gain_album": song.get("replayGain", {}).get("albumGain", 0)
                        }
                        tracks.append(track)

                offset += batch_size

                # If we found tracks, continue until we have enough or no more songs
                if len(songs) < batch_size:
                    break

            print(f"📊 Fallback search found {len(tracks)} tracks for genre '{genre}'")
            return tracks

        except Exception as e:
            print(f"❌ Fallback genre search failed: {e}")
            return []

    async def _get_genres_fallback(self, library_id: Union[str, None]) -> List[Dict[str, Any]]:
        """Fallback method using search to sample tracks and extract genres"""
        try:
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all
            params["artistCount"] = "0"
            params["albumCount"] = "0"
            params["songCount"] = "1000"  # Sample tracks

            if library_id:
                params["musicFolderId"] = library_id

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            search_result = subsonic_response.get("searchResult3", {})
            songs = search_result.get("song", [])

            genre_counts = {}
            for song in songs:
                genre = song.get("genre")
                if genre:
                    parsed_genres = self._parse_genre_string(genre)
                    for parsed_genre in parsed_genres:
                        genre_counts[parsed_genre] = genre_counts.get(parsed_genre, 0) + 1

            genres = [{"name": name, "songCount": count} for name, count in genre_counts.items() if count > 0]
            print(f"📊 Retrieved {len(genres)} genres using search fallback (sampled {len(songs)} tracks)")
            return genres

        except Exception as e:
            raise Exception(f"Fallback genre fetching failed: {e}")

    def _parse_genre_string(self, genre_str: str) -> List[str]:
        """Parse genre strings that may contain multiple genres separated by delimiters"""
        if not genre_str:
            return []

        # Common separators: comma, slash, bullet, tab, pipe, semicolon, ampersand, newline
        separators = [",", "/", "•", "\t", "|", ";", "&", "\n"]

        # Try each separator
        for sep in separators:
            if sep in genre_str:
                parts = [part.strip() for part in genre_str.split(sep) if part.strip()]
                if len(parts) > 1:
                    return parts

        # No separators found, return as single genre
        return [genre_str.strip()]

    async def get_genres(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Get list of genres (legacy method for compatibility)"""
        # For backward compatibility, return genres from all libraries
        genres = await self._get_genres_from_library(None)
        return [{"name": g["name"], "songCount": g["songCount"]} for g in genres]

    async def get_library_track_counts(self, library_ids: Optional[List[str]] = None) -> Dict[str, int]:
        """Get total track counts for specified libraries

        Args:
            library_ids: List of library IDs to check, or None for all libraries

        Returns:
            Dict mapping library_id to track count
        """
        try:
            await self._ensure_authenticated()

            if not library_ids:
                # Get all libraries
                folders = await self.get_music_folders()
                library_ids = [folder["id"] for folder in folders]

            track_counts = {}

            for lib_id in library_ids:
                try:
                    # Use search3 with musicFolderId to count tracks in this library
                    params = self._get_subsonic_params()
                    params["query"] = ""
                    params["count"] = "1"  # Just need count, not actual tracks
                    params["musicFolderId"] = lib_id

                    response = await self.client.get(
                        f"{self.base_url}/rest/search3.view",
                        params=params
                    )
                    response.raise_for_status()

                    data = response.json()
                    subsonic_response = data.get("subsonic-response", {})
                    if subsonic_response.get("status") != "ok":
                        print(f"⚠️ Failed to get track count for library {lib_id}")
                        continue

                    search_result = subsonic_response.get("searchResult3", {})
                    songs = search_result.get("song", [])
                    # The total count isn't directly available, but we can estimate from offset
                    # For now, we'll use a different approach - get a small sample and note it
                    track_counts[lib_id] = len(songs) if isinstance(songs, list) else 1

                except Exception as e:
                    print(f"⚠️ Error getting track count for library {lib_id}: {e}")
                    track_counts[lib_id] = 0

            print(f"📊 Retrieved track counts for {len(track_counts)} libraries")
            return track_counts

        except Exception as e:
            print(f"❌ Error getting library track counts: {e}")
            return {}

    async def build_genre_cache(self, library_ids: Optional[List[str]] = None, db = None) -> Dict[str, Any]:
        """Build genre cache for specified libraries using the three use case approach

        Args:
            library_ids: List of library IDs to cache genres for
            db: Database manager instance for caching

        Returns:
            Cache data structure with genre counts per library
        """
        try:
            await self._ensure_authenticated()

            # Determine which libraries to process
            if not library_ids:
                folders = await self.get_music_folders()
                all_library_ids = [folder["id"] for folder in folders]
            else:
                all_library_ids = library_ids.copy()

            # Get track counts for cache validation
            track_counts = await self.get_library_track_counts(all_library_ids)
            total_tracks = sum(track_counts.values())

            cache_data = {
                "libraries": {},
                "cached_at": datetime.now().isoformat(),
                "total_tracks": total_tracks
            }

            # Case determination
            if not library_ids or len(library_ids) == len(all_library_ids):
                # Case 1 & 2: Single library or all libraries selected
                print("🎵 Building genre cache for all/single library scenario")
                await self._build_genre_cache_all_libraries(cache_data, all_library_ids)
            else:
                # Case 3: Partial libraries selected
                print("🎵 Building genre cache for partial libraries scenario")
                await self._build_genre_cache_partial_libraries(cache_data, library_ids)

            # Save to cache if db provided
            if db:
                import hashlib
                library_ids_hash = hashlib.md5(",".join(sorted(library_ids or all_library_ids)).encode()).hexdigest()
                server_id = self.base_url  # Use base URL as server identifier

                await db.set_genre_cache(server_id, library_ids_hash, cache_data, total_tracks)
                print(f"💾 Saved genre cache for {len(cache_data['libraries'])} libraries")

            return cache_data

        except Exception as e:
            print(f"❌ Error building genre cache: {e}")
            raise

    async def _build_genre_cache_all_libraries(self, cache_data: Dict[str, Any], library_ids: List[str]) -> None:
        """Build cache for case 1&2: getGenres + getSongsByGenre counting"""
        try:
            # Get all genres first
            params = self._get_subsonic_params()
            response = await self.client.get(
                f"{self.base_url}/rest/getGenres.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                raise Exception(f"Subsonic API error: {subsonic_response.get('error', {}).get('message', 'Unknown error')}")

            genres_data = subsonic_response.get("genres", {})
            all_genres = genres_data.get("genre", [])

            # For each genre, count tracks per library
            for genre_item in all_genres:
                genre_name = genre_item.get("value")
                if not genre_name:
                    continue

                # Count tracks for this genre in each library
                for lib_id in library_ids:
                    try:
                        track_count = await self._count_tracks_by_genre(genre_name, lib_id)
                        if track_count > 0:
                            if lib_id not in cache_data["libraries"]:
                                cache_data["libraries"][lib_id] = {"genres": {}, "total_tracks": 0}
                            cache_data["libraries"][lib_id]["genres"][genre_name] = track_count

                    except Exception as e:
                        print(f"⚠️ Error counting tracks for genre '{genre_name}' in library {lib_id}: {e}")
                        continue

        except Exception as e:
            print(f"❌ Error in all libraries genre cache building: {e}")
            raise

    async def _build_genre_cache_partial_libraries(self, cache_data: Dict[str, Any], library_ids: List[str]) -> None:
        """Build cache for case 3: getGenres globally + getSongsByGenre per library"""
        try:
            # Get all genres first
            params = self._get_subsonic_params()
            response = await self.client.get(
                f"{self.base_url}/rest/getGenres.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                raise Exception(f"Subsonic API error: {subsonic_response.get('error', {}).get('message', 'Unknown error')}")

            genres_data = subsonic_response.get("genres", {})
            all_genres = genres_data.get("genre", [])

            # For each genre, count tracks in each selected library
            for genre_item in all_genres:
                genre_name = genre_item.get("value")
                if not genre_name:
                    continue

                for lib_id in library_ids:
                    try:
                        track_count = await self._count_tracks_by_genre(genre_name, lib_id)
                        if track_count > 0:
                            if lib_id not in cache_data["libraries"]:
                                cache_data["libraries"][lib_id] = {"genres": {}, "total_tracks": 0}
                            cache_data["libraries"][lib_id]["genres"][genre_name] = track_count

                    except Exception as e:
                        print(f"⚠️ Error counting tracks for genre '{genre_name}' in library {lib_id}: {e}")
                        continue

        except Exception as e:
            print(f"❌ Error in partial libraries genre cache building: {e}")
            raise

    async def _count_tracks_by_genre(self, genre: str, library_id: Optional[str] = None) -> int:
        """Count total tracks for a genre in a specific library or all libraries"""
        try:
            count = 0
            offset = 0
            batch_size = 500

            while True:
                params = self._get_subsonic_params()
                params["genre"] = genre
                params["count"] = batch_size
                params["offset"] = offset

                if library_id:
                    params["musicFolderId"] = library_id

                response = await self.client.get(
                    f"{self.base_url}/rest/getSongsByGenre.view",
                    params=params
                )
                response.raise_for_status()

                data = response.json()
                subsonic_response = data.get("subsonic-response", {})
                if subsonic_response.get("status") != "ok":
                    error = subsonic_response.get("error", {})
                    raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

                songs_by_genre = subsonic_response.get("songsByGenre", {})
                songs = songs_by_genre.get("song", [])

                count += len(songs)
                offset += batch_size

                if len(songs) < batch_size:
                    break

                # Safety limit
                if count >= 50000:
                    print(f"⚠️ Reached safety limit counting tracks for genre '{genre}'")
                    break

            return count

        except Exception as e:
            print(f"❌ Error counting tracks for genre '{genre}': {e}")
            return 0

    async def get_starred(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Fetch starred tracks from Navidrome using getStarred API

        Args:
            library_ids: Optional library ID(s) to filter starred tracks

        Returns:
            List of starred track metadata
        """
        try:
            await self._ensure_authenticated()

            # Normalize library_ids to a single string for musicFolderId parameter
            library_id = None
            if isinstance(library_ids, list) and library_ids:
                library_id = library_ids[0]  # Use first library ID
            elif isinstance(library_ids, str):
                library_id = library_ids

            params = self._get_subsonic_params()
            if library_id:
                params["musicFolderId"] = library_id

            response = await self.client.get(
                f"{self.base_url}/rest/getStarred.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            starred_data = subsonic_response.get("starred", {})
            songs = starred_data.get("song", [])

            # Convert to consistent format
            tracks = []
            for song in songs:
                tracks.append({
                    "id": song.get("id"),
                    "title": song.get("title"),
                    "artist": song.get("artist"),
                    "album": song.get("album"),
                    "genre": song.get("genre"),
                    "year": song.get("year"),
                    "duration": song.get("duration"),
                    "play_count": song.get("playCount", 0),
                    "played": song.get("played"),
                    "starred": song.get("starred"),
                    "genres": song.get("genres", []),
                    "path": song.get("path")
                })

            print(f"⭐ Retrieved {len(tracks)} starred tracks")
            return tracks

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching starred tracks: {e}")

    async def get_genre_stats(self) -> List[Dict[str, Any]]:
        """Get genre statistics with track counts

        Returns:
            List of dicts with genre name and track count, sorted by count descending
        """
        try:
            await self._ensure_authenticated()

            # Get a larger sample of tracks to count genres
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all
            params["artistCount"] = 0
            params["albumCount"] = 0
            params["songCount"] = 5000  # Get large sample for genre stats

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
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

            # Count tracks per genre
            genre_counts = {}
            for song in songs:
                genre = song.get("genre")
                if genre:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1

            # Convert to list of dicts, sorted by count descending
            genre_stats = [
                {"genre": genre, "track_count": count}
                for genre, count in genre_counts.items()
            ]
            genre_stats.sort(key=lambda x: x["track_count"], reverse=True)

            return genre_stats

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching genre stats: {e}")

    async def create_playlist(self, name: str, track_ids: List[str], comment: Optional[str] = None) -> str:
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
            
            # Create the playlist using Subsonic API (note: createPlaylist doesn't support comment)
            params = self._get_subsonic_params()
            params["name"] = name
            # Note: comment will be set via updatePlaylist after creation
            
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
            
            # Add tracks to the playlist if provided - PRESERVE ORDER
            if track_ids:
                print(f"🎵 Adding {len(track_ids)} tracks to playlist in AI-curated order using updatePlaylist...")
                
                # Use proper Subsonic API with multiple songIdToAdd parameters in single call
                update_params = self._get_subsonic_params()
                update_params["playlistId"] = playlist_id
                # Set as list - httpx will create multiple parameters: songIdToAdd=id1&songIdToAdd=id2&...
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
                
                print(f"🎯 Successfully added all {len(track_ids)} tracks in single API call")
            
            # Add comment via updatePlaylist if provided (createPlaylist doesn't support comments)
            if comment:
                print(f"💬 Adding comment to playlist via updatePlaylist...")
                comment_params = self._get_subsonic_params()
                comment_params["playlistId"] = playlist_id
                comment_params["comment"] = comment
                
                comment_response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=comment_params
                )
                comment_response.raise_for_status()
                
                comment_data = comment_response.json()
                comment_subsonic = comment_data.get("subsonic-response", {})
                if comment_subsonic.get("status") != "ok":
                    error = comment_subsonic.get("error", {})
                    print(f"⚠️ Warning: Failed to add comment to playlist: {error.get('message', 'Unknown error')}")
                else:
                    print(f"✅ Successfully added comment to playlist")
                
            return playlist_id
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error creating playlist: {e}")
    
    async def update_playlist(self, playlist_id: str, track_ids: List[str], comment: Optional[str] = None) -> bool:
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
            
            # First, get current playlist to find all song IDs to remove
            get_params = self._get_subsonic_params()
            get_params["id"] = playlist_id
            
            response = await self.client.get(
                f"{self.base_url}/rest/getPlaylist.view",
                params=get_params
            )
            response.raise_for_status()
            
            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Failed to get playlist for clearing: {error.get('message', 'Unknown error')}")
            
            # Get current song IDs to remove
            current_playlist = subsonic_response.get("playlist", {})
            current_songs = current_playlist.get("entry", [])
            current_song_ids = [song.get("id") for song in current_songs if song.get("id")]
            
            # Remove all existing songs if any exist
            if current_song_ids:
                clear_params = self._get_subsonic_params()
                clear_params["playlistId"] = playlist_id
                clear_params["songIndexToRemove"] = list(range(len(current_song_ids)))  # Remove all by index
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
            elif comment:
                # Just update comment if no songs to remove
                clear_params = self._get_subsonic_params()
                clear_params["playlistId"] = playlist_id
                clear_params["comment"] = comment
                
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=clear_params
                )
                response.raise_for_status()
            
            # Then add the new tracks - PRESERVE ORDER
            if track_ids:
                print(f"🎵 Updating playlist with {len(track_ids)} tracks in AI-curated order...")
                
                # Use proper Subsonic API with multiple songIdToAdd parameters in single call
                update_params = self._get_subsonic_params()
                update_params["playlistId"] = playlist_id
                # Set as list - httpx will create multiple parameters: songIdToAdd=id1&songIdToAdd=id2&...
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
                
                print(f"🎯 Successfully updated playlist with all {len(track_ids)} tracks in single API call")
            
            return True
                
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error updating playlist: {e}")
    
    async def get_playlist_track_ids(self, playlist_id: str) -> List[str]:
        """Get track IDs from an existing playlist

        Args:
            playlist_id: ID of the playlist to get tracks from

        Returns:
            List of track IDs in the playlist
        """
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["id"] = playlist_id

            response = await self.client.get(
                f"{self.base_url}/rest/getPlaylist.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Failed to get playlist: {error.get('message', 'Unknown error')}")

            playlist_data = subsonic_response.get("playlist", {})
            entries = playlist_data.get("entry", [])

            track_ids = []
            for entry in entries:
                if entry.get("id"):
                    track_ids.append(entry["id"])

            return track_ids

        except Exception as e:
            logger.error(f"Failed to get playlist track IDs for {playlist_id}: {e}")
            return []

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
            params["id"] = playlist_id  # According to Subsonic API docs, parameter should be "id", not "playlistId"
            
            print(f"🗑️ Attempting to delete playlist with ID: {playlist_id}")
            print(f"🔧 Delete request URL: {self.base_url}/rest/deletePlaylist.view")
            print(f"🔧 Delete request params: {params}")
            
            response = await self.client.get(
                f"{self.base_url}/rest/deletePlaylist.view",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            print(f"🔧 Delete response data: {data}")
            
            subsonic_response = data.get("subsonic-response", {})
            print(f"🔧 Subsonic response status: {subsonic_response.get('status')}")
            
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                error_message = error.get('message', 'Unknown error')
                error_code = error.get('code', 'Unknown code')
                print(f"❌ Subsonic API error: {error_message} (code: {error_code})")
                raise Exception(f"Failed to delete playlist: {error_message} (code: {error_code})")
            
            print(f"✅ Successfully deleted playlist {playlist_id} from Navidrome")
            return True
                
        except httpx.RequestError as e:
            print(f"🌐 Network error deleting playlist: {e}")
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            print(f"🚨 HTTP error deleting playlist: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"💥 Unexpected error deleting playlist: {e}")
            raise Exception(f"Unexpected error deleting playlist: {e}")
    
    async def get_total_song_count(self) -> int:
        """Get the total number of songs in the library using startScan API

        Returns:
            int: Total number of songs in the library
        """
        try:
            await self._ensure_authenticated()

            # Use startScan API to get accurate song count
            params = self._get_subsonic_params()

            response = await self.client.get(
                f"{self.base_url}/rest/startScan.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            scan_status = subsonic_response.get("scanStatus", {})
            count = scan_status.get("count", 0)

            print(f"📊 Total song count in library (via startScan): {count}")
            return count

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error getting song count: {e}")

    async def get_library_song_count(self, library_id: str) -> int:
        """Get the total number of songs in a specific library

        Args:
            library_id: The library ID to get count for

        Returns:
            int: Total number of songs in the specific library
        """
        try:
            await self._ensure_authenticated()

            # Use search3 API with library filter to get all tracks (set very high limit)
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all tracks
            params["artistCount"] = "0"
            params["albumCount"] = "0"
            params["songCount"] = "10000"  # Get up to 10,000 tracks (should be enough for large libraries)
            params["musicFolderId"] = library_id

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
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

            count = len(songs)
            print(f"📊 Song count in library {library_id}: {count}")
            return count

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error getting library song count: {e}")
    
    async def get_library_stats(self) -> dict:
        """
        Calculate statistics needed for track scoring normalization.

        Returns:
            dict: Library statistics including max_play_count and max_playlist_appearances
        """
        try:
            await self._ensure_authenticated()

            # Try to get total song count from scan status
            total_tracks = await self.get_total_song_count()

            # For max_play_count, we'll estimate based on total tracks
            # Assuming most popular tracks might have 10-20% of total plays
            # This is a rough estimate since we can't get actual max play count easily
            estimated_max_plays = max(100, int(total_tracks * 0.1))

            stats = {
                'max_play_count': estimated_max_plays,
                'max_playlist_appearances': 10,  # Default reasonable max
                'total_tracks': total_tracks
            }

            print(f"📊 Calculated library stats: {stats}")
            return stats

        except Exception as e:
            print(f"⚠️ Error getting library stats, using defaults: {e}")
            # Return safe defaults if we can't get stats
            return {
                'max_play_count': 100,
                'max_playlist_appearances': 10,
                'total_tracks': 0
            }
    
    async def get_tracks(self, library_ids: Union[List[str], None] = None) -> List[Dict[str, Any]]:
        """Fetch all tracks from Navidrome, optionally filtered by library IDs
        
        Args:
            library_ids: Optional list of library IDs to filter tracks
            
        Returns:
            List of tracks with format: {id, title, artist, album, year, play_count, genre}
        """
        try:
            await self._ensure_authenticated()
            
            params = self._get_subsonic_params()

            # Add library filter if specified (use first library if multiple provided)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
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
            
            tracks_list = []
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
                    "path": song.get("path")
                }
                tracks_list.append(track)

            logger.info(f"Retrieved {len(tracks_list)} tracks from Navidrome")
            return tracks_list
            
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching tracks: {e}")
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()