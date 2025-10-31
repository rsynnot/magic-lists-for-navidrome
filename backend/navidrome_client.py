import httpx
import os
from typing import List, Dict, Any, Union, Optional

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
                        "name": artist.get("name")
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

    async def get_tracks_by_genre(self, genre: str, library_ids: List[str] = None) -> List[Dict[str, Any]]:
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
            total_fetched = 0
            offset = 0
            batch_size = 500  # Max allowed by API

            library_filter = library_ids[0] if library_ids and len(library_ids) > 0 else None
            print(f"🎵 Starting genre track collection for '{genre}'{' in library ' + library_filter if library_filter else ''}")

            while True:
                params = self._get_subsonic_params()
                params["genre"] = genre
                params["count"] = batch_size
                params["offset"] = offset

                # Add library filter if specified (use first library if multiple provided)
                if library_ids and len(library_ids) > 0:
                    params["musicFolderId"] = library_ids[0]

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

                    # If getSongsByGenre is not supported, fall back to search approach
                    if "not implemented" in error_msg.lower() or error_code == 0:
                        print(f"⚠️ getSongsByGenre not supported, falling back to search method")
                        return await self._get_tracks_by_genre_fallback(genre)
                    else:
                        raise Exception(f"Subsonic API error: {error_msg}")

                songs_by_genre = subsonic_response.get("songsByGenre", {})
                songs = songs_by_genre.get("song", [])

                # If no songs returned, we've reached the end
                if not songs:
                    break

                # Convert songs to our track format
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
                        "track_number": song.get("track")
                    }
                    all_tracks.append(track)

                batch_count = len(songs)
                total_fetched += batch_count
                offset += batch_size

                print(f"📦 Fetched batch: {batch_count} tracks (total: {total_fetched})")

                # Safety check: prevent infinite loops
                if batch_count < batch_size:
                    break

                # Safety check: prevent too many API calls (max 100 batches = 50k tracks)
                if offset >= 50000:
                    print(f"⚠️ Reached safety limit of 50k tracks for genre '{genre}'")
                    break

            print(f"✅ Completed genre collection: {len(all_tracks)} tracks for '{genre}'")
            return all_tracks

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching tracks for genre {genre}: {e}")

    async def _get_tracks_by_genre_fallback(self, genre: str) -> List[Dict[str, Any]]:
        """Fallback method using search3 when getSongsByGenre is not available

        Args:
            genre: The genre name

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        print(f"🔄 Using fallback search method for genre '{genre}'")

        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all tracks
            params["artistCount"] = 0
            params["albumCount"] = 0
            params["songCount"] = 5000  # Get large sample to find genre tracks

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
                # Filter songs that match the genre exactly
                if song.get("genre") == genre:
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
                        "track_number": song.get("track")
                    }
                    tracks_list.append(track)

            print(f"✅ Fallback method found {len(tracks_list)} tracks for '{genre}'")
            return tracks_list

        except Exception as e:
            print(f"❌ Fallback method also failed: {e}")
            return []

    async def get_genres(self, library_ids: Union[List[str], str, None] = None) -> List[str]:
        """Fetch all available genres from Navidrome using search

        Args:
            library_ids: Optional library ID(s) to filter genres (string, list of strings, or None)

        Returns:
            List of unique genre names
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

            all_genres = set()

            if library_ids_list:
                # Fetch from specific libraries
                for lib_id in library_ids_list:
                    print(f"🎵 Fetching genres from library ID: {lib_id}")
                    genres = await self._get_genres_from_library(lib_id)
                    all_genres.update(genres)
            else:
                # Fetch from all libraries (no filter)
                print("🎵 Fetching genres from all libraries")
                genres = await self._get_genres_from_library(None)
                all_genres.update(genres)

            print(f"✅ Retrieved {len(all_genres)} unique genres from {len(library_ids_list) if library_ids_list else 'all'} libraries")
            return sorted(list(all_genres))

        except Exception as e:
            print(f"❌ Error in get_genres: {e}")
            raise

    async def _get_genres_from_library(self, library_id: Union[str, None]) -> List[str]:
        """Fetch genres from a specific library or all libraries"""
        try:
            # Use a broad search to get tracks with genre information
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all
            params["artistCount"] = 0
            params["albumCount"] = 0
            params["songCount"] = 2000  # Get larger sample of tracks

            # Add library filter if specified
            if library_id:
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

            # Extract unique genres
            genres = set()
            for song in songs:
                genre = song.get("genre")
                if genre:
                    genres.add(genre)

            return list(genres)

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching genres: {e}")

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
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()