import httpx
import os
import json
from typing import List, Dict, Any

class AIClient:
    """Client for AI-powered track curation"""
    
    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY")
        self.model = os.getenv("AI_MODEL", "gpt-3.5-turbo")
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient()
        
    async def curate_artist_radio(
        self, 
        artist_name: str, 
        tracks_json: List[Dict[str, Any]], 
        num_tracks: int = 20
    ) -> List[str]:
        """Curate a radio-style playlist for an artist using AI
        
        Args:
            artist_name: Name of the artist
            tracks_json: List of track dictionaries with id, title, album, year, play_count
            num_tracks: Number of tracks to select (default: 20)
            
        Returns:
            List of track IDs in curated order
        """
        
        if not self.api_key:
            # Fallback: return first num_tracks by play count
            sorted_tracks = sorted(
                tracks_json, 
                key=lambda x: x.get("play_count", 0), 
                reverse=True
            )
            return [track["id"] for track in sorted_tracks[:num_tracks]]
        
        try:
            # Prepare the tracks data for the AI prompt
            tracks_data = json.dumps(tracks_json, indent=2)
            
            prompt = f"""
You are a music curator creating a radio playlist for {artist_name}.

Here are all available tracks:
{tracks_data}

Please select exactly {num_tracks} tracks that would make the best radio playlist for this artist. Consider:
- Song quality and popularity (play_count)
- Variety across different albums and eras
- Flow and pacing for radio play
- Mix of well-known hits and deep cuts

Return ONLY a JSON array of track IDs in the order they should be played. Example format:
["track_id_1", "track_id_2", "track_id_3"]

Do not include any other text or explanation.
"""
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are a professional music curator. Always respond with valid JSON arrays of track IDs only."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            async with self.client as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                
                # Parse the JSON response
                try:
                    track_ids = json.loads(content)
                    
                    # Validate that it's a list of strings
                    if isinstance(track_ids, list) and all(isinstance(tid, str) for tid in track_ids):
                        # Ensure we only return valid track IDs that exist in the input
                        valid_ids = {track["id"] for track in tracks_json}
                        filtered_ids = [tid for tid in track_ids if tid in valid_ids]
                        
                        # Return up to num_tracks
                        return filtered_ids[:num_tracks]
                    else:
                        raise ValueError("Invalid response format")
                        
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"Failed to parse AI response: {e}")
                    print(f"Response content: {content}")
                    # Fall back to simple selection
                    return self._fallback_selection(tracks_json, num_tracks)
                
        except httpx.RequestError as e:
            print(f"Network error calling AI API: {e}")
            return self._fallback_selection(tracks_json, num_tracks)
        except httpx.HTTPStatusError as e:
            print(f"HTTP error from AI API: {e.response.status_code}")
            return self._fallback_selection(tracks_json, num_tracks)
        except Exception as e:
            print(f"Unexpected error in AI curation: {e}")
            return self._fallback_selection(tracks_json, num_tracks)
    
    def _fallback_selection(self, tracks_json: List[Dict[str, Any]], num_tracks: int) -> List[str]:
        """Fallback selection algorithm when AI is unavailable"""
        # Sort by play count (descending) then by year (descending for newer songs)
        sorted_tracks = sorted(
            tracks_json,
            key=lambda x: (x.get("play_count", 0), x.get("year", 0)),
            reverse=True
        )
        
        return [track["id"] for track in sorted_tracks[:num_tracks]]
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()