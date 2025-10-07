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
        print(f"🔍 AIClient initialized")
        
    async def _get_client(self):
        """Get or recreate the HTTP client if needed"""
        if not hasattr(self, 'client') or not self.client or (hasattr(self.client, 'is_closed') and self.client.is_closed):
            self.client = httpx.AsyncClient()
        return self.client
        
    async def curate_this_is(
        self, 
        artist_name: str, 
        tracks_json: List[Dict[str, Any]], 
        num_tracks: int = 20,
        include_reasoning: bool = False,
        variety_context: str = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a 'This Is' playlist for a single artist using AI
        
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
            # Processing tracks for curation (logging moved to scheduler_logger)
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
            # Using AI to curate playlist (logging moved to scheduler_logger)
            
            # SHUFFLE tracks to prevent AI from album-grouping based on input order
            import random
            shuffled_tracks = tracks_json.copy()  # Don't modify the original list
            random.shuffle(shuffled_tracks)
            
            # Prepare the tracks data for the AI prompt
            tracks_data = json.dumps(shuffled_tracks, indent=2)
            
            # Use recipe system to generate prompt and get LLM parameters
            recipe_inputs = {
                "artists": artist_name,
                "tracks_data": tracks_data,
                "num_tracks": num_tracks,
                "variety_context": variety_context or ""
            }
            
            final_recipe = recipe_manager.apply_recipe("this_is", recipe_inputs, include_reasoning)
            
            # Check if this is new recipe format (has llm_config) or legacy format
            if "llm_config" in final_recipe:
                # New recipe format
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")
                
                # Use model from recipe first, then fallback to environment
                model = llm_config.get("model_name") or self.model or "openai/gpt-3.5-turbo"
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1000)
                
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": model_instructions
                        },
                        {
                            "role": "user", 
                            "content": f"Here are the available tracks to choose from:\n{tracks_data}\n\nPlease create the playlist according to the instructions and respond with valid JSON containing track_ids array and reasoning string."
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            else:
                # Legacy recipe format
                prompt = final_recipe["prompt"]
                llm_params = final_recipe["llm_params"]
                
                # Use model from environment first, only fallback to recipe if not set
                model = self.model or llm_params.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_params.get("temperature", 0.7)
                max_tokens = llm_params.get("max_tokens", 1000)
                
                print(f"🤖 AI CLIENT - LEGACY RECIPE FORMAT DETECTED")
                print(f"🎯 Environment model: {self.model}")
                print(f"🎯 Recipe model fallback: {llm_params.get('model_fallback')}")
                print(f"🎯 Final model to use: {model}")
                print(f"🌡️ Temperature: {temperature}")
                print(f"🔢 Max tokens: {max_tokens}")
                print(f"📝 Prompt length: {len(prompt)} characters")
                
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
            
            
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            # Log API response details
            print(f"📊 AI Response status: {response.status_code}")
            
            # Log the raw AI response for debugging (truncated preview)
            import re
            
            # Extract first 3 track IDs for preview
            track_preview = ""
            try:
                # Look for track_ids array in the content
                track_ids_match = re.search(r'"track_ids":\s*\[(.*?)\]', content, re.DOTALL)
                if track_ids_match:
                    track_ids_content = track_ids_match.group(1)
                    # Split by commas and take first 3
                    track_lines = [line.strip() for line in track_ids_content.split(',')]
                    first_three = track_lines[:3]
                    track_preview = '[\n    ' + ',\n    '.join(first_three) + ',\n    ...\n  ]'
                else:
                    track_preview = content[:100] + "..."
            except:
                track_preview = content[:100] + "..."
            
            print(f"🤖 RAW AI RESPONSE for {artist_name}: {track_preview}")

            # Parse the JSON response
            try:
                # Clean up the response - remove markdown code fences and comments
                cleaned_content = content.strip()
                
                # Remove markdown code fences if present
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]  # Remove ```json
                if cleaned_content.startswith("```"):
                    cleaned_content = cleaned_content[3:]   # Remove ```
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]  # Remove trailing ```
                
                cleaned_content = cleaned_content.strip()
                
                # Remove JavaScript-style comments (// comments) 
                import re
                lines = cleaned_content.split('\n')
                cleaned_lines = []
                
                for line in lines:
                    # Remove // comments but preserve URLs like http://
                    if '//' in line and 'http://' not in line and 'https://' not in line:
                        comment_pos = line.find('//')
                        line = line[:comment_pos].rstrip()
                    
                    # Fix unquoted strings like: "track123",\n    Say You Will
                    # Should be: "track123",\n    "Say You Will"
                    line = re.sub(r'^(\s*)(Say You Will)(\s*$)', r'\1"\2"\3', line)
                    line = re.sub(r'^(\s*)([A-Za-z][A-Za-z0-9\s\']+)(\s*$)', r'\1"\2"\3', line)
                    
                    # Remove trailing commas before closing brackets
                    line = re.sub(r',(\s*[\]}])', r'\1', line)
                    
                    if line.strip():  # Only add non-empty lines
                        cleaned_lines.append(line)
                
                cleaned_content = '\n'.join(cleaned_lines)
                
                
                # Try to parse as JSON object (new recipe format)
                response_data = json.loads(cleaned_content)

                if isinstance(response_data, dict) and "track_ids" in response_data:
                    # New format with reasoning
                    track_ids = response_data.get("track_ids", [])
                    reasoning = response_data.get("reasoning", "")

                    # Validate track IDs
                    if isinstance(track_ids, list) and all(isinstance(tid, str) for tid in track_ids):
                        valid_ids = {track["id"] for track in shuffled_tracks}
                        filtered_ids = [tid for tid in track_ids if tid in valid_ids]
                        final_selection = filtered_ids[:num_tracks]

                        # AI curation successful (logging moved to scheduler_logger)
                        if reasoning:
                            # AI reasoning available (logged in main.py scheduler_logger)
                            pass

                        if include_reasoning:
                            return final_selection, reasoning
                        else:
                            return final_selection
                    else:
                        raise ValueError("Invalid track_ids format in response")

                # Handle simple array format (legacy)
                elif isinstance(response_data, list) and all(isinstance(tid, str) for tid in response_data):
                    valid_ids = {track["id"] for track in shuffled_tracks}
                    filtered_ids = [tid for tid in response_data if tid in valid_ids]
                    final_selection = filtered_ids[:num_tracks]

                    # AI curation successful (logging moved to scheduler_logger)

                    if include_reasoning:
                        return final_selection, ""  # No reasoning available
                    else:
                        return final_selection
                else:
                    raise ValueError("Invalid response format: expected dict with track_ids or array of track IDs")

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
    
    async def curate_rediscover_weekly(
        self, 
        candidate_tracks: List[Dict[str, Any]], 
        analysis_summary: str,
        num_tracks: int = 20,
        include_reasoning: bool = True,
        variety_context: str = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Re-Discover Weekly playlist using AI
        
        Args:
            candidate_tracks: List of pre-filtered candidate tracks with metadata
            analysis_summary: Summary of the algorithmic analysis performed
            num_tracks: Number of tracks to select (default: 20)
            include_reasoning: Whether to return AI's reasoning along with track IDs
            
        Returns:
            List of track IDs in curated order, or tuple of (track_ids, reasoning) if include_reasoning=True
        """
        
        if not self.api_key:
            print(f"❌ No AI API key configured, using fallback curation for Re-Discover Weekly")
            # Processing candidate tracks for curation (logging moved to scheduler_logger)
            # Fallback: return first num_tracks by score (should already be sorted by rediscover algorithm)
            track_ids = [track["id"] for track in candidate_tracks[:num_tracks]]

            if include_reasoning:
                fallback_reasoning = f"Fallback curation: Selected top {len(track_ids)} tracks from algorithmic scoring (highest score first). No AI API key configured."
                return track_ids, fallback_reasoning
            else:
                return track_ids
        
        try:
            # Using AI to curate Re-Discover Weekly (logging moved to scheduler_logger)
            
            # Prepare the tracks data for the AI prompt
            tracks_data = json.dumps(candidate_tracks, indent=2)
            
            # Use recipe system with proper placeholder replacement
            recipe_inputs = {
                "candidate_tracks": tracks_data,
                "analysis_summary": analysis_summary,
                "num_tracks": num_tracks
            }
            
            final_recipe = recipe_manager.apply_recipe("re_discover", recipe_inputs, include_reasoning)
            
            # Check if this is new recipe format (has llm_config) or legacy format
            if "llm_config" in final_recipe:
                # New recipe format with placeholders properly replaced
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")
                
                # Use model from recipe first, then fallback to environment
                model = llm_config.get("model_name") or self.model or "openai/gpt-3.5-turbo"
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1500)
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": model_instructions
                        },
                        {
                            "role": "user", 
                            "content": f"Here are the candidate tracks to choose from:\n{tracks_data}\n\n" + (f"REFRESH CONTEXT: {variety_context}\n\n" if variety_context else "") + "Please analyze these candidate tracks and create the playlist according to the instructions. Respond with valid JSON containing track_ids array and reasoning string."
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            else:
                # Legacy recipe format fallback
                prompt = final_recipe.get("prompt", "")
                llm_params = final_recipe.get("llm_params", {})
                
                model = self.model or llm_params.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_params.get("temperature", 0.8)
                max_tokens = llm_params.get("max_tokens", 2500)
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a professional music curator specializing in rediscovery playlists. Always respond with valid JSON containing track_ids array and reasoning string. No other text outside the JSON."
                        },
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            
            # DEBUG: Dump payload to file for inspection (disabled by default)
            DEBUG_DUMP_PAYLOADS = False  # Set to True to enable payload dumping for development
            
            if DEBUG_DUMP_PAYLOADS:
                import time
                
                timestamp = int(time.time())
                dump_filename = f"debug_payloads/rediscover_payload_{timestamp}.json"
                dump_path = os.path.join(os.getcwd(), dump_filename)
                
                try:
                    os.makedirs(os.path.dirname(dump_path), exist_ok=True)
                    with open(dump_path, 'w') as f:
                        json.dump(payload, f, indent=2)
                    print(f"✅ DEBUG: Re-Discover payload dumped to: {dump_filename}")
                except Exception as e:
                    print(f"❌ DEBUG: Failed to dump Re-Discover payload: {e}")
            
            print(f"🚀 MAKING API CALL FOR RE-DISCOVER")
            print(f"🎯 Model in payload: {payload['model']}")
            print(f"🌡️ Temperature: {payload['temperature']}")
            print(f"🔢 Max tokens: {payload['max_tokens']}")
            print(f"💬 Messages: {len(payload['messages'])}")
            
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()

            # Log API response details
            print(f"📊 Re-Discover AI Response status: {response.status_code}")
            
            # Log the raw AI response for debugging (truncated preview)
            import re
            
            # Extract first 3 track IDs for preview
            track_preview = ""
            try:
                # Look for track_ids array in the content
                track_ids_match = re.search(r'"track_ids":\s*\[(.*?)\]', content, re.DOTALL)
                if track_ids_match:
                    track_ids_content = track_ids_match.group(1)
                    # Split by commas and take first 3
                    track_lines = [line.strip() for line in track_ids_content.split(',')]
                    first_three = track_lines[:3]
                    track_preview = '[\n    ' + ',\n    '.join(first_three) + ',\n    ...\n  ]'
                else:
                    track_preview = content[:100] + "..."
            except:
                track_preview = content[:100] + "..."
            
            print(f"🤖 RAW AI RESPONSE for Re-Discover Weekly: {track_preview}")

            # Parse the JSON response
            try:
                # Clean up the response - remove markdown code fences and comments
                cleaned_content = content.strip()
                
                # Remove markdown code fences if present
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]  # Remove ```json
                if cleaned_content.startswith("```"):
                    cleaned_content = cleaned_content[3:]   # Remove ```
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]  # Remove trailing ```
                
                cleaned_content = cleaned_content.strip()
                
                # Remove JavaScript-style comments (// comments) 
                import re
                lines = cleaned_content.split('\n')
                cleaned_lines = []
                
                for line in lines:
                    # Remove // comments but preserve URLs like http://
                    if '//' in line and 'http://' not in line and 'https://' not in line:
                        comment_pos = line.find('//')
                        line = line[:comment_pos].rstrip()
                    
                    # Remove trailing commas before closing brackets
                    line = re.sub(r',(\s*[\]}])', r'\1', line)
                    
                    if line.strip():  # Only add non-empty lines
                        cleaned_lines.append(line)
                
                cleaned_content = '\n'.join(cleaned_lines)
                
                # Try to parse as JSON object
                response_data = json.loads(cleaned_content)

                if isinstance(response_data, dict) and "track_ids" in response_data:
                    # New format with reasoning
                    track_ids = response_data.get("track_ids", [])
                    reasoning = response_data.get("reasoning", "")

                    # Validate track IDs
                    if isinstance(track_ids, list) and all(isinstance(tid, str) for tid in track_ids):
                        valid_ids = {track["id"] for track in candidate_tracks}
                        filtered_ids = [tid for tid in track_ids if tid in valid_ids]
                        final_selection = filtered_ids[:num_tracks]

                        # AI curation successful for Re-Discover Weekly (logging moved to scheduler_logger)
                        if reasoning:
                            # AI reasoning available (logged in main.py scheduler_logger)
                            pass

                        if include_reasoning:
                            return final_selection, reasoning
                        else:
                            return final_selection
                    else:
                        raise ValueError("Invalid track_ids format in response")

                # Handle simple array format (legacy)
                elif isinstance(response_data, list) and all(isinstance(tid, str) for tid in response_data):
                    valid_ids = {track["id"] for track in candidate_tracks}
                    filtered_ids = [tid for tid in response_data if tid in valid_ids]
                    final_selection = filtered_ids[:num_tracks]

                    # AI curation successful for Re-Discover Weekly (logging moved to scheduler_logger)

                    if include_reasoning:
                        return final_selection, ""  # No reasoning available
                    else:
                        return final_selection
                else:
                    raise ValueError("Invalid response format: expected dict with track_ids or array of track IDs")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse AI response: {e}")
                print(f"Response content: {content}")
                # Fall back to simple selection
                return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning)
                
        except httpx.RequestError as e:
            print(f"🌐 Network error calling AI API: {e}")
            print(f"🔑 API Key present: {bool(self.api_key)}")
            print(f"🌐 Base URL: {self.base_url}")
            return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning, f"Network error: {e}")
        except httpx.HTTPStatusError as e:
            print(f"🚨 HTTP error from AI API: {e.response.status_code} - {e.response.text}")
            print(f"🔑 API Key present: {bool(self.api_key)}")
            print(f"🤖 Model: {self.model}")
            return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning, f"HTTP {e.response.status_code}: {e.response.text}")
        except Exception as e:
            print(f"💥 Unexpected error in AI curation: {e}")
            import traceback
            print(f"📋 Traceback: {traceback.format_exc()}")
            return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning, f"Unexpected error: {e}")
    
    def _fallback_rediscover_selection(self, candidate_tracks: List[Dict[str, Any]], num_tracks: int, include_reasoning: bool = False, error_reason: str = "AI service was unavailable") -> Union[List[str], Tuple[List[str], str]]:
        """Fallback selection algorithm for rediscover when AI is unavailable"""
        # Use the pre-sorted candidates (should already be sorted by score)
        track_ids = [track["id"] for track in candidate_tracks[:num_tracks]]
        
        if include_reasoning:
            reasoning = f"Fallback curation: Selected top {len(track_ids)} tracks from algorithmic pre-filtering (sorted by play count × days since last play). {error_reason}"
            return track_ids, reasoning
        else:
            return track_ids

    async def close(self):
        """Close the HTTP client"""
        try:
            if hasattr(self, 'client') and self.client:
                if hasattr(self.client, 'is_closed') and not self.client.is_closed:
                    await self.client.aclose()
        except Exception as e:
            print(f"Warning: Error closing HTTP client: {e}")