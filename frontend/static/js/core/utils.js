/**
 * Utility functions for Magic Lists frontend
 * Contains formatting helpers, toast notifications, and common utilities
 */

// Global state for toast management
let currentToast = null;

/**
 * Format dates in friendly format (e.g., "5 Oct 2025 10:12am")
 * @param {string} dateString - Date string to format
 * @returns {string} Formatted date string
 */
export function formatFriendlyDate(dateString) {
    if (!dateString) return 'Never';

    // Handle timestamps that come from server without timezone info
    // Treat them as UTC and convert to local timezone
    let date;
    
    if (dateString.includes('T') && (dateString.includes('Z') || dateString.includes('+') || dateString.includes('-'))) {
        // ISO format with timezone - parse as-is
        date = new Date(dateString);
    } else {
        // Format without timezone (e.g., "2025-11-17 03:17:59") - treat as UTC
        // Add Z suffix to indicate UTC
        const isoString = dateString.replace(' ', 'T') + 'Z';
        date = new Date(isoString);
    }
    
    // Use Intl API to format with user's local timezone
    // This automatically handles timezone conversion based on browser settings
    const formatter = new Intl.DateTimeFormat('en-AU', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
    });
    
    const parts = formatter.formatToParts(date);
    const day = parts.find(p => p.type === 'day').value;
    const month = parts.find(p => p.type === 'month').value;
    const year = parts.find(p => p.type === 'year').value;
    const hour = parts.find(p => p.type === 'hour').value;
    const minute = parts.find(p => p.type === 'minute').value;
    const period = parts.find(p => p.type === 'dayPeriod').value;

    return `${day} ${month} ${year} ${hour}:${minute}${period.toLowerCase()}`;
}

/**
 * Format duration in seconds to readable format
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted duration string
 */
export function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '-';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

/**
 * Format track titles for better display in select options
 * @param {string} title - Track title
 * @param {string} artist - Artist name
 * @returns {string} Formatted track title
 */
export function formatTrackTitle(title, artist) {
    if (!title) return 'Unknown Track';
    
    // Clean up the title
    let cleanTitle = title.replace(/^\d+\s+/, ''); // Remove leading track numbers
    cleanTitle = cleanTitle.replace(/\.(mp3|flac|wav|m4a|aac|ogg|wma)$/i, ''); // Remove extensions
    cleanTitle = cleanTitle.replace(/[-_]/g, ' '); // Replace separators
    cleanTitle = cleanTitle.replace(/\s+/g, ' ').trim(); // Clean whitespace
    
    // Capitalize words (title case)
    cleanTitle = cleanTitle.replace(/\b\w/g, l => l.toUpperCase());
    
    // Fix common capitalization issues
    cleanTitle = cleanTitle.replace(/\(Remix\)/gi, '(remix)');
    cleanTitle = cleanTitle.replace(/\(Mix\)/gi, '(mix)');
    cleanTitle = cleanTitle.replace(/\(Edit\)/gi, '(edit)');
    cleanTitle = cleanTitle.replace(/\bDj\b/gi, 'DJ');
    cleanTitle = cleanTitle.replace(/\bFt\b/gi, 'ft.');
    cleanTitle = cleanTitle.replace(/\bFeat\b/gi, 'feat.');
    
    // If artist is unknown, try to extract artist info from title if it looks like "Artist - Title"
    if (artist === 'Unknown Artist' || !artist) {
        // Check if title contains " - " which might indicate "Artist - Title"
        if (cleanTitle.includes(' - ')) {
            const parts = cleanTitle.split(' - ');
            if (parts.length >= 2) {
                const possibleArtist = parts[0].trim();
                const possibleTitle = parts.slice(1).join(' - ').trim();
                return `${possibleTitle} - ${possibleArtist}`;
            }
        }
        return cleanTitle;
    }
    
    // If we have proper artist info, format as "Title - Artist" for select options
    return `${cleanTitle} - ${artist}`;
}

/**
 * Format track title with HTML for display (not for select options)
 * @param {string} title - Track title
 * @param {string} artist - Artist name
 * @returns {string} Formatted HTML track title
 */
export function formatTrackTitleHTML(title, artist) {
    if (!title) return 'Unknown Track';
    
    // Clean up the title
    let cleanTitle = title.replace(/^\d+\s+/, ''); // Remove leading track numbers
    cleanTitle = cleanTitle.replace(/\.(mp3|flac|wav|m4a|aac|ogg|wma)$/i, ''); // Remove extensions
    cleanTitle = cleanTitle.replace(/[-_]/g, ' '); // Replace separators
    cleanTitle = cleanTitle.replace(/\s+/g, ' ').trim(); // Clean whitespace
    
    // Capitalize words (title case)
    cleanTitle = cleanTitle.replace(/\b\w/g, l => l.toUpperCase());
    
    // Fix common capitalization issues
    cleanTitle = cleanTitle.replace(/\(Remix\)/gi, '(remix)');
    cleanTitle = cleanTitle.replace(/\(Mix\)/gi, '(mix)');
    cleanTitle = cleanTitle.replace(/\(Edit\)/gi, '(edit)');
    cleanTitle = cleanTitle.replace(/\bDj\b/gi, 'DJ');
    cleanTitle = cleanTitle.replace(/\bFt\b/gi, 'ft.');
    cleanTitle = cleanTitle.replace(/\bFeat\b/gi, 'feat.');
    
    // If artist is unknown, try to extract artist info from title if it looks like "Artist - Title"
    if (artist === 'Unknown Artist' || !artist) {
        // Check if title contains " - " which might indicate "Artist - Title"
        if (cleanTitle.includes(' - ')) {
            const parts = cleanTitle.split(' - ');
            if (parts.length >= 2) {
                const possibleArtist = parts[0].trim();
                const possibleTitle = parts.slice(1).join(' - ').trim();
                return `${possibleTitle} - ${possibleArtist}`;
            }
        }
        return cleanTitle;
    }
    
    // If we have proper artist info, format as "Title <i>Artist</i>" with HTML
    return `${cleanTitle} <i class="text-gray-500">${artist}</i>`;
}

/**
 * Show toast notification
 * @param {string} type - Type of toast: 'success', 'error', 'loading'
 * @param {string} message - Message to display
 * @param {number} duration - Auto-dismiss duration in milliseconds (default: 5000)
 * @returns {string} Toast ID for reference
 */
export function showToast(type, message, duration = 5000) {
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

/**
 * Hide toast notification
 * @param {string} toastId - ID of toast to hide
 */
export function hideToast(toastId) {
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

/**
 * Debounce function calls
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Check if an element is visible in viewport
 * @param {Element} element - Element to check
 * @returns {boolean} Whether element is visible
 */
export function isElementInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
        rect.top >= 0 &&
        rect.left >= 0 &&
        rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
        rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
}