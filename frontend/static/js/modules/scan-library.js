// Library Scan Module
// Handles all library scanning functionality including test scans, full scans, progress tracking, and scan history

// Import utility functions
import { formatFriendlyDate, formatDuration, showToast } from '../core/utils.js';
import { checkLibraryMappingNeeded, populateLibraryMappingForm, saveLibraryMappings } from './library-manager.js';

/**
 * Format elapsed time in the format: 0:25s, 12m:34s, 9h:1m:59s
 * @param {number} milliseconds - Elapsed time in milliseconds
 * @returns {string} Formatted elapsed time string
 */
function formatElapsedTime(milliseconds) {
    if (!milliseconds || milliseconds < 0) return '0:00s';

    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
        return `${hours}h:${minutes.toString().padStart(2, '0')}m:${seconds.toString().padStart(2, '0')}s`;
    } else if (minutes > 0) {
        return `${minutes}m:${seconds.toString().padStart(2, '0')}s`;
    } else {
        return `${seconds}s`;
    }
}

/**
 * Generate ASCII progress bar with filled and empty blocks
 * @param {number} percentage - Progress percentage (0-100)
 * @param {number} totalWidth - Total width of the bar in characters (default 50)
 * @returns {object} Object with filled and empty properties
 */
function generateProgressBar(percentage, totalWidth = 50) {
    const filledCount = Math.round((percentage / 100) * totalWidth);
    const emptyCount = totalWidth - filledCount;
    
    return {
        filled: '█'.repeat(filledCount),
        empty: '░'.repeat(emptyCount)
    };
}

/**
 * Format elapsed time for display (simplified format for terminal)
 * @param {number} seconds - Elapsed time in seconds
 * @returns {string} Formatted time string (e.g., "12m:42s", "1h:30m")
 */
function formatTerminalElapsedTime(seconds) {
    if (!seconds || seconds < 0) return '0:00s';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}h:${String(minutes).padStart(2, '0')}m`;
    } else if (minutes > 0) {
        return `${minutes}m:${String(secs).padStart(2, '0')}s`;
    } else {
        return `${Math.round(secs)}s`;
    }
}

/**
 * Calculate ETA based on progress
 * @param {number} current - Current tracks processed
 * @param {number} total - Total tracks to process
 * @param {number} elapsedSeconds - Elapsed time in seconds
 * @returns {string} Formatted ETA string
 */
function calculateETA(current, total, elapsedSeconds) {
    if (current === 0 || elapsedSeconds === 0) return 'Calculating...';
    if (current >= total) return 'Done';
    
    const avgTimePerTrack = elapsedSeconds / current;
    const remainingTracks = total - current;
    const etaSeconds = Math.round(avgTimePerTrack * remainingTracks);
    
    return formatTerminalElapsedTime(etaSeconds);
}

/**
 * Update terminal progress display
 * @param {number} percentage - Progress percentage (0-100)
 * @param {number} current - Current tracks processed
 * @param {number} total - Total tracks to process
 * @param {number} elapsedSeconds - Elapsed time in seconds
 * @param {string} statusText - Status message
 */
function updateTerminalProgress(percentage, current, total, elapsedSeconds, statusText = '') {
    // Generate progress bar
    const { filled, empty } = generateProgressBar(percentage, 50);
    
    // Update status and percentage
    const statusEl = document.getElementById('terminal-status-text');
    const percentageEl = document.getElementById('terminal-percentage');
    
    if (statusEl && statusText) {
        // Remove existing spinner if present (from beginning or end)
        let cleanStatusText = statusText.replace(/^[⣾⣽⣻⢿⡿⣟⣯⣷]\s*/, '').replace(/\s*[⣾⣽⣻⢿⡿⣟⣯⣷]$/, '');
        statusEl.textContent = cleanStatusText;
        // Update spinner display
        updateSpinnerDisplay();
    }
    if (percentageEl) {
        percentageEl.textContent = `${Math.round(percentage)}%`;
    }
    
    // Update progress bar
    const filledEl = document.getElementById('terminal-filled');
    const emptyEl = document.getElementById('terminal-empty');
    
    if (filledEl) filledEl.textContent = filled;
    if (emptyEl) emptyEl.textContent = empty;
    
    // Update track count
    const trackCountEl = document.getElementById('terminal-track-count');
    if (trackCountEl) {
        trackCountEl.textContent = `${current.toLocaleString()}/${total.toLocaleString()} tracks`;
    }
    
     // Update time info
     const timeInfoEl = document.getElementById('terminal-time-info');
     if (timeInfoEl) {
         const elapsed = formatTerminalElapsedTime(elapsedSeconds);
         const eta = calculateETA(current, total, elapsedSeconds);
         timeInfoEl.innerHTML = `Elapsed ${elapsed}<span id="eta-section"> / ETA ${eta}</span>`;
     }
}

/**
 * Start the spinner animation
 */
function startSpinner() {
    if (spinnerActive) return;
    spinnerActive = true;
    spinnerFrameIndex = 0;

    spinnerInterval = setInterval(() => {
        spinnerFrameIndex = (spinnerFrameIndex + 1) % spinnerFrames.length;
        updateSpinnerDisplay();
    }, spinnerIntervalMs);
}

/**
 * Stop the spinner animation
 */
function stopSpinner() {
    if (!spinnerActive) return;
    spinnerActive = false;
    if (spinnerInterval) {
        clearInterval(spinnerInterval);
        spinnerInterval = null;
    }
    // Clear spinner from display
    updateSpinnerDisplay();
}

/**
 * Update the spinner display in the status text
 */
function updateSpinnerDisplay() {
    const statusEl = document.getElementById('terminal-status-text');
    if (!statusEl) return;

    let currentText = statusEl.textContent || '';

    // Remove existing spinner if present (at the end)
    currentText = currentText.replace(/\s*[⣾⣽⣻⢿⡿⣟⣯⣷]$/, '');

    // Add spinner at the end if active
    if (spinnerActive) {
        currentText = `${currentText} ${spinnerFrames[spinnerFrameIndex]}`;
    }

    statusEl.textContent = currentText;
}

/**
 * Start the summary loading spinner
 */
function startSummarySpinner() {
    if (summarySpinnerActive) return;
    summarySpinnerActive = true;
    summarySpinnerFrameIndex = 0;

    const summaryNameEl = document.getElementById('summary-library-name');
    if (summaryNameEl) {
        summarySpinnerInterval = setInterval(() => {
            summarySpinnerFrameIndex = (summarySpinnerFrameIndex + 1) % spinnerFrames.length;
            summaryNameEl.textContent = spinnerFrames[summarySpinnerFrameIndex];
        }, spinnerIntervalMs);
    }
}

/**
 * Stop the summary loading spinner
 */
function stopSummarySpinner() {
    if (!summarySpinnerActive) return;
    summarySpinnerActive = false;
    if (summarySpinnerInterval) {
        clearInterval(summarySpinnerInterval);
        summarySpinnerInterval = null;
    }
}

/**
 * Hide the ETA section (called at completion)
 */
function hideETASection() {
    const etaSection = document.getElementById('eta-section');
    if (etaSection) {
        etaSection.style.display = 'none';
    }
}

// ===== ELAPSED TIME CLOCK =====

let elapsedInterval = null;
let scanStartTime = null;

/**
 * Start the elapsed time clock (updates UI every 1 second)
 */
function startElapsedClock() {
    scanStartTime = Date.now();
    elapsedInterval = setInterval(() => {
        const elapsedSeconds = Math.floor((Date.now() - scanStartTime) / 1000);
        updateElapsedTimeOnly(elapsedSeconds);
    }, 1000); // Update every 1 second
}

/**
 * Stop the elapsed time clock
 */
function stopElapsedClock() {
    if (elapsedInterval) {
        clearInterval(elapsedInterval);
        elapsedInterval = null;
    }
}

/**
 * Truncate text to specified length with ellipsis
 */
function truncateText(text, maxLength) {
    if (!text || text.length <= maxLength) {
        return text;
    }
    return text.substring(0, maxLength - 1) + '…';
}

/**
 * Update only the elapsed time display (called by real-time clock)
 */
function updateElapsedTimeOnly(elapsedSeconds) {
    const timeInfoEl = document.getElementById('terminal-time-info');
    if (timeInfoEl && scanInProgress) {
        const elapsed = formatTerminalElapsedTime(elapsedSeconds);
        // Preserve existing ETA if it exists
        const etaSection = document.getElementById('eta-section');
        const etaText = etaSection ? etaSection.textContent : ' / ETA Calculating...';
        timeInfoEl.innerHTML = `Elapsed ${elapsed}<span id="eta-section">${etaText}</span>`;
    }
}

/**
 * Get elapsed seconds since scan start
 */
function getElapsedSeconds() {
    if (!scanStartTime) return 0;
    return Math.floor((Date.now() - scanStartTime) / 1000);
}

import { loadLibraryStats } from './library-manager.js';

// Global state for scan
let scanInProgress = false;
let scanAbortController = null;
let currentScanSessionId = null;
let lastTestScanDuration = null;
let selectedScanLibraryId = null;
let selectedLibraryTotalTracks = 0;  // Total tracks in the selected library

// SSE and streaming state
let eventSource = null;
let retryCount = 0;
let testModeActive = false;  // Track whether test or full scan is active
let currentScanId = null;  // Track the current streaming scan ID
let scanState = {
    totalTracks: 0,
    processedTracks: 0,
    currentPercent: 0
};

// Spinner animation state
let spinnerActive = false;
let spinnerInterval = null;
let spinnerFrameIndex = 0;
const spinnerFrames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];
const spinnerIntervalMs = 80;

// Summary loading spinner state
let summarySpinnerActive = false;
let summarySpinnerInterval = null;
let summarySpinnerFrameIndex = 0;

// Export state and functions
export {
    scanInProgress,
    scanAbortController,
    currentScanSessionId,
    currentScanId,
    lastTestScanDuration,
    selectedScanLibraryId,
    selectedLibraryTotalTracks,
    startScan,
    cancelScan,
    updateFullScanTimeEstimate,
    initializeScanLibraryPage,
    loadScanLibraries,
    loadLibraryScanProgress,
    handleScanLibrarySelection,
    checkScanReadiness,
    loadScanHistory
};

// Start a library scan (test or full)
async function startScan(testMode = false) {
    if (scanInProgress) {
        showToast('warning', 'An analysis is already in progress');
        return;
    }

    if (!selectedScanLibraryId) {
        showToast('warning', 'Please select a library first');
        return;
    }

    const testScanBtn = document.getElementById('test-scan-btn');
    const fullScanBtn = document.getElementById('full-scan-btn');
    const progressEmptyState = document.getElementById('progress-empty-state');
    const progressActiveState = document.getElementById('progress-active-state');
    const systemCpu = document.getElementById('system-cpu');
    const systemMemory = document.getElementById('system-memory');
    const cancelBtn = document.getElementById('cancel-scan-btn');

    // Disable buttons and radio buttons
    testScanBtn.disabled = true;
    fullScanBtn.disabled = true;

    // Get library radio buttons for later use
    const radioButtons = document.querySelectorAll('#scan-library-radios input[type="radio"]');

    // Disable all library radio buttons during scan
    radioButtons.forEach(radio => {
        radio.disabled = true;
    });

    // Show cancel button
    if (cancelBtn) {
        cancelBtn.style.display = 'block';
    }

    // Show active progress state
    progressEmptyState.classList.add('hidden');
    progressActiveState.classList.remove('hidden');

    // Reset progress using terminal display
    updateTerminalProgress(0, 0, 0, 0, 'Preparing analysis...');

     scanInProgress = true;
     scanAbortController = new AbortController();

     // Start scan with SSE streaming
     startScanWithStreaming(testMode);
}

// Cancel an ongoing scan
async function cancelScan() {
    if (!scanInProgress) {
        showToast('info', 'No analysis is currently running');
        return;
    }

    // Prevent multiple cancel requests
    if (scanAbortController && scanAbortController.signal.aborted) {
        showToast('info', 'Cancel request already sent');
        return;
    }

      try {
          // Send cancel request to backend if we have a scan ID
          if (currentScanId) {
              try {
                  await fetch(`/api/scan/stream-cancel/${currentScanId}`, {
                      method: 'DELETE'
                  });
                  console.log(`Sent cancel request for scan ${currentScanId}`);
              } catch (cancelError) {
                  console.warn('Failed to send cancel request to backend:', cancelError);
                  // Continue with UI cleanup even if backend cancel fails
              }
          }

          // Close EventSource first
          if (eventSource) {
              eventSource.close();
              eventSource = null;
          }

          // Stop elapsed clock
          stopElapsedClock();

         // Update UI to cancelled state
         const finalElapsed = getElapsedSeconds();
         updateTerminalProgress(scanState.currentPercent, scanState.processedTracks, 
             scanState.totalTracks, finalElapsed, 'Analysis cancelled.');
         hideETASection();

          // Reset scan state
          scanInProgress = false;
          currentScanSessionId = null;
          currentScanId = null;

         // Update buttons
         const testScanBtn = document.getElementById('test-scan-btn');
         const fullScanBtn = document.getElementById('full-scan-btn');
         if (testScanBtn) testScanBtn.disabled = false;
         if (fullScanBtn) fullScanBtn.disabled = false;

         // Re-enable library radio buttons
         const radioButtons = document.querySelectorAll('#scan-library-radios input[type="radio"]');
         radioButtons.forEach(radio => {
             radio.disabled = false;
         });

         // Hide cancel button
         const cancelBtn = document.getElementById('cancel-scan-btn');
         if (cancelBtn) {
             cancelBtn.style.display = 'none';
         }

         showToast('info', 'Analysis cancelled');

     } catch (error) {
         console.error('Cancel scan error:', error);
         showToast('error', 'Failed to cancel analysis properly');
      }
  }
 
 // ===== SSE STREAMING FUNCTIONS =====
 
 /**
  * Start scan with streaming progress via Server-Sent Events
  */
 function startScanWithStreaming(testMode = false) {
    const baseEndpoint = testMode ? '/api/scan/test-stream' : '/api/scan/full-stream';
    const endpoint = selectedScanLibraryId ? `${baseEndpoint}?library_id=${selectedScanLibraryId}` : baseEndpoint;
    testModeActive = testMode;

    try {
        eventSource = new EventSource(endpoint);
         retryCount = 0;
         
          // Event: started
          eventSource.addEventListener('started', (event) => {
              const data = JSON.parse(event.data);
              currentScanId = data.scan_id;  // Store scan ID for cancellation
              startElapsedClock();
              startSpinner();  // Start spinner animation
              updateTerminalProgress(0, 0, 0, getElapsedSeconds(), 'Analysis started...');
          });
         
         // Event: preflight_complete
         eventSource.addEventListener('preflight_complete', (event) => {
             const data = JSON.parse(event.data);
             scanState.totalTracks = data.tracks_to_scan;  // Use tracks to scan for progress bar
             const libraryTotal = selectedLibraryTotalTracks || data.total_tracks;
             updateTerminalProgress(0, 0, scanState.totalTracks, getElapsedSeconds(),
                 `Pre-flight completed, ${libraryTotal} tracks, ${data.tracks_to_scan} to scan`);
         });
         
// Event: processing (batch update with filename)
eventSource.addEventListener('processing', (event) => {
    const data = JSON.parse(event.data);

    // DEBUG LOGGING
    console.log('🎵 Received processing event:', data.filename, data.processed, '/', data.total);

    scanState.processedTracks = data.processed;
    scanState.currentPercent = (data.processed / data.total) * 100;

    const truncatedTitle = truncateText(data.filename, 45); // Limit to ~45 chars to fit status line
    updateTerminalProgress(
        scanState.currentPercent,
        scanState.processedTracks,
        scanState.totalTracks,
        getElapsedSeconds(),
        `Analysing: ${truncatedTitle}`
    );
});
         
// Event: progress (for non-filename updates)
eventSource.addEventListener('progress', (event) => {
    const data = JSON.parse(event.data);

    // DEBUG LOGGING
    console.log('📊 Received progress event:', data);
    console.log('   Processed:', data.processed || data.processed_tracks, 'Total:', data.total || data.total_tracks);

    // Handle both data formats: 'processed'/'total' and 'processed_tracks'/'total_tracks'
    const processed = data.processed || data.processed_tracks || 0;
    const total = data.total || data.total_tracks || scanState.totalTracks;

    scanState.processedTracks = processed;
    scanState.currentPercent = (processed / total) * 100;

    // Update total tracks if provided (for consistency)
    if (total && total !== scanState.totalTracks) {
        scanState.totalTracks = total;
    }

    // Update without changing status text
    updateTerminalProgress(
        scanState.currentPercent,
        scanState.processedTracks,
        scanState.totalTracks,
        getElapsedSeconds()
    );
});

           // Event: cancelled
           eventSource.addEventListener('cancelled', (event) => {
               const data = JSON.parse(event.data);
               stopElapsedClock();

                const finalElapsed = getElapsedSeconds();
                updateTerminalProgress(scanState.currentPercent, scanState.processedTracks,
                    scanState.totalTracks, finalElapsed, 'Analysis cancelled.');
                stopSpinner();  // Stop spinner animation after updating display
                hideETASection();

               eventSource.close();
               eventSource = null;
               scanInProgress = false;
               currentScanId = null;

              // Re-enable buttons
              const testScanBtn = document.getElementById('test-scan-btn');
              const fullScanBtn = document.getElementById('full-scan-btn');
              if (testScanBtn) testScanBtn.disabled = false;
              if (fullScanBtn) fullScanBtn.disabled = false;

              // Re-enable library radio buttons
              const radioButtons = document.querySelectorAll('#scan-library-radios input[type="radio"]');
              radioButtons.forEach(radio => {
                  radio.disabled = false;
              });

              // Hide cancel button
              const cancelBtn = document.getElementById('cancel-scan-btn');
              if (cancelBtn) {
                  cancelBtn.style.display = 'none';
              }

              showToast('info', 'Analysis cancelled');
          });

          // Event: completed
          eventSource.addEventListener('completed', (event) => {
              const data = JSON.parse(event.data);
              stopElapsedClock();

               const finalElapsed = getElapsedSeconds();
               updateTerminalProgress(100, data.processed, data.total, finalElapsed, 'Analysis complete!');
               stopSpinner();  // Stop spinner animation after updating display
               hideETASection();

              eventSource.close();
              eventSource = null;
              scanInProgress = false;
             
             // Re-enable buttons
             const testScanBtn = document.getElementById('test-scan-btn');
             const fullScanBtn = document.getElementById('full-scan-btn');
             if (testScanBtn) testScanBtn.disabled = false;
             if (fullScanBtn) fullScanBtn.disabled = false;
             
             // Re-enable library radio buttons
             const radioButtons = document.querySelectorAll('#scan-library-radios input[type="radio"]');
             radioButtons.forEach(radio => {
                 radio.disabled = false;
             });
             
             // Hide cancel button
             const cancelBtn = document.getElementById('cancel-scan-btn');
             if (cancelBtn) {
                 cancelBtn.style.display = 'none';
             }
             
             // Update history
             loadScanHistory();
             updateFullScanTimeEstimate();
         });
         
         // Event: error
         eventSource.addEventListener('error', (event) => {
             if (event.readyState === EventSource.CLOSED) {
                 handleConnectionError();
             } else {
                 try {
                     const data = JSON.parse(event.data);
                     console.error('Scan error:', data.message);
                     updateTerminalProgress(scanState.currentPercent, scanState.processedTracks, 
                         scanState.totalTracks, getElapsedSeconds(), `Error: ${data.message}`);
                 } catch (e) {
                     console.error('Error parsing error event:', e);
                 }
             }
         });
         
     } catch (error) {
         console.error('Failed to start SSE connection:', error);
         handleConnectionError();
     }
 }
 
 /**
  * Handle connection errors and retry
  */
 function handleConnectionError() {
     stopElapsedClock();
     updateTerminalProgress(scanState.currentPercent, scanState.processedTracks, 
         scanState.totalTracks, getElapsedSeconds(), 'Connecting...');
     
     if (retryCount < 10) {
         retryCount++;
         console.log(`Retry attempt ${retryCount}/10 in 5 seconds...`);
         setTimeout(() => {
             startScanWithStreaming(testModeActive);
         }, 5000);
     } else {
          stopSpinner();  // Stop spinner on final connection failure
          updateTerminalProgress(scanState.currentPercent, scanState.processedTracks,
              scanState.totalTracks, getElapsedSeconds(), 'Connection lost. Try again?');
          scanInProgress = false;
          showToast('error', 'Connection lost after 10 retries');
     }
 }
 
 // Update full scan time estimate based on historical scan data
 async function updateFullScanTimeEstimate() {
    const timeTextElement = document.getElementById('full-scan-time-text');
    if (!timeTextElement) return;

    // Prioritize selected library total tracks for estimation
    let tracksToEstimate = selectedLibraryTotalTracks;

    if (tracksToEstimate === 0) {
        // Fall back to total across all libraries if selected library total not available
        try {
            const countResponse = await fetch('/api/tracks/count');
            if (countResponse.ok) {
                const countData = await countResponse.json();
                tracksToEstimate = countData.total_tracks || 0;
                console.log(`Fetched total library size from Navidrome: ${tracksToEstimate} total tracks (${countData.cached ? 'cached' : 'fresh'})`);
            } else {
                console.warn('Failed to fetch total track count from Navidrome');
            }
        } catch (error) {
            console.warn('Error fetching total track count:', error);
        }
    }

    // If we still don't have tracks, use approximation from scan history
    if (tracksToEstimate === 0) {
        console.log('No track count available, will use scan history approximation');
    }

    try {
        // Fetch scan history to calculate average time per track
        const response = await fetch('/api/scan/history');
        if (!response.ok) {
            throw new Error('Failed to fetch scan history');
        }

        const data = await response.json();
        const history = data.scan_history || [];

        console.log('Scan history fetched:', history.length, 'scans');

        if (history.length === 0) {
            // If no history, show default message
            timeTextElement.textContent = 'Test scan will estimate time';
            console.log('No scan history found, showing placeholder');
            return;
        }

        // Use the most recent completed scan for estimation (test or full)
        const completedScans = history.filter(scan => scan.status === 'completed');

        if (completedScans.length > 0) {
            // Get the most recent completed scan
            const latestScan = completedScans[0]; // History is sorted by date desc

            // tracksToEstimate is already set above with proper prioritization
            
            if (tracksToEstimate === 0) {
                tracksToEstimate = latestScan.total_tracks || latestScan.processed_tracks * 2; // Rough approximation
                console.log(`Using approximation: ${tracksToEstimate} tracks (from scan history)`);
            }

            // Skip estimation only if we have no track count information at all
            if (tracksToEstimate <= 0) {
            timeTextElement.textContent = 'Test scan will estimate time';
            timeTextElement.className = 'text-sm';
                return;
            }

            // Calculate: (elapsed time / tracks processed) * total library tracks
            const avgSecondsPerTrack = latestScan.duration_seconds / latestScan.processed_tracks;
            const estimatedSeconds = avgSecondsPerTrack * tracksToEstimate;
            const estimatedMinutes = Math.ceil(estimatedSeconds / 60);

            // Format the time estimate
            let timeEstimate;
            if (estimatedMinutes < 60) {
                timeEstimate = `~${estimatedMinutes} min`;
            } else {
                const hours = Math.floor(estimatedMinutes / 60);
                const mins = estimatedMinutes % 60;
                timeEstimate = `~${hours}h ${mins}min`;
            }

            timeTextElement.textContent = timeEstimate;
            timeTextElement.className = 'text-sm';

            console.log(`Time estimate: (${latestScan.duration_seconds}s / ${latestScan.processed_tracks} tracks) × ${tracksToEstimate} total = ${timeEstimate}`);
        } else {
            // No completed scans available
            timeTextElement.textContent = 'Test scan will estimate time';
            timeTextElement.className = 'text-sm';
            console.log('No completed scans found in history');
        }

    } catch (error) {
        console.error('Failed to update scan time estimate:', error);
        timeTextElement.textContent = 'Test scan will estimate time';
        timeTextElement.className = 'text-sm';
    }
}

// Initialize the scan library page
async function initializeScanLibraryPage() {
    console.log('Initializing scan library page...');

    // Load libraries for the sidebar dropdown
    await window.loadLibraries();

    // Load libraries for scan page radio buttons (this auto-selects a library)
    await loadScanLibraries();

    // Load scan history
    await loadScanHistory();

    // Update scan time estimate (library should be selected now)
    await updateFullScanTimeEstimate();

    // Check scan readiness
    await checkScanReadiness();

    // Check for partial scans
    await checkPartialScan();
}

// Load libraries for scan page radio buttons
async function loadScanLibraries() {
    try {
        const response = await fetch('/api/libraries');
        if (!response.ok) {
            throw new Error('Failed to fetch libraries');
        }

        const libraries = await response.json();
        const radiosContainer = document.getElementById('scan-library-radios');
        const librarySelectorSection = document.getElementById('library-selector-section');
        const librarySummarySection = document.getElementById('library-summary-section');

        if (radiosContainer) {
            // Clear existing radio buttons
            radiosContainer.innerHTML = '';

            // Get analyzed tracks count (total unique tracks scanned across all libraries)
            let allAnalyzedTracks = [];
            try {
                const analyzedResponse = await fetch('/api/radio/analyzed-tracks');
                if (analyzedResponse.ok) {
                    const analyzedData = await analyzedResponse.json();
                    allAnalyzedTracks = analyzedData.tracks || [];
                }
            } catch (error) {
                console.warn('Failed to fetch analyzed tracks:', error);
            }

            // Get current library mappings
            let libraryMappings = [];
            try {
                const mappingsResponse = await fetch('/api/library-mappings');
                if (mappingsResponse.ok) {
                    const mappingsData = await mappingsResponse.json();
                    libraryMappings = mappingsData.mappings || [];
                }
            } catch (error) {
                console.warn('Failed to fetch library mappings:', error);
            }

            // Create a map of library_id to mapping for quick lookup
            const mappingsByLibraryId = {};
            libraryMappings.forEach(mapping => {
                mappingsByLibraryId[mapping.library_id] = mapping;
            });

            // Check if single library scenario
            if (libraries.length === 1) {
                // Hide selector, show summary
                librarySelectorSection.classList.add('hidden');
                librarySummarySection.classList.remove('hidden');

                const library = libraries[0];

                // Start spinner in library name field while loading
                startSummarySpinner();

                let totalTracks = 0;
                let scannedTracks = allAnalyzedTracks.length;

                try {
                    const statsResponse = await fetch(`/api/libraries/${library.id}/stats`);
                    if (statsResponse.ok) {
                        const stats = await statsResponse.json();
                        totalTracks = stats.total_tracks || 0;
                    }
                } catch (error) {
                    console.warn(`Failed to fetch stats for library ${library.id}:`, error);
                }

                // Stop spinner and populate summary well
                stopSummarySpinner();
                document.getElementById('summary-library-name').textContent = library.name;
                document.getElementById('summary-total-tracks').textContent = totalTracks.toLocaleString();
                document.getElementById('summary-scanned-tracks').textContent = scannedTracks.toLocaleString();

                // Auto-select the library and store its total track count
                selectedScanLibraryId = library.id;
                selectedLibraryTotalTracks = totalTracks;
                console.log(`Single library detected: "${library.name}" with ${totalTracks} total tracks`);
                return; // Skip radio button creation
            } else {
                // Show selector, hide summary
                librarySelectorSection.classList.remove('hidden');
                librarySummarySection.classList.add('hidden');
            }

            // Add radio button options
            for (const library of libraries) {
                // Get total tracks and scanned tracks for this library
                let totalTracks = 0;
                let scannedTracks = 0;

                try {
                    // Get total tracks from Navidrome
                    const statsResponse = await fetch(`/api/libraries/${library.id}/stats`);
                    if (statsResponse.ok) {
                        const stats = await statsResponse.json();
                        totalTracks = stats.total_tracks || 0;
                    }

                    // Get analyzed tracks count for this specific library
                    scannedTracks = 0;
                    try {
                        const analyzedResponse = await fetch(`/api/radio/analyzed-tracks?library_id=${library.id}`);
                        if (analyzedResponse.ok) {
                            const analyzedData = await analyzedResponse.json();
                            scannedTracks = analyzedData.tracks.length;
                        }
                    } catch (error) {
                        console.warn(`Failed to get analyzed tracks for library ${library.id}:`, error);
                    }
                } catch (error) {
                    console.warn(`Failed to fetch stats for library ${library.id}:`, error);
                }

                // Check if library has a mapping
                const hasMapping = mappingsByLibraryId[library.id] !== undefined;

                // Calculate percentage scanned (only if library has a mapping)
                const percentageScanned = totalTracks > 0 ? Math.round((scannedTracks / totalTracks) * 100) : 0;

                const radioLabel = document.createElement('label');
                radioLabel.htmlFor = `scan-library-${library.id}`;

                // Style differently if no mapping
                if (hasMapping) {
                    radioLabel.className = 'flex p-3 w-full bg-white border border-gray-200 rounded-lg text-sm focus:border-blue-500 focus:ring-blue-500 cursor-pointer hover:bg-gray-50';
                } else {
                    radioLabel.className = 'flex p-3 w-full bg-gray-100 border border-gray-300 rounded-lg text-sm opacity-60 cursor-not-allowed';
                }

                const radioInput = document.createElement('input');
                radioInput.type = 'radio';
                radioInput.id = `scan-library-${library.id}`;
                radioInput.name = 'scan-library';
                radioInput.value = library.id;
                radioInput.disabled = !hasMapping; // Disable if no mapping
                radioInput.className = 'shrink-0 mt-0.5 border-gray-200 rounded-full text-blue-600 focus:ring-blue-500 checked:border-blue-500 disabled:opacity-50 disabled:pointer-events-none';

                // Create container for library info
                const libraryInfo = document.createElement('div');
                libraryInfo.className = 'flex-1 ms-3';

                // Line 1: Library name (already bold from radio label)
                // Lines 2 & 3: Total tracks and scan progress
                const libraryName = document.createElement('div');
                if (hasMapping) {
                    libraryName.className = 'text-sm font-medium text-gray-900';
                } else {
                    libraryName.className = 'text-sm font-medium text-gray-500';
                }
                libraryName.textContent = library.name;

                const libraryStats = document.createElement('div');
                if (hasMapping) {
                    libraryStats.className = 'text-xs text-gray-600 font-normal mt-1 space-y-0.5';
                } else {
                    libraryStats.className = 'text-xs text-gray-500 font-normal mt-1 space-y-0.5';
                }

                let scanStatus;
                if (!hasMapping) {
                    scanStatus = 'Library not mapped to a file path';
                } else {
                    // Show "Not scanned" if no scanned tracks, otherwise show percentage
                    scanStatus = scannedTracks === 0 ? 'Not scanned' : `${percentageScanned}% analysed`;
                }

                libraryStats.innerHTML = `
                    <div>${totalTracks.toLocaleString()} tracks</div>
                    <div>${scanStatus}</div>
                `;

                libraryInfo.appendChild(libraryName);
                libraryInfo.appendChild(libraryStats);

                radioLabel.appendChild(radioInput);
                radioLabel.appendChild(libraryInfo);
                radiosContainer.appendChild(radioLabel);

                // Add change event listener
                radioInput.addEventListener('change', () => handleScanLibrarySelection(library.id));
            }

            // Pre-select library from localStorage if available, otherwise select first mapped library
            const savedLibraryIds = JSON.parse(localStorage.getItem('selectedLibraryIds') || '[]');
            let libraryToSelect = null;

            if (savedLibraryIds.length > 0 && mappingsByLibraryId[savedLibraryIds[0]]) {
                // Use saved library if it has a mapping
                libraryToSelect = savedLibraryIds[0];
            } else {
                // Otherwise select the first library that has a mapping
                for (const library of libraries) {
                    if (mappingsByLibraryId[library.id]) {
                        libraryToSelect = library.id;
                        break;
                    }
                }
            }

            if (libraryToSelect) {
                selectedScanLibraryId = libraryToSelect;
                const preSelectRadio = document.getElementById(`scan-library-${selectedScanLibraryId}`);
                if (preSelectRadio) {
                    preSelectRadio.checked = true;
                    // Apply visual selection styling and load stats
                    await handleScanLibrarySelection(selectedScanLibraryId);
                }
            }
        }
    } catch (error) {
        console.error('Failed to load scan libraries:', error);
        showToast('error', 'Failed to load libraries');
    }
}

// Load scan progress for a specific library
async function loadLibraryScanProgress(libraryId, progressElement, labelElement) {
    try {
        // Get library stats
        const statsResponse = await fetch(`/api/libraries/${libraryId}/stats`);
        if (!statsResponse.ok) {
            progressElement.textContent = 'Unable to get stats';
            return;
        }

        const stats = await statsResponse.json();
        const totalTracks = stats.total_tracks || 0;

        // Get analyzed tracks count
        const analyzedResponse = await fetch('/api/radio/analyzed-tracks');
        if (!analyzedResponse.ok) {
            progressElement.textContent = 'Unable to get scan status';
            return;
        }

        const analyzedData = await analyzedResponse.json();
        const analyzedTracks = analyzedData.tracks || [];

        // Show total analyzed tracks (same for all libraries since scan analyzes everything)
        const totalAnalyzed = analyzedTracks.length;

        if (totalAnalyzed > 0) {
            // Show as fully scanned if we have analyzed tracks
            progressElement.textContent = `✅ ${totalAnalyzed} tracks analyzed`;
            progressElement.className = 'text-xs text-blue-800 font-medium mt-1';
            labelElement.className = 'flex p-3 w-full bg-blue-100 border border-blue-200 rounded-lg text-sm focus:border-blue-500 focus:ring-blue-500 cursor-pointer hover:bg-blue-200';

            // Update library name text color for contrast
            const libraryName = labelElement.querySelector('.text-sm.font-medium');
            if (libraryName) {
                libraryName.className = 'text-sm font-medium text-blue-800';
                // Also update the track count span color
                const trackCountSpan = libraryName.querySelector('.text-xs.text-gray-500');
                if (trackCountSpan) {
                    trackCountSpan.className = 'text-xs text-blue-600 font-normal';
                }
            }
        } else {
            progressElement.textContent = 'Not scanned';
        }

    } catch (error) {
        console.error('Failed to load scan progress:', error);
        progressElement.textContent = 'Scan status unavailable';
    }
}

// Handle library selection for scanning
async function handleScanLibrarySelection(libraryId) {
    selectedScanLibraryId = libraryId;

    // Update radio button styling to show selected state
    const allRadioLabels = document.querySelectorAll('#scan-library-radios label');
    allRadioLabels.forEach(label => {
        const radio = label.querySelector('input[type="radio"]');
        if (radio && radio.value === libraryId) {
            // Selected library - add blue border and background, with darker hover
            label.classList.add('border-blue-500', 'bg-blue-50', 'hover:bg-blue-100');
            label.classList.remove('border-gray-200', 'bg-white', 'hover:bg-gray-50');
        } else {
            // Unselected libraries - reset to default styling
            label.classList.remove('border-blue-500', 'bg-blue-50', 'hover:bg-blue-100');
            label.classList.add('border-gray-200', 'bg-white', 'hover:bg-gray-50');
        }
    });

    // Fetch total tracks for the selected library for time estimation
    try {
        const statsResponse = await fetch(`/api/libraries/${libraryId}/stats`);
        if (statsResponse.ok) {
            const stats = await statsResponse.json();
            selectedLibraryTotalTracks = stats.total_tracks || 0;
            console.log(`Selected library total tracks updated: ${selectedLibraryTotalTracks}`);
        }
    } catch (error) {
        console.warn('Failed to fetch library total tracks:', error);
    }

    // Load stats for the selected library
    await loadLibraryStats(libraryId);

    // Update scan time estimate with fresh library data
    await updateFullScanTimeEstimate();

    // Update scan readiness
    await checkScanReadiness();
}

// Check if system is ready for scanning
async function checkScanReadiness() {
    const readinessBadge = document.getElementById('readiness-badge');
    const readinessIndicator = document.getElementById('readiness-indicator');
    const readinessText = document.getElementById('readiness-text');
    const testScanBtn = document.getElementById('test-scan-btn');
    const fullScanBtn = document.getElementById('full-scan-btn');

    try {
        // Check if library mappings exist
        const hasMappings = !(await checkLibraryMappingNeeded());
        if (!hasMappings) {
            readinessBadge.className = 'py-1 px-2 inline-flex items-center gap-x-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full';
            readinessIndicator.innerHTML = '<div class="w-3 h-3 rounded-full bg-yellow-400"></div>';
            readinessText.textContent = 'Setup required';
            testScanBtn.disabled = true;
            fullScanBtn.disabled = true;
            return;
        }

        // Check if we have a selected library
        if (!selectedScanLibraryId) {
            readinessBadge.className = 'py-1 px-2 inline-flex items-center gap-x-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full';
            readinessIndicator.innerHTML = '<div class="w-3 h-3 rounded-full bg-yellow-400"></div>';
            readinessText.textContent = 'Select library';
            testScanBtn.disabled = true;
            fullScanBtn.disabled = true;
            return;
        }

        // Check system health
        const healthResponse = await fetch('/api/health');
        if (!healthResponse.ok) {
            throw new Error('System health check failed');
        }

        // Check if ChromaDB is available
        const chromaResponse = await fetch('/api/scan/stats');
        if (!chromaResponse.ok) {
            throw new Error('Audio analysis service unavailable');
        }

        // All checks passed
        readinessBadge.className = 'py-1 px-2 inline-flex items-center gap-x-1 text-xs font-medium bg-green-100 text-green-800 rounded-full';
        readinessIndicator.innerHTML = '<div class="w-3 h-3 rounded-full bg-green-300 animate-ping opacity-75" style="animation-duration: 2s;"></div><div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-green-700"></div>';
        readinessText.textContent = 'Ready';
        testScanBtn.disabled = false;
        fullScanBtn.disabled = false;

    } catch (error) {
        console.error('Readiness check failed:', error);
        readinessBadge.className = 'py-1 px-2 inline-flex items-center gap-x-1 text-xs font-medium bg-red-100 text-red-800 rounded-full';
        readinessIndicator.innerHTML = '<div class="w-3 h-3 rounded-full bg-red-400"></div>';
        readinessText.textContent = 'Error';
        testScanBtn.disabled = true;
        fullScanBtn.disabled = true;
    }
}

// Load scan history
async function loadScanHistory() {
    const historyLoading = document.getElementById('scan-history-loading');
    const historyEmpty = document.getElementById('scan-history-empty');
    const historyTable = document.getElementById('scan-history-table');
    const historyBody = document.getElementById('scan-history-body');

    try {
        console.log('Fetching scan history...');
        const response = await fetch('/api/scan/history');
        if (!response.ok) {
            throw new Error('Failed to fetch scan history');
        }

        const data = await response.json();
        const history = data.scan_history || [];
        console.log('Scan history received:', history);

        // Clear loading state
        historyLoading.classList.add('hidden');

        if (history.length === 0) {
            // Show empty state
            historyEmpty.classList.remove('hidden');
            historyTable.classList.add('hidden');
        } else {
            // Show table with history
            historyEmpty.classList.add('hidden');
            historyTable.classList.remove('hidden');

            // Clear existing rows
            historyBody.innerHTML = '';

            // Add history rows
            history.forEach(scan => {
                const row = document.createElement('tr');
                row.className = 'hover:bg-gray-50';

                const date = scan.completed_at ? formatFriendlyDate(scan.completed_at) : 'Unknown';
                const type = scan.max_tracks === 10 ? 'Test Scan' : 'Full Scan';
                const tracks = scan.processed_tracks || 0;
                const duration = formatDuration(scan.duration_seconds);
                const status = scan.status === 'completed' ? '✅ Completed' : scan.status || 'Unknown';

                row.innerHTML = `
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${date}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${type}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${tracks}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${duration}</td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${status}</td>
                `;

                historyBody.appendChild(row);
            });
        }

        // Update time estimate after history table is loaded
        await updateFullScanTimeEstimate();

    } catch (error) {
        console.error('Failed to load scan history:', error);
        historyLoading.classList.add('hidden');
        historyEmpty.classList.remove('hidden');
        historyTable.classList.add('hidden');
    }
}

// Check for partial scans and show alert if found
async function checkPartialScan() {
    try {
        const response = await fetch('/api/scan/partial-status');
        if (!response.ok) {
            console.warn('Failed to check partial scan status');
            return;
        }

        const data = await response.json();
        const alertDiv = document.getElementById('partial-scan-alert');
        const messageDiv = document.getElementById('partial-scan-message');

        if (data.has_partial) {
            // Update message with details
            const progress = data.progress_percentage ? `${data.progress_percentage.toFixed(1)}%` : 'unknown progress';
            const tracks = data.completed_tracks_count || 0;
            const total = data.total_tracks || 'unknown';
            const started = data.started_at ? new Date(data.started_at).toLocaleString() : 'unknown time';

            messageDiv.innerHTML = `
                A previous scan was interrupted at ${tracks}/${total} tracks (${progress} complete).<br>
                Started: ${started}<br>
                Last processed: ${data.current_file || 'unknown'}
            `;

            // Show alert
            alertDiv.classList.remove('hidden');
        } else {
            // Hide alert
            alertDiv.classList.add('hidden');
        }
    } catch (error) {
        console.error('Failed to check partial scan:', error);
    }
}

// Handle continue partial scan
async function continuePartialScan() {
    try {
        const response = await fetch('/api/scan/partial-status');
        if (!response.ok) throw new Error('Failed to get partial scan info');

        const data = await response.json();
        if (!data.has_partial) {
            showToast('No partial scan found to continue', 'error');
            return;
        }

        // Start scan with resume capability (existing startScan function will handle resume)
        await startScan(false, true); // false = full scan, true = resume mode

        // Hide alert
        document.getElementById('partial-scan-alert').classList.add('hidden');
    } catch (error) {
        console.error('Failed to continue partial scan:', error);
        showToast('Failed to continue partial scan', 'error');
    }
}

// Handle cancel partial scan
async function cancelPartialScan() {
    try {
        const response = await fetch('/api/scan/partial-status');
        if (!response.ok) throw new Error('Failed to get partial scan info');

        const data = await response.json();
        if (!data.has_partial) {
            showToast('No partial scan found to cancel', 'error');
            return;
        }

        // Cancel the partial scan
        const cancelResponse = await fetch('/api/scan/partial', {
            method: 'DELETE'
        });

        if (!cancelResponse.ok) {
            throw new Error('Failed to cancel partial scan');
        }

        showToast('Partial scan cancelled. You can now start a fresh scan.', 'success');

        // Hide alert and refresh
        document.getElementById('partial-scan-alert').classList.add('hidden');
        await checkPartialScan(); // Re-check in case there are other partial scans

    } catch (error) {
        console.error('Failed to cancel partial scan:', error);
        showToast('Failed to cancel partial scan', 'error');
    }
}

// Handle dismiss partial scan alert
function dismissPartialScan() {
    document.getElementById('partial-scan-alert').classList.add('hidden');
}

// Update scan history table with provided data (no API call needed)
async function updateScanHistoryTable(history) {
    const historyLoading = document.getElementById('scan-history-loading');
    const historyEmpty = document.getElementById('scan-history-empty');
    const historyTable = document.getElementById('scan-history-table');
    const historyBody = document.getElementById('scan-history-body');

    console.log('Updating history table with data:', history);

    // Clear loading state
    historyLoading.classList.add('hidden');

    if (!history || history.length === 0) {
        // Show empty state
        historyEmpty.classList.remove('hidden');
        historyTable.classList.add('hidden');
    } else {
        // Show table with history
        historyEmpty.classList.add('hidden');
        historyTable.classList.remove('hidden');

        // Clear existing rows
        historyBody.innerHTML = '';

        // Add history rows
        history.forEach(scan => {
            const row = document.createElement('tr');
            row.className = 'hover:bg-gray-50';

            const date = scan.completed_at ? formatFriendlyDate(scan.completed_at) : 'Unknown';
            const type = scan.max_tracks === 10 ? 'Test Scan' : 'Full Scan';
            const tracks = scan.processed_tracks || 0;
            const duration = formatDuration(scan.duration_seconds);
            const status = scan.status === 'completed' ? '✅ Completed' : scan.status || 'Unknown';

            row.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${date}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${type}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${tracks}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${duration}</td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${status}</td>
            `;

            historyBody.appendChild(row);
        });

        // Update time estimate after history table is updated
        await updateFullScanTimeEstimate();
    }
}

// Populate the library mapping form for scan library page
async function populateScanLibraryMappingForm() {
    console.log('🎵 Populating library mapping form for scan library page...');

    try {
        // Get configured paths
        const pathsResponse = await fetch('/api/library-paths');
        const pathsData = await pathsResponse.json();
        const paths = pathsData.paths || [];

        // Get available libraries from Navidrome
        const librariesResponse = await fetch('/api/music-folders');
        const libraries = await librariesResponse.json();

        // Get current mappings
        const mappingsResponse = await fetch('/api/library-mappings');
        const mappingsData = await mappingsResponse.json();
        const currentMappings = {};
        mappingsData.mappings.forEach(m => {
            currentMappings[m.music_path] = m.library_id;
        });

        console.log(`📍 Found ${paths.length} paths and ${libraries.length} libraries`);

        // Build form
        const container = document.getElementById('scan-library-mappings-container');
        if (!container) return;

        container.innerHTML = '';

        // Create a row for each path
        paths.forEach((path, index) => {
            const currentLibraryId = currentMappings[path];

            container.innerHTML += `
                <div class="flex gap-3 items-center">
                    <div class="w-20 text-sm font-medium text-gray-600 flex-shrink-0">
                        Path ${index + 1}:
                    </div>
                    <div class="w-32 text-sm text-gray-600 px-3 py-2 bg-white rounded font-mono flex-shrink-0 truncate border border-gray-300">
                        ${path}
                    </div>
                    <select class="scan-library-selector flex-1 max-w-xs px-3 py-2 border border-gray-300 rounded text-sm bg-white text-gray-800" data-path="${path}" data-index="${index}">
                        <option value="">← Select library</option>
                        ${libraries.map(lib => `<option value="${lib.id}" ${currentLibraryId && String(currentLibraryId) === String(lib.id) ? 'selected' : ''}>${lib.name} (ID: ${lib.id})</option>`).join('')}
                    </select>
                </div>
            `;
        });

        // Add event listeners
        const selectors = container.querySelectorAll('.scan-library-selector');
        selectors.forEach(selector => {
            selector.addEventListener('change', updateScanLibraryAvailability);
        });

        console.log('✅ Library mapping form populated for scan library page');
    } catch (error) {
        console.error('Error populating library mapping form for scan page:', error);
    }
}

// Update library availability in scan library page
function updateScanLibraryAvailability() {
    const selectors = document.querySelectorAll('.scan-library-selector');
    const selectedLibraries = new Set();

    selectors.forEach(selector => {
        if (selector.value) {
            selectedLibraries.add(selector.value);
        }
    });

    selectors.forEach(selector => {
        const currentValue = selector.value;
        const options = selector.querySelectorAll('option');

        options.forEach(option => {
            if (option.value === '' || option.value === currentValue) {
                option.disabled = false;
            } else if (selectedLibraries.has(option.value)) {
                option.disabled = true;
            } else {
                option.disabled = false;
            }
        });
    });
}

// Save library mappings from scan library page
async function saveScanLibraryMappings() {
    console.log('💾 Saving library mappings from scan library page...');

    try {
        const selectors = document.querySelectorAll('.scan-library-selector');
        const mappings = [];
        let hasError = false;

        selectors.forEach(selector => {
            if (!selector.value) {
                hasError = true;
                selector.classList.add('border-red-500', 'bg-red-50');
                return;
            }
            selector.classList.remove('border-red-500', 'bg-red-50');

            mappings.push({
                library_id: selector.value,
                music_path: selector.dataset.path
            });
        });

        if (hasError) {
            showToast('error', 'Please select a library for each path');
            return;
        }

        // Save all mappings
        let successCount = 0;
        for (const mapping of mappings) {
            try {
                const response = await fetch(`/api/library-mappings/${mapping.library_id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ music_path: mapping.music_path })
                });

                if (response.ok) {
                    successCount++;
                }
            } catch (error) {
                console.error(`Error saving mapping:`, error);
            }
        }

        if (successCount === mappings.length) {
            showToast('success', `Successfully configured ${successCount} librar${successCount === 1 ? 'y' : 'ies'}!`);
            // Hide alert, refresh readiness, and rebuild library selector
            document.getElementById('scan-library-setup-alert').classList.add('hidden');
            await checkScanReadiness();
            await loadScanLibraries(); // Rebuild radio buttons with updated mappings
        } else {
            showToast('error', `Saved ${successCount}/${mappings.length} mappings. Please try again.`);
        }
    } catch (error) {
        console.error('Error saving library mappings from scan page:', error);
        showToast('error', 'Failed to save library mappings');
    }
}

// Check library mappings when scan library page becomes active
async function checkLibraryMappingsForScanPage() {
    console.log('🔍 Checking library mappings for scan library page...');

    try {
        const needsSetup = await checkLibraryMappingNeeded();
        console.log(`Library mapping needed: ${needsSetup}`);

        if (needsSetup) {
            // Show alert and populate form
            await populateScanLibraryMappingForm();
            const alert = document.getElementById('scan-library-setup-alert');
            if (alert) {
                alert.classList.remove('hidden');
                console.log('✅ Showed library setup alert on scan library page');
            }

            // Setup button handler
            const saveBtn = document.getElementById('scan-save-library-mappings-btn');
            if (saveBtn) {
                saveBtn.addEventListener('click', saveScanLibraryMappings);
            }
        } else {
            // Hide alert if it exists
            const alert = document.getElementById('scan-library-setup-alert');
            if (alert) {
                alert.classList.add('hidden');
                console.log('✅ Hid library setup alert (mappings exist)');
            }
        }
    } catch (error) {
        console.error('Error checking library mappings for scan page:', error);
    }
}

// Setup scan event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', async function() {
    // Check library mappings first
    await checkLibraryMappingsForScanPage();

    // Setup scan library event listeners
    const testScanBtn = document.getElementById('test-scan-btn');
    const fullScanBtn = document.getElementById('full-scan-btn');
    const cancelScanBtn = document.getElementById('cancel-scan-btn');

    if (testScanBtn) {
        testScanBtn.addEventListener('click', () => startScan(true));
    }
    if (fullScanBtn) {
        fullScanBtn.addEventListener('click', () => startScan(false));
    }
    if (cancelScanBtn) {
        cancelScanBtn.addEventListener('click', cancelScan);
    }

    // Partial scan alert buttons
    const continuePartialBtn = document.getElementById('continue-partial-btn');
    const cancelPartialBtn = document.getElementById('cancel-partial-btn');
    const dismissPartialBtn = document.getElementById('dismiss-partial-btn');

    if (continuePartialBtn) {
        continuePartialBtn.addEventListener('click', continuePartialScan);
    }
    if (cancelPartialBtn) {
        cancelPartialBtn.addEventListener('click', cancelPartialScan);
    }
    if (dismissPartialBtn) {
        dismissPartialBtn.addEventListener('click', dismissPartialScan);
    }
});

// Danger Zone functions
async function toggleDangerZone() {
    const content = document.getElementById('danger-zone-content');
    const icon = document.getElementById('danger-zone-icon');

    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        icon.classList.add('rotate-180');
        // Load current count when opening
        await updateSonicProfilesCount();
    } else {
        content.classList.add('hidden');
        icon.classList.remove('rotate-180');
    }
}

async function updateSonicProfilesCount() {
    try {
        const response = await fetch('/api/radio/analyzed-tracks');
        if (response.ok) {
            const data = await response.json();
            const count = data.tracks.length;
            const button = document.getElementById('erase-profiles-btn');
            if (button) {
                button.textContent = `Erase all Sonic Profiles (${count})`;
            }
        }
    } catch (error) {
        console.warn('Failed to get sonic profiles count:', error);
    }
}

async function eraseSonicProfiles() {
    // Browser confirmation dialog
    const confirmed = confirm(
        '⚠️ WARNING: This will permanently delete ALL sonic analysis data!\n\n' +
        'This includes:\n' +
        '• All audio embeddings\n' +
        '• All track analysis results\n' +
        '• All similarity data\n\n' +
        'This action CANNOT be undone.\n\n' +
        'Are you absolutely sure you want to continue?'
    );

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch('/api/admin/erase-chroma-db', {
            method: 'POST'
        });

        if (response.ok) {
            showToast('success', 'All sonic profiles have been erased successfully.');
            // Update the count to 0
            const button = document.getElementById('erase-profiles-btn');
            if (button) {
                button.textContent = 'Erase all Sonic Profiles (0)';
            }
            // Update the library summary to show 0 analyzed tracks
            const summaryScannedElement = document.getElementById('summary-scanned-tracks');
            if (summaryScannedElement) {
                summaryScannedElement.textContent = '0';
            }
            // Refresh scan readiness to update UI
            await checkScanReadiness();
        } else {
            const errorData = await response.json();
            showToast('error', `Failed to erase sonic profiles: ${errorData.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Error erasing sonic profiles:', error);
        showToast('error', 'Failed to erase sonic profiles. Please try again.');
    }
}

// Make functions globally available for onclick handlers
window.toggleDangerZone = toggleDangerZone;
window.eraseSonicProfiles = eraseSonicProfiles;

// Export functions for use by other modules
export {
    checkLibraryMappingsForScanPage,
    toggleDangerZone,
    updateSonicProfilesCount,
    eraseSonicProfiles,
    startSummarySpinner,
    stopSummarySpinner
};