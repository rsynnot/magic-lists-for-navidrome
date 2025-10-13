import os
import httpx
import asyncio
from typing import Dict, List, Any


class HealthCheckService:
    """Service to perform startup system checks for MagicLists application"""
    
    def __init__(self):
        self.timeout = 10.0
        
    async def run_checks(self) -> Dict[str, Any]:
        """Run all system health checks
        
        Returns:
            Dict containing all_passed status and list of check results
        """
        checks = []
        all_passed = True
        
        # Run checks in order
        env_check = await self._check_environment_variables()
        checks.append(env_check)
        if env_check["status"] == "error":
            all_passed = False
            
        url_check = await self._check_navidrome_url_reachable()
        checks.append(url_check)
        if url_check["status"] == "error":
            all_passed = False
            
        auth_check = await self._check_navidrome_authentication()
        checks.append(auth_check)
        if auth_check["status"] == "error":
            all_passed = False
            
        artists_check = await self._check_navidrome_artists_api()
        checks.append(artists_check)
        if artists_check["status"] == "error":
            all_passed = False
            
        openrouter_check = await self._check_openrouter_api_key()
        checks.append(openrouter_check)
        if openrouter_check["status"] == "error":
            all_passed = False
            
        # MULTIPLE LIBRARIES FIX: Check for library configuration
        library_check = await self._check_navidrome_library_config()
        checks.append(library_check)
        # Library config is informational only, don't fail on it
            
        # Track Umami events
        await self._track_umami_events(all_passed, checks)
        
        return {
            "all_passed": all_passed,
            "checks": checks
        }
    
    async def _check_environment_variables(self) -> Dict[str, str]:
        """Check that required environment variables are present"""
        required_vars = ["NAVIDROME_URL", "NAVIDROME_USERNAME", "NAVIDROME_PASSWORD"]
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            return {
                "name": "Environment Variables Present",
                "status": "error",
                "message": f"Missing required environment variables: {', '.join(missing_vars)}",
                "suggestion": "Add the missing environment variables to your .env file"
            }
        else:
            return {
                "name": "Environment Variables Present",
                "status": "success", 
                "message": "All required environment variables are present",
                "suggestion": ""
            }
    
    async def _check_navidrome_url_reachable(self) -> Dict[str, str]:
        """Check if Navidrome URL is reachable"""
        navidrome_url = os.getenv("NAVIDROME_URL")
        
        if not navidrome_url:
            return {
                "name": "Navidrome URL Reachable",
                "status": "error",
                "message": "NAVIDROME_URL environment variable not set",
                "suggestion": "Set NAVIDROME_URL in your .env file"
            }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(navidrome_url)
                response.raise_for_status()
                
            return {
                "name": "Navidrome URL Reachable",
                "status": "success",
                "message": f"Successfully connected to {navidrome_url}",
                "suggestion": ""
            }
            
        except httpx.ConnectError:
            return {
                "name": "Navidrome URL Reachable", 
                "status": "error",
                "message": f"Could not connect to {navidrome_url}. Check your .env file and Docker networking.",
                "suggestion": "If running in Docker, try using the container name (e.g., 'navidrome:4533') instead of 'localhost'. Ensure containers are on the same network."
            }
        except httpx.TimeoutException:
            return {
                "name": "Navidrome URL Reachable",
                "status": "error", 
                "message": f"Connection to {navidrome_url} timed out after {self.timeout} seconds",
                "suggestion": "If running in Docker, try using the container name (e.g., 'navidrome:4533') instead of 'localhost'. Ensure containers are on the same network."
            }
        except Exception as e:
            return {
                "name": "Navidrome URL Reachable",
                "status": "error",
                "message": f"Error connecting to {navidrome_url}: {str(e)}",
                "suggestion": "If running in Docker, try using the container name (e.g., 'navidrome:4533') instead of 'localhost'. Ensure containers are on the same network."
            }
    
    async def _check_navidrome_authentication(self) -> Dict[str, str]:
        """Check if Navidrome authentication works"""
        navidrome_url = os.getenv("NAVIDROME_URL")
        username = os.getenv("NAVIDROME_USERNAME")
        password = os.getenv("NAVIDROME_PASSWORD")
        
        if not all([navidrome_url, username, password]):
            return {
                "name": "Navidrome Authentication",
                "status": "error",
                "message": "Missing authentication credentials",
                "suggestion": "Verify username and password are correct in your .env file"
            }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{navidrome_url}/auth/login",
                    json={"username": username, "password": password}
                )
                response.raise_for_status()
                
                data = response.json()
                if data.get("token"):
                    return {
                        "name": "Navidrome Authentication",
                        "status": "success",
                        "message": "Successfully authenticated with Navidrome",
                        "suggestion": ""
                    }
                else:
                    return {
                        "name": "Navidrome Authentication",
                        "status": "error",
                        "message": "Authentication succeeded but no token received",
                        "suggestion": "Verify username and password are correct in your .env file"
                    }
                    
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return {
                    "name": "Navidrome Authentication",
                    "status": "error",
                    "message": "Invalid username or password. Check your .env file credentials.",
                    "suggestion": "Verify NAVIDROME_USERNAME and NAVIDROME_PASSWORD are correct in your .env file"
                }
            else:
                return {
                    "name": "Navidrome Authentication", 
                    "status": "error",
                    "message": f"Authentication failed with status {e.response.status_code}",
                    "suggestion": "Verify username and password are correct in your .env file"
                }
        except Exception as e:
            return {
                "name": "Navidrome Authentication",
                "status": "error",
                "message": f"Authentication error: {str(e)}",
                "suggestion": "Verify username and password are correct in your .env file"
            }
    
    async def _check_navidrome_artists_api(self) -> Dict[str, str]:
        """Check if Navidrome Artists API works"""
        navidrome_url = os.getenv("NAVIDROME_URL")
        username = os.getenv("NAVIDROME_USERNAME") 
        password = os.getenv("NAVIDROME_PASSWORD")
        
        if not all([navidrome_url, username, password]):
            return {
                "name": "Navidrome Artists API",
                "status": "error",
                "message": "Missing authentication credentials for API test",
                "suggestion": "This may be a Navidrome library configuration issue. Check Navidrome logs for 'Library not found' errors."
            }
        
        try:
            # First authenticate to get token
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                auth_response = await client.post(
                    f"{navidrome_url}/auth/login",
                    json={"username": username, "password": password}
                )
                auth_response.raise_for_status()
                
                auth_data = auth_response.json()
                subsonic_token = auth_data.get("subsonicToken")
                subsonic_salt = auth_data.get("subsonicSalt")
                
                if not subsonic_token or not subsonic_salt:
                    return {
                        "name": "Navidrome Artists API",
                        "status": "error",
                        "message": "No Subsonic credentials received from login",
                        "suggestion": "This may be a Navidrome library configuration issue. Check Navidrome logs for 'Library not found' errors."
                    }
                
                # Test getArtists API
                params = {
                    "u": username,
                    "t": subsonic_token,
                    "s": subsonic_salt,
                    "v": "1.16.1",
                    "c": "MagicLists",
                    "f": "json"
                }
                
                response = await client.get(
                    f"{navidrome_url}/rest/getArtists.view",
                    params=params
                )
                response.raise_for_status()
                
                data = response.json()
                subsonic_response = data.get("subsonic-response", {})
                
                if subsonic_response.get("status") == "ok":
                    artists_data = subsonic_response.get("artists", {})
                    artist_count = sum(len(index_group.get("artist", [])) for index_group in artists_data.get("index", []))
                    
                    return {
                        "name": "Navidrome Artists API",
                        "status": "success",
                        "message": f"Successfully fetched artists data ({artist_count} artists found)",
                        "suggestion": ""
                    }
                else:
                    error = subsonic_response.get("error", {})
                    error_message = error.get('message', 'Unknown error')
                    
                    # MULTIPLE LIBRARIES FIX: Handle "Library not found" as warning
                    if "Library not found" in error_message or "empty" in error_message.lower():
                        return {
                            "name": "Navidrome Artists API",
                            "status": "warning",
                            "message": f"Library issue detected: {error_message}",
                            "suggestion": "Your Navidrome instance has multiple libraries. MagicLists will attempt to work with all available libraries."
                        }
                    else:
                        return {
                            "name": "Navidrome Artists API",
                            "status": "error", 
                            "message": f"Subsonic API error: {error_message}",
                            "suggestion": "This may be a Navidrome library configuration issue. Check Navidrome logs for 'Library not found' errors."
                        }
                    
        except Exception as e:
            return {
                "name": "Navidrome Artists API",
                "status": "error",
                "message": f"Artists API error: {str(e)}",
                "suggestion": "This may be a Navidrome library configuration issue. Check Navidrome logs for 'Library not found' errors."
            }
    
    async def _check_openrouter_api_key(self) -> Dict[str, str]:
        """Check if OpenRouter API key is present"""
        api_key = os.getenv("AI_API_KEY")  # Following existing pattern from ai_client.py
        
        if not api_key:
            return {
                "name": "OpenRouter API Key Present",
                "status": "warning",
                "message": "AI_API_KEY environment variable not set - AI features will use fallback algorithms",
                "suggestion": "Set AI_API_KEY in your .env file to enable AI-powered playlist curation"
            }
        else:
            return {
                "name": "OpenRouter API Key Present", 
                "status": "success",
                "message": "AI API key is configured",
                "suggestion": ""
            }
    
    async def _check_navidrome_library_config(self) -> Dict[str, str]:
        """Check if Navidrome library configuration is present"""
        library_id = os.getenv("NAVIDROME_LIBRARY_ID")
        
        if library_id:
            return {
                "name": "Navidrome Library Configuration",
                "status": "info",
                "message": f"Using specific library ID: {library_id}",
                "suggestion": ""
            }
        else:
            return {
                "name": "Navidrome Library Configuration", 
                "status": "info",
                "message": "Using automatic library detection",
                "suggestion": "For multiple libraries: Set NAVIDROME_LIBRARY_ID in your .env file if you want to target a specific library"
            }
    
    async def _track_umami_events(self, all_passed: bool, checks: List[Dict[str, str]]):
        """Track Umami events for system check results"""
        # Note: Actual Umami tracking happens client-side in JavaScript
        # This is just for logging the events that should be tracked
        
        if all_passed:
            print("📊 Umami event: system_check_all_passed")
        else:
            # Check for specific failures
            for check in checks:
                if check["status"] == "error":
                    if "URL Reachable" in check["name"]:
                        print("📊 Umami event: system_check_failed_url")
                    elif "Authentication" in check["name"]:
                        print("📊 Umami event: system_check_failed_auth") 
                    elif "Artists API" in check["name"]:
                        print("📊 Umami event: system_check_failed_artists")