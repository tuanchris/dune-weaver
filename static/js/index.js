// Global variables
let allPatterns = [];
let selectedPattern = null;
let previewObserver = null;
let currentBatch = 0;
const BATCH_SIZE = 40; // Increased batch size for better performance
let previewCache = new Map(); // Simple in-memory cache for preview data
let imageCache = new Map(); // Cache for preloaded images

// Global variables for lazy loading
let pendingPatterns = new Map(); // pattern -> element mapping
let batchTimeout = null;
const INITIAL_BATCH_SIZE = 12; // Smaller initial batch for faster first load
const LAZY_BATCH_SIZE = 5; // Reduced batch size for smoother loading
const MAX_RETRIES = 3; // Maximum number of retries for failed loads
const RETRY_DELAY = 1000; // Delay between retries in ms

// Shared caching for patterns list (persistent across sessions)
const PATTERNS_CACHE_KEY = 'dune_weaver_patterns_cache';

// Define constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Function to show status message
function showStatusMessage(message, type = 'success') {
    const statusContainer = document.getElementById('status-message-container');
    const statusMessage = document.getElementById('status-message');
    
    if (!statusContainer || !statusMessage) return;
    
    // Set message and color based on type
    statusMessage.textContent = message;
    statusMessage.className = `text-base font-semibold opacity-0 transform -translate-y-2 transition-all duration-300 ease-in-out px-4 py-2 rounded-lg shadow-lg ${
        type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' :
        type === 'error' ? 'bg-red-50 text-red-700 border border-red-200' :
        type === 'warning' ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' :
        'bg-blue-50 text-blue-700 border border-blue-200'
    }`;
    
    // Show message with animation
    requestAnimationFrame(() => {
        statusMessage.classList.remove('opacity-0', '-translate-y-2');
        statusMessage.classList.add('opacity-100', 'translate-y-0');
    });
    
    // Hide message after 5 seconds
    setTimeout(() => {
        statusMessage.classList.remove('opacity-100', 'translate-y-0');
        statusMessage.classList.add('opacity-0', '-translate-y-2');
    }, 5000);
}

// Function to log messages
function logMessage(message, type = LOG_TYPE.DEBUG) {
    console.log(`[${type}] ${message}`);
}

// Preload images in batch
async function preloadImages(urls) {
    const promises = urls.map(url => {
        return new Promise((resolve, reject) => {
            if (imageCache.has(url)) {
                resolve(imageCache.get(url));
                return;
            }
            const img = new Image();
            img.onload = () => {
                imageCache.set(url, img);
                resolve(img);
            };
            img.onerror = reject;
            img.src = url;
        });
    });
    return Promise.allSettled(promises);
}

// Initialize Intersection Observer for lazy loading
function initPreviewObserver() {
    if (previewObserver) {
        previewObserver.disconnect();
    }

    previewObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const previewContainer = entry.target;
                const pattern = previewContainer.dataset.pattern;
                if (pattern) {
                    addPatternToBatch(pattern, previewContainer);
                    previewObserver.unobserve(previewContainer);
                }
            }
        });
    }, {
        rootMargin: '200px 0px', // Reduced margin for more precise loading
        threshold: 0.1
    });
}

// Add pattern to pending batch for efficient loading
function addPatternToBatch(pattern, element) {
    // Check in-memory cache first
    if (previewCache.has(pattern)) {
        const previewData = previewCache.get(pattern);
        if (previewData && !previewData.error) {
            if (element) {
                updatePreviewElement(element, previewData.image_data);
            }
        }
        return;
    }

    // Add loading indicator with better styling
    if (!element.querySelector('img')) {
        element.innerHTML = `
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 rounded-full">
                <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-500"></div>
            </div>
            <div class="absolute inset-0 flex items-center justify-center">
                <div class="text-xs text-slate-500 mt-12">Loading...</div>
            </div>
        `;
    }

    // Add to pending batch
    pendingPatterns.set(pattern, element);
    
    // Process batch immediately if it's full
    if (pendingPatterns.size >= LAZY_BATCH_SIZE) {
        processPendingBatch();
    }
}

// Update preview element with smooth transition
function updatePreviewElement(element, imageData) {
    const img = new Image();
    img.onload = () => {
        element.innerHTML = '';
        element.appendChild(img);
        img.className = 'w-full h-full object-contain transition-opacity duration-300';
        img.style.opacity = '0';
        requestAnimationFrame(() => {
            img.style.opacity = '1';
        });
    };
    img.src = imageData;
    img.alt = 'Pattern Preview';
}

// Process pending patterns in batches
async function processPendingBatch() {
    if (pendingPatterns.size === 0) return;
    
    // Create a copy of current pending patterns and clear the original
    const currentBatch = new Map(pendingPatterns);
    pendingPatterns.clear();
    
    const patternsToLoad = Array.from(currentBatch.keys());
    
    try {
        logMessage(`Loading batch of ${patternsToLoad.length} pattern previews`, LOG_TYPE.DEBUG);
        
        const response = await fetch('/preview_thr_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_names: patternsToLoad })
        });

        if (response.ok) {
            const results = await response.json();
            
            // Process all results
            for (const [pattern, data] of Object.entries(results)) {
                const element = currentBatch.get(pattern);
                
                if (data && !data.error) {
                    // Cache in memory with size limit
                    if (previewCache.size > 100) { // Limit cache size
                        const oldestKey = previewCache.keys().next().value;
                        previewCache.delete(oldestKey);
                    }
                    previewCache.set(pattern, data);
                    
                    if (element) {
                        updatePreviewElement(element, data.image_data);
                    }
                } else {
                    handleLoadError(pattern, element, data?.error || 'Failed to load preview');
                }
            }
        }
    } catch (error) {
        logMessage(`Error loading preview batch: ${error.message}`, LOG_TYPE.ERROR);
        
        // Handle error for each pattern in batch
        for (const pattern of patternsToLoad) {
            const element = currentBatch.get(pattern);
            handleLoadError(pattern, element, error.message);
        }
    }
}

// Handle load errors with retry logic
function handleLoadError(pattern, element, error) {
    const retryCount = element.dataset.retryCount || 0;
    
    if (retryCount < MAX_RETRIES) {
        // Update retry count
        element.dataset.retryCount = parseInt(retryCount) + 1;
        
        // Show retry message
        element.innerHTML = `
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 rounded-full">
                <div class="text-xs text-slate-500 text-center">
                    <div>Failed to load</div>
                    <div>Retrying... (${retryCount + 1}/${MAX_RETRIES})</div>
                </div>
            </div>
        `;
        
        // Retry after delay
        setTimeout(() => {
            addPatternToBatch(pattern, element);
        }, RETRY_DELAY);
    } else {
        // Show final error state
        element.innerHTML = `
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 rounded-full">
                <div class="text-xs text-slate-500 text-center">
                    <div>Failed to load</div>
                    <div>Click to retry</div>
                </div>
            </div>
        `;
        
        // Add click handler for manual retry
        element.onclick = () => {
            element.dataset.retryCount = '0';
            addPatternToBatch(pattern, element);
        };
    }
    
    previewCache.set(pattern, { error: true });
}

// Load and display patterns
async function loadPatterns(forceRefresh = false) {
    try {
        logMessage('Loading patterns...', LOG_TYPE.INFO);
        
        // Check cache first (unless force refresh is requested)
        let patterns = null;
        if (!forceRefresh) {
            patterns = loadPatternsFromCache();
            if (patterns) {
                logMessage(`Using cached patterns list (${patterns.length} patterns)`, LOG_TYPE.DEBUG);
            }
        }
        
        // If no cache or force refresh, fetch from API
        if (!patterns) {
            logMessage('Fetching fresh patterns list from server', LOG_TYPE.DEBUG);
            const response = await fetch('/list_theta_rho_files');
            const allFiles = await response.json();
            logMessage(`Received ${allFiles.length} files from server`, LOG_TYPE.INFO);

            // Filter for .thr files
            patterns = allFiles.filter(file => file.endsWith('.thr'));
            logMessage(`Filtered to ${patterns.length} .thr files`, LOG_TYPE.INFO);
            
            // Save to cache
            savePatternsToCache(patterns);
            
            if (forceRefresh) {
                showStatusMessage('Patterns list refreshed successfully', 'success');
            }
        }
        
        // Sort patterns with custom_patterns on top and all alphabetically sorted
        const sortedPatterns = patterns.sort((a, b) => {
            const isCustomA = a.startsWith('custom_patterns/');
            const isCustomB = b.startsWith('custom_patterns/');

            if (isCustomA && !isCustomB) return -1;
            if (!isCustomA && isCustomB) return 1;
            return a.localeCompare(b);
        });

        allPatterns = sortedPatterns;
        currentBatch = 0;
        logMessage('Displaying initial batch of patterns...', LOG_TYPE.INFO);
        displayPatternBatch();
        logMessage('Initial batch loaded successfully.', LOG_TYPE.SUCCESS);
    } catch (error) {
        logMessage(`Error loading patterns: ${error.message}`, LOG_TYPE.ERROR);
        console.error('Full error:', error);
        
        // If this was a forced refresh and it failed, try to fall back to cache
        if (forceRefresh) {
            const cachedPatterns = loadPatternsFromCache();
            if (cachedPatterns) {
                logMessage('Falling back to cached patterns list', LOG_TYPE.WARNING);
                const sortedPatterns = cachedPatterns.sort((a, b) => {
                    const isCustomA = a.startsWith('custom_patterns/');
                    const isCustomB = b.startsWith('custom_patterns/');

                    if (isCustomA && !isCustomB) return -1;
                    if (!isCustomA && isCustomB) return 1;
                    return a.localeCompare(b);
                });
                allPatterns = sortedPatterns;
                currentBatch = 0;
                displayPatternBatch();
                showStatusMessage('Using cached patterns (refresh failed)', 'warning');
            } else {
                showStatusMessage('Failed to load patterns', 'error');
            }
        }
    }
}

// Display a batch of patterns with improved initial load
function displayPatternBatch() {
    const patternGrid = document.querySelector('.grid');
    if (!patternGrid) {
        logMessage('Pattern grid not found in the DOM', LOG_TYPE.ERROR);
        return;
    }

    const start = currentBatch * BATCH_SIZE;
    const end = Math.min(start + BATCH_SIZE, allPatterns.length);
    const batchPatterns = allPatterns.slice(start, end);

    // Display batch patterns
    batchPatterns.forEach(pattern => {
        const patternCard = createPatternCard(pattern);
        patternGrid.appendChild(patternCard);
    });

    // If there are more patterns to load, set up the observer for the last few cards
    if (end < allPatterns.length) {
        const lastCards = Array.from(patternGrid.children).slice(-3); // Observe last 3 cards
        lastCards.forEach(card => {
            const observer = new IntersectionObserver((entries) => {
                if (entries[0].isIntersecting) {
                    currentBatch++;
                    displayPatternBatch();
                    observer.disconnect();
                }
            }, {
                rootMargin: '200px 0px',
                threshold: 0.1
            });
            observer.observe(card);
        });
    }
}

// Create a pattern card element
function createPatternCard(pattern) {
    const card = document.createElement('div');
    card.className = 'pattern-card flex flex-col items-center gap-3 bg-gray-50';
    card.dataset.pattern = pattern;
    
    // Create preview container with proper styling for loading indicator
    const previewContainer = document.createElement('div');
    previewContainer.className = 'w-32 h-32 rounded-full bg-center bg-no-repeat bg-cover shadow-md relative bg-slate-100';
    previewContainer.dataset.pattern = pattern;
    
    // Add loading indicator
    previewContainer.innerHTML = '<div class="absolute inset-0 flex items-center justify-center"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-500"></div></div>';
    
    // Create pattern name
    const patternName = document.createElement('p');
    patternName.className = 'text-gray-700 text-sm font-medium text-center truncate w-full';
    patternName.textContent = pattern.replace('.thr', '').split('/').pop();

    // Add click handler
    card.onclick = () => selectPattern(pattern, card);

    // Start observing the preview container for lazy loading
    previewObserver.observe(previewContainer);

    card.appendChild(previewContainer);
    card.appendChild(patternName);
    
    return card;
}

// Select a pattern
function selectPattern(pattern, card) {
    // Remove selected class from all cards
    document.querySelectorAll('.pattern-card').forEach(c => {
        c.classList.remove('selected');
    });
    
    // Add selected class to clicked card
    card.classList.add('selected');
    
    // Show pattern preview
    showPatternPreview(pattern);
}

// Show pattern preview
async function showPatternPreview(pattern) {
    try {
        // Check in-memory cache first
        let data = previewCache.get(pattern);
        
        // If not in cache, fetch it
        if (!data) {
            const response = await fetch('/preview_thr_batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_names: [pattern] })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const results = await response.json();
            data = results[pattern];
            if (data && !data.error) {
                // Cache in memory
                previewCache.set(pattern, data);
            } else {
                throw new Error(data?.error || 'Failed to get preview data');
            }
        }

        const previewPanel = document.getElementById('patternPreviewPanel');
        const layoutContainer = document.querySelector('.layout-content-container');
        
        // Update preview content
        if (data.image_data) {
            document.getElementById('patternPreviewImage').src = data.image_data;
        }
        
        // Set pattern name in the preview panel
        const patternName = pattern.replace('.thr', '').split('/').pop();
        document.getElementById('patternPreviewTitle').textContent = patternName;

        // Format and display coordinates
        const formatCoordinate = (coord) => {
            if (!coord) return '(0, 0)';
            const x = coord.x !== undefined ? coord.x.toFixed(1) : '0.0';
            const y = coord.y !== undefined ? coord.y.toFixed(1) : '0.0';
            return `(${x}, ${y})`;
        };

        document.getElementById('firstCoordinate').textContent = formatCoordinate(data.first_coordinate);
        document.getElementById('lastCoordinate').textContent = formatCoordinate(data.last_coordinate);
        
        // Show preview panel
        previewPanel.classList.remove('translate-x-full');
        if (window.innerWidth >= 1024) {
            // For large screens, show preview alongside content
            layoutContainer.parentElement.classList.add('preview-open');
            previewPanel.classList.remove('lg:opacity-0', 'lg:pointer-events-none');
        } else {
            // For small screens, show preview as overlay
            layoutContainer.parentElement.classList.remove('preview-open');
        }

        // Setup preview panel events
        setupPreviewPanelEvents(pattern);
    } catch (error) {
        logMessage(`Error showing preview: ${error.message}`, LOG_TYPE.ERROR);
    }
}

function hidePatternPreview() {
    const previewPanel = document.getElementById('patternPreviewPanel');
    const layoutContainer = document.querySelector('.layout-content-container');
    
    previewPanel.classList.add('translate-x-full');
    if (window.innerWidth >= 1024) {
        previewPanel.classList.add('lg:opacity-0', 'lg:pointer-events-none');
    }
    layoutContainer.parentElement.classList.remove('preview-open');
}

// Add window resize handler
window.addEventListener('resize', () => {
    const previewPanel = document.getElementById('patternPreviewPanel');
    const layoutContainer = document.querySelector('.layout-content-container');
    
    if (window.innerWidth >= 1024) {
        if (!previewPanel.classList.contains('translate-x-full')) {
            layoutContainer.parentElement.classList.add('preview-open');
            previewPanel.classList.remove('lg:opacity-0', 'lg:pointer-events-none');
        }
    } else {
        layoutContainer.parentElement.classList.remove('preview-open');
        previewPanel.classList.add('lg:opacity-0', 'lg:pointer-events-none');
    }
});

// Setup preview panel events
function setupPreviewPanelEvents(pattern) {
    const panel = document.getElementById('patternPreviewPanel');
    const closeButton = document.getElementById('closePreviewPanel');
    const playButton = document.getElementById('playPattern');
    const deleteButton = document.getElementById('deletePattern');
    const preExecutionInputs = document.querySelectorAll('input[name="preExecutionAction"]');

    // Close panel when clicking the close button
    closeButton.onclick = () => {
        hidePatternPreview();
        // Remove selected state from all cards when closing
        document.querySelectorAll('.pattern-card').forEach(c => {
            c.classList.remove('selected');
        });
    };

    // Handle play button click
    playButton.onclick = async () => {
        if (!pattern) {
            showStatusMessage('No pattern selected', 'error');
            return;
        }

        try {
            // Immediately show the currently playing bar
            try {
                localStorage.setItem('playerBarVisible', '1');
                if (window.setPlayerBarVisibility) {
                    window.setPlayerBarVisibility(true, true);
                }
            } catch (e) {}

            // Get the selected pre-execution action
            const preExecutionInput = document.querySelector('input[name="preExecutionAction"]:checked');
            const preExecution = preExecutionInput ? preExecutionInput.parentElement.textContent.trim().toLowerCase() : 'none';

            const response = await fetch('/run_theta_rho', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_name: pattern,
                    pre_execution: preExecution
                })
            });

            const data = await response.json();
            if (response.ok) {
                showStatusMessage(`Running pattern: ${pattern.split('/').pop()}`, 'success');
                hidePatternPreview();
                
            } else {
                throw new Error(data.detail || 'Failed to run pattern');
            }
        } catch (error) {
            console.error('Error running pattern:', error);
            if (error.message.includes('409')) {
                showStatusMessage('Another pattern is already running', 'error');
            } else {
                showStatusMessage('Failed to run pattern', 'error');
            }
        }
    };

    // Handle delete button click
    deleteButton.onclick = async () => {
        if (!pattern.startsWith('custom_patterns/')) {
            logMessage('Cannot delete built-in patterns', LOG_TYPE.WARNING);
            showStatusMessage('Cannot delete built-in patterns', 'warning');
            return;
        }

        if (confirm('Are you sure you want to delete this pattern?')) {
            try {
                logMessage(`Deleting pattern: ${pattern}`, LOG_TYPE.INFO);
                const response = await fetch('/delete_theta_rho_file', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ file_name: pattern })
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                if (result.success) {
                    logMessage(`Pattern deleted successfully: ${pattern}`, LOG_TYPE.SUCCESS);
                    showStatusMessage(`Pattern "${pattern.split('/').pop()}" deleted successfully`);
                    // Remove the pattern card
                    const selectedCard = document.querySelector('.pattern-card.selected');
                    if (selectedCard) {
                        selectedCard.remove();
                    }
                    // Close the preview panel
                    const previewPanel = document.getElementById('patternPreviewPanel');
                    const layoutContainer = document.querySelector('.layout-content-container');
                    previewPanel.classList.add('translate-x-full');
                    if (window.innerWidth >= 1024) {
                        previewPanel.classList.add('lg:opacity-0', 'lg:pointer-events-none');
                    }
                    layoutContainer.parentElement.classList.remove('preview-open');
                    // Clear the preview panel content
                    document.getElementById('patternPreviewImage').src = '';
                    document.getElementById('patternPreviewTitle').textContent = 'Pattern Details';
                    document.getElementById('firstCoordinate').textContent = '(0, 0)';
                    document.getElementById('lastCoordinate').textContent = '(0, 0)';
                    // Refresh the pattern list (force refresh since pattern was deleted)
                    await loadPatterns(true);
                } else {
                    throw new Error(result.error || 'Unknown error');
                }
            } catch (error) {
                logMessage(`Failed to delete pattern: ${error.message}`, LOG_TYPE.ERROR);
                showStatusMessage(`Failed to delete pattern: ${error.message}`, 'error');
            }
        }
    };

    // Handle pre-execution action changes
    preExecutionInputs.forEach(input => {
        input.onchange = () => {
            const action = input.parentElement.textContent.trim();
            logMessage(`Pre-execution action changed to: ${action}`, LOG_TYPE.INFO);
        };
    });
}

// Search patterns
function searchPatterns(query) {
    if (!query) {
        // If search is empty, clear grid and show all patterns
        const patternGrid = document.querySelector('.grid');
        if (patternGrid) {
            patternGrid.innerHTML = '';
        }
        // Reset current batch and display from beginning
        currentBatch = 0;
        displayPatternBatch();
        return;
    }

    const searchInput = query.toLowerCase();
    const patternGrid = document.querySelector('.grid');
    if (!patternGrid) {
        logMessage('Pattern grid not found in the DOM', LOG_TYPE.ERROR);
        return;
    }

    // Clear existing patterns
    patternGrid.innerHTML = '';
    
    // Filter patterns
    const filteredPatterns = allPatterns.filter(pattern => 
        pattern.toLowerCase().includes(searchInput)
    );

    // Display filtered patterns
    filteredPatterns.forEach(pattern => {
        const patternCard = createPatternCard(pattern);
        patternGrid.appendChild(patternCard);
    });

    logMessage(`Showing ${filteredPatterns.length} patterns matching "${query}"`, LOG_TYPE.INFO);
}

// Filter patterns by category
function filterPatternsByCategory(category) {
    // TODO: Implement category filtering logic
    logMessage(`Filtering patterns by category: ${category}`, LOG_TYPE.INFO);
}

// Filter patterns by tag
function filterPatternsByTag(tag) {
    // TODO: Implement tag filtering logic
    logMessage(`Filtering patterns by tag: ${tag}`, LOG_TYPE.INFO);
}

// Initialize the patterns page
document.addEventListener('DOMContentLoaded', async () => {
    try {
        logMessage('Initializing patterns page...', LOG_TYPE.DEBUG);
        
        // Setup upload event handlers
        setupUploadEventHandlers();
        
        // Initialize intersection observer for lazy loading
        initPreviewObserver();

        // Setup search functionality
        const searchInput = document.getElementById('patternSearch');
        const searchButton = document.getElementById('searchButton');
        
        if (searchInput && searchButton) {
            // Search on button click
            searchButton.addEventListener('click', () => {
                searchPatterns(searchInput.value.trim());
            });
            
            // Search on Enter key
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    searchPatterns(searchInput.value.trim());
                }
            });
            
            // Clear search when input is empty
            searchInput.addEventListener('input', (e) => {
                if (e.target.value.trim() === '') {
                    searchPatterns('');
                }
            });
        }

        // Load patterns on page load
        await loadPatterns();
        
        logMessage('Patterns page initialized successfully', LOG_TYPE.SUCCESS);
    } catch (error) {
        logMessage(`Error during initialization: ${error.message}`, LOG_TYPE.ERROR);
    }
});

function updateCurrentlyPlayingUI(status) {
    // Get all required DOM elements once
    const container = document.getElementById('currently-playing-container');
    const fileNameElement = document.getElementById('currently-playing-file');
    const progressBar = document.getElementById('play_progress');
    const progressText = document.getElementById('play_progress_text');
    const pausePlayButton = document.getElementById('pausePlayCurrent');
    const speedDisplay = document.getElementById('current_speed_display');
    const speedInput = document.getElementById('speedInput');

    // Check if all required elements exist
    if (!container || !fileNameElement || !progressBar || !progressText) {
        console.log('Required DOM elements not found:', {
            container: !!container,
            fileNameElement: !!fileNameElement,
            progressBar: !!progressBar,
            progressText: !!progressText
        });
        setTimeout(() => updateCurrentlyPlayingUI(status), 100);
        return;
    }

    // Update container visibility based on status
    if (status.current_file && status.is_running) {
        document.body.classList.add('playing');
        container.style.display = 'flex';
    } else {
        document.body.classList.remove('playing');
        container.style.display = 'none';
    }

    // Update file name display
    if (status.current_file) {
        const fileName = status.current_file.replace('./patterns/', '');
        fileNameElement.textContent = fileName;
    } else {
        fileNameElement.textContent = 'No pattern playing';
    }

    // Update next file display
    const nextFileElement = document.getElementById('next-file');
    if (nextFileElement) {
        if (status.playlist && status.playlist.next_file) {
            const nextFileName = status.playlist.next_file.replace('./patterns/', '');
            nextFileElement.textContent = `(Next: ${nextFileName})`;
            nextFileElement.style.display = 'block';
        } else {
            nextFileElement.style.display = 'none';
        }
    }

    // Update speed display and input if they exist
    if (status.speed) {
        if (speedDisplay) {
            speedDisplay.textContent = `Current Speed: ${status.speed}`;
        }
        if (speedInput) {
            speedInput.value = status.speed;
        }
    }

    // Update pattern preview if it's a new pattern
    // ... existing code ...
}

// Load patterns from cache
function loadPatternsFromCache() {
    try {
        const cached = localStorage.getItem(PATTERNS_CACHE_KEY);
        if (cached) {
            return JSON.parse(cached);
        }
    } catch (error) {
        logMessage(`Error loading patterns from cache: ${error.message}`, LOG_TYPE.ERROR);
    }
    return null;
}

// Save patterns to cache
function savePatternsToCache(patterns) {
    try {
        localStorage.setItem(PATTERNS_CACHE_KEY, JSON.stringify(patterns));
    } catch (error) {
        logMessage(`Error saving patterns to cache: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Clear patterns cache
function clearPatternsCache() {
    try {
        localStorage.removeItem(PATTERNS_CACHE_KEY);
    } catch (error) {
        logMessage(`Error clearing patterns cache: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Check if patterns are cached
function hasCachedPatterns() {
    return localStorage.getItem(PATTERNS_CACHE_KEY) !== null;
}

// Get preview from IndexedDB cache
async function getPreviewFromCache(pattern) {
    try {
        const response = await fetch('/preview_thr_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_names: [pattern] })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const results = await response.json();
        return results[pattern];
    } catch (error) {
        logMessage(`Error getting preview from cache: ${error.message}`, LOG_TYPE.WARNING);
        return null;
    }
}

// Save preview to IndexedDB cache with size management
async function savePreviewToCache(pattern, previewData) {
    try {
        const response = await fetch(previewData.preview_url);
        const blob = await response.blob();
        const size = blob.size;
        
        const cacheEntry = {
            pattern: pattern,
            data: previewData,
            size: size,
            lastAccessed: Date.now(),
            created: Date.now()
        };
        
        return new Promise((resolve, reject) => {
            const request = store.put(cacheEntry);
            
            request.onsuccess = () => {
                logMessage(`Preview cached for ${pattern} (${(size / 1024).toFixed(1)}KB)`, LOG_TYPE.DEBUG);
                resolve();
            };
            
            request.onerror = () => reject(request.error);
        });
        
    } catch (error) {
        logMessage(`Error saving preview to cache: ${error.message}`, LOG_TYPE.WARNING);
    }
}

// Setup upload event handlers
function setupUploadEventHandlers() {
    // Upload file input handler
    document.getElementById('patternFileInput').addEventListener('change', async function(e) {
        const file = e.target.files[0];
        if (!file) return;

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/upload_theta_rho', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            if (result.success) {
                showStatusMessage(`Pattern "${file.name}" uploaded successfully`);
                // Refresh the pattern list (force refresh since new pattern was uploaded)
                await loadPatterns(true);
                // Clear the file input
                e.target.value = '';
            } else {
                showStatusMessage(`Failed to upload pattern: ${result.error}`, 'error');
            }
        } catch (error) {
            console.error('Error uploading pattern:', error);
            showStatusMessage(`Error uploading pattern: ${error.message}`, 'error');
        }
    });

    // Pattern deletion handler
    const deleteModal = document.getElementById('deleteConfirmModal');
    if (deleteModal) {
        const confirmBtn = deleteModal.querySelector('#confirmDeleteBtn');
        const cancelBtn = deleteModal.querySelector('#cancelDeleteBtn');
        
        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                const patternToDelete = confirmBtn.dataset.pattern;
                if (patternToDelete) {
                    await deletePattern(patternToDelete);
                    // Force refresh after deletion
                    await loadPatterns(true);
                }
                deleteModal.classList.add('hidden');
            });
        }
        
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                deleteModal.classList.add('hidden');
            });
        }
    }
} 