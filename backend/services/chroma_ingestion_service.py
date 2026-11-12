"""
Chroma Ingestion Service
Handles Phase 2 of two-phase scanning: ingesting cached audio embeddings into ChromaDB.

This service provides:
- Batch ingestion from cached JSONL files
- Memory-efficient processing with configurable batch sizes
- Progress tracking and resumability
- Error handling and recovery
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings

from ..services.audio_analysis_cache import get_audio_analysis_cache

logger = logging.getLogger(__name__)

class ChromaIngestionService:
    """Service for ingesting cached audio embeddings into ChromaDB"""

    def __init__(self, chroma_path: str = "./chroma_db", collection_name: str = "audio_embeddings"):
        """
        Initialize Chroma ingestion service

        Args:
            chroma_path: Path to ChromaDB persistence directory
            collection_name: Name of the ChromaDB collection
        """
        self.chroma_path = Path(chroma_path)
        self.collection_name = collection_name
        self.cache_service = get_audio_analysis_cache()

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_path),
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )

        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
            logger.info(f"Using existing ChromaDB collection: {collection_name}")
        except ValueError:
            self.collection = self.client.create_collection(name=collection_name)
            logger.info(f"Created new ChromaDB collection: {collection_name}")

    def ingest_batch(self, batch_number: int, write_batch_size: int = 100) -> Dict[str, Any]:
        """
        Ingest a single batch from cache into ChromaDB

        Args:
            batch_number: Batch number to ingest
            write_batch_size: Number of embeddings to write at once

        Returns:
            Dict with ingestion results
        """
        try:
            # Read batch data from cache
            batch_data = self.cache_service.read_batch(batch_number)

            if not batch_data:
                logger.warning(f"Batch {batch_number} is empty, skipping")
                return {"batch_number": batch_number, "ingested_count": 0, "errors": []}

            # Prepare data for ChromaDB
            ids = []
            embeddings = []
            metadatas = []
            documents = []

            errors = []

            for item in batch_data:
                try:
                    track_id = item.get("track_id")
                    embedding = item.get("embedding")
                    metadata = item.get("metadata", {})

                    if not track_id or embedding is None or len(embedding) == 0:
                        errors.append(f"Missing track_id or embedding in item: {item}")
                        continue

                    # Check if this navidrome_id already exists in ChromaDB
                    navidrome_id = metadata.get("navidrome_id")
                    if navidrome_id:
                        # Query ChromaDB for existing tracks with this navidrome_id
                        existing_results = self.collection.get(
                            where={"navidrome_id": str(navidrome_id)},
                            include=[]
                        )
                        if existing_results.get("ids"):
                            logger.info(f"Skipping duplicate track {track_id} (navidrome_id: {navidrome_id}) - already exists in ChromaDB")
                            continue

                    # Clean metadata: remove None values and convert to strings
                    clean_metadata = {}
                    for key, value in metadata.items():
                        if value is not None:
                            clean_metadata[key] = str(value)

                    ids.append(str(track_id))
                    embeddings.append(embedding)
                    metadatas.append(clean_metadata)
                    documents.append(clean_metadata.get("title", f"Track {track_id}"))

                except Exception as e:
                    errors.append(f"Error processing item: {e}")
                    continue

            # Ingest in batches to manage memory
            total_ingested = 0
            for i in range(0, len(ids), write_batch_size):
                end_idx = min(i + write_batch_size, len(ids))

                batch_ids = ids[i:end_idx]
                batch_embeddings = embeddings[i:end_idx]
                batch_metadatas = metadatas[i:end_idx]
                batch_documents = documents[i:end_idx]

                try:
                    self.collection.add(
                        ids=batch_ids,
                        embeddings=batch_embeddings,
                        metadatas=batch_metadatas,
                        documents=batch_documents
                    )
                    total_ingested += len(batch_ids)
                    logger.debug(f"Ingested sub-batch {i//write_batch_size + 1} of batch {batch_number}")

                except Exception as e:
                    logger.error(f"Failed to ingest sub-batch {i//write_batch_size + 1} of batch {batch_number}: {e}")
                    errors.append(f"Sub-batch ingestion error: {e}")

            logger.info(f"Successfully ingested batch {batch_number}: {total_ingested} embeddings")
            return {
                "batch_number": batch_number,
                "ingested_count": total_ingested,
                "errors": errors
            }

        except Exception as e:
            logger.error(f"Failed to ingest batch {batch_number}: {e}")
            return {
                "batch_number": batch_number,
                "ingested_count": 0,
                "errors": [str(e)]
            }

    def ingest_all_cached_batches(self, write_batch_size: int = 100) -> Dict[str, Any]:
        """
        Ingest all completed cached batches into ChromaDB

        Args:
            write_batch_size: Number of embeddings to write at once

        Returns:
            Dict with overall ingestion results
        """
        completed_batches = self.cache_service.get_completed_batches()

        if not completed_batches:
            logger.warning("No completed batches found in cache")
            return {"total_batches": 0, "successful_batches": 0, "total_ingested": 0, "errors": []}

        logger.info(f"Starting ingestion of {len(completed_batches)} cached batches")

        total_ingested = 0
        successful_batches = 0
        all_errors = []

        for batch_num in completed_batches:
            result = self.ingest_batch(batch_num, write_batch_size)
            total_ingested += result["ingested_count"]
            all_errors.extend(result["errors"])

            if result["ingested_count"] > 0:
                successful_batches += 1

        logger.info(f"Ingestion complete: {successful_batches}/{len(completed_batches)} batches, {total_ingested} total embeddings")

        return {
            "total_batches": len(completed_batches),
            "successful_batches": successful_batches,
            "total_ingested": total_ingested,
            "errors": all_errors
        }

    def get_ingestion_progress(self) -> Dict[str, Any]:
        """
        Get current ingestion progress

        Returns:
            Dict with progress information
        """
        cache_progress = self.cache_service.get_session_progress()

        # Count current embeddings in ChromaDB
        try:
            chroma_count = self.collection.count()
        except Exception as e:
            logger.warning(f"Failed to get ChromaDB count: {e}")
            chroma_count = 0

        return {
            "cache_progress": cache_progress,
            "chroma_embeddings_count": chroma_count,
            "is_ingestion_complete": chroma_count >= cache_progress.get("completed_batches", 0) * 100  # Rough estimate
        }

    def clear_collection(self):
        """Clear all data from the ChromaDB collection"""
        try:
            # Delete and recreate collection
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(name=self.collection_name)
            logger.info(f"Cleared ChromaDB collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Failed to clear collection: {e}")
            raise


# Global service instance
_chroma_ingestion_service = None

def get_chroma_ingestion_service() -> ChromaIngestionService:
    """Get the global Chroma ingestion service instance"""
    global _chroma_ingestion_service
    if _chroma_ingestion_service is None:
        _chroma_ingestion_service = ChromaIngestionService()
    return _chroma_ingestion_service