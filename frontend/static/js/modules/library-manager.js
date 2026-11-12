/**
 * Library Manager Module
 * Handles all library selection, loading, and management functionality
 */

import { showToast } from '../core/utils.js';

// Global state for library management
let selectedLibraryIds = [];
let allLibraries = [];

// Export state and functions
export {
    selectedLibraryIds,
    allLibraries,
    loadLibraries,
    handleLibraryCheckboxChange,
    updateLibraryDisplayText,
    checkLibrarySelection,
    loadRediscoverLibraries,
    updateRediscoverRadioStates,
    updateButtonStates,
    loadLibraryStats,
    initializeLibrarySetup,
    checkLibraryMappingNeeded,
    checkLibraryMappingsForWelcome,
    saveLibraryMappings,
    populateLibraryMappingForm
};

// Load libraries and populate the multi-select interface
async function loadLibraries() {
    try {
        console.log('📚 Loading libraries from API...');
        console.log(`📚 Current localStorage:`, localStorage.getItem('selectedLibraryIds'));
        const response = await fetch('/api/music-folders');
        if (!response.ok) {
            throw new Error(`Failed to fetch libraries: ${response.status} ${response.statusText}`);
        }
        allLibraries = await response.json();
        console.log(`📚 Loaded ${allLibraries.length} libraries:`, allLibraries);

        // Clear any previous selection
        selectedLibraryIds = [];

        // Get UI elements
        const desktopLoading = document.getElementById('library-loading');
        const desktopSingle = document.getElementById('library-single');
        const desktopSingleName = document.getElementById('library-single-name');
        const desktopMulti = document.getElementById('library-multi');
        const desktopMultiText = document.getElementById('library-multi-text');
        const desktopCheckboxes = document.getElementById('library-checkboxes');

        const mobileLoading = document.getElementById('mobile-library-loading');
        const mobileSingle = document.getElementById('mobile-library-single');
        const mobileSingleName = document.getElementById('mobile-library-single-name');
        const mobileMulti = document.getElementById('mobile-library-multi');
        const mobileMultiText = document.getElementById('mobile-library-multi-text');
        const mobileCheckboxes = document.getElementById('mobile-library-checkboxes');

        // Hide loading states
        if (desktopLoading) desktopLoading.classList.add('hidden');
        if (mobileLoading) mobileLoading.classList.add('hidden');

        // Hide all states initially
        if (desktopSingle) desktopSingle.classList.add('hidden');
        if (mobileSingle) mobileSingle.classList.add('hidden');
        if (desktopMulti) desktopMulti.classList.add('hidden');
        if (mobileMulti) mobileMulti.classList.add('hidden');

        if (allLibraries.length === 1) {
            // Single library - show read-only display (AC1)
            const library = allLibraries[0];
            selectedLibraryIds = [library.id];

            // Set global reference immediately
            window.selectedLibraryIds = selectedLibraryIds;

            if (desktopSingle && desktopSingleName) {
                desktopSingleName.textContent = library.name;
                desktopSingle.classList.remove('hidden');
            }
            if (mobileSingle && mobileSingleName) {
                mobileSingleName.textContent = library.name;
                mobileSingle.classList.remove('hidden');
            }

            console.log(`📚 Single library detected: ${library.name} (ID: ${library.id}) - showing readonly display`);

            // Save to localStorage
            localStorage.setItem('selectedLibraryIds', JSON.stringify(selectedLibraryIds));
            console.log(`📚 Saved to localStorage:`, selectedLibraryIds);

        } else {
            // Multiple libraries - show multi-select interface (AC2)
            console.log(`📚 Multiple libraries detected: ${allLibraries.length} libraries - showing multi-select`);

            // Load saved library selections from localStorage
            const savedLibraryIds = localStorage.getItem('selectedLibraryIds');
            if (savedLibraryIds) {
                try {
                    const parsedIds = JSON.parse(savedLibraryIds);
                    // Filter to only include libraries that still exist
                    selectedLibraryIds = parsedIds.filter(id => allLibraries.some(lib => lib.id === id));
                    console.log(`📚 Loaded saved library selections:`, selectedLibraryIds);
                } catch (e) {
                    console.warn('📚 Invalid saved library IDs, starting fresh');
                    selectedLibraryIds = [];
                }
            } else {
                console.log('📚 No saved library selections found');
                selectedLibraryIds = [];
            }

            // Set global reference immediately after loading from localStorage
            window.selectedLibraryIds = selectedLibraryIds;

            // Create checkboxes for desktop
            if (desktopCheckboxes) {
                desktopCheckboxes.innerHTML = '';
                allLibraries.forEach(library => {
                    const checkboxDiv = document.createElement('div');
                    checkboxDiv.className = 'flex items-center px-3 py-2 hover:bg-gray-50 rounded';
                    checkboxDiv.innerHTML = `
                        <input type="checkbox"
                               id="desktop-lib-${library.id}"
                               value="${library.id}"
                               class="shrink-0 mt-0.5 border-gray-200 rounded text-blue-600 focus:ring-blue-500"
                               ${selectedLibraryIds.includes(library.id) ? 'checked' : ''}>
                        <label for="desktop-lib-${library.id}" class="ml-2 text-sm text-gray-800 cursor-pointer">
                            ${library.name}
                        </label>
                    `;
                    desktopCheckboxes.appendChild(checkboxDiv);
                });
            }

            // Create checkboxes for mobile
            if (mobileCheckboxes) {
                mobileCheckboxes.innerHTML = '';
                allLibraries.forEach(library => {
                    const checkboxDiv = document.createElement('div');
                    checkboxDiv.className = 'flex items-center px-3 py-2 hover:bg-gray-50 rounded';
                    checkboxDiv.innerHTML = `
                        <input type="checkbox"
                               id="mobile-lib-${library.id}"
                               value="${library.id}"
                               class="shrink-0 mt-0.5 border-gray-200 rounded text-blue-600 focus:ring-blue-500"
                               ${selectedLibraryIds.includes(library.id) ? 'checked' : ''}>
                        <label for="mobile-lib-${library.id}" class="ml-2 text-sm text-gray-800 cursor-pointer">
                            ${library.name}
                        </label>
                    `;
                    mobileCheckboxes.appendChild(checkboxDiv);
                });
            }

            // Update display text
            updateLibraryDisplayText();

            // Show multi-select interfaces
            if (desktopMulti) desktopMulti.classList.remove('hidden');
            if (mobileMulti) mobileMulti.classList.remove('hidden');

            // Add event listeners for dropdown toggles (only if not already added)
            const desktopToggle = document.getElementById('library-multi-toggle');
            const desktopDropdown = document.getElementById('library-multi-dropdown');
            const mobileToggle = document.getElementById('mobile-library-multi-toggle');
            const mobileDropdown = document.getElementById('mobile-library-multi-dropdown');

            if (desktopToggle && desktopDropdown && !desktopToggle.hasAttribute('data-listener-attached')) {
                desktopToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    desktopDropdown.classList.toggle('hidden');
                });
                desktopToggle.setAttribute('data-listener-attached', 'true');
            }
            if (mobileToggle && mobileDropdown && !mobileToggle.hasAttribute('data-listener-attached')) {
                mobileToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    mobileDropdown.classList.toggle('hidden');
                });
                mobileToggle.setAttribute('data-listener-attached', 'true');
            }

            // Add event listeners for checkboxes (only if not already added)
            allLibraries.forEach(library => {
                const desktopCheckbox = document.getElementById(`desktop-lib-${library.id}`);
                const mobileCheckbox = document.getElementById(`mobile-lib-${library.id}`);

                if (desktopCheckbox && !desktopCheckbox.hasAttribute('data-listener-attached')) {
                    desktopCheckbox.addEventListener('change', handleLibraryCheckboxChange);
                    desktopCheckbox.setAttribute('data-listener-attached', 'true');
                }
                if (mobileCheckbox && !mobileCheckbox.hasAttribute('data-listener-attached')) {
                    mobileCheckbox.addEventListener('change', handleLibraryCheckboxChange);
                    mobileCheckbox.setAttribute('data-listener-attached', 'true');
                }
            });

            // Close dropdowns when clicking outside (only if not already added)
            if (!window.libraryClickListenerAttached) {
                document.addEventListener('click', (e) => {
                    if (desktopDropdown && !desktopMulti.contains(e.target)) {
                        desktopDropdown.classList.add('hidden');
                    }
                    if (mobileDropdown && !mobileMulti.contains(e.target)) {
                        mobileDropdown.classList.add('hidden');
                    }
                });
                window.libraryClickListenerAttached = true;
            }
        }

    } catch (error) {
        console.error('Error loading libraries:', error);
        showToast('error', 'Failed to load music libraries');

        // Hide loading and show error state
        const desktopLoading = document.getElementById('library-loading');
        const mobileLoading = document.getElementById('mobile-library-loading');
        const desktopSingle = document.getElementById('library-single');
        const mobileSingle = document.getElementById('mobile-library-single');
        const desktopMulti = document.getElementById('library-multi');
        const mobileMulti = document.getElementById('mobile-library-multi');

        // Hide all states
        if (desktopLoading) desktopLoading.classList.add('hidden');
        if (mobileLoading) mobileLoading.classList.add('hidden');
        if (desktopSingle) desktopSingle.classList.add('hidden');
        if (mobileSingle) mobileSingle.classList.add('hidden');
        if (desktopMulti) desktopMulti.classList.add('hidden');
        if (mobileMulti) mobileMulti.classList.add('hidden');
    }
}

// Update the display text for multi-library selector
function updateLibraryDisplayText() {
    const desktopText = document.getElementById('library-multi-text');
    const mobileText = document.getElementById('mobile-library-multi-text');

    if (selectedLibraryIds.length === 0) {
        if (desktopText) desktopText.textContent = 'Select library';
        if (mobileText) mobileText.textContent = 'Select library';
        if (desktopText) desktopText.className = 'text-gray-500 truncate';
        if (mobileText) mobileText.className = 'text-gray-500 truncate';
    } else if (selectedLibraryIds.length === 1) {
        const library = allLibraries.find(lib => lib.id === selectedLibraryIds[0]);
        const libraryName = library ? library.name : '1 library';
        if (desktopText) desktopText.textContent = libraryName;
        if (mobileText) mobileText.textContent = libraryName;
        if (desktopText) desktopText.className = 'text-gray-900 truncate';
        if (mobileText) mobileText.className = 'text-gray-900 truncate';
    } else {
        if (desktopText) desktopText.textContent = `${selectedLibraryIds.length} libraries`;
        if (mobileText) mobileText.textContent = `${selectedLibraryIds.length} libraries`;
        if (desktopText) desktopText.className = 'text-gray-900 truncate';
        if (mobileText) mobileText.className = 'text-gray-900 truncate';
    }
}

// Handle library checkbox changes
function handleLibraryCheckboxChange(e) {
    const libraryId = e.target.value;
    const isChecked = e.target.checked;

    if (isChecked) {
        if (!selectedLibraryIds.includes(libraryId)) {
            selectedLibraryIds.push(libraryId);
        }
    } else {
        selectedLibraryIds = selectedLibraryIds.filter(id => id !== libraryId);
    }

    // Sync checkboxes between desktop and mobile
    const desktopCheckbox = document.getElementById(`desktop-lib-${libraryId}`);
    const mobileCheckbox = document.getElementById(`mobile-lib-${libraryId}`);

    if (desktopCheckbox && desktopCheckbox !== e.target) {
        desktopCheckbox.checked = isChecked;
    }
    if (mobileCheckbox && mobileCheckbox !== e.target) {
        mobileCheckbox.checked = isChecked;
    }

    // Update localStorage
    localStorage.setItem('selectedLibraryIds', JSON.stringify(selectedLibraryIds));

    // Update global reference for navigation module
    window.selectedLibraryIds = selectedLibraryIds;

    // Update display text
    updateLibraryDisplayText();

    // Refresh current page content if needed
    const currentPage = window.getPageFromURL ? window.getPageFromURL(window.location.pathname) : 'home';
    console.log(`📚 Current page detected: ${currentPage}, pathname: ${window.location.pathname}`);
    if (currentPage === 'this-is-artist') {
        console.log(`🎨 Reloading artists for libraries:`, selectedLibraryIds);
        // Import and call loadArtists from playlist-manager when needed
        import('./playlist-manager.js').then(module => {
            if (module.loadArtists) {
                module.loadArtists(selectedLibraryIds);
            }
        });
    } else if (currentPage === 'genre-mix') {
        console.log(`🎨 Reloading genres for libraries:`, selectedLibraryIds);
        // Import and call loadGenres from playlist-manager when needed
        import('./playlist-manager.js').then(module => {
            if (module.loadGenres) {
                module.loadGenres(selectedLibraryIds);
            }
        });
    } else if (currentPage === 'song-radio') {
        console.log(`🎵 Reloading scan status for libraries:`, selectedLibraryIds);
        // Import and call loadSongRadioScanStatus from song-radio when needed
        import('./song-radio.js').then(module => {
            if (module.loadSongRadioScanStatus) {
                module.loadSongRadioScanStatus();
            }
        });
    }

    // Update button states based on library selection
    updateButtonStates();

    console.log(`📚 Library selection updated:`, selectedLibraryIds);
}

// Update visual state of rediscover library radio buttons
function updateRediscoverRadioStates() {
    const freshRadiosContainer = document.getElementById('fresh-rediscover-library-radios');
    if (!freshRadiosContainer) return;

    const radioLabels = freshRadiosContainer.querySelectorAll('label');
    radioLabels.forEach(label => {
        const radioInput = label.querySelector('input[type="radio"]');
        const libraryInfo = label.querySelector('div.flex-1');
        const libraryName = libraryInfo ? libraryInfo.querySelector('div') : null;

        if (radioInput.checked) {
            // Selected state - blue background and border (matching scan library)
            label.classList.add('border-blue-500', 'bg-blue-50', 'hover:bg-blue-100');
            label.classList.remove('border-gray-200', 'bg-white', 'hover:bg-gray-50');
            if (libraryName) {
                libraryName.className = 'text-sm font-medium text-blue-900';
            }
        } else {
            // Unselected state - white background with gray border
            label.classList.remove('border-blue-500', 'bg-blue-50', 'hover:bg-blue-100');
            label.classList.add('border-gray-200', 'bg-white', 'hover:bg-gray-50');
            if (libraryName) {
                libraryName.className = 'text-sm font-medium text-gray-900';
            }
        }
    });
}

// Load libraries for rediscover page radio buttons
async function loadRediscoverLibraries() {
    try {
        const response = await fetch('/api/libraries');
        if (!response.ok) {
            throw new Error('Failed to fetch libraries');
        }

        const libraries = await response.json();

        // Get the parent container for the entire library selection section
        const librarySelectionSection = document.querySelector('[id="fresh-rediscover-library-radios"]')?.closest('div.block.mb-4');

        // If only one library, hide the entire section and auto-select it
        if (libraries.length === 1) {
            if (librarySelectionSection) {
                librarySelectionSection.classList.add('hidden');
            }
            // Auto-select the single library
            window.selectedRediscoverLibraryId = libraries[0].id;
            console.log(`📚 Single library detected for re-discover: ${libraries[0].name} (ID: ${libraries[0].id}) - hiding selector`);
            // Update button states before returning
            updateButtonStates();
            return;
        }

        // Load fresh radio buttons (only shown if multiple libraries)
        const freshRadiosContainer = document.getElementById('fresh-rediscover-library-radios');
        if (freshRadiosContainer) {
            freshRadiosContainer.innerHTML = '';

            for (const library of libraries) {
                // Get library stats to fetch track count
                let totalTracks = 0;
                try {
                    const statsResponse = await fetch(`/api/libraries/${library.id}/stats`);
                    if (statsResponse.ok) {
                        const stats = await statsResponse.json();
                        totalTracks = stats.total_tracks || 0;
                    }
                } catch (error) {
                    console.warn(`Failed to fetch stats for library ${library.id}:`, error);
                }

                const radioLabel = document.createElement('label');
                radioLabel.htmlFor = `fresh-rediscover-library-${library.id}`;
                radioLabel.className = 'flex p-3 w-full bg-white border border-gray-200 rounded-lg text-sm focus:border-blue-500 focus:ring-blue-500 cursor-pointer hover:bg-gray-50';

                const radioInput = document.createElement('input');
                radioInput.type = 'radio';
                radioInput.id = `fresh-rediscover-library-${library.id}`;
                radioInput.name = 'fresh-rediscover-library';
                radioInput.value = library.id;
                radioInput.className = 'shrink-0 mt-0.5 border-gray-200 rounded-full text-blue-600 focus:ring-blue-500 checked:border-blue-500 disabled:opacity-50 disabled:pointer-events-none';

                // Create container for library info
                const libraryInfo = document.createElement('div');
                libraryInfo.className = 'flex-1 ms-3';

                const libraryName = document.createElement('div');
                libraryName.className = 'text-sm font-medium text-gray-900';
                libraryName.innerHTML = `${library.name}<br><span class="text-xs text-gray-500 font-normal">${totalTracks} tracks</span>`;

                libraryInfo.appendChild(libraryName);

                radioLabel.appendChild(radioInput);
                radioLabel.appendChild(libraryInfo);
                freshRadiosContainer.appendChild(radioLabel);

                // Add change event listener
                radioInput.addEventListener('change', () => {
                    window.selectedRediscoverLibraryId = library.id;
                    updateRediscoverRadioStates(); // Update visual states
                    updateButtonStates();
                    console.log(`Selected rediscover library: ${library.id} (${library.name})`);
                });
            }

            // Pre-select first library if available
            if (libraries.length > 0) {
                const firstRadio = freshRadiosContainer.querySelector('input[type="radio"]');
                if (firstRadio) {
                    firstRadio.checked = true;
                    window.selectedRediscoverLibraryId = libraries[0].id;
                    updateRediscoverRadioStates(); // Update visual states initially
                    updateButtonStates();
                    console.log(`Pre-selected rediscover library: ${libraries[0].id} (${libraries[0].name})`);
                }
            }
        }
    } catch (error) {
        console.error('Error loading rediscover libraries:', error);
        showToast('error', 'Failed to load libraries for rediscover');
    }
}

// Update button states based on library and content selection
function updateButtonStates() {
    const hasRediscoverLibrary = window.selectedRediscoverLibraryId;

    // Update rediscover button
    const rediscoverBtn = document.getElementById('rediscover-btn');
    if (rediscoverBtn) {
        rediscoverBtn.disabled = !hasRediscoverLibrary;
    }

    // Update other buttons that require libraries
    // Add more button updates here as needed
}

// Check if libraries are selected and show warning if not
function checkLibrarySelection() {
    if (selectedLibraryIds.length === 0) {
        showToast('warning', 'Please select a music library.');
        // Highlight the library selector
        const libraryMulti = document.getElementById('library-multi');
        const mobileLibraryMulti = document.getElementById('mobile-library-multi');
        if (libraryMulti) {
            libraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
            setTimeout(() => libraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
        }
        if (mobileLibraryMulti) {
            mobileLibraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
            setTimeout(() => mobileLibraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
        }
        return false;
    }
    return true;
}

// Load statistics for a specific library (for scan page)
async function loadLibraryStats(libraryId) {
    try {
        console.log(`📊 Loading stats for library ${libraryId}`);

        // Get library stats from the proper endpoint
        const statsResponse = await fetch(`/api/libraries/${libraryId}/stats`);
        if (!statsResponse.ok) {
            throw new Error('Failed to fetch library statistics');
        }
        const statsData = await statsResponse.json();
        const totalTracks = statsData.total_tracks || 0;

        // Get scanned tracks count for this specific library
        let scannedTracks = 0;
        try {
            const analyzedResponse = await fetch(`/api/radio/analyzed-tracks?library_id=${libraryId}`);
            if (analyzedResponse.ok) {
                const analyzedData = await analyzedResponse.json();
                scannedTracks = analyzedData.tracks.length;
            }
        } catch (error) {
            console.warn('Failed to get analyzed tracks for library:', error);
        }

        // Update UI with stats
        const totalTracksElement = document.getElementById('library-total-tracks');
        const scannedTracksElement = document.getElementById('library-scanned-tracks');
        const progressBar = document.getElementById('library-scan-progress');

        if (totalTracksElement) {
            totalTracksElement.textContent = totalTracks.toLocaleString();
        }
        if (scannedTracksElement) {
            scannedTracksElement.textContent = scannedTracks.toLocaleString();
        }

        let percentage = 0;
        if (progressBar && totalTracks > 0) {
            percentage = Math.round((scannedTracks / totalTracks) * 100);
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }

        console.log(`📊 Library stats: ${scannedTracks}/${totalTracks} tracks scanned (${percentage}%)`);

    } catch (error) {
        console.error('Error loading library stats:', error);
        showToast('error', 'Failed to load library statistics');
    }
}
/**
 * LIBRARY SETUP FUNCTIONS
 * One-time setup for mapping music library paths to Navidrome libraries
 */

/**
 * Check if library mapping setup is needed
 * @returns {Promise<boolean>} true if setup is needed
 */
async function checkLibraryMappingNeeded() {
    try {
        // Check if MUSIC_LIBRARY_PATHS is configured
        const pathsResponse = await fetch('/api/library-paths');
        if (!pathsResponse.ok) return false;
        
        const pathsData = await pathsResponse.json();
        if (!pathsData.paths || pathsData.paths.length === 0) return false;

        // Check if any mappings already exist
        const mappingsResponse = await fetch('/api/library-mappings');
        if (!mappingsResponse.ok) return false;
        
        const mappingsData = await mappingsResponse.json();
        const existingMappings = mappingsData.mappings || [];

        // Setup needed if we have paths but no mappings
        return pathsData.paths.length > 0 && existingMappings.length === 0;
    } catch (error) {
        console.error('Error checking library mapping status:', error);
        return false;
    }
}

/**
 * Initialize library setup UI on welcome page
 */
async function initializeLibrarySetup() {
    console.log('🎵 Initializing library setup...');
    
    const needsSetup = await checkLibraryMappingNeeded();
    console.log(`Library mapping needed: ${needsSetup}`);

    if (!needsSetup) {
        console.log('✅ Library mapping already complete');
        return;
    }

    // Populate and show form
    await populateLibraryMappingForm();
    
    const alert = document.getElementById('library-setup-alert');
    if (alert) {
        alert.classList.remove('hidden');
        console.log('✅ Showed library setup alert with form');
    }

    // Setup button handler
    const saveBtn = document.getElementById('save-library-mappings-btn');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveLibraryMappings);
    }
}

/**
 * Populate the library mapping form with paths and libraries
 */
async function populateLibraryMappingForm() {
    console.log('🎵 Populating library mapping form...');
    
    try {
        // Get configured paths
        const pathsResponse = await fetch('/api/library-paths');
        const pathsData = await pathsResponse.json();
        const paths = pathsData.paths || [];

        // Get available libraries from Navidrome
        const librariesResponse = await fetch('/api/music-folders');
        const libraries = await librariesResponse.json();

        console.log(`📍 Found ${paths.length} paths and ${libraries.length} libraries`);

        // Build form
        const container = document.getElementById('library-mappings-container');
        if (!container) return;

        container.innerHTML = '';

        // Create a row for each path
        paths.forEach((path, index) => {
            const row = document.createElement('div');
            row.className = 'flex gap-3 items-center';
            row.innerHTML = `
                <div class="w-20 text-sm font-medium text-gray-600 flex-shrink-0">
                    Path ${index + 1}:
                </div>
                <div class="w-32 text-sm text-gray-600 px-3 py-2 bg-white rounded font-mono flex-shrink-0 truncate border border-gray-300">
                    ${path}
                </div>
                <select class="library-selector flex-1 max-w-xs px-3 py-2 border border-gray-300 rounded text-sm bg-white text-gray-800" data-path="${path}" data-index="${index}">
                    <option value="">← Select library</option>
                    ${libraries.map(lib => `<option value="${lib.id}">${lib.name} (ID: ${lib.id})</option>`).join('')}
                </select>
            `;
            container.appendChild(row);
        });

        // Add change event listeners to disable selected libraries in other dropdowns
        const selectors = container.querySelectorAll('.library-selector');
        selectors.forEach(selector => {
            selector.addEventListener('change', updateLibraryAvailability);
        });

        console.log('✅ Library mapping form populated');
    } catch (error) {
        console.error('Error populating library mapping form:', error);
        showToast('error', 'Failed to load library setup form');
    }
}

/**
 * Update library availability based on selections
 * Disables libraries that are already selected in other dropdowns
 */
function updateLibraryAvailability() {
    const selectors = document.querySelectorAll('.library-selector');
    const selectedLibraries = new Set();
    
    // Collect all selected library IDs
    selectors.forEach(selector => {
        if (selector.value) {
            selectedLibraries.add(selector.value);
        }
    });
    
    // Update each dropdown's options
    selectors.forEach(selector => {
        const currentValue = selector.value;
        const options = selector.querySelectorAll('option');
        
        options.forEach(option => {
            // Keep the empty option and currently selected option enabled
            if (option.value === '' || option.value === currentValue) {
                option.disabled = false;
            } else if (selectedLibraries.has(option.value)) {
                // Disable options that are selected in other dropdowns
                option.disabled = true;
            } else {
                // Enable options that are not selected
                option.disabled = false;
            }
        });
    });
}

/**
 * Save library mappings
 */
async function saveLibraryMappings() {
    console.log('💾 Saving library mappings...');
    
    try {
        const selectors = document.querySelectorAll('.library-selector');
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
                    console.log(`✅ Saved mapping for library ${mapping.library_id}`);
                } else {
                    console.error(`❌ Failed to save mapping for library ${mapping.library_id}`);
                }
            } catch (error) {
                console.error(`Error saving mapping:`, error);
            }
        }

        if (successCount === mappings.length) {
            showToast('success', `✅ Successfully configured ${successCount} librar${successCount === 1 ? 'y' : 'ies'}!`);
            document.getElementById('library-setup-alert')?.classList.add('hidden');
            console.log('✅ All library mappings saved successfully');
        } else {
            showToast('error', `⚠️ Saved ${successCount}/${mappings.length} mappings. Please try again.`);
        }
    } catch (error) {
        console.error('Error saving library mappings:', error);
        showToast('error', 'Failed to save library mappings');
    }
}

/**
 * Check library mappings when welcome page becomes active
 * Shows alert if no mappings exist
 */
async function checkLibraryMappingsForWelcome() {
    console.log('🔍 Checking library mappings for welcome page...');

    try {
        const needsSetup = await checkLibraryMappingNeeded();
        console.log(`Library mapping needed: ${needsSetup}`);

        if (needsSetup) {
            // Show alert and populate form
            await populateLibraryMappingForm();
            const alert = document.getElementById('library-setup-alert');
            if (alert) {
                alert.classList.remove('hidden');
                console.log('✅ Showed library setup alert with form on welcome page');
            }

            // Setup button handler (same as initializeLibrarySetup)
            const saveBtn = document.getElementById('save-library-mappings-btn');
            if (saveBtn) {
                saveBtn.addEventListener('click', saveLibraryMappings);
                console.log('✅ Attached save event listener for welcome page navigation');
            }
        } else {
            // Hide alert if it exists
            const alert = document.getElementById('library-setup-alert');
            if (alert) {
                alert.classList.add('hidden');
                console.log('✅ Hid library setup alert (mappings exist)');
            }
        }
    } catch (error) {
        console.error('Error checking library mappings for welcome:', error);
    }
}

// Make function available globally
window.checkLibraryMappingsForWelcome = checkLibraryMappingsForWelcome;
