"""
Audio Analysis Cache Service
Handles writing and reading cached audio embeddings to/from disk for two-phase scanning.

This service provides:
- Writing batch embeddings to JSONL files
- Reading batch embeddings from disk
- Progress tracking for cached batches
- Manifest management for resumability
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid
import datetime
import numpy as np

logger = logging.getLogger(__name__)

class AudioAnalysisCache:
    """Service for caching audio analysis results to disk"""

    def __init__(self, cache_dir: str = "./cache/audio_analysis"):
        """
        Initialize audio analysis cache

        Args:
            cache_dir: Directory to store cached analysis results
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.cache_dir / "manifest.json"
        self.records_per_file = 100  # Accumulate 100 records per file
        self.pending_records = []  # Buffer for accumulating records
        self.next_file_number = 1  # Track next file number to write

        # Initialize manifest if it doesn't exist
        if not self.manifest_path.exists():
            self._init_manifest()

    def _init_manifest(self) -> Dict[str, Any]:
        """Initialize the cache manifest"""
        manifest = {
            "version": "1.0",
            "session_id": None,
            "total_batches": 0,
            "completed_batches": [],
            "created_at": None,
            "last_updated": None
        }
        self._save_manifest(manifest)
        return manifest

    def _load_manifest(self) -> Dict[str, Any]:
        """Load the cache manifest"""
        try:
            with open(self.manifest_path, 'r') as f:
                data = json.load(f)
                if data is not None and isinstance(data, dict):
                    return data
                else:
                    return self._init_manifest()
        except Exception as e:
            logger.warning(f"Failed to load manifest: {e}")
            return self._init_manifest()

    def _save_manifest(self, manifest: Dict[str, Any]):
        """Save the cache manifest"""
        try:
            with open(self.manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save manifest: {e}")

    def start_session(self, session_id: str):
        """Start a new caching session"""
        manifest = self._load_manifest()
        manifest["session_id"] = session_id
        manifest["total_batches"] = 0
        manifest["completed_batches"] = []
        now = datetime.datetime.now().isoformat()
        manifest["created_at"] = now
        manifest["last_updated"] = now
        self._save_manifest(manifest)
        self.next_file_number = 1  # Reset file numbering
        self.pending_records = []  # Clear any pending records
        logger.info(f"Started cache session: {session_id}")

    def write_batch(self, batch_data: List[Dict[str, Any]], batch_number: int) -> Optional[str]:
        """
        Accumulate analysis results and write to disk when 100 records are reached

        Args:
            batch_data: List of analysis results (track_id, embedding, metadata)
            batch_number: Sequential batch number

        Returns:
            Path to the written batch file if written, None if accumulated
        """
        # Add new records to pending buffer
        self.pending_records.extend(batch_data)

        # Check if we have enough records to write a file
        if len(self.pending_records) >= self.records_per_file:
            # Calculate how many files we can write
            num_files = len(self.pending_records) // self.records_per_file
            written_files = []

            for file_idx in range(num_files):
                start_idx = file_idx * self.records_per_file
                end_idx = start_idx + self.records_per_file
                file_records = self.pending_records[start_idx:end_idx]

                file_number = self.next_file_number
                self.next_file_number += 1
                batch_filename = f"batch_{file_number:03d}.jsonl"
                batch_path = self.cache_dir / batch_filename

                try:
                    with open(batch_path, 'w') as f:
                        for item in file_records:
                            # Convert numpy arrays to lists for JSON serialization
                            serializable_item = {}
                            for key, value in item.items():
                                if hasattr(value, 'tolist'):  # Check if it's a numpy array
                                    serializable_item[key] = value.tolist()
                                else:
                                    serializable_item[key] = value
                            json.dump(serializable_item, f)
                            f.write('\n')

                    written_files.append(str(batch_path))

                    # Update manifest
                    manifest = self._load_manifest()
                    manifest["total_batches"] = max(manifest["total_batches"], file_number)
                    if file_number not in manifest["completed_batches"]:
                        manifest["completed_batches"].append(file_number)
                        manifest["completed_batches"].sort()
                    manifest["last_updated"] = datetime.datetime.now().isoformat()
                    self._save_manifest(manifest)

                    logger.info(f"Written file {file_number} with {len(file_records)} items to {batch_path}")

                except Exception as e:
                    logger.error(f"Failed to write file {file_number}: {e}")
                    raise

            # Remove written records from pending buffer
            self.pending_records = self.pending_records[num_files * self.records_per_file:]

            return written_files[0] if written_files else None

        logger.debug(f"Accumulated {len(self.pending_records)} records, waiting for {self.records_per_file} to write file")
        return None

    def read_batch(self, batch_number: int) -> List[Dict[str, Any]]:
        """
        Read a batch of analysis results from disk

        Args:
            batch_number: Batch number to read

        Returns:
            List of analysis results
        """
        batch_filename = f"batch_{batch_number:03d}.jsonl"
        batch_path = self.cache_dir / batch_filename

        if not batch_path.exists():
            raise FileNotFoundError(f"Batch file not found: {batch_path}")

        try:
            batch_data = []
            with open(batch_path, 'r') as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line.strip())
                        # Convert lists back to numpy arrays for embeddings
                        if 'embedding' in item and isinstance(item['embedding'], list):
                            item['embedding'] = np.array(item['embedding'])
                        batch_data.append(item)

            logger.info(f"Read batch {batch_number} with {len(batch_data)} items from {batch_path}")
            return batch_data

        except Exception as e:
            logger.error(f"Failed to read batch {batch_number}: {e}")
            raise

    def get_completed_batches(self) -> List[int]:
        """Get list of completed batch numbers"""
        manifest = self._load_manifest()
        return sorted(manifest.get("completed_batches", []))

    def get_total_batches(self) -> int:
        """Get total number of batches expected"""
        manifest = self._load_manifest()
        return manifest.get("total_batches", 0)

    def is_batch_completed(self, batch_number: int) -> bool:
        """Check if a specific batch is completed"""
        manifest = self._load_manifest()
        return batch_number in manifest.get("completed_batches", [])

    def get_session_progress(self) -> Dict[str, Any]:
        """Get current session progress information"""
        manifest = self._load_manifest()
        completed = len(manifest.get("completed_batches", []))
        total = manifest.get("total_batches", 0)

        return {
            "session_id": manifest.get("session_id"),
            "completed_batches": completed,
            "total_batches": total,
            "progress_percentage": (completed / total * 100) if total > 0 else 0,
            "is_complete": completed == total and total > 0
        }

    def flush_pending_records(self) -> Optional[str]:
        """
        Flush any remaining pending records to disk

        Returns:
            Path to the written file if any records were written, None otherwise
        """
        if not self.pending_records:
            return None

        # Use next file number
        next_file_number = self.next_file_number
        self.next_file_number += 1

        batch_filename = f"batch_{next_file_number:03d}.jsonl"
        batch_path = self.cache_dir / batch_filename

        try:
            with open(batch_path, 'w') as f:
                for item in self.pending_records:
                    # Convert numpy arrays to lists for JSON serialization
                    serializable_item = {}
                    for key, value in item.items():
                        if hasattr(value, 'tolist'):  # Check if it's a numpy array
                            serializable_item[key] = value.tolist()
                        else:
                            serializable_item[key] = value
                    json.dump(serializable_item, f)
                    f.write('\n')

            # Update manifest
            manifest = self._load_manifest()
            manifest["total_batches"] = max(manifest["total_batches"], next_file_number)
            if next_file_number not in manifest["completed_batches"]:
                manifest["completed_batches"].append(next_file_number)
                manifest["completed_batches"].sort()
            manifest["last_updated"] = datetime.datetime.now().isoformat()
            self._save_manifest(manifest)

            logger.info(f"Flushed {len(self.pending_records)} remaining records to {batch_path}")

            # Clear pending records
            self.pending_records = []

            return str(batch_path)

        except Exception as e:
            logger.error(f"Failed to flush pending records: {e}")
            raise

    def clear_cache(self):
        """Clear all cached data"""
        try:
            for file_path in self.cache_dir.glob("*"):
                if file_path.is_file():
                    file_path.unlink()

            self._init_manifest()
            # Clear pending records
            self.pending_records = []
            logger.info("Cleared audio analysis cache")

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            raise

    def get_cache_size_mb(self) -> float:
        """Get total size of cache in MB"""
        try:
            total_size = 0
            for file_path in self.cache_dir.glob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            return total_size / (1024 * 1024)

        except Exception as e:
            logger.error(f"Failed to calculate cache size: {e}")
            return 0.0


# Global service instance
_audio_analysis_cache = None

def get_audio_analysis_cache() -> AudioAnalysisCache:
    """Get the global audio analysis cache instance"""
    global _audio_analysis_cache
    if _audio_analysis_cache is None:
        _audio_analysis_cache = AudioAnalysisCache()
    return _audio_analysis_cache