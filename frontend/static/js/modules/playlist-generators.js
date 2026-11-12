/**
 * Playlist Generators for Magic Lists
 * Handles all 4 playlist types: This Is Artist, Genre Mix, Song Radio, Re-Discover
 */

import { showToast, hideToast, formatFriendlyDate } from '../core/utils.js';

// Global state for playlist generators
let selectedArtistId = null;

let allArtists = [];
let allGenres = [];
// selectedSeedSongId is now global from song-radio.js
let allAnalyzedSongs = [];

/**
 * Handle artist selection change
 * @param {Event} e - Change event
 */
export function handleArtistSelection(e) {
    selectedArtistId = e.target.value;
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (selectedArtistId) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

/**
 * Create "This Is Artist" playlist
 */
export async function createArtistPlaylist() {
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (!selectedArtistId) {
        showToast('error', 'Please select an artist first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="thisis-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="thisis-playlist-length"]:checked').value;
        const includeMentionsCheckbox = document.getElementById('thisis-include-mentions');
        const includeMentions = includeMentionsCheckbox ? includeMentionsCheckbox.checked : false;
        
        console.log('DEBUG: includeMentionsCheckbox element:', includeMentionsCheckbox);
        console.log('DEBUG: includeMentions value:', includeMentions);

        const response = await fetch('/api/create_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_ids: [selectedArtistId],
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: window.selectedLibraryIds || [],
                include_mentions: includeMentions
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();
        hideToast('loading');
        showToast('success', `Successfully created "${data.name}" playlist!`);
        
        // Update playlist count
        if (window.updatePlaylistCount) {
            window.updatePlaylistCount();
        }

    } catch (error) {
        console.error('Error creating playlist:', error);
        hideToast('loading');
        showToast('error', error.message);
        submitBtn.disabled = false;
    }
}

/**
 * Handle genre selection change
 * @param {Event} e - Change event
 */
export function handleGenreSelection(e) {
    window.selectedGenre = e.target.value;
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (window.selectedGenre) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

/**
 * Create "Genre Mix" playlist
 */
export async function createGenrePlaylist() {
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (!window.selectedGenre) {
        showToast('error', 'Please select a genre first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="genre-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="genre-playlist-length"]:checked').value;

        const response = await fetch('/api/create_genre_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                genre: window.selectedGenre,
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: window.selectedLibraryIds || []
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            let errorMessage = 'Failed to create playlist';
            if (typeof errorData.detail === 'string') {
                errorMessage = errorData.detail;
            } else if (errorData.detail && typeof errorData.detail === 'object') {
                errorMessage = JSON.stringify(errorData.detail);
            } else if (errorData.message) {
                errorMessage = errorData.message;
            }
            throw new Error(errorMessage);
        }

        const data = await response.json();
        hideToast('loading');
        showToast('success', `Successfully created "${data.name}" playlist!`);

        // Update playlist count
        if (window.updatePlaylistCount) {
            window.updatePlaylistCount();
        }

    } catch (error) {
        console.error('Error creating playlist:', error);
        hideToast('loading');
        showToast('error', error.message);
        submitBtn.disabled = false;
    }
}

/**
 * Create "Song Radio" playlist
 */
export async function createRadioPlaylist() {
    const submitBtn = document.getElementById('create-radio-playlist-btn');

    if (!window.selectedSeedSongId) {
        showToast('error', 'Please select a starting track first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const playlistLength = document.querySelector('input[name="radio-playlist-length"]:checked').value;

        const refreshFrequency = document.querySelector('input[name="radio-refresh-frequency"]:checked').value;

        const response = await fetch('/api/radio/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                seed_track_id: window.selectedSeedSongId,
                num_tracks: parseInt(playlistLength),
                refresh_frequency: refreshFrequency
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();
        hideToast('loading');
        showToast('success', `Created "${data.name}" with ${data.total_tracks} tracks`);

        // Update playlist count
        if (window.updatePlaylistCount) {
            window.updatePlaylistCount();
        }

    } catch (error) {
        console.error('Error creating playlist:', error);
        hideToast('loading');
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

/**
 * Generate "Re-Discover Weekly" playlist
 */
export async function generateRediscoverWeekly() {
    const submitBtn = document.getElementById('rediscover-generate-btn');

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Generating your weekly rediscovery...', 0);
    submitBtn.disabled = true;

    try {
        const response = await fetch('/api/create_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                recipe_name: 're_discover_phase2_v2',
                library_ids: window.selectedLibraryIds || []
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            console.log('API error response:', response.status, errorData);
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();
        hideToast('loading');
        showToast('success', `Successfully generated "${data.name}" playlist!`);
        
        // Update playlist count
        if (window.updatePlaylistCount) {
            window.updatePlaylistCount();
        }

    } catch (error) {
        console.error('Error generating rediscovery:', error);
        hideToast('loading');
        showToast('error', error.message);
        submitBtn.disabled = false;
    }
}

/**
 * Load artists and populate the select dropdown
 */
export async function loadArtists() {
    try {
        let url = '/api/artists';
        if (window.selectedLibraryIds && window.selectedLibraryIds.length > 0) {
            const libraryIdsParam = window.selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/artists?${libraryIdsParam}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch artists');
        }
        allArtists = await response.json();

        // Clear any previous selection
        selectedArtistId = null;

        // Populate the select dropdown
        const artistSelect = document.getElementById('artist-search-select');
        if (artistSelect) {
            // Clear existing options except the first one
            while (artistSelect.options.length > 1) {
                artistSelect.remove(1);
            }

            // Add artist options
            allArtists.forEach(artist => {
                const option = document.createElement('option');
                option.value = artist.id;
                option.textContent = artist.name;
                artistSelect.appendChild(option);
            });

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                const selectInstance = window.HSSelect.getInstance(artistSelect);
                if (selectInstance) {
                    selectInstance.destroy();
                }
                window.HSSelect.autoInit();
            }
        }
    } catch (error) {
        console.error('Error loading artists:', error);
        showToast('error', 'Failed to load artists from your library');
    }
}

/**
 * Load genres and populate the select dropdown
 */
export async function loadGenres() {
    try {
        let url = '/api/genres';
        if (window.selectedLibraryIds && window.selectedLibraryIds.length > 0) {
            const libraryIdsParam = window.selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/genres?${libraryIdsParam}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch genres');
        }
        allGenres = await response.json();

        // Get the genre select element
        const genreSelect = document.getElementById('genre-select');

        // Update the placeholder text to show genre count
        if (genreSelect && window.HSSelect) {
            const selectInstance = window.HSSelect.getInstance(genreSelect);
            if (selectInstance) {
                selectInstance.destroy();
            }

            // Update the data-hs-select attribute with new placeholder
            const newPlaceholder = `Select from ${allGenres.length} genres...`;
            genreSelect.setAttribute('data-hs-select', JSON.stringify({
                "placeholder": newPlaceholder,
                "toggleTag": "<button type=\"button\"></button>",
                "toggleClasses": "hs-select-disabled:pointer-events-none hs-select-disabled:opacity-50 relative py-3 px-4 pe-9 flex text-nowrap w-full cursor-pointer bg-white border border-gray-200 rounded-lg text-start text-sm focus:border-blue-500 focus:ring-blue-500 before:absolute before:inset-0 before:z-[1]",
                "dropdownClasses": "hs-select-dropdown mt-2 z-50 w-full max-h-72 p-1 space-y-0.5 bg-white border border-gray-200 rounded-lg overflow-hidden overflow-y-auto [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-track]:bg-gray-100 [&::-webkit-scrollbar-thumb]:bg-gray-300",
                "optionClasses": "py-2 px-4 w-full text-sm text-gray-800 cursor-pointer hover:bg-gray-100 rounded-lg focus:outline-none focus:bg-gray-100",
                "optionTemplate": "<div class=\"flex justify-between items-center w-full\"><span data-title></span><span class=\"hidden hs-selected:block\"><svg class=\"flex-shrink-0 size-3.5 text-blue-600\" xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><polyline points=\"20 6 9 17 4 12\"/></svg></span></div>",
                "hasSearch": true,
                "searchPlaceholder": "Search...",
                "searchClasses": "block w-full text-sm border-gray-200 rounded-lg focus:border-blue-500 focus:ring-blue-500 before:absolute before:inset-0 before:z-[1] py-2 px-3",
                "searchWrapperClasses": "bg-white p-2 -mx-1 sticky top-0"
            }));
        }

        // Clear any previous selection
        window.selectedGenre = null;

        // Populate the select dropdown
        if (genreSelect) {
            // Clear existing options except the first one
            while (genreSelect.options.length > 1) {
                genreSelect.remove(1);
            }

            // Add genre options
            allGenres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre.name;
                option.textContent = `${genre.name} (${genre.songCount})`;
                genreSelect.appendChild(option);
            });

            // Setup genre selection change handler
            genreSelect.addEventListener('change', handleGenreSelection);

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                window.HSSelect.autoInit();
            }
        }
    } catch (error) {
        console.error('Error loading genres:', error);
        showToast('error', 'Failed to load genres from your library');
    }
}

/**
 * Load playlists for management page
 */
export async function loadPlaylists() {
    const playlistContainer = document.getElementById('playlist-container');
    const loadingElement = document.getElementById('playlists-loading');
    const emptyElement = document.getElementById('playlists-empty');

    try {
        const response = await fetch('/api/playlists');
        if (!response.ok) {
            throw new Error('Failed to fetch playlists');
        }

        const playlists = await response.json();

        // Hide loading state
        if (loadingElement) loadingElement.classList.add('hidden');
        if (emptyElement) emptyElement.classList.add('hidden');

        if (playlists.length === 0) {
            // Show empty state
            if (emptyElement) emptyElement.classList.remove('hidden');
        } else {
            // Render playlists
            renderPlaylists(playlists);
        }

    } catch (error) {
        console.error('Error loading playlists:', error);
        if (loadingElement) loadingElement.classList.add('hidden');
        if (emptyElement) emptyElement.classList.remove('hidden');
        showToast('error', 'Failed to load playlists');
    }
}

/**
 * Render playlists in the management interface
 * @param {Array} playlists - Array of playlist objects
 */
export function renderPlaylists(playlists) {
    const playlistContainer = document.getElementById('playlist-container');
    if (!playlistContainer) return;

    playlistContainer.innerHTML = '';

    playlists.forEach(playlist => {
        const playlistCard = document.createElement('div');
        playlistCard.className = 'bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow';
        
        const createdDate = formatFriendlyDate(playlist.created_at);
        const refreshText = playlist.refresh_frequency === 'none' ? 'No refresh' : 
                           playlist.refresh_frequency === 'daily' ? 'Daily' :
                           playlist.refresh_frequency === 'weekly' ? 'Weekly' : 'Monthly';

        playlistCard.innerHTML = `
            <div class="flex justify-between items-start mb-4">
                <div>
                    <h3 class="text-lg font-semibold text-gray-900">${playlist.name}</h3>
                    <p class="text-sm text-gray-600 mt-1">${playlist.description || 'No description'}</p>
                </div>
                <div class="flex gap-2">
                    <button onclick="window.location.href='${playlist.external_url}'" 
                            class="inline-flex items-center gap-x-2 px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors">
                        <svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 18V5l12-2v13"/>
                            <circle cx="6" cy="18" r="3"/>
                            <circle cx="18" cy="16" r="3"/>
                        </svg>
                        Open in Navidrome
                    </button>
                    <button onclick="deletePlaylist('${playlist.id}', '${playlist.name.replace(/'/g, "\\'")}')" 
                            class="inline-flex items-center gap-x-2 px-3 py-2 text-sm font-medium text-red-600 hover:text-red-700 border border-red-200 hover:border-red-300 rounded-lg transition-colors">
                        <svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 6h18"/>
                            <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                        </svg>
                        Delete
                    </button>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <div>
                    <span class="text-gray-500">Tracks:</span>
                    <span class="font-medium text-gray-900">${playlist.track_count || 0}</span>
                </div>
                <div>
                    <span class="text-gray-500">Created:</span>
                    <span class="font-medium text-gray-900">${createdDate}</span>
                </div>
                <div>
                    <span class="text-gray-500">Refresh:</span>
                    <span class="font-medium text-gray-900">${refreshText}</span>
                </div>
            </div>
        `;

        playlistContainer.appendChild(playlistCard);
    });
}

/**
 * Delete a playlist
 * @param {string} playlistId - ID of playlist to delete
 * @param {string} playlistName - Name of playlist for confirmation
 */
export async function deletePlaylist(playlistId, playlistName) {
    if (!confirm(`Are you sure you want to delete "${playlistName}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/playlists/${playlistId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('Failed to delete playlist');
        }

        showToast('success', `Successfully deleted "${playlistName}"`);
        
        // Reload playlists
        loadPlaylists();
        
        // Update playlist count
        if (window.updatePlaylistCount) {
            window.updatePlaylistCount();
        }

    } catch (error) {
        console.error('Error deleting playlist:', error);
        showToast('error', 'Failed to delete playlist');
    }
}

/**
 * Update playlist count display
 */
export async function updatePlaylistCount() {
    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            const playlists = await response.json();
            const countElement = document.getElementById('playlist-count');
            if (countElement) {
                countElement.textContent = playlists.length;
            }
        }
    } catch (error) {
        console.error('Error updating playlist count:', error);
    }
}

/**
 * Check if libraries are selected
 * @returns {boolean} True if libraries are selected
 */
function checkLibrarySelection() {
    if (!window.selectedLibraryIds || window.selectedLibraryIds.length === 0) {
        showToast('warning', 'Please select music libraries first.');
        return false;
    }
    return true;
}

/**
 * Make functions globally available
 */
export function initializePlaylistGenerators() {
    window.handleArtistSelection = handleArtistSelection;

    window.handleGenreSelection = handleGenreSelection;
    window.createGenrePlaylist = createGenrePlaylist;
    window.createRadioPlaylist = createRadioPlaylist;
    window.generateRediscoverWeekly = generateRediscoverWeekly;
    window.loadArtists = loadArtists;
    window.loadGenres = loadGenres;
    window.loadPlaylists = loadPlaylists;
    window.deletePlaylist = deletePlaylist;
    window.updatePlaylistCount = updatePlaylistCount;
}
