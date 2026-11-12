/**
 * Main App Orchestrator
 * Thin entry point that imports and initializes all modules
 */

// Import core modules
import { formatFriendlyDate, formatDuration, formatTrackTitle, formatTrackTitleHTML, showToast, hideToast } from './js/core/utils.js';
import { initializeMobileMenu, initializeNavigation, handlePageNavigation, getPageFromURL, updateURL } from './js/core/navigation.js';

// Import feature modules
import { 
    checkDatabaseConnectivity, 
    runSystemChecks, 
    displaySystemChecks, 
    toggleCheckDetails, 
    getStatusIcon, 
    getStatusColor, 
    getStatusText, 
    showSettingsHelp, 
    initSystemCheckPage 
} from './js/modules/system-check.js';

import { 
    scanInProgress, 
    scanAbortController, 
    currentScanSessionId, 
    lastTestScanDuration, 
    selectedScanLibraryId,
    startScan, 
    cancelScan, 
    updateFullScanTimeEstimate, 
    initializeScanLibraryPage, 
    loadScanLibraries, 
    loadLibraryScanProgress, 
    handleScanLibrarySelection, 
    checkScanReadiness, 
    loadScanHistory 
} from './js/modules/scan-library.js';

import {
    createGenrePlaylist,
    createRadioPlaylist,
    generateRediscoverWeekly,
    loadArtists,
    loadGenres,
    loadPlaylists
} from './js/modules/playlist-generators.js';

import {
    createArtistPlaylist,
    loadRediscoverLibraries,
    initializeSongRadioPage,
    trackLibrarySize,
    initializeRadioButtons
} from './js/modules/main-app.js';

import {
    loadLibraries,
    initializeLibrarySetup,
    checkLibraryMappingNeeded,
    populateLibraryMappingForm,
    saveLibraryMappings,
    checkLibraryMappingsForWelcome
} from './js/modules/library-manager.js';

import {
    checkLibraryMappingsForScanPage
} from './js/modules/scan-library.js';

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async function() {
    // Initialize Preline components
    if (window.HSStaticMethods) {
        window.HSStaticMethods.autoInit();
        console.log('Preline initialized');
    } else {
        console.error('Preline not loaded');
    }
    
    // Initialize navigation and mobile menu
    initializeMobileMenu();
    initializeNavigation();
    
    // Load libraries on page load, then handle routing
    console.log('🚀 Starting app initialization - loading libraries first...');
    await loadLibraries();
    console.log('📚 Libraries loaded, now setting up globals...');
    
    // Load playlist count on page load
    updatePlaylistCount();

    // Make global functions available to navigation module
    window.getSelectedLibraryIds = () => window.selectedLibraryIds || [];
    window.getPageFromURL = getPageFromURL;
    window.loadLibraries = loadLibraries;
    window.loadArtists = loadArtists;
    window.loadGenres = loadGenres;
    window.loadRediscoverLibraries = loadRediscoverLibraries;
    window.initializeSongRadioPage = initializeSongRadioPage;
    window.loadPlaylists = loadPlaylists;
    window.checkLibraryMappingsForWelcome = checkLibraryMappingsForWelcome;
    window.checkLibraryMappingsForScanPage = checkLibraryMappingsForScanPage;
    window.runSystemChecks = runSystemChecks;
    window.initializeScanLibraryPage = initializeScanLibraryPage;
    
    // Also expose selectedLibraryIds directly for debugging
    window.selectedLibraryIds = window.selectedLibraryIds || [];

    // Initialize library setup on welcome page (one-time setup)
    console.log('🎵 Checking if library setup is needed...');
    await initializeLibrarySetup();

    // Handle initial page routing (after libraries are loaded)
    setTimeout(() => {
        const currentPage = getPageFromURL(window.location.pathname);
        console.log('📚 Handling initial page navigation to:', currentPage, 'with libraries:', window.getSelectedLibraryIds());
        handlePageNavigation(currentPage);
    }, 200); // Increased delay to ensure libraries are fully loaded

    // Track library size post-launch (with delay to not interfere with app loading)
    setTimeout(trackLibrarySize, 2000);
    
    // Setup form submission handlers
    const thisIsForm = document.getElementById('this-is-form');
    if (thisIsForm) {
        thisIsForm.addEventListener('submit', function(e) {
            e.preventDefault();
            createArtistPlaylist();
        });
    }

    const genreMixForm = document.getElementById('genre-mix-form');
    if (genreMixForm) {
        genreMixForm.addEventListener('submit', function(e) {
            e.preventDefault();
            createGenrePlaylist();
        });
    }

    const songRadioForm = document.getElementById('song-radio-form');
    if (songRadioForm) {
        songRadioForm.addEventListener('submit', function(e) {
            e.preventDefault();
            createRadioPlaylist();
        });
    }

    // Initialize radio button active state management
    initializeRadioButtons();
});

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