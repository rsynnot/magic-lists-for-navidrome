// Global state for artist selection
let selectedArtistId = null;
let selectedGenre = null;
let allArtists = [];
let allGenres = [];
let currentToast = null;


// Helper function to format dates in friendly format (e.g., "5 Oct 2025 10:12am")
function formatFriendlyDate(dateString) {
    if (!dateString) return 'Never';
    
    const date = new Date(dateString);
    const day = date.getDate();
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[date.getMonth()];
    const year = date.getFullYear();
    
    let hours = date.getHours();
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'pm' : 'am';
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12
    
    return `${day} ${month} ${year} ${hours}:${minutes}${ampm}`;
}

// Toast utility functions
function showToast(type, message, duration = 5000) {
    // Remove any existing toast
    if (currentToast) {
        hideToast(currentToast);
    }

    const container = document.getElementById('toast-container');
    const toastId = 'toast-' + Date.now();

    let bgClass, textClass, borderClass, icon;

    if (type === 'success') {
        bgClass = 'bg-green-50 border-green-200';
        textClass = 'text-green-800';
        borderClass = 'border';
        icon = '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>';
    } else if (type === 'loading') {
        bgClass = 'bg-blue-50 border-blue-200';
        textClass = 'text-blue-800';
        borderClass = 'border';
        icon = '<svg class="size-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
    } else {
        bgClass = 'bg-red-50 border-red-200';
        textClass = 'text-red-800';
        borderClass = 'border';
        icon = '<svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';
    }

    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `${bgClass} ${borderClass} ${textClass} rounded-lg shadow-lg p-4 pointer-events-auto transition-all duration-300 transform translate-x-0 opacity-100`;
    toast.innerHTML = `
        <div class="flex items-center gap-3">
            <div class="flex-shrink-0">
                ${icon}
            </div>
            <div class="flex-grow">
                <p class="text-sm font-medium">${message}</p>
            </div>
            ${type !== 'loading' ? `
            <button type="button" class="flex-shrink-0 inline-flex items-center justify-center size-5 rounded-lg text-gray-800 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-400" onclick="hideToast('${toastId}')">
                <span class="sr-only">Close</span>
                <svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
            ` : ''}
        </div>
    `;

    container.appendChild(toast);
    currentToast = toastId;

    // Auto-dismiss (except for loading toasts)
    if (type !== 'loading' && duration > 0) {
        setTimeout(() => hideToast(toastId), duration);
    }

    return toastId;
}

function hideToast(toastId) {
    const toast = document.getElementById(toastId);
    if (toast) {
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            if (currentToast === toastId) {
                currentToast = null;
            }
        }, 300);
    }
}

// Mobile menu toggle functionality
const mobileMenuBtn = document.getElementById('hs-navbar-alignment-collapse');
const mobileSidebar = document.getElementById('mobileSidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const closeMobileSidebarBtn = document.getElementById('closeMobileSidebar');

mobileMenuBtn.addEventListener('click', function() {
    mobileSidebar.classList.toggle('-translate-x-full');
    sidebarOverlay.classList.toggle('hidden');
});

// Close sidebar when clicking on close button
closeMobileSidebarBtn.addEventListener('click', function() {
    mobileSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
});

// Close sidebar when clicking on overlay
sidebarOverlay.addEventListener('click', function() {
    mobileSidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('hidden');
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', function(event) {
    if (window.innerWidth < 768 && 
        !mobileSidebar.contains(event.target) && 
        !mobileMenuBtn.contains(event.target) &&
        !mobileSidebar.classList.contains('-translate-x-full')) {
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
});

// Handle window resize to ensure proper state
window.addEventListener('resize', function() {
    if (window.innerWidth >= 768) {
        mobileSidebar.classList.add('-translate-x-full'); // Hide mobile sidebar on large screens
        sidebarOverlay.classList.add('hidden'); // Hide overlay on large screens
    } else {
        // On mobile, ensure sidebar is hidden when switching from desktop view
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
});

// Sidebar navigation active state management
function setActiveMenuItem(page) {
    // Remove active state from all links in desktop sidebar
    const desktopLinks = document.querySelectorAll('#desktopSidebar [data-page]');
    desktopLinks.forEach(link => {
        link.classList.remove('bg-gray-200');
        link.classList.add('bg-gray-100');
    });
    
    // Remove active state from all links in mobile sidebar
    const mobileLinks = document.querySelectorAll('#mobileSidebar [data-page]');
    mobileLinks.forEach(link => {
        link.classList.remove('bg-gray-200');
        link.classList.add('bg-white');
    });
    
    // Add active state to clicked desktop sidebar links
    const activeDesktopLinks = document.querySelectorAll(`#desktopSidebar [data-page="${page}"]`);
    activeDesktopLinks.forEach(link => {
        link.classList.add('bg-gray-200');
        link.classList.remove('bg-gray-100');
    });
    
    // Add active state to clicked mobile sidebar links
    const activeMobileLinks = document.querySelectorAll(`#mobileSidebar [data-page="${page}"]`);
    activeMobileLinks.forEach(link => {
        link.classList.add('bg-gray-200');
        link.classList.remove('bg-white');
    });
}

// Navigation functionality
function showContent(contentId) {
    // Hide all content sections
    const contentSections = ['welcome-content', 'this-is-content', 'rediscover-content', 'manage-playlists-content', 'system-check-content', 'terms-content'];
    contentSections.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = 'none';
        }
    });

    // Show the selected content
    const targetContent = document.getElementById(contentId);
    if (targetContent) {
        targetContent.style.display = 'block';
    }
}

// Add click handlers to all navigation links
document.addEventListener('click', function(event) {
    const link = event.target.closest('[data-page]');
    if (link) {
        event.preventDefault();
        const page = link.getAttribute('data-page');
        
        // Use the shared navigation handler
        handlePageNavigation(page);
        
        // Update URL based on page (only for click navigation, not popstate)
        updateURL(page);
        
        // Close mobile sidebar if clicked
        if (window.innerWidth < 768) {
            mobileSidebar.classList.add('-translate-x-full');
            sidebarOverlay.classList.add('hidden');
        }
    }
});

// AI model information cache
let aiModelInfo = null;

// Get AI model information for analytics
async function getAIModelInfo() {
    if (aiModelInfo) {
        return aiModelInfo;
    }
    
    try {
        const response = await fetch('/api/ai-model-info');
        if (response.ok) {
            aiModelInfo = await response.json();
            return aiModelInfo;
        }
    } catch (error) {
        console.error('Error fetching AI model info:', error);
    }
    
    // Fallback
    return {
        provider: 'unknown',
        model: 'unknown',
        has_api_key: false
    };
}

// Post-launch library size tracking
async function trackLibrarySize() {
    try {
        const response = await fetch('/api/track-library-size', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const data = await response.json();
            
            if (data.tracked && typeof window.rybbit !== 'undefined') {
                // Track library size event with Rybbit
                window.rybbit.event('Library Size Tracked', {
                    songCount: data.song_count,
                    userId: data.user_id
                });
                console.log('📊 Library size tracked for analytics');
            }
        }
    } catch (error) {
        console.error('Error tracking library size:', error);
        // Silently fail - don't disrupt user experience
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Preline components
    if (window.HSStaticMethods) {
        window.HSStaticMethods.autoInit();
        console.log('Preline initialized');
    } else {
        console.error('Preline not loaded');
    }
    
    // Setup artist selection change handler
    const artistSelect = document.getElementById('artist-search-select');
    if (artistSelect) {
        artistSelect.addEventListener('change', handleArtistSelection);
    }
    
    // Load playlist count on page load
    updatePlaylistCount();
    
    // Handle initial page routing
    const currentPage = getPageFromURL(window.location.pathname);
    handlePageNavigation(currentPage);
    
    // Track library size post-launch (with delay to not interfere with app loading)
    setTimeout(trackLibrarySize, 2000);
});

// Load artists and populate the select (from original working code)
async function loadArtists() {
    try {
        const response = await fetch('/api/artists');
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

async function loadGenres() {
    try {
        const response = await fetch('/api/genres');
        if (!response.ok) {
            throw new Error('Failed to fetch genres');
        }
        allGenres = await response.json();

        // Clear any previous selection
        selectedGenre = null;

        // Populate the select dropdown
        const genreSelect = document.getElementById('genre-select');
        if (genreSelect) {
            // Clear existing options except the first one
            while (genreSelect.options.length > 1) {
                genreSelect.remove(1);
            }

            // Add genre options
            allGenres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre;
                option.textContent = genre;
                genreSelect.appendChild(option);
            });

            // Setup genre selection change handler
            genreSelect.addEventListener('change', handleGenreSelection);

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                const selectInstance = window.HSSelect.getInstance(genreSelect);
                if (selectInstance) {
                    selectInstance.destroy();
                }
                window.HSSelect.autoInit();
            }
        }

        showToast('success', `Loaded ${allGenres.length} genres from your library`);
    } catch (error) {
        console.error('Error loading genres:', error);
        showToast('error', 'Failed to load genres from your library');
    }
}

// Handle genre selection change
function handleGenreSelection(e) {
    selectedGenre = e.target.value;
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (selectedGenre) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// Handle artist selection change
function handleArtistSelection(e) {
    selectedArtistId = e.target.value;
    const submitBtn = document.getElementById('create-artist-playlist-btn');
    
    if (selectedArtistId) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// This Is Artist form submission
document.getElementById('this-is-form').addEventListener('submit', function(e) {
    e.preventDefault();
    createArtistPlaylist();
});

// Genre Mix form submission
document.getElementById('genre-mix-form').addEventListener('submit', function(e) {
    e.preventDefault();
    createGenrePlaylist();
});

async function createArtistPlaylist() {
    const submitBtn = document.getElementById('create-artist-playlist-btn');
    
    if (!selectedArtistId) {
        showToast('error', 'Please select an artist first');
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="artist-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="artist-playlist-length"]:checked').value;

        const response = await fetch('/api/create_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_ids: [selectedArtistId],
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength)
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

async function createGenrePlaylist() {
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (!selectedGenre) {
        showToast('error', 'Please select a genre first');
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
                genre: selectedGenre,
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength)
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
                genre: selectedGenre,
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

// Re-discover Weekly functionality
async function generateRediscoverWeekly() {
    const button = document.getElementById('rediscover-btn');

    // Show loading toast
    showToast('loading', 'Analyzing your listening history...', 0);
    button.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="rediscover-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="rediscover-playlist-length"]:checked').value;

        const response = await fetch('/api/create-rediscover-playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength)
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create Re-Discover playlist');
        }

        const data = await response.json();

        // Track successful Re-Discover Weekly generation with Rybbit
        if (typeof window.rybbit !== 'undefined') {
            const modelInfo = await getAIModelInfo();
            window.rybbit.event('Re-Discover Playlist Created', {
                trackCount: data.tracks ? data.tracks.length : 0,
                refreshFrequency: refreshFrequency,
                aiModel: modelInfo.model,
                aiProvider: modelInfo.provider
            });
        }

        // Show success toast
        showToast('success', `Re-Discover playlist created with ${data.tracks ? data.tracks.length : 0} tracks`);
        
        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error generating Re-Discover Weekly:', error);
        showToast('error', error.message);
    } finally {
        button.disabled = false;
    }
}

// Update playlist count in sidebar
async function updatePlaylistCount() {
    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            const playlists = await response.json();
            const count = playlists.length;
            
            // Update both desktop and mobile sidebar text
            const desktopText = document.getElementById('desktop-playlists-text');
            const mobileText = document.getElementById('mobile-playlists-text');
            
            if (count > 0) {
                if (desktopText) desktopText.textContent = `Playlists (${count})`;
                if (mobileText) mobileText.textContent = `Playlists (${count})`;
            } else {
                if (desktopText) desktopText.textContent = 'Playlists';
                if (mobileText) mobileText.textContent = 'Playlists';
            }
        }
    } catch (error) {
        console.error('Error fetching playlist count:', error);
        // Keep default text on error
    }
}

// Manage Playlists functionality
// Format next refresh time in a user-friendly way
function formatNextRefresh(nextRefreshTime) {
    const nextRefresh = new Date(nextRefreshTime);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    const nextRefreshDate = new Date(nextRefresh.getFullYear(), nextRefresh.getMonth(), nextRefresh.getDate());
    
    const timeString = nextRefresh.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit', hour12: true});
    
    if (nextRefreshDate.getTime() === today.getTime()) {
        return `${timeString} today`;
    } else if (nextRefreshDate.getTime() === tomorrow.getTime()) {
        return `${timeString} tomorrow`;
    } else {
        return `${nextRefresh.toLocaleDateString('en-GB')} ${timeString}`;
    }
}

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

function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

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
                        onclick="deletePlaylist(${playlist.id}, '${playlist.playlist_name}')"
                        class="text-sm font-medium underline cursor-pointer border-none bg-transparent text-red-600 hover:text-red-800 px-2 py-1"
                    >
                        Delete
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

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

        // Reload the playlists list and update count
        loadPlaylists();
        updatePlaylistCount();

        // Show success toast - note that the backend may only delete locally if Navidrome deletion fails
        showToast('success', 'Playlist deleted from local database (check Navidrome if it still appears there)');

    } catch (error) {
        console.error('Error deleting playlist:', error);
        showToast('error', error.message);
    }
}

// System Check functionality
async function runSystemChecks() {
    const listContainer = document.getElementById('system-checks-list');
    const resultsContainer = document.getElementById('system-check-results');
    const successBanner = document.getElementById('success-banner');
    const errorBanner = document.getElementById('error-banner');
    const continueBtn = document.getElementById('continue-btn');
    const updateSettingsBtn = document.getElementById('update-settings-btn');
    const rerunBtn = document.getElementById('rerun-checks-btn');

    // Reset UI
    successBanner.classList.add('hidden');
    errorBanner.classList.add('hidden');
    continueBtn.classList.add('hidden');
    updateSettingsBtn.classList.add('hidden');
    rerunBtn.disabled = true;
    rerunBtn.textContent = 'Running Checks...';

    try {
        // Call backend health check endpoint
        const response = await fetch('/api/health-check');
        if (!response.ok) {
            throw new Error('Failed to run system checks');
        }

        const data = await response.json();
        
        // Display check results
        displaySystemChecks(data.checks);
        
        // Show appropriate banner and buttons
        if (data.all_passed) {
            successBanner.classList.remove('hidden');
            continueBtn.classList.remove('hidden');
            
            // Track Rybbit event
            if (typeof window.rybbit !== 'undefined') {
                window.rybbit.event('System Check Completed', {
                    status: 'all_passed',
                    checkCount: data.checks ? data.checks.length : 0
                });
            }
        } else {
            errorBanner.classList.remove('hidden');
            updateSettingsBtn.classList.remove('hidden');
            
            // Track specific failure events with Rybbit
            if (typeof window.rybbit !== 'undefined') {
                const failedChecks = data.checks.filter(check => check.status === 'error');
                
                window.rybbit.event('System Check Completed', {
                    status: 'failed',
                    checkCount: data.checks ? data.checks.length : 0,
                    failedCount: failedChecks.length
                });
                
                // Track specific failure types
                failedChecks.forEach(check => {
                    if (check.name.includes('URL Reachable')) {
                        window.rybbit.event('System Check Failed', { type: 'url_reachable' });
                    } else if (check.name.includes('Authentication')) {
                        window.rybbit.event('System Check Failed', { type: 'authentication' });
                    } else if (check.name.includes('Artists API')) {
                        window.rybbit.event('System Check Failed', { type: 'artists_api' });
                    } else if (check.name.includes('AI Provider')) {
                        window.rybbit.event('System Check Failed', { type: 'ai_provider' });
                    }
                });
            }
        }
        
    } catch (error) {
        console.error('System check error:', error);
        listContainer.innerHTML = `
            <div class="p-4 text-red-600 border border-red-300 rounded-lg bg-red-50">
                <p class="font-medium">Error running system checks</p>
                <p class="text-sm mt-1">${error.message}</p>
            </div>
        `;
        errorBanner.classList.remove('hidden');
    } finally {
        rerunBtn.disabled = false;
        rerunBtn.textContent = 'Re-run Checks';
    }
}

function displaySystemChecks(checks) {
    const container = document.getElementById('system-checks-list');
    
    container.innerHTML = checks.map(check => {
        const statusIcon = getStatusIcon(check.status);
        const statusColor = getStatusColor(check.status);
        const hasDetails = check.message || check.suggestion;
        
        return `
            <div class="border border-gray-200 rounded-lg overflow-hidden">
                <div class="p-4 ${hasDetails ? 'cursor-pointer' : ''}" ${hasDetails ? `onclick="toggleCheckDetails('${check.name.replace(/[^a-zA-Z0-9]/g, '')}')"` : ''}>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                ${statusIcon}
                            </div>
                            <div class="ml-3">
                                <h3 class="text-sm font-medium text-gray-900">${check.name}</h3>
                                <p class="text-sm ${statusColor}">${getStatusText(check.status)}</p>
                            </div>
                        </div>
                        ${hasDetails ? `
                            <div class="flex-shrink-0">
                                <svg class="w-5 h-5 text-gray-400 transform transition-transform rotate-90" id="chevron-${check.name.replace(/[^a-zA-Z0-9]/g, '')}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
                                </svg>
                            </div>
                        ` : ''}
                    </div>
                </div>
                ${hasDetails ? `
                    <div class="hidden px-4 pb-4 pt-4 border-t border-gray-100 bg-gray-50" id="details-${check.name.replace(/[^a-zA-Z0-9]/g, '')}">
                        ${check.message ? `<p class="text-sm text-gray-600 mb-2">${check.message}</p>` : ''}
                        ${check.suggestion ? `<p class="text-sm text-blue-600 font-medium">${check.suggestion}</p>` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

function toggleCheckDetails(checkId) {
    const detailsDiv = document.getElementById(`details-${checkId}`);
    const chevron = document.getElementById(`chevron-${checkId}`);
    
    if (detailsDiv.classList.contains('hidden')) {
        detailsDiv.classList.remove('hidden');
        chevron.classList.remove('rotate-90');
        chevron.classList.add('-rotate-90');
    } else {
        detailsDiv.classList.add('hidden');
        chevron.classList.remove('-rotate-90');
        chevron.classList.add('rotate-90');
    }
}

function getStatusIcon(status) {
    switch (status) {
        case 'success':
            return `<svg class="w-5 h-5 text-green-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
            </svg>`;
        case 'warning':
            return `<svg class="w-5 h-5 text-yellow-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>`;
        case 'info':
            return `<svg class="w-5 h-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
            </svg>`;
        case 'error':
            return `<svg class="w-5 h-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
            </svg>`;
        default:
            return `<svg class="w-5 h-5 text-gray-400 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="m12 2v4l4-4h-4z"></path>
            </svg>`;
    }
}

function getStatusColor(status) {
    switch (status) {
        case 'success':
            return 'text-green-600';
        case 'warning':
            return 'text-yellow-600';
        case 'info':
            return 'text-blue-600';
        case 'error':
            return 'text-red-600';
        default:
            return 'text-gray-500';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'success':
            return 'Success';
        case 'warning':
            return 'Warning';
        case 'info':
            return 'Info';
        case 'error':
            return 'Failed';
        default:
            return 'Checking...';
    }
}

// URL management function
function updateURL(page) {
    let url = '/';
    
    // Map pages to URL paths
    switch(page) {
        case 'home':
            url = '/';
            break;
        case 'this-is-artist':
            url = '/this-is';
            break;
        case 're-discover':
            url = '/re-discover';
            break;
        case 'genre-mix':
            url = '/genre-mix';
            break;
        case 'playlists':
            url = '/playlists';
            break;
        case 'system-check':
            url = '/system-check';
            break;
        case 'terms':
            url = '/terms';
            break;
        default:
            url = '/';
    }
    
    // Update browser URL without page reload
    if (window.location.pathname !== url) {
        window.history.pushState({ page: page }, '', url);
    }
}

function navigateToHome() {
    // Navigate to home page (this will trigger a redirect to / which checks system status)
    window.location.href = '/';
}

function showSettingsHelp() {
    alert('To update your settings:\n\n1. Edit your .env file with the correct values\n2. Restart the application\n3. Run the system check again\n\nRefer to the SETUP.md file for detailed configuration instructions.');
}

// Auto-run system checks when the system-check page loads
function initSystemCheckPage() {
    runSystemChecks();
}

// URL ROUTING
// Handle browser back/forward navigation
window.addEventListener('popstate', function(event) {
    if (event.state && event.state.page) {
        // Use the stored page state
        handlePageNavigation(event.state.page);
    } else {
        // Determine page from URL
        const page = getPageFromURL(window.location.pathname);
        handlePageNavigation(page);
    }
});

// Get page from URL path
function getPageFromURL(pathname) {
    switch(pathname) {
        case '/':
            return 'home';
        case '/this-is':
            return 'this-is-artist';
        case '/re-discover':
            return 're-discover';
        case '/genre-mix':
            return 'genre-mix';
        case '/playlists':
            return 'playlists';
        case '/system-check':
            return 'system-check';
        case '/terms':
            return 'terms';
        default:
            return 'home';
    }
}

// Handle page navigation (used by both click and popstate)
function handlePageNavigation(page) {
    // Track page view with Rybbit
    if (typeof window.rybbit !== 'undefined') {
        window.rybbit.pageview();
    }
    
    // Map page to content
    let contentId;
    if (page === 'home') {
        contentId = 'welcome-content';
    } else if (page === 'this-is-artist') {
        contentId = 'this-is-content';
        // Load artists when navigating to This Is page
        setTimeout(() => loadArtists(), 100);
    } else if (page === 're-discover') {
        contentId = 'rediscover-content';
    } else if (page === 'genre-mix') {
        contentId = 'genre-mix-content';
        // Load genres when navigating to Genre Mix page
        setTimeout(() => loadGenres(), 100);
    } else if (page === 'playlists') {
        contentId = 'manage-playlists-content';
        // Load playlists when navigating to manage page
        setTimeout(() => loadPlaylists(), 100);
    } else if (page === 'system-check') {
        contentId = 'system-check-content';
        // Auto-run system checks when navigating to system check page
        setTimeout(() => runSystemChecks(), 100);
    } else if (page === 'terms') {
        contentId = 'terms-content';
    }
    
    setActiveMenuItem(page);
    showContent(contentId);
}


