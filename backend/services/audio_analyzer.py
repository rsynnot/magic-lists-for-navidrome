"""
Audio analysis service using Librosa for extracting features from audio files.

This service provides:
- Audio feature extraction (MFCC, chroma, spectral contrast, etc.)
- Embedding generation for similarity comparison
- Batch processing capabilities
- Error handling for corrupted files
"""

import os
import logging
import gc
import warnings
import sys
from contextlib import redirect_stderr, redirect_stdout
import librosa
import numpy as np
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import psutil
import io

logger = logging.getLogger(__name__)

# Note: mpg123 warnings about malformed ID3 tags are common and harmless
# They indicate files with corrupted or missing metadata, not processing errors
# These warnings don't affect the audio analysis results

class AudioAnalyzer:
    """Service for analyzing audio files and extracting embeddings"""

    def __init__(self, sample_rate: int = 22050, n_mfcc: int = 13):
        """
        Initialize audio analyzer

        Args:
            sample_rate: Target sample rate for audio processing
            n_mfcc: Number of MFCC coefficients to extract
        """
        self.sample_rate = sample_rate
        self.n_mfcc = n_mfcc

        # Memory and file size limits from environment
        self.max_file_size_mb = int(os.getenv('MAX_FILE_SIZE_MB', '65'))
        self.memory_threshold_percent = int(os.getenv('MEMORY_THRESHOLD_PERCENT', '75'))

        # Disable librosa caching to prevent memory accumulation
        librosa.cache.level = 0
        logger.info("Disabled librosa caching to prevent memory accumulation")

    def analyze_file(self, file_path: str) -> Tuple[Optional[np.ndarray], Optional[str]]:
        """
        Analyze an audio file and extract embedding

        Args:
            file_path: Path to audio file

        Returns:
            Tuple of (embedding, reason) where reason is None for success,
            "skipped_size" for file too large, "skipped_memory" for high memory,
            "failed" for processing error
        """
        try:
            logger.debug(f"Analyzing audio file: {file_path}")

            # Check file size before loading
            file_size_mb = os.path.getsize(file_path) / (1024**2)
            if file_size_mb > self.max_file_size_mb:
                logger.warning(f"Skipping large audio file: {file_path} ({file_size_mb:.1f}MB > {self.max_file_size_mb}MB limit)")
                return None, "skipped_size"

            # Check memory usage before loading
            mem_before = psutil.virtual_memory()
            logger.debug(f"Memory before audio load: {mem_before.percent:.1f}% used ({mem_before.used / (1024**3):.2f}GB)")

            if mem_before.percent > self.memory_threshold_percent:
                logger.warning(f"Skipping audio file due to high memory usage: {file_path} ({mem_before.percent:.1f}% > {self.memory_threshold_percent}%)")
                return None, "skipped_memory"

            # Load audio file (this will fail if file doesn't exist or isn't readable)
            # Suppress mpg123 warnings about malformed ID3 tags by redirecting stderr
            stderr_capture = io.StringIO()
            with redirect_stderr(stderr_capture):
                audio, sr = librosa.load(file_path, sr=self.sample_rate, mono=True)

            # Check if there were any non-mpg123 errors in stderr
            stderr_output = stderr_capture.getvalue()
            if stderr_output and "src/libmpg123" not in stderr_output:
                # Log non-mpg123 errors
                logger.warning(f"Audio loading warnings: {stderr_output.strip()}")

            # Log memory usage after loading
            mem_after_load = psutil.virtual_memory()
            audio_size_mb = len(audio) * audio.itemsize / (1024**2)
            logger.debug(f"Memory after audio load: {mem_after_load.percent:.1f}% used ({mem_after_load.used / (1024**3):.2f}GB), audio size: {audio_size_mb:.1f}MB")

            # Skip very short audio
            if len(audio) < self.sample_rate:  # Less than 1 second
                logger.warning(f"Audio file too short: {file_path} ({len(audio)/sr:.2f}s)")
                return None, "skipped_short"

            # Extract features
            embedding = self._extract_features(audio, sr)

            # AGGRESSIVE MEMORY CLEANUP
            del audio, sr
            gc.collect()

            # Log memory usage after processing
            mem_after_process = psutil.virtual_memory()
            logger.debug(f"Memory after processing: {mem_after_process.percent:.1f}% used ({mem_after_process.used / (1024**3):.2f}GB)")

            logger.debug(f"Successfully analyzed: {file_path}")
            return embedding, None

        except Exception as e:
            # Cleanup on error
            try:
                del audio
            except NameError:
                pass
            try:
                del sr
            except NameError:
                pass
            try:
                del embedding
            except NameError:
                pass
            gc.collect()
            logger.error(f"Failed to analyze audio file {file_path}: {e}")
            return None, "failed"

    def _extract_features(self, audio: np.ndarray, sr: float) -> np.ndarray:
        """
        Extract audio features and create embedding

        Args:
            audio: Audio time series
            sr: Sample rate

        Returns:
            Feature embedding vector
        """
        features = []

        try:
            # MFCC (Mel-frequency cepstral coefficients) with cleanup
            mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=self.n_mfcc)
            mfcc_mean = np.mean(mfcc, axis=1)
            mfcc_std = np.std(mfcc, axis=1)
            features.extend(mfcc_mean)
            features.extend(mfcc_std)
            del mfcc, mfcc_mean, mfcc_std
            gc.collect()

            # Chroma features with cleanup
            chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            chroma_std = np.std(chroma, axis=1)
            features.extend(chroma_mean)
            features.extend(chroma_std)
            del chroma, chroma_mean, chroma_std
            gc.collect()

            # Spectral contrast with cleanup
            contrast = librosa.feature.spectral_contrast(y=audio, sr=sr)
            contrast_mean = np.mean(contrast, axis=1)
            contrast_std = np.std(contrast, axis=1)
            features.extend(contrast_mean)
            features.extend(contrast_std)
            del contrast, contrast_mean, contrast_std
            gc.collect()

            # RMS energy with cleanup
            rms = librosa.feature.rms(y=audio)
            rms_mean = np.mean(rms)
            rms_std = np.std(rms)
            features.extend([rms_mean, rms_std])
            del rms, rms_mean, rms_std
            gc.collect()

            # Zero crossing rate with cleanup
            zcr = librosa.feature.zero_crossing_rate(y=audio)
            zcr_mean = np.mean(zcr)
            zcr_std = np.std(zcr)
            features.extend([zcr_mean, zcr_std])
            del zcr, zcr_mean, zcr_std
            gc.collect()

            # Spectral centroid with cleanup
            centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)
            centroid_mean = np.mean(centroid)
            centroid_std = np.std(centroid)
            features.extend([centroid_mean, centroid_std])
            del centroid, centroid_mean, centroid_std
            gc.collect()

            # Spectral bandwidth with cleanup
            bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sr)
            bandwidth_mean = np.mean(bandwidth)
            bandwidth_std = np.std(bandwidth)
            features.extend([bandwidth_mean, bandwidth_std])
            del bandwidth, bandwidth_mean, bandwidth_std
            gc.collect()

            # Convert to numpy array and normalize
            embedding = np.array(features, dtype=np.float32)
            del features

            # L2 normalization
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm

            return embedding

        except Exception as e:
            # Cleanup on error
            try:
                del features
            except NameError:
                pass
            gc.collect()
            logger.error(f"Failed to extract features: {e}")
            # Return zero vector as fallback
            return np.zeros(64, dtype=np.float32)  # Reasonable embedding size

    def get_audio_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get basic audio file information

        Args:
            file_path: Path to audio file

        Returns:
            Dictionary with audio info or None if failed
        """
        try:
            if not os.path.exists(file_path):
                return None

            # Get basic file info
            stat = os.stat(file_path)

            # Load audio to get duration and sample rate
            audio, sr = librosa.load(file_path, sr=None)

            info = {
                "file_path": file_path,
                "file_size": stat.st_size,
                "duration": len(audio) / sr,
                "sample_rate": sr,
                "channels": 1 if audio.ndim == 1 else audio.shape[0],
                "file_format": Path(file_path).suffix.lower()
            }

            return info

        except Exception as e:
            logger.error(f"Failed to get audio info for {file_path}: {e}")
            return None

    def is_supported_format(self, file_path: str) -> bool:
        """
        Check if audio file format is supported

        Args:
            file_path: Path to audio file

        Returns:
            True if format is supported
        """
        supported_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma'}
        extension = Path(file_path).suffix.lower()
        return extension in supported_extensions

    def get_system_resources(self) -> Dict[str, Any]:
        """
        Get current system resource usage

        Returns:
            Dictionary with CPU and memory usage
        """
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_gb": psutil.virtual_memory().used / (1024**3),
            "memory_available_gb": psutil.virtual_memory().available / (1024**3)
        }


# Global service instance
_audio_analyzer = None

def get_audio_analyzer() -> AudioAnalyzer:
    """Get the global audio analyzer instance"""
    global _audio_analyzer
    if _audio_analyzer is None:
        _audio_analyzer = AudioAnalyzer()
    return _audio_analyzer