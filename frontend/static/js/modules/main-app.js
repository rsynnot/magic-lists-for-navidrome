/**
 * Main App Module - Coordinator
 * Imports and coordinates all other modules, handles UI initialization
 */

// Import utility functions
import { showToast } from '../core/utils.js';

// Import all module functions
import {
    loadLibraries,
    handleLibraryCheckboxChange,
    updateLibraryDisplayText,
    checkLibrarySelection,
    loadRediscoverLibraries,
    updateRediscoverRadioStates,
    updateButtonStates,
    loadLibraryStats
} from './library-manager.js';

import {
    loadArtists,
    loadGenres,
    handleArtistSelection,
    handleGenreSelection,
    createArtistPlaylist,
    createGenrePlaylist,
    createRadioPlaylist,
    generateRediscoverWeekly,
    loadPlaylists,
    updatePlaylistCount,
    deletePlaylist
} from './playlist-manager.js';

import {
     initializeSongRadioPage,
     initializeSongRadio
 } from './song-radio.js';

 import { getAIModelInfo, trackLibrarySize } from './analytics.js';

 // Export all imported functions for backward compatibility and global access
 export {
     // Library management
     loadLibraries,
     handleLibraryCheckboxChange,
     updateLibraryDisplayText,
     checkLibrarySelection,
     loadRediscoverLibraries,
     updateRediscoverRadioStates,
     loadLibraryStats,

     // Artist/Genre management
     loadArtists,
     loadGenres,
     handleArtistSelection,
     handleGenreSelection,

     // Song radio functionality
     initializeSongRadioPage,
     initializeSongRadio,

     // Playlist creation
     createArtistPlaylist,
     createGenrePlaylist,
     createRadioPlaylist,
     generateRediscoverWeekly,

     // Playlist management
     loadPlaylists,
     updatePlaylistCount,
     deletePlaylist,

     // Analytics
     getAIModelInfo,
     trackLibrarySize,

     // UI initialization
     initializeRadioButtons
 };

// Initialize radio button active state management
function initializeRadioButtons() {
    // Handle This Is playlist length radio buttons
    const thisisLengthRadios = document.querySelectorAll('input[name="thisis-playlist-length"]');
    const thisisLengthGroup = document.getElementById('thisis-playlist-length-group');

    if (thisisLengthRadios.length > 0 && thisisLengthGroup) {
        thisisLengthRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(thisisLengthGroup, this);
            });
        });
    }

    // Handle This Is refresh frequency radio buttons
    const thisisFreqRadios = document.querySelectorAll('input[name="thisis-refresh-frequency"]');
    const thisisFreqGroup = document.getElementById('thisis-refresh-frequency-group');

    if (thisisFreqRadios.length > 0 && thisisFreqGroup) {
        thisisFreqRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(thisisFreqGroup, this);
            });
        });
    }

    // Handle Genre Mix playlist length radio buttons
    const genreLengthRadios = document.querySelectorAll('input[name="genre-playlist-length"]');
    const genreLengthGroup = document.getElementById('genre-playlist-length-group');

    if (genreLengthRadios.length > 0 && genreLengthGroup) {
        genreLengthRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(genreLengthGroup, this);
            });
        });
    }

    // Handle Genre Mix refresh frequency radio buttons
    const genreFreqRadios = document.querySelectorAll('input[name="genre-refresh-frequency"]');
    const genreFreqGroup = document.getElementById('genre-refresh-frequency-group');

    if (genreFreqRadios.length > 0 && genreFreqGroup) {
        genreFreqRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(genreFreqGroup, this);
            });
        });
    }

    // Handle Re-Discover playlist length radio buttons
    const rediscoverLengthRadios = document.querySelectorAll('input[name="rediscover-playlist-length"]');
    const rediscoverLengthGroup = document.getElementById('rediscover-playlist-length-group');

    if (rediscoverLengthRadios.length > 0 && rediscoverLengthGroup) {
        rediscoverLengthRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(rediscoverLengthGroup, this);
            });
        });
    }

    // Handle Re-Discover refresh frequency radio buttons
    const rediscoverFreqRadios = document.querySelectorAll('input[name="rediscover-refresh-frequency"]');
    const rediscoverFreqGroup = document.getElementById('rediscover-refresh-frequency-group');

    if (rediscoverFreqRadios.length > 0 && rediscoverFreqGroup) {
        rediscoverFreqRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(rediscoverFreqGroup, this);
            });
        });
    }

    // Handle Song Radio refresh frequency radio buttons
    const radioFreqRadios = document.querySelectorAll('input[name="radio-refresh-frequency"]');
    const radioFreqGroup = document.getElementById('radio-refresh-frequency-group');

    if (radioFreqRadios.length > 0 && radioFreqGroup) {
        radioFreqRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                updateRadioActiveState(radioFreqGroup, this);
            });
        });
    }

    // Handle Re-Discover button click
    const rediscoverBtn = document.getElementById('rediscover-btn');
    if (rediscoverBtn) {
        rediscoverBtn.addEventListener('click', generateRediscoverWeekly);
    }

    // Update button states based on current selections
    updateButtonStates();
}

// Update visual active state for radio button groups
function updateRadioActiveState(group, selectedRadio) {
    // Remove active state from all items in the group
    const allItems = group.querySelectorAll('li');
    allItems.forEach(item => {
        item.classList.remove('bg-blue-100', 'border-blue-200', 'text-blue-800');
        item.classList.add('bg-white', 'border-gray-200', 'text-gray-800');
    });

    // Add active state to selected item
    const selectedItem = selectedRadio.closest('li');
    selectedItem.classList.remove('bg-white', 'border-gray-200', 'text-gray-800');
    selectedItem.classList.add('bg-blue-100', 'border-blue-200', 'text-blue-800');
}

// Make key functions globally available for backward compatibility
window.deletePlaylist = deletePlaylist;
window.updatePlaylistCount = updatePlaylistCount;

