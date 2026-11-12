/**
 * Navigation and Mobile Menu functionality for Magic Lists
 * Handles page routing, sidebar management, and mobile menu interactions
 */

import { showToast } from './utils.js';
import { selectedLibraryIds } from '../modules/library-manager.js';
import { loadArtists, loadGenres } from '../modules/playlist-manager.js';
import { initializeSongRadioPage } from '../modules/main-app.js';

// Mobile menu elements
let mobileMenuBtn, mobileSidebar, sidebarOverlay, closeMobileSidebarBtn;

/**
 * Initialize mobile menu functionality
 */
export function initializeMobileMenu() {
    mobileMenuBtn = document.getElementById('hs-navbar-alignment-collapse');
    mobileSidebar = document.getElementById('mobileSidebar');
    sidebarOverlay = document.getElementById('sidebarOverlay');
    closeMobileSidebarBtn = document.getElementById('closeMobileSidebar');

    if (!mobileMenuBtn || !mobileSidebar || !sidebarOverlay) {
        console.warn('Mobile menu elements not found');
        return;
    }

    // Mobile menu toggle
    mobileMenuBtn.addEventListener('click', function() {
        mobileSidebar.classList.toggle('-translate-x-full');
        sidebarOverlay.classList.toggle('hidden');
    });

    // Close sidebar when clicking on close button
    if (closeMobileSidebarBtn) {
        closeMobileSidebarBtn.addEventListener('click', function() {
            mobileSidebar.classList.add('-translate-x-full');
            sidebarOverlay.classList.add('hidden');
        });
    }

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
}

/**
 * Set active menu item styling
 * @param {string} page - Page identifier
 */
export function setActiveMenuItem(page) {
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

/**
 * Show/hide content sections based on page
 * @param {string} contentId - ID of content section to show
 */
export function showContent(contentId) {
     // Hide all content sections
     const contentSections = ['welcome-content', 'this-is-content', 'rediscover-content', 'genre-mix-content', 'song-radio-content', 'manage-playlists-content', 'system-check-content', 'scan-library-content', 'manage-library-mappings-page', 'terms-content'];
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

          // Load content-specific data
          if (contentId === 'welcome-content') {
              setTimeout(() => {
                  console.log('🔄 Checking library mappings for welcome page...');
                  if (window.checkLibraryMappingsForWelcome) {
                      window.checkLibraryMappingsForWelcome();
                  } else {
                      console.error('checkLibraryMappingsForWelcome not found on window');
                  }
              }, 100);
          } else if (contentId === 'scan-library-content') {
              setTimeout(() => {
                  console.log('🔄 Checking library mappings for scan library page...');
                  if (window.checkLibraryMappingsForScanPage) {
                      window.checkLibraryMappingsForScanPage();
                  } else {
                      console.error('checkLibraryMappingsForScanPage not found on window');
                  }
              }, 100);
          } else if (contentId === 'rediscover-content') {
              setTimeout(() => {
                  console.log('🔄 Loading rediscover libraries...');
                  if (window.loadRediscoverLibraries) {
                      window.loadRediscoverLibraries();
                  } else {
                      console.error('loadRediscoverLibraries not found on window');
                  }
              }, 100);
          }
     } else {
         console.log('Target content not found:', contentId);
     }
 }

/**
 * Get page identifier from URL path
 * @param {string} pathname - URL pathname
 * @returns {string} Page identifier
 */
export function getPageFromURL(pathname) {
    if (pathname === '/' || pathname === '/index.html') {
        return 'welcome';
    }
    
    // Remove leading slash and convert to page name
    const page = pathname.replace(/^\//, '');
    
    // Map paths to page identifiers
     const pageMap = {
         'this-is': 'this-is-artist',
         're-discover': 're-discover',
         'genre-mix': 'genre-mix',
         'song-radio': 'song-radio',
         'playlists': 'playlists',
         'system-check': 'system-check',
         'scan-library': 'scan-library',
         'manage-library-mappings': 'manage-library-mappings',
         'terms': 'terms'
     };
    
    return pageMap[page] || 'welcome';
}

/**
 * Update browser URL without page reload
 * @param {string} page - Page identifier
 */
export function updateURL(page) {
     const pageToPath = {
         'welcome': '/',
         'this-is-artist': '/this-is',
         're-discover': '/re-discover',
         'genre-mix': '/genre-mix',
         'song-radio': '/song-radio',
         'playlists': '/playlists',
         'system-check': '/system-check',
         'scan-library': '/sonic-analysis',
         'manage-library-mappings': '/library-settings',
         'terms': '/terms'
     };
    
    const path = pageToPath[page] || '/';
    
    if (window.history && window.history.pushState) {
        window.history.pushState({ page: page }, '', path);
    }
}

/**
 * Navigate to home page
 */
export function navigateToHome() {
    showContent('welcome-content');
    setActiveMenuItem('welcome');
    updateURL('welcome');
}

/**
 * Close mobile sidebar (utility function)
 */
export function closeMobileSidebar() {
    if (mobileSidebar && sidebarOverlay) {
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
}

/**
 * Setup global navigation event listeners
 */
export function initializeNavigation() {
    // Add click handlers to all navigation links
    document.addEventListener('click', function(event) {
        const link = event.target.closest('[data-page]');
        if (link) {
            event.preventDefault();
            const page = link.getAttribute('data-page');
            console.log('Clicked link with data-page:', page);

            // Use the shared navigation handler
            handlePageNavigation(page);
            
            // Update URL based on page (only for click navigation, not popstate)
            updateURL(page);
            
            // Close mobile sidebar if clicked
            if (window.innerWidth < 768) {
                closeMobileSidebar();
            }
        }
    });

    // Handle browser back/forward buttons
    window.addEventListener('popstate', function(event) {
        const page = event.state ? event.state.page : getPageFromURL(window.location.pathname);
        handlePageNavigation(page);
    });
}

/**
 * Handle page navigation (used by both click and popstate)
 * @param {string} page - Page identifier
 */
export function handlePageNavigation(page) {
    console.log('Navigating to page:', page, 'typeof:', typeof page);
    
    // Cleanup Song Radio event listener when navigating away
    if (window.songRadioClickHandler && page !== 'song-radio') {
        document.removeEventListener('click', window.songRadioClickHandler);
        window.songRadioClickHandler = null;
        console.log('🧹 Cleaned up Song Radio event listener');
    }
    
    // Track page view with Rybbit
    if (typeof window.rybbit !== 'undefined') {
        window.rybbit.pageview();
    }

    // Map page to content
    let contentId;
    console.log('Setting contentId for page:', page, 'length:', page.length);
    console.log('Page === "scan-library":', page === 'scan-library');
    if (page === 'home') {
        contentId = 'welcome-content';
    } else if (page === 'this-is-artist') {
        contentId = 'this-is-content';
        // Load artists when navigating to This Is page (only if libraries selected)
        console.log('🧭 Navigation to this-is-artist, selectedLibs:', selectedLibraryIds);
        if (selectedLibraryIds && selectedLibraryIds.length > 0) {
            console.log('🧭 Calling loadArtists in 100ms...');
            setTimeout(() => {
                loadArtists();
            }, 100);
        } else {
            console.log('🧭 Not loading artists - no libraries selected');
        }
    } else if (page === 're-discover') {
        contentId = 'rediscover-content';
    } else if (page === 'genre-mix') {
        contentId = 'genre-mix-content';
        // Load genres when navigating to Genre Mix page (only if libraries selected)
        if (selectedLibraryIds && selectedLibraryIds.length > 0) {
            setTimeout(() => {
                loadGenres(selectedLibraryIds);
            }, 100);
        }
    } else if (page === 'song-radio') {
        contentId = 'song-radio-content';
        // Initialize song radio page
        setTimeout(() => {
            initializeSongRadioPage();
        }, 100);
        // Always refresh scan status on page visit
        setTimeout(() => {
            import('../modules/song-radio.js').then(module => {
                if (module.loadSongRadioScanStatus) module.loadSongRadioScanStatus();
            });
        }, 100);
        // Check for scan path errors on song radio page visit
        setTimeout(() => {
            import('../modules/system-check.js').then(module => {
                if (module.checkScanPathErrors) module.checkScanPathErrors();
            });
        }, 200);
    } else if (page === 'playlists') {
        contentId = 'manage-playlists-content';
        // Load playlists when navigating to manage page
        setTimeout(() => {
            import('../modules/playlist-manager.js').then(module => {
                if (module.loadPlaylists) module.loadPlaylists();
            });
        }, 100);
    } else if (page === 'system-check') {
        contentId = 'system-check-content';
        // Auto-run system checks when navigating to system check page
        setTimeout(() => {
            import('../modules/system-check.js').then(module => {
                if (module.runSystemChecks) module.runSystemChecks();
            });
        }, 100);
    } else if (page === 'scan-library') {
        console.log('SCAN-LIBRARY CASE EXECUTED');
        contentId = 'scan-library-content';
        console.log('Set contentId to:', contentId);
        // Initialize scan library page
        setTimeout(() => {
            import('../modules/scan-library.js').then(module => {
                if (module.initializeScanLibraryPage) module.initializeScanLibraryPage();
            });
        }, 100);
     } else if (page === 'manage-library-mappings') {
         contentId = 'manage-library-mappings-page';
         // Initialize library mappings page
         setTimeout(() => {
             import('../modules/library-mappings.js').then(module => {
                 if (module.initializeLibraryMappings) module.initializeLibraryMappings();
             });
         }, 100);
     } else if (page === 'terms') {
         contentId = 'terms-content';
     } else {
         console.log('Unknown page:', page);
         contentId = 'welcome-content'; // Default fallback
     }
    console.log('Final contentId:', contentId);

    setActiveMenuItem(page);
    showContent(contentId);
}