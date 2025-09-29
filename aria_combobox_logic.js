    // ARIA Combobox component logic
    const artistSearchInput = document.getElementById('artist-search-input');
    const artistResultsDropdown = document.getElementById('artist-results-dropdown');
    const artistResultsList = document.getElementById('artist-results-list');

    let allArtists = [];
    let availableArtists = [];
    let selectedArtist = null;  // For single selection
    let currentFocusedIndex = -1; // Track the currently focused item index

    // Show dropdown on focus
    artistSearchInput.addEventListener('focus', () => {
        if (availableArtists.length > 0 && artistSearchInput.value === '') {
            renderDropdown(availableArtists);
            artistResultsDropdown.classList.remove('dn');
            artistSearchInput.setAttribute('aria-expanded', 'true');
        }
    });

    // Handle clicks outside to close dropdown
    document.addEventListener('click', (e) => {
      const searchContainer = artistSearchInput.closest('.relative');
      if (!searchContainer.contains(e.target)) {
        artistResultsDropdown.classList.add('dn');
        artistSearchInput.setAttribute('aria-expanded', 'false');
        currentFocusedIndex = -1;
      }
    });

    // Filter dropdown list as user types
    artistSearchInput.addEventListener('input', () => {
      const searchTerm = artistSearchInput.value.toLowerCase();
      const filteredArtists = availableArtists.filter(artist =>
        artist.name.toLowerCase().includes(searchTerm)
      );
      renderDropdown(filteredArtists);
      
      // Show dropdown if we have results
      if (filteredArtists.length > 0 && artistSearchInput.value !== '') {
          artistResultsDropdown.classList.remove('dn');
          artistSearchInput.setAttribute('aria-expanded', 'true');
          currentFocusedIndex = -1; // Reset focus index when filtering
      } else {
          artistResultsDropdown.classList.add('dn');
          artistSearchInput.setAttribute('aria-expanded', 'false');
      }
    });
    
    // Keyboard navigation for the combobox
    artistSearchInput.addEventListener('keydown', (e) => {
        const items = Array.from(artistResultsList.querySelectorAll('[role="option"]'));
        const isVisible = !artistResultsDropdown.classList.contains('dn');
        
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                if (!isVisible && availableArtists.length > 0) {
                    // Show dropdown if not visible
                    const filteredArtists = availableArtists.filter(artist => 
                        artist.name.toLowerCase().includes(artistSearchInput.value.toLowerCase())
                    );
                    renderDropdown(filteredArtists);
                    artistResultsDropdown.classList.remove('dn');
                    artistSearchInput.setAttribute('aria-expanded', 'true');
                }
                
                if (items.length > 0) {
                    currentFocusedIndex = (currentFocusedIndex + 1) % items.length;
                    updateAriaActivedescendant(items[currentFocusedIndex]);
                }
                break;
                
            case 'ArrowUp':
                e.preventDefault();
                if (isVisible && items.length > 0) {
                    currentFocusedIndex = currentFocusedIndex <= 0 ? items.length - 1 : currentFocusedIndex - 1;
                    updateAriaActivedescendant(items[currentFocusedIndex]);
                }
                break;
                
            case 'Enter':
            case ' ':
                e.preventDefault(); // Prevent form submission
                if (isVisible && items.length > 0 && currentFocusedIndex >= 0) {
                    const selectedElement = items[currentFocusedIndex];
                    const artistId = selectedElement.dataset.id;
                    const artistName = selectedElement.textContent;
                    selectArtist({ id: artistId, name: artistName });
                }
                break;
                
            case 'Escape':
                e.preventDefault();
                artistResultsDropdown.classList.add('dn');
                artistSearchInput.setAttribute('aria-expanded', 'false');
                currentFocusedIndex = -1;
                break;
                
            case 'Tab':
                // Allow tab to move to next element, just hide the dropdown
                artistResultsDropdown.classList.add('dn');
                artistSearchInput.setAttribute('aria-expanded', 'false');
                currentFocusedIndex = -1;
                break;
        }
    });

    // Handle selection via mouse click
    artistResultsList.addEventListener('click', (e) => {
        if (e.target.getAttribute('role') === 'option') {
            const artistId = e.target.dataset.id;
            const artistName = e.target.textContent;
            selectArtist({ id: artistId, name: artistName });
        }
    });
    
    function selectArtist(artist) {
        selectedArtist = artist;
        
        // Mark artist as selected in available artists list
        const artistInList = availableArtists.find(a => a.id === artist.id);
        if (artistInList) {
            artistInList.selected = true;
        }
        
        // Set the input value to the selected artist name
        artistSearchInput.value = artist.name;
        
        // Close the dropdown
        artistResultsDropdown.classList.add('dn');
        artistSearchInput.setAttribute('aria-expanded', 'false');
        currentFocusedIndex = -1;
        
        // Remove focus from the input so user can tab to the submit button
        artistSearchInput.blur();
    }

    function renderDropdown(artists) {
        artistResultsList.innerHTML = '';
        
        if (artists.length === 0) {
            const noResults = document.createElement('div');
            noResults.className = 'pa2 gray f6';
            noResults.textContent = 'No results found';
            artistResultsList.appendChild(noResults);
            return;
        }

        artists.forEach((artist, index) => {
            const item = document.createElement('div');
            item.className = 'pa2 f6 pointer hover-bg-light-gray';
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', 'false');
            if (artist.selected) {
                item.classList.add('gray', 'bg-light-gray');
                item.style.cursor = 'default';
                item.style.opacity = '0.6';
            }
            item.dataset.id = artist.id;
            item.textContent = artist.name;
            artistResultsList.appendChild(item);
        });
    }
    
    function updateAriaActivedescendant(element) {
        if (element) {
            // Generate a temporary ID if needed
            if (!element.id) {
                element.id = 'option-' + element.dataset.id;
            }
            artistSearchInput.setAttribute('aria-activedescendant', element.id);
            
            // Remove previous highlighting
            const items = Array.from(artistResultsList.querySelectorAll('[role="option"]'));
            items.forEach(item => {
                item.classList.remove('bg-near-white');
            });
            
            // Highlight the current item
            element.classList.add('bg-near-white');
            
            // Scroll the focused item into view
            element.scrollIntoView({ block: 'nearest' });
        }
    }