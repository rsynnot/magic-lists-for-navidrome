import httpx
import os
import json
from typing import List, Dict, Any, Union, Tuple
from .recipe_manager import recipe_manager

class AIClient:
    """Client for AI-powered track curation using OpenRouter"""
    
    def __init__(self):
        self.api_key = os.getenv("AI_API_KEY")
        self.model = os.getenv("AI_MODEL", "openai/gpt-3.5-turbo")
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient()

        # Debug logging
        print(f"🔍 AIClient initialized:")
        print(f"   🔑 API Key present: {bool(self.api_key)}")
        print(f"   🔑 API Key length: {len(self.api_key) if self.api_key else 0}")
        print(f"   🤖 Model: {self.model}")
        print(f"   🌐 Base URL: {self.base_url}")
        
    async def curate_artist_radio(
        self, 
        artist_name: str, 
        tracks_json: List[Dict[str, Any]], 
        num_tracks: int = 20,
        include_reasoning: bool = False
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a radio-style playlist for an artist using AI
        
        Args:
            artist_name: Name of the artist
            tracks_json: List of track dictionaries with id, title, album, year, play_count
            num_tracks: Number of tracks to select (default: 20)
            include_reasoning: Whether to return AI's reasoning along with track IDs
            
        Returns:
            List of track IDs in curated order, or tuple of (track_ids, reasoning) if include_reasoning=True
        """
        
        if not self.api_key:
            print(f"❌ No AI API key configured, using fallback curation for {artist_name}")
            print(f"📊 Processing {len(tracks_json)} tracks for curation")
            # Fallback: return first num_tracks by play count
            sorted_tracks = sorted(
                tracks_json,
                key=lambda x: x.get("play_count", 0),
                reverse=True
            )
            track_ids = [track["id"] for track in sorted_tracks[:num_tracks]]

            if include_reasoning:
                fallback_reasoning = f"Fallback curation: Selected {len(track_ids)} tracks sorted by play count (highest first). No AI API key configured."
                return track_ids, fallback_reasoning
            else:
                return track_ids
        
        try:
            print(f"Using AI to curate playlist for {artist_name} from {len(tracks_json)} available tracks")
            
            # Prepare the tracks data for the AI prompt
            tracks_data = json.dumps(tracks_json, indent=2)
            
            # Use recipe system to generate prompt and get LLM parameters
            recipe_inputs = {
                "artists": artist_name,  # Match recipe expectation: "artists"
                "tracks_data": tracks_data,
                "track_count": num_tracks,  # Match recipe expectation: "track_count"
                "playlist_length": num_tracks,  # Match recipe expectation: "playlist_length"
                "refresh_frequency": "daily",  # Default value for recipe
                "steer": "balanced"  # Default steer value for now
            }
            
            recipe_result = recipe_manager.apply_recipe("artist_radio", recipe_inputs, include_reasoning)
            prompt = recipe_result["prompt"]
            llm_params = recipe_result["llm_params"]
            
            # Use model from recipe or fall back to environment/default
            model = llm_params.get("model_fallback", self.model)
            temperature = llm_params.get("temperature", 0.7)
            max_tokens = llm_params.get("max_tokens", 1000)
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a professional music curator. Always respond with valid JSON containing track_ids array and reasoning string. No other text outside the JSON."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
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

                # Log the raw AI response for debugging
                print(f"🤖 RAW AI RESPONSE for {artist_name}: {content}")

                # Parse the JSON response
                try:
                    # Try to parse as JSON object first (new recipe format)
                    try:
                        response_data = json.loads(content)
                        if isinstance(response_data, dict) and "track_ids" in response_data:
                            # New format with reasoning
                            track_ids = response_data.get("track_ids", [])
                            reasoning = response_data.get("reasoning", "")
                            
                            # Validate track IDs
                            if isinstance(track_ids, list) and all(isinstance(tid, str) for tid in track_ids):
                                valid_ids = {track["id"] for track in tracks_json}
                                filtered_ids = [tid for tid in track_ids if tid in valid_ids]
                                final_selection = filtered_ids[:num_tracks]
                                
                                print(f"AI successfully curated {len(final_selection)} tracks for {artist_name}")
                                if reasoning:
                                    print(f"AI reasoning: {reasoning[:200]}...")
                                
                                if include_reasoning or reasoning:
                                    return final_selection, reasoning
                                else:
                                    return final_selection
                            else:
                                raise ValueError("Invalid track_ids format in response")
                        else:
                            # Fall back to treating as simple array
                            track_ids = response_data if isinstance(response_data, list) else json.loads(content)
                    except (json.JSONDecodeError, TypeError):
                        # Parse as simple track list (legacy format)
                        track_ids = json.loads(content)
                    
                    # Handle simple array format
                    if isinstance(track_ids, list) and all(isinstance(tid, str) for tid in track_ids):
                        valid_ids = {track["id"] for track in tracks_json}
                        filtered_ids = [tid for tid in track_ids if tid in valid_ids]
                        final_selection = filtered_ids[:num_tracks]
                        
                        print(f"AI successfully curated {len(final_selection)} tracks for {artist_name}")
                        
                        if include_reasoning:
                            return final_selection, ""  # No reasoning available
                        else:
                            return final_selection
                    else:
                        raise ValueError("Invalid response format")
                        
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"Failed to parse AI response: {e}")
                    print(f"Response content: {content}")
                    # Fall back to simple selection
                    return self._fallback_selection(tracks_json, num_tracks, include_reasoning)
                
        except httpx.RequestError as e:
            print(f"🌐 Network error calling AI API: {e}")
            print(f"🔑 API Key present: {bool(self.api_key)}")
            print(f"🌐 Base URL: {self.base_url}")
            return self._fallback_selection(tracks_json, num_tracks, include_reasoning, f"Network error: {e}")
        except httpx.HTTPStatusError as e:
            print(f"🚨 HTTP error from AI API: {e.response.status_code} - {e.response.text}")
            print(f"🔑 API Key present: {bool(self.api_key)}")
            print(f"🤖 Model: {self.model}")
            return self._fallback_selection(tracks_json, num_tracks, include_reasoning, f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            print(f"💥 Unexpected error in AI curation: {e}")
            import traceback
            print(f"📋 Traceback: {traceback.format_exc()}")
            return self._fallback_selection(tracks_json, num_tracks, include_reasoning, f"Unexpected error: {e}")
    
    def _fallback_selection(self, tracks_json: List[Dict[str, Any]], num_tracks: int, include_reasoning: bool = False, error_reason: str = "AI service was unavailable") -> Union[List[str], Tuple[List[str], str]]:
        """Fallback selection algorithm when AI is unavailable"""
        # Sort by play count (descending) then by year (descending for newer songs)
        sorted_tracks = sorted(
            tracks_json,
            key=lambda x: (x.get("play_count", 0), x.get("year", 0)),
            reverse=True
        )
        
        track_ids = [track["id"] for track in sorted_tracks[:num_tracks]]
        
        if include_reasoning:
            reasoning = f"Fallback curation: Selected {len(track_ids)} tracks sorted by play count and year (most popular and recent first). {error_reason}"
            return track_ids, reasoning
        else:
            return track_ids
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()