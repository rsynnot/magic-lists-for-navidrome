/**
 * Playlist Manager Module
 * Handles all playlist creation, loading, and management functionality
 */

import { formatFriendlyDate, showToast } from '../core/utils.js';
import { getAIModelInfo } from './analytics.js';

// Global state for playlist management
let allArtists = [];
let allGenres = [];

// Export state and functions
export {
    allArtists,
    allGenres,
    loadArtists,
    loadGenres,
    handleArtistSelection,
    handleGenreSelection,
    createArtistPlaylist,
    createGenrePlaylist,
    createRadioPlaylist,
    generateRediscoverWeekly,
    loadPlaylists,
    renderPlaylists,
    deletePlaylist,
    updatePlaylistCount,
    formatNextRefresh
};

// Load artists and populate the select dropdown
async function loadArtists(libraryIds = null) {
    try {
        const { selectedLibraryIds } = await import('./library-manager.js');
        const libsToUse = libraryIds || selectedLibraryIds;

        console.log('🎨 loadArtists called, libraryIds:', libsToUse);
        let url = '/api/artists';
        if (libsToUse.length > 0) {
            const libraryIdsParam = libsToUse.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/artists?${libraryIdsParam}`;
        }
        console.log('🎨 Fetching artists from URL:', url);
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch artists');
        }
        allArtists = await response.json();
        console.log('🎨 Loaded artists:', allArtists.length, 'artists');

        // Clear any previous selection
        window.selectedArtistId = null;

        // Populate the select dropdown
        const artistSelect = document.getElementById('artist-search-select');
        console.log('🎨 Artist select element found:', !!artistSelect);
        if (artistSelect) {
            // Update the placeholder text to show artist count
            if (artistSelect && window.HSSelect) {
                const selectInstance = window.HSSelect.getInstance(artistSelect);
                if (selectInstance) {
                    selectInstance.destroy();
                }

                // Update the data-hs-select attribute with new placeholder
                const newPlaceholder = `Select from ${allArtists.length} artists...`;
                artistSelect.setAttribute('data-hs-select', JSON.stringify({
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

            // Clear existing options except the first one
            while (artistSelect.options.length > 1) {
                artistSelect.remove(1);
            }

            // Add artist options
            allArtists.forEach(artist => {
                const option = document.createElement('option');
                option.value = artist.id;
                const albumCount = artist.albumCount || 0;
                const albumText = albumCount === 1 ? 'album' : 'albums';
                option.textContent = `${artist.name} (${albumCount} ${albumText})`;
                artistSelect.appendChild(option);
            });

            // Attach change event to handle artist selection before HSSelect init
            artistSelect.addEventListener('change', (e) => {
                window.selectedArtistId = e.target.value;
                const createBtn = document.getElementById('create-artist-playlist-btn');
                if (createBtn) {
                    createBtn.disabled = !window.selectedArtistId;
                }
            });
            artistSelect.addEventListener('input', (e) => {
                console.log('Artist input:', e.target.value);
                window.selectedArtistId = e.target.value;
                const createBtn = document.getElementById('create-artist-playlist-btn');
                if (createBtn) {
                    createBtn.disabled = !window.selectedArtistId;
                }
            });

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                window.HSSelect.autoInit();
            }

            // Disable create button since no artist is selected
            const createBtn = document.getElementById('create-artist-playlist-btn');
            if (createBtn) {
                createBtn.disabled = true;
            }
        }
    } catch (error) {
        console.error('Error loading artists:', error);
        showToast('error', 'Failed to load artists from your library');
    }
}

async function loadGenres(libraryIds = null) {
    console.log(`🎨 loadGenres called with libraryIds:`, libraryIds);
    try {
        const { allLibraries, selectedLibraryIds } = await import('./library-manager.js');
        const libsToUse = libraryIds || selectedLibraryIds;

        // In multi-library mode, if no libraries selected, show no genres
        if (allLibraries && allLibraries.length > 1 && (!libsToUse || libsToUse.length === 0)) {
            console.log('🎨 Multi-library mode with no selection - showing 0 genres');
            allGenres = [];
        } else {
            let url = '/api/genres';
            if (libsToUse && libsToUse.length > 0) {
                const libraryIdsParam = libsToUse.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
                url = `/api/genres?${libraryIdsParam}`;
            }
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error('Failed to fetch genres');
            }
            allGenres = await response.json();
        }
        console.log('🎨 Loaded genres:', allGenres.length, 'genres');

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
        console.log('🎨 Genre select element found:', !!genreSelect);

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

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                window.HSSelect.autoInit();
            }

            // Attach change event to handle genre selection
            genreSelect.addEventListener('change', handleGenreSelection);

            // Disable create button since no genre is selected
            const createBtn = document.getElementById('create-genre-playlist-btn');
            if (createBtn) {
                createBtn.disabled = true;
            }

            // Poll the select value to handle HSSelect selection
            setInterval(() => {
                const val = genreSelect.value;
                if (val !== (window.selectedGenre || '')) {
                    console.log('Polled genre:', val);
                    window.selectedGenre = val;
                    if (createBtn) {
                        createBtn.disabled = !window.selectedGenre;
                    }
                }
            }, 500);
        }
    } catch (error) {
        console.error('Error loading genres:', error);
        showToast('error', 'Failed to load genres from your library');
    }
}

// Handle genre selection change
function handleGenreSelection(e) {
    window.selectedGenre = e.target.value;
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (window.selectedGenre) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// Handle artist selection change
function handleArtistSelection(e) {
    window.selectedArtistId = e.target.value;
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (window.selectedArtistId) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// Create "This Is Artist" playlist
async function createArtistPlaylist() {
    console.log('createArtistPlaylist called, selectedArtistId:', window.selectedArtistId);
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (!window.selectedArtistId) {
        showToast('error', 'Please select an artist first');
        return;
    }

    const { checkLibrarySelection, selectedLibraryIds } = await import('./library-manager.js');
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
         
         console.log('DEBUG: createArtistPlaylist - includeMentions:', includeMentions);

         const response = await fetch('/api/create_playlist', {
             method: 'POST',
             headers: {
                 'Content-Type': 'application/json'
             },
             body: JSON.stringify({
                 artist_ids: [window.selectedArtistId],
                 refresh_frequency: refreshFrequency,
                 playlist_length: parseInt(playlistLength),
                 library_ids: selectedLibraryIds,
                 include_mentions: includeMentions
             })
         });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();

        // Track successful artist playlist creation with Rybbit
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('This Is Playlist Created', {
                trackCount: data.songs ? data.songs.length : 0,
                refreshFrequency: refreshFrequency,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider
            });
        }

        // Show success toast
        showToast('success', `Playlist created with ${data.songs ? data.songs.length : 0} tracks`);

        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error creating playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

// Create "Genre Mix" playlist
async function createGenrePlaylist() {
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (!window.selectedGenre) {
        showToast('error', 'Please select a genre first');
        return;
    }

    const { checkLibrarySelection, selectedLibraryIds } = await import('./library-manager.js');
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
                library_ids: selectedLibraryIds
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();

        // Track successful genre playlist creation with Rybbit
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('Genre Mix Playlist Created', {
                trackCount: data.songs ? data.songs.length : 0,
                refreshFrequency: refreshFrequency,
                genre: window.selectedGenre,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider
            });
        }

        // Show success toast
        showToast('success', `Successfully created "${data.name}" playlist!`);

        // Update playlist count in sidebar
        await updatePlaylistCount();

    } catch (error) {
        console.error('Error creating playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

// Create "Song Radio" playlist
async function createRadioPlaylist() {
    const submitBtn = document.getElementById('create-radio-playlist-btn');

    const { selectedSeedSongId } = await import('./song-radio.js');
    if (!selectedSeedSongId) {
        showToast('error', 'Please select a starting track first');
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your radio playlist...', 0);
    submitBtn.disabled = true;

    try {
        const playlistLength = document.querySelector('input[name="radio-playlist-length"]:checked').value;

        const response = await fetch('/api/radio/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                seed_track_id: selectedSeedSongId,
                num_tracks: parseInt(playlistLength)
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create radio playlist');
        }

        const data = await response.json();

        // Show success message
        showToast('success', `Radio playlist created! "${data.playlist_name}" with ${data.total_tracks} tracks`);

        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error creating radio playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

// Generate "Re-Discover Weekly" playlist
async function generateRediscoverWeekly() {
    const button = document.getElementById('rediscover-btn');

    if (!window.selectedRediscoverLibraryId) {
        showToast('warning', 'Please select a music library for Re-Discover.');
        return;
    }

    // Show loading toast
    showToast('loading', 'Analyzing your listening history...', 0);
    button.disabled = true;

    try {
        // Use v2.0 create endpoint (generates and creates playlist in one step)
        const refreshFrequency = document.querySelector('input[name="rediscover-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="rediscover-playlist-length"]:checked').value;

        const response = await fetch('/api/create-rediscover-playlist-v2', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_id: window.selectedRediscoverLibraryId
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create Re-Discover playlist');
        }

        const data = await response.json();

        // Track successful Re-Discover playlist creation
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('Re-Discover Playlist Created', {
                trackCount: data.track_count,
                theme: data.theme,
                mode: data.mode,
                refreshFrequency: refreshFrequency,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider,
                isFallback: data.is_fallback || false
            });
        }

        // Show success message
         const fallbackMsg = data.is_fallback ? ' (using fallback strategy)' : '';
         showToast('success', `Re-Discover playlist created! "${data.theme}" theme with ${data.track_count} tracks${fallbackMsg}`);

         // Update playlist count in sidebar
         await updatePlaylistCount();

     } catch (error) {
         showToast('error', error.message);
     } finally {
         button.disabled = false;
     }
 }

// Update playlist count in sidebar
async function updatePlaylistCount() {
    try {
        console.log('📊 updatePlaylistCount() called');
        const response = await fetch('/api/playlists');
        if (response.ok) {
            const playlists = await response.json();
            const count = playlists.length;
            console.log(`📊 Fetched ${count} playlists`);

            // Update both desktop and mobile sidebar text
            const desktopText = document.getElementById('desktop-playlists-text');
            const mobileText = document.getElementById('mobile-playlists-text');
            
            console.log('📊 Desktop element:', desktopText, 'Mobile element:', mobileText);

            if (count > 0) {
                if (desktopText) {
                    desktopText.textContent = `Playlists (${count})`;
                    console.log('📊 Updated desktop text to:', desktopText.textContent);
                }
                if (mobileText) {
                    mobileText.textContent = `Playlists (${count})`;
                    console.log('📊 Updated mobile text to:', mobileText.textContent);
                }
            } else {
                if (desktopText) desktopText.textContent = 'Playlists';
                if (mobileText) mobileText.textContent = 'Playlists';
            }
        } else {
            console.error('📊 Response not ok:', response.status);
        }
    } catch (error) {
        console.error('📊 Error fetching playlist count:', error);
        // Keep default text on error
    }
}

// Format next refresh time in a user-friendly way
function formatNextRefresh(nextRefreshTime) {
    // Handle timestamps that come from server without timezone info
    // These are local times (not UTC) since the app operates in local timezone
    let nextRefresh;

    if (nextRefreshTime.includes('T') && (nextRefreshTime.includes('Z') || nextRefreshTime.includes('+') || nextRefreshTime.includes('-'))) {
        // ISO format with timezone - parse as-is
        nextRefresh = new Date(nextRefreshTime);
    } else {
        // Format without timezone - treat as local time (not UTC)
        // Parse as-is without adding Z suffix
        const isoString = nextRefreshTime.replace(' ', 'T');
        nextRefresh = new Date(isoString);
    }
    
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    const nextRefreshDate = new Date(nextRefresh.getFullYear(), nextRefresh.getMonth(), nextRefresh.getDate());

    // Display time as :00 (on the hour) even though cron runs at :01
    const displayTime = new Date(nextRefresh.getTime() - 60000); // Subtract 1 minute
    const timeString = displayTime.toLocaleTimeString('en-AU', {hour: '2-digit', minute: '2-digit', hour12: true});

    if (nextRefreshDate.getTime() === today.getTime()) {
        return `${timeString} today`;
    } else if (nextRefreshDate.getTime() === tomorrow.getTime()) {
        return `${timeString} tomorrow`;
    } else {
        return `${nextRefresh.toLocaleDateString('en-GB')} ${timeString}`;
    }
}

// Load playlists for management page
async function loadPlaylists() {
    const loadingDiv = document.getElementById('playlists-loading');
    const containerDiv = document.getElementById('playlists-container');

    loadingDiv.classList.remove('hidden');
    containerDiv.innerHTML = '';

    try {
        const response = await fetch('/api/playlists');
        if (!response.ok) {
            throw new Error('Failed to load playlists');
        }

        let playlists = await response.json();

        loadingDiv.classList.add('hidden');

        // Filter duplicates by navidrome_playlist_id to address backend JOIN issue
        const seenIds = new Set();
        playlists = playlists.filter(playlist => {
            // Use navidrome_playlist_id as unique identifier
            const id = playlist.navidrome_playlist_id || playlist.id; // fallback to id if no navidrome id
            if (seenIds.has(id)) {
                return false; // duplicate, filter out
            }
            seenIds.add(id);
            return true; // unique, keep
        });

        if (playlists.length === 0) {
            containerDiv.innerHTML = `
                <div class="text-center p-8 text-gray-500">
                    <p class="text-lg mb-2">No playlists yet</p>
                    <p class="text-sm">Create your first playlist using the options in the sidebar!</p>
                </div>
            `;
            return;
        }

        renderPlaylists(playlists);

    } catch (error) {
        console.error('Error loading playlists:', error);
        loadingDiv.classList.add('hidden');
        containerDiv.innerHTML = `
            <div class="text-center p-8 text-red-600">
                <p class="text-lg mb-2">Error loading playlists</p>
                <p class="text-sm">${error.message}</p>
            </div>
        `;
    }
}

// Render playlists in the management interface
function renderPlaylists(playlists) {
    const container = document.getElementById('playlists-container');

    container.innerHTML = playlists.map(playlist => {
        return `
            <div class="flex items-start justify-between p-4 border border-gray-200 rounded-lg mb-4">
                <div class="flex-grow">
                    <h3 class="text-lg font-semibold text-gray-900 mb-1">${playlist.playlist_name}</h3>
                    <div class="text-sm text-gray-600 mb-2 space-y-1">
                        <p class="mb-0">
                            ${playlist.track_count || 0} tracks •
                            Refreshes ${playlist.refresh_frequency || 'manually'} •
                            ${playlist.next_refresh ? `Next refresh ${formatNextRefresh(playlist.next_refresh)}` : 'No scheduled refresh'}
                        </p>
                        <p class="mb-0">
                            Created ${formatFriendlyDate(playlist.created_at)} •
                            ${playlist.last_refreshed ? `Refreshed ${formatFriendlyDate(playlist.last_refreshed)}` : 'Not refreshed yet'}
                        </p>
                    </div>
                    ${playlist.reasoning ? `<p class="text-sm text-gray-600 m-0 mt-2 italic">${truncateText(playlist.reasoning, 140)}</p>` : ''}
                </div>
                <div class="flex-none">
                    <button
                        onclick="window.deletePlaylist(${playlist.id}, '${playlist.playlist_name.replace(/'/g, "\\'")}')"
                        class="py-1 px-2 text-sm font-medium rounded-md border border-red-500 text-red-500 hover:border-red-400 hover:text-red-400 focus:outline-none focus:border-red-400 focus:text-red-400 cursor-pointer"
                    >
                        Delete
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Delete a playlist
async function deletePlaylist(playlistId, playlistName) {
    if (!confirm(`Are you sure you want to delete "${playlistName}"?\n\nThis will permanently remove the playlist from both Magic Lists and your Navidrome library.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/playlists/${playlistId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to delete playlist');
        }

        const data = await response.json();
        const navidromeDeleted = data.navidrome_deleted;

        // Reload the playlists list and update count
        loadPlaylists();
        updatePlaylistCount();

        // Show appropriate success toast
        if (navidromeDeleted) {
            showToast('success', 'Playlist deleted successfully from both local database and Navidrome');
        } else {
            showToast('success', 'Playlist deleted from local database (may still appear in Navidrome if deletion failed)');
        }

    } catch (error) {
        console.error('Error deleting playlist:', error);
        showToast('error', error.message);
    }
}

// Helper function to truncate text
function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}