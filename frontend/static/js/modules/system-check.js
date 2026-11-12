// System Health Check Module
// Handles all system health check functionality including database connectivity, API checks, and UI display

// Import utility functions
import { showToast } from '../core/utils.js';

// Export functions
export {
    checkDatabaseConnectivity,
    runSystemChecks,
    displaySystemChecks,
    toggleCheckDetails,
    getStatusIcon,
    getStatusColor,
    getStatusText,
    showSettingsHelp,
    initSystemCheckPage,
    checkScanPathErrors,
    showScanPathErrorAlert,
    hideScanPathErrorAlert
};

// Check for scan path validation errors and show alert if needed
async function checkScanPathErrors(sessionId = null) {
    const alertDiv = document.getElementById('scan-path-error-alert');
    const errorMessageDiv = document.getElementById('scan-path-error-message');

    try {
        // If a specific session ID is provided, check that scan directly
        if (sessionId) {
            try {
                const statusResponse = await fetch(`/api/scan/status/${sessionId}`);
                if (statusResponse.ok) {
                    const statusText = await statusResponse.text();
                    if (statusText.trim()) {
                        const statusData = JSON.parse(statusText);
                        if (statusData.status === 'failed' && statusData.errors && statusData.errors.length > 0) {
                            const pathError = statusData.errors.find(error =>
                                error.includes('Path validation failed') ||
                                error.includes('sample tracks not found') ||
                                error.includes('MUSIC_PATH')
                            );

                            if (pathError) {
                                // Show the alert with the specific error message
                                errorMessageDiv.textContent = pathError;
                                alertDiv.classList.remove('hidden');
                                // Scroll to top to make the alert visible
                                window.scrollTo({ top: 0, behavior: 'smooth' });
                                return;
                            }
                        }
                    }
                }
            } catch (parseError) {
                console.warn('Failed to parse scan status response:', parseError);
            }
        }

        // First, check scan history for recent path validation errors
        try {
            const historyResponse = await fetch('/api/scan/history');
            if (historyResponse.ok) {
                const historyText = await historyResponse.text();
                if (historyText.trim()) {
                    const historyData = JSON.parse(historyText);
                    const recentScans = historyData.scan_history || [];

                    // Check the most recent scan for path validation errors
                    if (recentScans.length > 0) {
                        const latestScan = recentScans[0]; // Most recent scan

                        // Check if scan failed and has path validation errors
                        if (latestScan.status === 'failed' && latestScan.errors && latestScan.errors.length > 0) {
                            const pathError = latestScan.errors.find(error =>
                                error.includes('Path validation failed') ||
                                error.includes('sample tracks not found') ||
                                error.includes('MUSIC_PATH')
                            );

                            if (pathError) {
                                // Show the alert with the specific error message
                                errorMessageDiv.textContent = pathError;
                                alertDiv.classList.remove('hidden');
                                return;
                            }
                        }
                    }
                }
            }
        } catch (parseError) {
            console.warn('Failed to parse scan history response:', parseError);
        }

        // Also check active scans for any that might have failed
        try {
            const activeResponse = await fetch('/api/scan/active');
            if (activeResponse.ok) {
                const activeText = await activeResponse.text();
                if (activeText.trim()) {
                    const activeData = JSON.parse(activeText);
                    const activeScans = activeData.active_scans || [];

                            for (const scan of activeScans) {
                                if (scan.status === 'failed' && scan.errors && scan.errors.length > 0) {
                                    const pathError = scan.errors.find(error =>
                                        error.includes('Path validation failed') ||
                                        error.includes('sample tracks not found') ||
                                        error.includes('MUSIC_PATH')
                                    );

                                    if (pathError) {
                                        // Show the alert with the specific error message
                                        errorMessageDiv.textContent = pathError;
                                        alertDiv.classList.remove('hidden');
                                        // Scroll to top to make the alert visible
                                        window.scrollTo({ top: 0, behavior: 'smooth' });
                                        return;
                                    }
                                }
                            }
                }
            }
        } catch (parseError) {
            console.warn('Failed to parse active scans response:', parseError);
        }

        // If no path errors found, hide the alert
        alertDiv.classList.add('hidden');

    } catch (error) {
        console.error('Error checking scan path errors:', error);
        // Don't show alert on network errors, just hide it
        alertDiv.classList.add('hidden');
    }
}

// Show scan path error alert with custom message
function showScanPathErrorAlert(message) {
    const alertDiv = document.getElementById('scan-path-error-alert');
    const errorMessageDiv = document.getElementById('scan-path-error-message');

    errorMessageDiv.textContent = message;
    alertDiv.classList.remove('hidden');
    // Scroll to top to make the alert visible
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Hide scan path error alert
function hideScanPathErrorAlert() {
    const alertDiv = document.getElementById('scan-path-error-alert');
    alertDiv.classList.add('hidden');
}

// Check database connectivity on app load
async function checkDatabaseConnectivity() {
    const alertDiv = document.getElementById('database-error-alert');

    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            // Database is accessible, hide alert
            alertDiv.classList.add('hidden');
        } else {
            // Database error, show alert
            alertDiv.classList.remove('hidden');
        }
    } catch (error) {
        // Network/database error, show alert
        alertDiv.classList.remove('hidden');
        console.error('Database connectivity check failed:', error);
    }
}

// Run comprehensive system checks
async function runSystemChecks() {
    const listContainer = document.getElementById('system-checks-list');
    const resultsContainer = document.getElementById('system-check-results');
    const successBanner = document.getElementById('success-banner');
    const errorBanner = document.getElementById('error-banner');
    const updateSettingsBtn = document.getElementById('update-settings-btn');
    const rerunBtn = document.getElementById('rerun-checks-btn');

    // Reset UI
    successBanner.classList.add('hidden');
    errorBanner.classList.add('hidden');
    updateSettingsBtn.classList.add('hidden');
    rerunBtn.disabled = true;
    rerunBtn.innerHTML = `
        <svg class="animate-spin h-4 w-4 text-gray-400 mr-2 inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-gray-400">Running checks...</span>
    `;

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
        rerunBtn.innerHTML = 'Re-run Checks';
    }
}

// Display system check results in the UI
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
                                ${check.status !== 'success' ? `<p class="text-sm ${statusColor}">${getStatusText(check.status)}</p>` : ''}
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
                        ${check.name === 'Library Mappings' && (check.status === 'success' || check.status === 'warning') ? `
                            <div class="mt-6 pt-4 border-t border-gray-200">
                                <div id="library-mappings-edit-section">
                                    <!-- Edit form will be loaded here -->
                                </div>
                            </div>
                        ` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

// Toggle visibility of check details
function toggleCheckDetails(checkId) {
    const detailsDiv = document.getElementById(`details-${checkId}`);
    const chevron = document.getElementById(`chevron-${checkId}`);
    
    if (detailsDiv.classList.contains('hidden')) {
        detailsDiv.classList.remove('hidden');
        chevron.classList.remove('rotate-90');
        chevron.classList.add('-rotate-90');
        
        // Load Library Mappings edit form if this is the Library Mappings check
        if (checkId === 'LibraryMappings') {
            loadLibraryMappingsEditForm();
        }
    } else {
        detailsDiv.classList.add('hidden');
        chevron.classList.remove('-rotate-90');
        chevron.classList.add('rotate-90');
    }
}

// Load the library mappings edit form in the system check
async function loadLibraryMappingsEditForm() {
    console.log('🎵 Loading library mappings edit form from system check...');
    const editSection = document.getElementById('library-mappings-edit-section');
    console.log('📍 Edit section element:', editSection);
    
    if (!editSection) {
        console.error('❌ Edit section element not found');
        return;
    }
    
    // Check if already has content (more than just comments)
    const hasContent = editSection.children.length > 0;
    if (hasContent) {
        console.log('ℹ️ Form already loaded');
        return; // Already loaded
    }
    
    try {
        console.log('🔄 Fetching library paths...');
        // Get configured paths
        const pathsResponse = await fetch('/api/library-paths');
        const pathsData = await pathsResponse.json();
        const paths = pathsData.paths || [];
        console.log('📍 Paths:', paths);

        console.log('🔄 Fetching music folders...');
        // Get available libraries from Navidrome
        const librariesResponse = await fetch('/api/music-folders');
        const libraries = await librariesResponse.json();
        console.log('📍 Libraries:', libraries);

        console.log('🔄 Fetching current mappings...');
        // Get current mappings
        const mappingsResponse = await fetch('/api/library-mappings');
        const mappingsData = await mappingsResponse.json();
        const currentMappings = {};
        mappingsData.mappings.forEach(m => {
            currentMappings[m.music_path] = m.library_id;
        });
        console.log('📍 Current mappings:', currentMappings);

        // Build form HTML
        let formHTML = `
            <p class="text-sm font-semibold text-gray-900 mb-3">Edit Library Mappings</p>
            <p class="text-sm text-gray-600 mb-4">Update your library path mappings:</p>
            <div id="system-check-library-mappings-container" class="space-y-3 mb-4">
        `;

        // Create HTML for each path row
        paths.forEach((path, index) => {
            const currentLibraryId = currentMappings[path];

            formHTML += `
                <div class="flex gap-3 items-center">
                    <div class="w-20 text-sm font-medium text-gray-600 flex-shrink-0">
                        Path ${index + 1}:
                    </div>
                    <div class="w-32 text-sm text-gray-600 px-3 py-2 bg-white rounded font-mono flex-shrink-0 truncate border border-gray-300">
                        ${path}
                    </div>
                    <select class="system-check-library-selector flex-1 max-w-xs px-3 py-2 border border-gray-300 rounded text-sm bg-white text-gray-800" data-path="${path}" data-index="${index}">
                        <option value="">← Select library</option>
                        ${libraries.map(lib => `<option value="${lib.id}" ${currentLibraryId && String(currentLibraryId) === String(lib.id) ? 'selected' : ''}>${lib.name} (ID: ${lib.id})</option>`).join('')}
                    </select>
                </div>
            `;
        });



        // Always show the reset button

        formHTML += `
            </div>
            <div class="flex gap-2">
                <button id="save-system-check-mappings-btn" class="px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 text-sm">
                    Save Changes
                </button>
                <button id="reset-library-mappings-btn" class="px-4 py-2 border border-red-500 text-red-600 font-medium rounded-lg hover:bg-red-50 text-sm">
                    Reset Mappings
                </button>
            </div>
        `;

        console.log('🔄 Setting innerHTML...');
        editSection.innerHTML = formHTML;
        console.log('✅ HTML set, adding event listeners...');

        // Add event listeners
        const selectors = editSection.querySelectorAll('.system-check-library-selector');
        console.log('📍 Found selectors:', selectors.length);
        selectors.forEach(selector => {
            selector.addEventListener('change', updateSystemCheckLibraryAvailability);
        });

        const saveBtn = document.getElementById('save-system-check-mappings-btn');
        const resetBtn = document.getElementById('reset-library-mappings-btn');
        console.log('📍 Save button:', saveBtn);
        console.log('📍 Reset button:', resetBtn);

        if (saveBtn) saveBtn.addEventListener('click', saveSystemCheckLibraryMappings);
        if (resetBtn) resetBtn.addEventListener('click', resetLibraryMappings);

        console.log('✅ Library mappings edit form loaded');
    } catch (error) {
        console.error('Error loading library mappings edit form:', error);
        editSection.innerHTML = '<p class="text-sm text-red-600">Failed to load edit form</p>';
    }
}

// Update library availability in system check (disable already selected)
function updateSystemCheckLibraryAvailability() {
    const selectors = document.querySelectorAll('.system-check-library-selector');
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

// Save library mappings from system check page
async function saveSystemCheckLibraryMappings() {
    console.log('💾 Saving library mappings from system check...');
    
    try {
        const selectors = document.querySelectorAll('.system-check-library-selector');
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
            showToast('success', `Successfully updated ${successCount} librar${successCount === 1 ? 'y' : 'ies'}!`);
            // Rerun checks to update the display
            runSystemChecks();
        } else {
            showToast('error', `Saved ${successCount}/${mappings.length} mappings. Please try again.`);
        }
    } catch (error) {
        console.error('Error saving library mappings:', error);
        showToast('error', 'Failed to save library mappings');
    }
}

// Reset library mappings (delete and potentially re-auto-map)
async function resetLibraryMappings() {
    console.log('🔄 Resetting library mappings...');

    try {
        // First, check if this is a single library scenario
        const librariesResponse = await fetch('/api/music-folders');
        const libraries = await librariesResponse.json();
        const isSingleLibrary = libraries.length === 1;

        // Delete existing mappings
        const selectors = document.querySelectorAll('.system-check-library-selector');
        let deleteCount = 0;

        for (const selector of selectors) {
            if (selector.value) {
                try {
                    const response = await fetch(`/api/library-mappings/${selector.value}`, {
                        method: 'DELETE'
                    });

                    if (response.ok) {
                        deleteCount++;
                    }
                } catch (error) {
                    console.error(`Error deleting mapping:`, error);
                }
            }
        }

        if (deleteCount > 0) {
            if (isSingleLibrary) {
                // For single library, trigger re-auto-mapping by calling health check
                console.log('🔄 Single library detected, triggering re-auto-mapping...');
                const healthResponse = await fetch('/api/health-check');
                if (healthResponse.ok) {
                    showToast('success', `Mappings reset and re-configured automatically!`);
                } else {
                    showToast('error', 'Failed to re-configure mappings');
                }
            } else {
                // For multi-library, just show success and update UI
                showToast('success', `Successfully reset ${deleteCount} librar${deleteCount === 1 ? 'y' : 'ies'} mapping!`);
            }

            // Rerun checks to update the display
            await runSystemChecks();
        } else {
            showToast('error', 'No mappings found to reset');
        }
    } catch (error) {
        console.error('Error resetting library mappings:', error);
        showToast('error', 'Failed to reset library mappings');
    }
}

// Get status icon HTML based on status
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

// Get status color class based on status
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

// Get status text based on status
function getStatusText(status) {
    switch (status) {
        case 'success':
            return 'Success';
        case 'warning':
            return 'Warning';
        case 'info':
            return '';
        case 'error':
            return 'Failed';
        default:
            return 'Checking...';
    }
}

// Show settings help dialog
function showSettingsHelp() {
    alert('To update your settings:\n\n1. Edit your .env file with the correct values\n2. Restart the application\n3. Run the system check again\n\nRefer to the SETUP.md file for detailed configuration instructions.');
}

// Initialize system check page - auto-run checks when page loads
function initSystemCheckPage() {
    runSystemChecks();
}

// Setup system check event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Run database connectivity check on page load (with delay to ensure app is ready)
    setTimeout(checkDatabaseConnectivity, 1000);

    // Run scan path error check on page load
    setTimeout(checkScanPathErrors, 1000);

    // Make functions available globally for onclick handlers
    window.runSystemChecks = runSystemChecks;
    window.showSettingsHelp = showSettingsHelp;
    window.toggleCheckDetails = toggleCheckDetails;

    // Setup system check page event listeners
    const rerunBtn = document.getElementById('rerun-checks-btn');
    if (rerunBtn) {
        rerunBtn.addEventListener('click', runSystemChecks);
    }

    const updateSettingsBtn = document.getElementById('update-settings-btn');
    if (updateSettingsBtn) {
        updateSettingsBtn.addEventListener('click', showSettingsHelp);
    }

    // Setup scan path error alert dismiss button
    const dismissScanPathErrorBtn = document.getElementById('dismiss-scan-path-error');
    if (dismissScanPathErrorBtn) {
        dismissScanPathErrorBtn.addEventListener('click', hideScanPathErrorAlert);
    }
});