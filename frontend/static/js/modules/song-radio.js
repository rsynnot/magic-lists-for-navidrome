/**
 * Song Radio Module
 * Handles song search, selection, and radio playlist creation
 */

import { formatTrackTitle, formatTrackTitleHTML, showToast } from '../core/utils.js';

// Global state for song radio
let selectedSeedSongId = null;
window.selectedSeedSongId = null;

// Export state and functions
export {
    selectedSeedSongId,
    initializeSongRadioPage,
    initializeSongRadio,
    loadSongRadioScanStatus,
    setupPlaylistLengthRadios,
    setupTraditionalSongSearch,
    performTraditionalSongSearch,
    showSearchDropdown,
    hideSearchDropdown,
    showSearchLoading,
    showSearchError,
    displaySearchResults,
    handleSearchKeyNavigation,
    highlightSearchResult,
    selectTrack,
    clearTrackSelection
};

// Initialize song radio page
async function initializeSongRadioPage() {
    try {
        // Import library manager to load libraries
        const { loadLibraries } = await import('./library-manager.js');
        await loadLibraries();

        // Load scan status for selected libraries
        await loadSongRadioScanStatus();

        // Initialize song radio with search functionality
        await initializeSongRadio();
    } catch (error) {
        console.error('Error initializing song radio page:', error);
        showToast('error', 'Failed to initialize song radio page');
    }
}

// Load scan status for song radio (tracks from selected libraries only)
async function loadSongRadioScanStatus() {
    const { selectedLibraryIds } = await import('./library-manager.js');

    if (selectedLibraryIds.length === 0) {
        const statusElement = document.getElementById('song-radio-scan-status');
        statusElement.textContent = 'Please select libraries in the sidebar to view scan status.';
        return;
    }

    try {
        // Get total track count for selected libraries from stats API (accurate totals)
        let totalLibraryTracks = 0;
        for (const libraryId of selectedLibraryIds) {
            try {
                const statsResponse = await fetch(`/api/libraries/${libraryId}/stats`);
                if (statsResponse.ok) {
                    const stats = await statsResponse.json();
                    totalLibraryTracks += stats.total_tracks || 0;
                }
            } catch (error) {
                console.warn(`Failed to get stats for library ${libraryId}:`, error);
            }
        }

        // Get analyzed tracks for each selected library and combine
        let allSelectedAnalyzedTracks = [];
        for (const libraryId of selectedLibraryIds) {
            try {
                const analyzedResponse = await fetch(`/api/radio/analyzed-tracks?library_id=${libraryId}`);
                if (analyzedResponse.ok) {
                    const analyzedData = await analyzedResponse.json();
                    allSelectedAnalyzedTracks = allSelectedAnalyzedTracks.concat(analyzedData.tracks);
                }
            } catch (error) {
                console.warn(`Failed to get analyzed tracks for library ${libraryId}:`, error);
            }
        }

        // Count all analyzed tracks from selected libraries
        const scannedTrackCount = allSelectedAnalyzedTracks.length;

        // Update the info box with conditional logic
        const statusElement = document.getElementById('song-radio-scan-status');
        const infoBox = document.getElementById('song-radio-scan-info');
        const iconElement = infoBox.querySelector('svg');

        if (scannedTrackCount === 0) {
            // None scanned - warning style
            infoBox.className = 'bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4';
            statusElement.className = 'text-sm text-yellow-800';
            iconElement.outerHTML = '<svg class="shrink-0 size-4 mt-0.5 text-yellow-800" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>';
            statusElement.innerHTML = 'No tracks are ready to use. <a href="#" data-page="scan-library" class="text-yellow-800 hover:text-yellow-900 underline">Run Sonic Analysis</a>';
        } else {
            // Some or all scanned - info style
            infoBox.className = 'bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4';
            statusElement.className = 'text-sm text-blue-800';
            iconElement.outerHTML = '<svg class="h-5 w-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd" /></svg>';

            if (scannedTrackCount === totalLibraryTracks) {
                // All scanned
                statusElement.textContent = 'All tracks are ready to use for playlists.';
            } else {
                // Some scanned
                const percentage = Math.round((scannedTrackCount / totalLibraryTracks) * 100);
                statusElement.innerHTML = `${scannedTrackCount} tracks (${percentage}% of ${totalLibraryTracks}) are ready to use for playlists. <a href="#" data-page="scan-library" class="text-blue-600 hover:text-blue-800 underline">Run Sonic Analysis</a>`;
            }
        }

    } catch (error) {
        console.error('Error loading scan status:', error);
        const statusElement = document.getElementById('song-radio-scan-status');
        statusElement.textContent = 'Unable to load scan status. Please ensure your libraries have been scanned.';
    }
}

// Initialize song radio search functionality
async function initializeSongRadio() {
    try {
        const searchInput = document.getElementById('seed-song-search');
        const dropdown = document.getElementById('song-search-dropdown');
        const resultsContainer = document.getElementById('song-search-results');

        if (!searchInput || !dropdown || !resultsContainer) return;

        // Setup search functionality
        setupTraditionalSongSearch(searchInput, dropdown, resultsContainer);

        // Setup clear selection button
        const clearBtn = document.getElementById('clear-track-selection');
        if (clearBtn) {
            clearBtn.addEventListener('click', clearTrackSelection);
        }

        // Setup playlist length radio button styling
        setupPlaylistLengthRadios();

        // Setup click outside to close dropdown (page-specific)
        const songRadioClickHandler = function(e) {
            const container = document.getElementById('song-search-container');
            if (container && !container.contains(e.target)) {
                hideSearchDropdown();
            }
        };
        document.addEventListener('click', songRadioClickHandler);

        // Store handler reference for cleanup
        window.songRadioClickHandler = songRadioClickHandler;

        console.log('Song radio initialized with traditional search functionality');
    } catch (error) {
        console.error('Error initializing song radio:', error);
        showToast('error', 'Failed to initialize song radio');
    }
}

// Setup playlist length radio button visual styling
function setupPlaylistLengthRadios() {
    const radioButtons = document.querySelectorAll('input[name="radio-playlist-length"]');
    const radioGroup = document.getElementById('radio-playlist-length-group');

    if (!radioButtons.length || !radioGroup) return;

    // Function to update visual styling
    function updateRadioStyling() {
        const listItems = radioGroup.querySelectorAll('li');

        listItems.forEach((li, index) => {
            const radio = li.querySelector('input[type="radio"]');
            if (radio && radio.checked) {
                // Selected item - blue styling
                li.classList.add('bg-blue-100', 'border-blue-200', 'text-blue-800');
                li.classList.remove('bg-white', 'border-gray-200', 'text-gray-800');
                // Also update the label text color
                const label = li.querySelector('label');
                if (label) {
                    label.classList.add('text-blue-800');
                    label.classList.remove('text-gray-600');
                }
            } else {
                // Unselected items - default styling
                li.classList.remove('bg-blue-100', 'border-blue-200', 'text-blue-800');
                li.classList.add('bg-white', 'border-gray-200', 'text-gray-800');
                // Also update the label text color
                const label = li.querySelector('label');
                if (label) {
                    label.classList.remove('text-blue-800');
                    label.classList.add('text-gray-600');
                }
            }
        });
    }

    // Add change event listeners to all radio buttons
    radioButtons.forEach(radio => {
        radio.addEventListener('change', updateRadioStyling);
    });

    // Initial styling update
    updateRadioStyling();
}

// Setup traditional search functionality
function setupTraditionalSongSearch(searchInput, dropdown, resultsContainer) {
    let searchTimeout;
    let currentSearch = '';

    // Handle input focus
    searchInput.addEventListener('focus', function() {
        // If we have a selected track, clear it on focus to allow new search
        if (selectedSeedSongId && this.value) {
            this.value = '';
            this.placeholder = 'Search for a track or artist...';
            this.classList.remove('text-gray-900');
            this.classList.add('text-gray-500');

            // Hide clear button
            const clearBtn = document.getElementById('clear-track-selection');
            if (clearBtn) {
                clearBtn.classList.add('hidden');
            }

            // Clear hidden input and global state
            const hiddenInput = document.getElementById('selected-seed-track-id');
            if (hiddenInput) {
                hiddenInput.value = '';
            }
            selectedSeedSongId = null;

            // Disable submit button
            const submitBtn = document.getElementById('create-radio-playlist-btn');
            if (submitBtn) {
                submitBtn.disabled = true;
            }
        } else if (this.value === '') {
            // Clear placeholder on focus if empty
            this.placeholder = '';
        }
    });

    // Handle input blur
    searchInput.addEventListener('blur', function() {
        // Restore placeholder if empty and no selection
        if (this.value === '' && !selectedSeedSongId) {
            this.placeholder = 'Search for a track or artist...';
        }

        // Hide dropdown after a short delay to allow clicking on results
        setTimeout(() => {
            if (!dropdown.matches(':hover')) {
                hideSearchDropdown();
            }
        }, 150);
    });

    // Handle input changes
    searchInput.addEventListener('input', function(e) {
        const query = e.target.value.trim();

        // Clear previous timeout
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }

        // If query is 3+ characters, perform search
        if (query.length >= 3) {
            searchTimeout = setTimeout(() => {
                performTraditionalSongSearch(query, resultsContainer);
            }, 300); // Debounce for 300ms
        } else {
            // Hide dropdown if query is too short
            hideSearchDropdown();
        }
    });

    // Handle keyboard navigation
    searchInput.addEventListener('keydown', function(e) {
        handleSearchKeyNavigation(e, resultsContainer);
    });
}

// Perform search for songs using API
async function performTraditionalSongSearch(query, resultsContainer) {
    try {
        console.log(`Searching for tracks with query: "${query}"`);

        // Show loading state
        showSearchLoading(resultsContainer);
        showSearchDropdown();

        const response = await fetch(`/api/radio/search-tracks?q=${encodeURIComponent(query)}&limit=50`);
        if (!response.ok) {
            throw new Error('Failed to search songs');
        }

        const data = await response.json();
        const searchResults = data.tracks || [];

        console.log(`Found ${searchResults.length} tracks matching "${query}"`);

        // Display results
        displaySearchResults(searchResults, resultsContainer);

    } catch (error) {
        console.error('Error searching songs:', error);
        showToast('error', 'Failed to search songs');

        // Show error state
        showSearchError(resultsContainer);
    }
}

// Show search dropdown
function showSearchDropdown() {
    const dropdown = document.getElementById('song-search-dropdown');
    if (dropdown) {
        dropdown.style.display = 'block';
    }
}

// Hide search dropdown
function hideSearchDropdown() {
    const dropdown = document.getElementById('song-search-dropdown');
    if (dropdown) {
        dropdown.style.display = 'none';
    }
}

// Show loading state in search results
function showSearchLoading(resultsContainer) {
    resultsContainer.innerHTML = `
        <div class="p-4 text-center text-sm text-gray-500">
            <div class="inline-flex items-center">
                <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Searching...
            </div>
        </div>
    `;
}

// Show error state in search results
function showSearchError(resultsContainer) {
    resultsContainer.innerHTML = `
        <div class="p-4 text-center text-sm text-red-500">
            Error loading search results
        </div>
    `;
}

// Display search results
function displaySearchResults(results, resultsContainer) {
    if (results.length === 0) {
        resultsContainer.innerHTML = `
            <div class="p-4 text-center text-sm text-gray-500">
                No tracks found
            </div>
        `;
        return;
    }

    const resultsHTML = results.map((song, index) => {
        const displayText = formatTrackTitle(song.title, song.artist);
        const displayHTML = formatTrackTitleHTML(song.title, song.artist);

        return `
            <div class="search-result-item flex items-center cursor-pointer py-2 px-4 w-full text-sm text-gray-800 hover:bg-gray-100"
                 data-track-id="${song.id}"
                 data-track-title="${song.title}"
                 data-track-artist="${song.artist}"
                 tabindex="0">
                <div class="flex items-center w-full">
                    <div class="flex-1 min-w-0">
                        <div class="truncate font-medium">${displayHTML}</div>
                    </div>
                    <div class="hidden hs-combo-box-selected:block flex-shrink-0 ml-2">
                        <svg class="size-3.5 text-blue-600" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    resultsContainer.innerHTML = resultsHTML;

    // Add click handlers to result items
    resultsContainer.querySelectorAll('.search-result-item').forEach(item => {
        item.addEventListener('click', function() {
            selectTrack(this);
        });
    });
}

// Handle keyboard navigation in search results
function handleSearchKeyNavigation(e, resultsContainer) {
    const items = resultsContainer.querySelectorAll('.search-result-item');
    if (items.length === 0) return;

    let currentIndex = -1;
    const highlightedItem = resultsContainer.querySelector('.bg-gray-100');
    if (highlightedItem) {
        currentIndex = Array.from(items).indexOf(highlightedItem);
    }

    switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            currentIndex = Math.min(currentIndex + 1, items.length - 1);
            highlightSearchResult(items, currentIndex);
            break;
        case 'ArrowUp':
            e.preventDefault();
            currentIndex = Math.max(currentIndex - 1, 0);
            highlightSearchResult(items, currentIndex);
            break;
        case 'Enter':
            e.preventDefault();
            if (currentIndex >= 0 && items[currentIndex]) {
                selectTrack(items[currentIndex]);
            }
            break;
        case 'Escape':
            hideSearchDropdown();
            break;
    }
}

// Highlight search result item
function highlightSearchResult(items, index) {
    // Remove previous highlights
    items.forEach(item => item.classList.remove('bg-gray-100'));

    // Add highlight to current item
    if (items[index]) {
        items[index].classList.add('bg-gray-100');
        items[index].scrollIntoView({ block: 'nearest' });
    }
}

// Select a track from search results
function selectTrack(item) {
    const trackId = item.dataset.trackId;
    const trackTitle = item.dataset.trackTitle;
    const trackArtist = item.dataset.trackArtist;

    // Update hidden input
    const hiddenInput = document.getElementById('selected-seed-track-id');
    if (hiddenInput) {
        hiddenInput.value = trackId;
    }

    // Show selected track in search field
    const searchInput = document.getElementById('seed-song-search');
    const clearBtn = document.getElementById('clear-track-selection');

    if (searchInput) {
        const displayText = formatTrackTitle(trackTitle, trackArtist);
        searchInput.value = displayText;
        searchInput.classList.add('text-gray-900');
        searchInput.classList.remove('text-gray-500');
    }

    // Show clear button
    if (clearBtn) {
        clearBtn.classList.remove('hidden');
    }

    // Hide dropdown
    hideSearchDropdown();

    // Update global state
    selectedSeedSongId = trackId;
    window.selectedSeedSongId = trackId;

    // Enable submit button
    const submitBtn = document.getElementById('create-radio-playlist-btn');
    if (submitBtn) {
        submitBtn.disabled = false;
    }

    console.log(`Selected track: ${trackTitle} by ${trackArtist} (ID: ${trackId})`);
}

// Clear track selection
function clearTrackSelection() {
    // Clear hidden input
    const hiddenInput = document.getElementById('selected-seed-track-id');
    if (hiddenInput) {
        hiddenInput.value = '';
    }

    // Clear search input and restore placeholder
    const searchInput = document.getElementById('seed-song-search');
    const clearBtn = document.getElementById('clear-track-selection');

    if (searchInput) {
        searchInput.value = '';
        searchInput.placeholder = 'Search for a song or artist...';
        searchInput.classList.remove('text-gray-900');
        searchInput.classList.add('text-gray-500');
    }

    // Hide clear button
    if (clearBtn) {
        clearBtn.classList.add('hidden');
    }

    // Hide dropdown
    hideSearchDropdown();

    // Update global state
    selectedSeedSongId = null;
    window.selectedSeedSongId = null;

    // Disable submit button
    const submitBtn = document.getElementById('create-radio-playlist-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
    }

    console.log('Cleared track selection');
}