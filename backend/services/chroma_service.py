"""
ChromaDB service for audio embedding storage and similarity search.

This service provides:
- Persistent vector storage using ChromaDB
- Audio embedding storage and retrieval
- Similarity search for finding similar tracks
- Collection management for different embedding types
"""

import os
import logging
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class ChromaService:
    """Service for managing audio embeddings with ChromaDB"""

    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        Initialize ChromaDB service

        Args:
            persist_directory: Directory to persist ChromaDB data
        """
        # Use absolute path to avoid any path issues
        if not os.path.isabs(persist_directory):
            self.persist_directory = os.path.abspath(persist_directory)
        else:
            self.persist_directory = persist_directory

        self.persist_directory = persist_directory
        self.collection_name = "audio_embeddings"  # Default collection name
        self.client = None
        self.collection = None
        self._ensure_initialized()

    def _ensure_initialized(self):
        """Ensure ChromaDB client and collection are initialized"""
        if self.client is None:
            try:
                logger.info(f"Initializing ChromaDB with persist directory: {self.persist_directory}")
                # Ensure persist directory exists
                os.makedirs(self.persist_directory, exist_ok=True)

                # Create client - try different approaches
                try:
                    self.client = chromadb.PersistentClient(
                        path=self.persist_directory,
                        settings=Settings(allow_reset=True)  # Allow reset for empty databases
                    )
                    logger.info("Created ChromaDB persistent client")
                except Exception as client_error:
                    logger.warning(f"Failed to create persistent client: {client_error}, trying ephemeral client")
                    self.client = chromadb.EphemeralClient()
                    logger.info("Created ChromaDB ephemeral client")

                # Get or create collection using self.collection_name
                try:
                    # Try to create the collection (this will fail if it already exists)
                    self.collection = self.client.create_collection(name=self.collection_name)
                    logger.info(f"Created new ChromaDB collection: {self.collection_name}")
                except Exception as e:
                    error_msg = str(e).lower()
                    if "already exists" in error_msg or "exists" in error_msg:
                        # Collection already exists, get it
                        try:
                            self.collection = self.client.get_collection(name=self.collection_name)
                            logger.info(f"Loaded existing ChromaDB collection: {self.collection_name}")
                        except Exception as get_error:
                            logger.error(f"Failed to get existing collection {self.collection_name}: {get_error}")
                            # For database errors, set collection to None and continue
                            if "no such table" in str(get_error).lower() or "database error" in str(get_error).lower():
                                logger.warning("ChromaDB database tables missing, collection will be None")
                                self.collection = None
                            else:
                                raise
                    else:
                        # Check if it's a database error
                        if "no such table" in error_msg or "database error" in error_msg:
                            logger.warning("ChromaDB database not initialized, collection will be None")
                            self.collection = None
                        else:
                            # Some other error
                            logger.error(f"Failed to create collection {self.collection_name}: {e}")
                            raise

            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB: {e}")
                raise

    def store_embedding(self, track_id: str, embedding: np.ndarray, metadata: Dict[str, Any]) -> bool:
        """
        Store an audio embedding for a track

        Args:
            track_id: Unique track identifier
            embedding: Audio embedding vector
            metadata: Additional track metadata

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return False

            # Convert embedding to list for ChromaDB
            embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else embedding

            # Check if embedding dimension matches collection expectation
            try:
                # Try to add the embedding - this will fail if dimensions don't match
                test_collection = self.client.get_collection(self.collection.name)
                # If we get here, the collection exists, let's try the add operation
            except Exception:
                pass

            # Prepare metadata
            chroma_metadata = {
                "track_id": track_id,
                "title": metadata.get("title", ""),
                "artist": metadata.get("artist", ""),
                "album": metadata.get("album", ""),
                "genre": metadata.get("genre", ""),
                "duration": str(metadata.get("duration", 0)),
                "year": str(metadata.get("year", 0)),
                "navidrome_id": metadata.get("navidrome_id", ""),
                "library_id": metadata.get("library_id", "")  # NEW: include library_id for filtering
            }

            # Remove None values and convert to strings
            chroma_metadata = {k: str(v) for k, v in chroma_metadata.items() if v is not None}

            # Store in ChromaDB
            self.collection.add(
                ids=[track_id],
                embeddings=[embedding_list],
                metadatas=[chroma_metadata]
            )

            logger.debug(f"Stored embedding for track: {track_id}")
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if "dimension" in error_msg and ("64" in error_msg or "72" in error_msg):
                logger.warning(f"Dimension mismatch detected ({e}), attempting to recreate collection")
                try:
                    # Delete and recreate the collection
                    collection_name = self.collection.name
                    self.client.delete_collection(name=collection_name)
                    self.collection = self.client.create_collection(name=collection_name)
                    logger.info(f"Recreated ChromaDB collection: {collection_name}")

                    # Retry the storage
                    self.collection.add(
                        ids=[track_id],
                        embeddings=[embedding_list],
                        metadatas=[chroma_metadata]
                    )
                    logger.info(f"Successfully stored embedding after collection recreation: {track_id}")
                    return True

                except Exception as recreate_error:
                    logger.error(f"Failed to recreate collection and store embedding: {recreate_error}")
                    return False
            else:
                logger.error(f"Failed to store embedding for track {track_id}: {e}")
                return False

    def get_embedding(self, track_id: str) -> Optional[Tuple[np.ndarray, Dict[str, Any]]]:
        """
        Retrieve an embedding and metadata for a track

        Args:
            track_id: Track identifier

        Returns:
            Tuple of (embedding, metadata) or None if not found
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return None

            result = self.collection.get(
                ids=[track_id],
                include=['embeddings', 'metadatas']
            )

            # Check if the track_id exists in results
            if result['ids'] and track_id in result['ids']:
                idx = result['ids'].index(track_id)
                if (result['embeddings'] is not None and len(result['embeddings']) > idx and result['embeddings'][idx] is not None and
                    result['metadatas'] is not None and len(result['metadatas']) > idx):
                    embedding = result['embeddings'][idx] if isinstance(result['embeddings'][idx], np.ndarray) else np.array(result['embeddings'][idx])
                    raw_metadata = result['metadatas'][idx]
                    if isinstance(raw_metadata, dict):
                        metadata = dict(raw_metadata)
                    else:
                        # Fallback if metadata is not a dict
                        metadata = {}
                    return embedding, metadata

            return None

        except Exception as e:
            logger.error(f"Failed to retrieve embedding for track {track_id}: {e}")
            return None

    def track_exists(self, track_id: str) -> bool:
        """
        Check if a track exists in the collection

        Args:
            track_id: Track identifier

        Returns:
            True if track exists, False otherwise
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return False

            result = self.collection.get(ids=[track_id], include=[])
            return track_id in result['ids']

        except Exception as e:
            logger.error(f"Failed to check if track {track_id} exists: {e}")
            return False

    def find_similar_tracks(self, query_embedding: np.ndarray, n_results: int = 25,
                           exclude_track_ids: Optional[List[str]] = None, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find tracks similar to the query embedding

        Args:
            query_embedding: Query embedding vector
            n_results: Number of similar tracks to return
            exclude_track_ids: Track IDs to exclude from results
            library_id: Library ID to filter results (optional)

        Returns:
            List of similar tracks with metadata and similarity scores
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return []

            # Convert to list for ChromaDB
            query_list = query_embedding.tolist() if isinstance(query_embedding, np.ndarray) else query_embedding

            # Build where clause for library filtering
            where_clause = {}
            if library_id:
                where_clause["library_id"] = library_id

            # Query for similar tracks
            results = self.collection.query(
                query_embeddings=[query_list],
                n_results=n_results + (len(exclude_track_ids) if exclude_track_ids else 0),
                where=where_clause if where_clause else None,
                include=['distances', 'metadatas']
            )

            # Process results
            similar_tracks = []
            if results['ids'] and results['distances'] and results['metadatas']:
                for i, track_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i]
                    metadata = results['metadatas'][0][i]

                    # Skip if this track was in exclude list (double check)
                    if exclude_track_ids and track_id in exclude_track_ids:
                        continue

                    # Convert distance to similarity score (lower distance = higher similarity)
                    similarity_score = 1.0 / (1.0 + distance)

                    # Handle metadata - ensure it's a dict
                    if isinstance(metadata, dict):
                        title = metadata.get("title", "")
                        artist = metadata.get("artist", "")
                        album = metadata.get("album", "")
                        genre = metadata.get("genre", "")
                        duration = metadata.get("duration", "0")
                        year = metadata.get("year", "0")
                    else:
                        # Fallback if metadata is not a dict (e.g., stored as list)
                        title = "Unknown"
                        artist = "Unknown"
                        album = "Unknown"
                        genre = "Unknown"
                        duration = "0"
                        year = "0"

                    track_info = {
                        "track_id": track_id,
                        "similarity_score": similarity_score,
                        "title": title,
                        "artist": artist,
                        "album": album,
                        "genre": genre,
                        "duration": duration,
                        "year": year
                    }

                    similar_tracks.append(track_info)

                    # Stop when we have enough results
                    if len(similar_tracks) >= n_results:
                        break

            logger.debug(f"Found {len(similar_tracks)} similar tracks")
            return similar_tracks

        except Exception as e:
            logger.error(f"Failed to find similar tracks: {e}")
            return []

    def get_all_embeddings(self) -> List[Dict[str, Any]]:
        """
        Get all embeddings from the collection with their metadata.

        Returns:
            List of dictionaries containing id, embedding, and metadata
        """
        try:
            self._ensure_initialized()

            if not self.collection:
                logger.info("ChromaDB collection not available (likely empty database)")
                return []

            # Get all data from the collection
            results = self.collection.get(include=["embeddings", "metadatas"])

            embeddings_data = []
            if results and results.get("ids"):
                ids = results.get("ids", [])
                embeddings = results.get("embeddings", [])
                metadatas = results.get("metadatas", [])

                # Ensure lists are not None
                if ids is None:
                    ids = []
                if embeddings is None:
                    embeddings = []
                if metadatas is None:
                    metadatas = []

                for i, track_id in enumerate(ids):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    # Only include tracks that have actual embeddings (not None)
                    if i < len(embeddings) and embeddings[i] is not None:
                        embeddings_data.append({
                            "id": track_id,
                            "metadata": metadata
                        })

            return embeddings_data

        except Exception as e:
            error_msg = str(e).lower()
            if "no such table" in error_msg or "database error" in error_msg:
                logger.info("ChromaDB database not initialized yet, returning empty results")
                return []
            elif "hnsw segment reader" in error_msg or "nothing found on disk" in error_msg:
                # Only treat as corruption if we actually have data that should be there
                # Check if collection exists and has been used recently
                try:
                    count = self.collection.count() if self.collection else 0
                    if count > 0:
                        logger.warning(f"ChromaDB index corruption detected (collection has {count} items), attempting to rebuild: {e}")
                        # Try to rebuild the collection by clearing and reinitializing
                        try:
                            self._rebuild_corrupted_collection()
                            logger.info("Successfully rebuilt corrupted ChromaDB collection")
                            return []
                        except Exception as rebuild_error:
                            logger.error(f"Failed to rebuild corrupted collection: {rebuild_error}")
                            return []
                    else:
                        # Empty collection, not corruption
                        logger.info("ChromaDB collection appears empty, no corruption detected")
                        return []
                except Exception as count_error:
                    logger.warning(f"Could not check collection count during error handling: {count_error}")
                    return []
            logger.error(f"Failed to get all embeddings: {e}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the ChromaDB collection"""
        try:
            self._ensure_initialized()
            if not self.collection:
                return {
                    "total_embeddings": 0,
                    "collection_name": "audio_embeddings",
                    "persist_directory": self.persist_directory,
                    "status": "not_initialized"
                }
            count = self.collection.count()
            return {
                "total_embeddings": count,
                "collection_name": self.collection.name,
                "persist_directory": self.persist_directory
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "no such table" in error_msg or "database error" in error_msg:
                logger.info("ChromaDB database not initialized yet, returning empty stats")
                return {
                    "total_embeddings": 0,
                    "collection_name": "audio_embeddings",
                    "persist_directory": self.persist_directory,
                    "status": "not_initialized"
                }
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}

    def delete_embedding(self, track_id: str) -> bool:
        """
        Delete an embedding for a track

        Args:
            track_id: Track identifier to delete

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return False

            self.collection.delete(ids=[track_id])
            logger.debug(f"Deleted embedding for track: {track_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete embedding for track {track_id}: {e}")
            return False

    def switch_collection(self, collection_name: str):
        """
        Switch to a different collection.

        Args:
            collection_name: Name of the collection to switch to
        """
        logger.info(f"🔄 Switching from {self.collection_name} to {collection_name}")
        self.collection_name = collection_name
        
        # Ensure client is initialized
        if not self.client:
            self._ensure_initialized()
        
        # Directly get the collection (it should exist already)
        try:
            self.collection = self.client.get_collection(name=collection_name)
            logger.info(f"📦 Switched to collection: {collection_name}, count: {self.collection.count()}")
        except Exception as e:
            logger.error(f"Failed to switch to collection {collection_name}: {e}")
            self.collection = None

    def clear_collection(self) -> bool:
        """
        Clear all embeddings from the collection

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return False

            # Get all IDs and delete them
            all_ids = self.collection.get(include=[])['ids']
            if all_ids:
                self.collection.delete(ids=all_ids)

            logger.info(f"Cleared {len(all_ids)} embeddings from collection")
            return True

        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            return False

    def _rebuild_corrupted_collection(self):
        """Rebuild a corrupted ChromaDB collection"""
        try:
            collection_name = "audio_embeddings"

            # Try to delete the corrupted collection
            try:
                self.client.delete_collection(name=collection_name)
                logger.info(f"Deleted corrupted collection: {collection_name}")
            except Exception as e:
                logger.warning(f"Could not delete corrupted collection: {e}")

            # Create a new collection
            self.collection = self.client.create_collection(name=collection_name)
            logger.info(f"Created new collection after corruption: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to rebuild corrupted collection: {e}")
            raise

    def verify_ingestion(self, expected_track_ids: List[str]) -> Dict[str, Any]:
        """
        Verify that tracks were successfully ingested into ChromaDB.

        Args:
            expected_track_ids: List of track IDs that should be in the database

        Returns:
            Dictionary with verification results
        """
        try:
            self._ensure_initialized()
            if not self.collection:
                return {
                    "success": False,
                    "error": "Collection not available",
                    "expected_count": len(expected_track_ids),
                    "actual_count": 0,
                    "missing_tracks": expected_track_ids,
                    "extra_tracks": []
                }

            # Get current collection stats
            actual_count = self.collection.count()

            # Check which tracks are actually present
            present_tracks = set()
            missing_tracks = []

            for track_id in expected_track_ids:
                if self.track_exists(track_id):
                    present_tracks.add(track_id)
                else:
                    missing_tracks.append(track_id)

            # Check for unexpected tracks (though this is less critical)
            all_ids = set(self.collection.get(include=[])['ids'])
            extra_tracks = list(all_ids - present_tracks)

            success = len(missing_tracks) == 0

            result = {
                "success": success,
                "expected_count": len(expected_track_ids),
                "actual_count": actual_count,
                "present_count": len(present_tracks),
                "missing_tracks": missing_tracks,
                "extra_tracks": extra_tracks
            }

            if success:
                logger.info(f"✅ Ingestion verification successful: {len(present_tracks)}/{len(expected_track_ids)} tracks verified")
            else:
                logger.warning(f"❌ Ingestion verification failed: {len(missing_tracks)} missing tracks out of {len(expected_track_ids)}")

            return result

        except Exception as e:
            logger.error(f"Failed to verify ingestion: {e}")
            return {
                "success": False,
                "error": str(e),
                "expected_count": len(expected_track_ids),
                "actual_count": 0,
                "missing_tracks": expected_track_ids,
                "extra_tracks": []
            }

    def close(self):
        """Close the ChromaDB client"""
        # ChromaDB handles persistence automatically, no explicit close needed
        pass


# Global service instance
_chroma_service = None

def get_chroma_service() -> ChromaService:
    """Get the global ChromaDB service instance"""
    global _chroma_service
    if _chroma_service is None:
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        _chroma_service = ChromaService(persist_directory=persist_dir)
    return _chroma_service