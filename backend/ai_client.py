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
            
            # Note: We now pass shuffled_tracks directly as clean JSON array to the AI
            # No more string conversion and text blob parsing!
            
            # Log track data completeness
            original_track_count = len(tracks_json)
            shuffled_track_count = len(shuffled_tracks)
            
            print(f"🎵 Preparing {shuffled_track_count} tracks for AI curation")
            
            # Verify track data includes essential fields
            if shuffled_tracks:
                sample_track = shuffled_tracks[0]
                essential_fields = ['id', 'title', 'artist', 'album']
                missing_fields = [field for field in essential_fields if field not in sample_track]
                if missing_fields:
                    print(f"⚠️  Missing essential fields in tracks: {missing_fields}")
            else:
                print(f"❌ ERROR: No tracks available for curation!")
            
            # Use recipe system to generate prompt and get LLM parameters
            recipe_inputs = {
                "artists": artist_name,
                "num_tracks": num_tracks,
                "variety_context": variety_context or ""
            }
            
            print(f"🍳 Applying recipe for {artist_name} ({num_tracks} tracks)")
            
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
                
                print(f"🤖 Using AI model: {model}")
                
                # Serialize the complete recipe (excluding tracks_data to avoid duplication)
                recipe_without_tracks = {k: v for k, v in final_recipe.items() if k != "tracks_data"}
                
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                # Build structured JSON payload with INDEX-BASED approach
                # Create indexed tracks (remove complex IDs, use simple indices)
                indexed_tracks = []
                track_id_map = []  # Keep mapping of index → actual track ID
                
                for index, track in enumerate(shuffled_tracks):
                    # Store the actual track ID in our mapping
                    track_id_map.append(track["id"])
                    
                    # Create indexed track (no complex ID, just index + music data)
                    indexed_track = {
                        "index": index,
                        "track_name": track.get("title", "Unknown"),
                        "artist": track.get("artist", "Unknown"),
                        "album": track.get("album", "Unknown"),
                        "genre": track.get("genre", "Unknown"),
                        "year": track.get("year", 0),
                        "play_count": track.get("play_count", 0)
                    }
                    indexed_tracks.append(indexed_track)
                
                structured_payload = {
                    "recipe": recipe_without_tracks,
                    "available_tracks": indexed_tracks,  # INDEX-BASED tracks (no complex IDs)
                    "request": {
                        "artist_name": artist_name,
                        "desired_track_count": num_tracks,
                        "playlist_type": "this_is"
                    }
                }
                
                print(f"🔢 Using index-based approach for {len(track_id_map)} tracks")
                
                user_content = f"""STRUCTURED PLAYLIST REQUEST:

{json.dumps(structured_payload, indent=2, ensure_ascii=False)}

CRITICAL INSTRUCTIONS:
- Analyze the recipe configuration (processing steps, filters, curation rules)
- Select tracks from the available_tracks array
- **IMPORTANT**: USE THE 'index' FIELD ONLY - never use the track_name, artist, or any other field
- Your track_ids array must contain ONLY the exact 'index' values (as integers) from the available_tracks
- Create a playlist of {num_tracks} tracks for {artist_name}
- Respond with valid JSON: {{"track_ids": [0, 5, 12, 3, ...], "reasoning": "explanation"}}

EXAMPLE: If track has "index": 5, return 5 in track_ids array. If track has "index": 12, return 12."""
                
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": model_instructions
                        },
                        {
                            "role": "user", 
                            "content": user_content
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                print(f"💬 Sending structured payload to AI")
                
                # DEBUG: Dump payload to file for "This Is" playlist inspection
                DEBUG_DUMP_THIS_IS_PAYLOADS = False  # Disabled for production
                
                if DEBUG_DUMP_THIS_IS_PAYLOADS:
                    import time
                    
                    timestamp = int(time.time())
                    dump_filename = f"debug_payloads/this_is_payload_{artist_name.replace(' ', '_')}_{timestamp}.json"
                    dump_path = os.path.join(os.getcwd(), dump_filename)
                    
                    try:
                        os.makedirs(os.path.dirname(dump_path), exist_ok=True)
                        with open(dump_path, 'w', encoding='utf-8') as f:
                            json.dump(payload, f, indent=2, ensure_ascii=False, separators=(',', ': '))
                        print(f"✅ DEBUG: This Is payload dumped to: {dump_filename}")
                    except Exception as e:
                        print(f"❌ DEBUG: Failed to dump This Is payload: {e}")
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

            # Parse the JSON response with comprehensive validation
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

                # STEP 2: RESPONSE STRUCTURE VALIDATION
                source_track_count = len(shuffled_tracks)
                
                # Validate response structure
                if isinstance(response_data, dict) and "track_ids" in response_data:
                    # New format with reasoning - validate structure
                    track_ids = response_data.get("track_ids", [])
                    reasoning = response_data.get("reasoning", "")
                    
                    # Structure checks
                    if not isinstance(track_ids, list):
                        print(f"❌ Response validation failed: track_ids is not a list")
                        raise ValueError("Response structure invalid: track_ids must be a list")
                    
                    if not isinstance(reasoning, str):
                        print(f"❌ Response validation failed: reasoning is not a string")
                        raise ValueError("Response structure invalid: reasoning must be a string")
                    
                    # INDEX-BASED: Validate all track IDs are integers (indices)
                    if not all(isinstance(tid, int) for tid in track_ids):
                        print(f"❌ Response validation: FAILED - not all track_ids are integers")
                        raise ValueError("Invalid track_ids format: all IDs must be integers (indices)")
                    
                    returned_track_count = len(track_ids)
                    
                    # Sanity checks
                    # Check 1: Large source, tiny return
                    if source_track_count >= 100 and returned_track_count <= 10:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: Too few tracks returned from large source set. {error_msg}")
                    
                    # Check 2: Less than 20% returned
                    min_expected = max(1, int(source_track_count * 0.2))  # At least 20% or 1 track
                    if returned_track_count < min_expected:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: Returned tracks less than 20% of source. {error_msg}")
                    
                    # Check 3: More returned than source
                    if returned_track_count > source_track_count:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: More tracks returned than provided. {error_msg}")
                    
                    print(f"✅ AI returned {returned_track_count} tracks, validation passed")

                    # INDEX-BASED: Map indices back to actual track IDs
                    # Find which indices are invalid (out of range)
                    invalid_indices = [idx for idx in track_ids if idx < 0 or idx >= len(track_id_map)]
                    if invalid_indices:
                        print(f"❌ AI returned {len(invalid_indices)} invalid indices out of {len(track_ids)}")
                    
                    # Map valid indices to actual track IDs
                    valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
                    mapped_track_ids = [track_id_map[idx] for idx in valid_indices]
                    print(f"🔄 Mapped {len(mapped_track_ids)} valid indices to track IDs")
                    
                    # Final selection (limit to requested count)
                    final_selection = mapped_track_ids[:num_tracks]

                    # AI curation successful (logging moved to scheduler_logger)
                    if reasoning:
                        # AI reasoning available (logged in main.py scheduler_logger)
                        pass

                    if include_reasoning:
                        return final_selection, reasoning
                    else:
                        return final_selection

                # Handle simple array format (legacy)
                elif isinstance(response_data, list) and all(isinstance(tid, str) for tid in response_data):
                    print(f"✅ Response validation: structure OK (legacy array format)")
                    
                    returned_track_count = len(response_data)
                    
                    # SANITY CHECKS for legacy format
                    print(f"🧠 SANITY CHECKS:")
                    print(f"   Returned tracks: {returned_track_count}")
                    
                    # Check 1: Large source, tiny return
                    if source_track_count >= 100 and returned_track_count <= 10:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: Too few tracks returned from large source set. {error_msg}")
                    
                    # Check 2: Less than 20% returned
                    min_expected = max(1, int(source_track_count * 0.2))
                    if returned_track_count < min_expected:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: Returned tracks less than 20% of source. {error_msg}")
                    
                    # Check 3: More returned than source
                    if returned_track_count > source_track_count:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: More tracks returned than provided. {error_msg}")
                    
                    print(f"✅ Response validation passed: received {returned_track_count} tracks from {source_track_count} source tracks")

                    valid_ids = {track["id"] for track in shuffled_tracks}
                    filtered_ids = [tid for tid in response_data if tid in valid_ids]
                    final_selection = filtered_ids[:num_tracks]

                    # AI curation successful (logging moved to scheduler_logger)

                    if include_reasoning:
                        return final_selection, ""  # No reasoning available
                    else:
                        return final_selection
                else:
                    print(f"❌ Response validation: FAILED - invalid response format")
                    raise ValueError("Invalid response format: expected dict with track_ids or array of track IDs")

            except (json.JSONDecodeError, ValueError) as e:
                error_msg = str(e)
                print(f"❌ AI RESPONSE VALIDATION FAILED: {error_msg}")
                print(f"Response content preview: {content[:200]}...")
                
                # Check if this is a validation error vs parsing error
                if "PAYLOAD ERROR:" in error_msg or "Sanity check failed:" in error_msg:
                    print(f"🚨 CRITICAL VALIDATION FAILURE - STOPPING SUBMISSION PROCESS")
                    print(f"💡 User-friendly message: Playlist generation failed: unexpected response from AI. Please try again.")
                    
                    # Return error state to prevent partial processing
                    if include_reasoning:
                        return [], f"Playlist generation failed: {error_msg}. Please try again."
                    else:
                        return []
                else:
                    print(f"🔄 JSON parsing failed, falling back to simple selection")
                    # Fall back to simple selection for parsing errors only
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
            # Preparing candidates for AI curation
            
            # Build structured JSON payload with INDEX-BASED approach
            # Create indexed tracks (remove complex IDs, use simple indices)
            indexed_tracks = []
            track_id_map = []  # Keep mapping of index → actual track ID
            
            for index, track in enumerate(candidate_tracks):
                # Store the actual track ID in our mapping
                track_id_map.append(track["id"])
                
                # Create indexed track (no complex ID, just index + music data)
                indexed_track = {
                    "index": index,
                    "track_name": track.get("title", "Unknown"),
                    "artist": track.get("artist", "Unknown"),
                    "album": track.get("album", "Unknown"),
                    "genre": track.get("genre", "Unknown"),
                    "year": track.get("year", 0),
                    "play_count": track.get("play_count", 0),
                    "rediscovery_score": track.get("rediscovery_score", 0)
                }
                indexed_tracks.append(indexed_track)
            
            # Using index-based approach
            
            # Use recipe system with proper placeholder replacement
            recipe_inputs = {
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
                
                # Using AI model
                
                # Serialize the complete recipe (excluding tracks for structured payload)
                recipe_without_tracks = {k: v for k, v in final_recipe.items() if k not in ["candidate_tracks", "tracks_data"]}
                
                structured_payload = {
                    "recipe": recipe_without_tracks,
                    "available_tracks": indexed_tracks,  # INDEX-BASED tracks (no complex IDs)
                    "analysis_summary": analysis_summary,
                    "request": {
                        "desired_track_count": num_tracks,
                        "playlist_type": "rediscover",
                        "variety_context": variety_context or ""
                    }
                }
                
                user_content = f"""STRUCTURED REDISCOVER REQUEST:

{json.dumps(structured_payload, indent=2, ensure_ascii=False)}

CRITICAL INSTRUCTIONS:
- Analyze the recipe configuration (processing steps, filters, curation rules)
- Select tracks from the available_tracks array using rediscovery_score and other metadata
- **IMPORTANT**: USE THE 'index' FIELD ONLY - return the index numbers, NOT track_name, artist, or any other field
- Your track_ids array must contain ONLY the exact 'index' values (as integers) from the available_tracks
- Create a rediscover playlist of {num_tracks} tracks
- Respond with valid JSON: {{"track_ids": [0, 5, 12, 3, ...], "reasoning": "explanation"}}

EXAMPLE: If track has "index": 5, return 5 in track_ids array. If track has "index": 12, return 12."""
                
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
                            "content": user_content
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                # Sending structured payload to AI
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
            
            # DEBUG: Dump payload to file for inspection
            DEBUG_DUMP_PAYLOADS = False  # Disabled for production
            
            if DEBUG_DUMP_PAYLOADS:
                import time
                
                timestamp = int(time.time())
                dump_filename = f"debug_payloads/rediscover_payload_{timestamp}.json"
                dump_path = os.path.join(os.getcwd(), dump_filename)
                
                try:
                    os.makedirs(os.path.dirname(dump_path), exist_ok=True)
                    with open(dump_path, 'w', encoding='utf-8') as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False, separators=(',', ': '))
                    print(f"✅ DEBUG: Re-Discover payload dumped to: {dump_filename}")
                except Exception as e:
                    print(f"❌ DEBUG: Failed to dump Re-Discover payload: {e}")
            
            
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            
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

                # Validate response structure with index-based approach
                source_track_count = len(candidate_tracks)
                
                if isinstance(response_data, dict) and "track_ids" in response_data:
                    # New format with reasoning - validate structure
                    track_ids = response_data.get("track_ids", [])
                    reasoning = response_data.get("reasoning", "")
                    
                    # Structure checks
                    if not isinstance(track_ids, list):
                        print(f"❌ Response validation failed: track_ids is not a list")
                        raise ValueError("Response structure invalid: track_ids must be a list")
                    
                    if not isinstance(reasoning, str):
                        print(f"❌ Response validation failed: reasoning is not a string")
                        raise ValueError("Response structure invalid: reasoning must be a string")

                    # INDEX-BASED: Validate all track IDs are integers (indices)
                    if not all(isinstance(tid, int) for tid in track_ids):
                        print(f"❌ Response validation failed: not all track_ids are integers")
                        raise ValueError("Invalid track_ids format: all IDs must be integers (indices)")
                    
                    returned_track_count = len(track_ids)
                    
                    # Sanity checks
                    # Check 1: Large source, tiny return
                    if source_track_count >= 100 and returned_track_count <= 10:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: Too few tracks returned from large source set. {error_msg}")
                    
                    # Check 2: Less than 20% returned
                    min_expected = max(1, int(source_track_count * 0.2))  # At least 20% or 1 track
                    if returned_track_count < min_expected:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: Returned tracks less than 20% of source. {error_msg}")
                    
                    # Check 3: More returned than source
                    if returned_track_count > source_track_count:
                        error_msg = f"PAYLOAD ERROR: Received {returned_track_count} tracks but provided {source_track_count} source tracks"
                        print(f"❌ {error_msg}")
                        raise ValueError(f"Sanity check failed: More tracks returned than provided. {error_msg}")
                    
                    # AI validation passed

                    # INDEX-BASED: Map indices back to actual track IDs
                    # Find which indices are invalid (out of range)
                    invalid_indices = [idx for idx in track_ids if idx < 0 or idx >= len(track_id_map)]
                    if invalid_indices:
                        print(f"❌ AI returned {len(invalid_indices)} invalid indices out of {len(track_ids)}")
                    
                    # Map valid indices to actual track IDs
                    valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
                    mapped_track_ids = [track_id_map[idx] for idx in valid_indices]
                    # Mapped indices to track IDs
                    
                    # AI curation successful for Re-Discover Weekly (logging moved to scheduler_logger)
                    if reasoning:
                        # AI reasoning available (logged in main.py scheduler_logger)
                        pass

                    # Final selection (limit to requested count)
                    final_selection = mapped_track_ids[:num_tracks]

                    if include_reasoning:
                        return final_selection, reasoning
                    else:
                        return final_selection

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