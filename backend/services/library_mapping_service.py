"""
Library Mapping Service for Multi-Library Support

Handles discovery of Navidrome libraries and mapping them to filesystem paths.
Provides automatic detection for single libraries and user-guided setup for multi-library.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..database import DatabaseManager
from ..navidrome_client import NavidromeClient

logger = logging.getLogger(__name__)

class LibraryMappingService:
    """Service for managing library-to-filesystem mappings"""

    def __init__(self, db: DatabaseManager, navidrome_client: NavidromeClient):
        self.db = db
        self.navidrome_client = navidrome_client

    async def discover_navidrome_libraries(self) -> List[Dict[str, Any]]:
        """Discover all libraries from Navidrome via getMusicFolders API"""
        logger.info("LibraryMappingService: Starting discovery...")
        try:
            logger.info("LibraryMappingService: Calling navidrome_client.get_music_folders()")
            # Use the client's get_music_folders method which handles authentication and error handling
            libraries = await self.navidrome_client.get_music_folders()
            logger.info(f"LibraryMappingService: SUCCESS - Discovered {len(libraries)} libraries from Navidrome: {[lib['name'] for lib in libraries]}")
            return libraries
        except Exception as e:
            logger.error(f"LibraryMappingService: FAILED - Exception in get_music_folders(): {type(e).__name__}: {e}")
            import traceback
            logger.error(f"LibraryMappingService: Traceback: {traceback.format_exc()}")
            return []

            music_folders = subsonic_response.get("musicFolders", {}).get("musicFolder", [])
            libraries = []

            for folder in music_folders:
                libraries.append({
                    "id": folder["id"],
                    "name": folder["name"]
                })

            logger.info(f"Discovered {len(libraries)} libraries from Navidrome: {[lib['name'] for lib in libraries]}")
            return libraries

        except Exception as e:
            logger.error(f"Failed to discover Navidrome libraries: {e}")
            return []

    async def get_or_create_mappings(self, navidrome_libraries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Get existing mappings or create default ones for discovered libraries"""
        mappings = []

        for library in navidrome_libraries:
            library_id = library["id"]
            library_name = library["name"]

            # Check if mapping already exists
            existing = await self.db.get_library_mapping(library_id)
            if existing:
                mappings.append(existing)
                continue

            # Create default mapping
            default_path = await self._guess_default_path(library_id, library_name, len(navidrome_libraries))
            success = await self.db.upsert_library_mapping(library_id, library_name, default_path)

            if success:
                mapping = await self.db.get_library_mapping(library_id)
                if mapping:
                    mappings.append(mapping)
                    logger.info(f"Created default mapping for {library_name}: {default_path}")

        return mappings

    async def _guess_default_path(self, library_id: str, library_name: str, total_libraries: int) -> str:
        """Guess a default filesystem path for a library"""
        # For single library, use the standard MUSIC_PATH
        if total_libraries == 1:
            return os.getenv("MUSIC_PATH", "/music")

        # For multiple libraries, try common patterns
        # Pattern 1: /music-{library_id}
        candidate1 = f"/music-{library_id}"
        if Path(candidate1).exists():
            return candidate1

        # Pattern 2: /music-{library_name.lower().replace(' ', '-')}
        candidate2 = f"/music-{library_name.lower().replace(' ', '-')}"
        if Path(candidate2).exists():
            return candidate2

        # Pattern 3: Check environment variables
        env_paths = os.getenv("MUSIC_PATHS", "").split(",")
        try:
            library_index = int(library_id) - 1
            if 0 <= library_index < len(env_paths):
                candidate3 = env_paths[library_index].strip()
                if candidate3 and Path(candidate3).exists():
                    return candidate3
        except ValueError:
            pass  # library_id is not a number, skip this pattern

        # Fallback: /music-{library_id} (even if it doesn't exist yet)
        return f"/music-{library_id}"

    async def validate_mappings(self, mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate that all mapped paths exist and are readable"""
        results = {
            "valid": [],
            "invalid": [],
            "all_valid": True
        }

        for mapping in mappings:
            path = mapping["music_path"]
            path_obj = Path(path)

            if path_obj.exists() and path_obj.is_dir():
                # Check if readable
                try:
                    list(path_obj.iterdir())
                    results["valid"].append(mapping)
                    # Update last_verified timestamp
                    await self.db.upsert_library_mapping(
                        mapping["library_id"],
                        mapping["library_name"],
                        mapping["music_path"]
                    )
                except PermissionError:
                    results["invalid"].append({
                        **mapping,
                        "error": "Permission denied"
                    })
                    results["all_valid"] = False
            else:
                results["invalid"].append({
                    **mapping,
                    "error": "Path does not exist"
                })
                results["all_valid"] = False

        return results

    async def setup_library_mappings(self) -> Dict[str, Any]:
        """Complete setup process: discover, map, and validate libraries"""
        logger.info("LibraryMappingService.setup_library_mappings: Starting setup...")

        # Step 1: Discover libraries from Navidrome
        logger.info("LibraryMappingService.setup_library_mappings: Discovering libraries...")
        navidrome_libraries = await self.discover_navidrome_libraries()
        logger.info(f"LibraryMappingService.setup_library_mappings: Discovered {len(navidrome_libraries)} libraries")
        if not navidrome_libraries:
            return {
                "success": False,
                "error": "Could not discover any libraries from Navidrome. Please check that Navidrome is running and accessible, and that your NAVIDROME_URL, NAVIDROME_USERNAME, and NAVIDROME_PASSWORD environment variables are correctly configured."
            }

        # For single library, auto-setup without user confirmation
        if len(navidrome_libraries) == 1:
            logger.info("Single library detected - auto-setting up mapping")
            library = navidrome_libraries[0]
            default_path = await self._guess_default_path(library["id"], library["name"], 1)

            # Create and validate the mapping
            success = await self.db.upsert_library_mapping(library["id"], library["name"], default_path)
            if success:
                mapping = await self.db.get_library_mapping(library["id"])
                validation = await self.validate_mappings([mapping] if mapping else [])

                return {
                    "success": validation["all_valid"],
                    "navidrome_libraries": navidrome_libraries,
                    "mappings": [mapping] if mapping else [],
                    "validation": validation,
                    "auto_setup": True,
                    "message": f"Single library '{library['name']}' auto-mapped to {default_path}"
                }

        # Step 2: Get or create mappings (for multiple libraries)
        mappings = await self.get_or_create_mappings(navidrome_libraries)

        # Step 3: Validate mappings
        validation = await self.validate_mappings(mappings)

        result = {
            "success": validation["all_valid"],
            "navidrome_libraries": navidrome_libraries,
            "mappings": mappings,
            "validation": validation,
            "auto_setup": False
        }

        if validation["all_valid"]:
            logger.info(f"✅ Library mapping setup completed successfully for {len(mappings)} libraries")
        else:
            logger.warning(f"⚠️ Library mapping setup completed with issues. {len(validation['invalid'])} paths need attention")

        return result

    async def get_music_path_for_library(self, library_id: str) -> Optional[str]:
        """Get the validated music path for a library ID"""
        return await self.db.get_music_path_for_library(library_id)

    async def update_mapping(self, library_id: str, music_path: str) -> bool:
        """Update the music path for a library mapping"""
        mapping = await self.db.get_library_mapping(library_id)
        if not mapping:
            return False

        return await self.db.upsert_library_mapping(library_id, mapping["library_name"], music_path)