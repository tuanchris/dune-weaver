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

// IndexedDB cache for preview images with size management (shared with playlists page)
const PREVIEW_CACHE_DB_NAME = 'dune_weaver_previews';
const PREVIEW_CACHE_DB_VERSION = 1;
const PREVIEW_CACHE_STORE_NAME = 'previews';
const MAX_CACHE_SIZE_MB = 200;
const MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024;

let previewCacheDB = null;

// Define constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Cache progress storage keys
const CACHE_PROGRESS_KEY = 'dune_weaver_cache_progress';
const CACHE_TIMESTAMP_KEY = 'dune_weaver_cache_timestamp';
const CACHE_PROGRESS_EXPIRY = 24 * 60 * 60 * 1000; // 24 hours in milliseconds

// Animated Preview Variables
let animatedPreviewData = null;
let animationFrameId = null;
let isPlaying = false;
let currentProgress = 0;
let animationSpeed = 1;
let lastTimestamp = 0;

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

// Initialize IndexedDB for preview caching (shared with playlists page)
async function initPreviewCacheDB() {
    if (previewCacheDB) return previewCacheDB;
    
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(PREVIEW_CACHE_DB_NAME, PREVIEW_CACHE_DB_VERSION);
        
        request.onerror = () => {
            logMessage('Failed to open preview cache database', LOG_TYPE.ERROR);
            reject(request.error);
        };
        
        request.onsuccess = () => {
            previewCacheDB = request.result;
            logMessage('Preview cache database opened successfully', LOG_TYPE.DEBUG);
            resolve(previewCacheDB);
        };
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            
            // Create object store for preview cache
            const store = db.createObjectStore(PREVIEW_CACHE_STORE_NAME, { keyPath: 'pattern' });
            store.createIndex('lastAccessed', 'lastAccessed', { unique: false });
            store.createIndex('size', 'size', { unique: false });
            
            logMessage('Preview cache database schema created', LOG_TYPE.DEBUG);
        };
    });
}

// Get preview from IndexedDB cache
async function getPreviewFromCache(pattern) {
    try {
        if (!previewCacheDB) await initPreviewCacheDB();
        
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        
        return new Promise((resolve, reject) => {
            const request = store.get(pattern);
            
            request.onsuccess = () => {
                const result = request.result;
                if (result) {
                    // Update last accessed time
                    result.lastAccessed = Date.now();
                    store.put(result);
                    resolve(result.data);
                } else {
                    resolve(null);
                }
            };
            
            request.onerror = () => reject(request.error);
        });
    } catch (error) {
        logMessage(`Error getting preview from cache: ${error.message}`, LOG_TYPE.WARNING);
        return null;
    }
}

// Save preview to IndexedDB cache with size management
async function savePreviewToCache(pattern, previewData) {
    try {
        if (!previewCacheDB) await initPreviewCacheDB();
        
        // Validate preview data before attempting to fetch
        if (!previewData || !previewData.image_data) {
            logMessage(`Invalid preview data for ${pattern}, skipping cache save`, LOG_TYPE.WARNING);
            return;
        }
        
        // Convert preview URL to blob for size calculation
        const response = await fetch(previewData.image_data);
        const blob = await response.blob();
        const size = blob.size;
        
        // Check if we need to free up space
        await managePreviewCacheSize(size);
        
        const cacheEntry = {
            pattern: pattern,
            data: previewData,
            size: size,
            lastAccessed: Date.now(),
            created: Date.now()
        };
        
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        
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

// Manage cache size by removing least recently used items
async function managePreviewCacheSize(newItemSize) {
    try {
        const currentSize = await getPreviewCacheSize();
        
        if (currentSize + newItemSize <= MAX_CACHE_SIZE_BYTES) {
            return; // No cleanup needed
        }
        
        logMessage(`Cache size would exceed limit (${((currentSize + newItemSize) / 1024 / 1024).toFixed(1)}MB), cleaning up...`, LOG_TYPE.DEBUG);
        
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        const index = store.index('lastAccessed');
        
        // Get all entries sorted by last accessed (oldest first)
        const entries = await new Promise((resolve, reject) => {
            const request = index.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
        
        // Sort by last accessed time (oldest first)
        entries.sort((a, b) => a.lastAccessed - b.lastAccessed);
        
        let freedSpace = 0;
        const targetSpace = newItemSize + (MAX_CACHE_SIZE_BYTES * 0.1); // Free 10% extra buffer
        
        for (const entry of entries) {
            if (freedSpace >= targetSpace) break;
            
            await new Promise((resolve, reject) => {
                const deleteRequest = store.delete(entry.pattern);
                deleteRequest.onsuccess = () => {
                    freedSpace += entry.size;
                    logMessage(`Evicted cached preview for ${entry.pattern} (${(entry.size / 1024).toFixed(1)}KB)`, LOG_TYPE.DEBUG);
                    resolve();
                };
                deleteRequest.onerror = () => reject(deleteRequest.error);
            });
        }
        
        logMessage(`Freed ${(freedSpace / 1024 / 1024).toFixed(1)}MB from preview cache`, LOG_TYPE.DEBUG);
        
    } catch (error) {
        logMessage(`Error managing cache size: ${error.message}`, LOG_TYPE.WARNING);
    }
}

// Get current cache size
async function getPreviewCacheSize() {
    try {
        if (!previewCacheDB) return 0;
        
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readonly');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        
        return new Promise((resolve, reject) => {
            const request = store.getAll();
            
            request.onsuccess = () => {
                const totalSize = request.result.reduce((sum, entry) => sum + (entry.size || 0), 0);
                resolve(totalSize);
            };
            
            request.onerror = () => reject(request.error);
        });
        
    } catch (error) {
        logMessage(`Error getting cache size: ${error.message}`, LOG_TYPE.WARNING);
        return 0;
    }
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
async function addPatternToBatch(pattern, element) {
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

    // Check IndexedDB cache
    const cachedData = await getPreviewFromCache(pattern);
    if (cachedData && !cachedData.error) {
        // Add to in-memory cache for faster access
        previewCache.set(pattern, cachedData);
        if (element) {
            updatePreviewElement(element, cachedData.image_data);
        }
        return;
    }

    // Check if this is a newly uploaded pattern
    const isNewUpload = element?.dataset.isNewUpload === 'true';
    
    // Reset retry flags when starting fresh
    if (element) {
        element.dataset.retryCount = '0';
        element.dataset.hasTriedIndividual = 'false';
    }
    
    // Add loading indicator with better styling
    if (!element.querySelector('img')) {
        const loadingText = isNewUpload ? 'Generating preview...' : 'Loading...';
        element.innerHTML = `
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 rounded-full">
                <div class="bg-slate-200 rounded-full h-8 w-8 flex items-center justify-center">
                    <div class="bg-slate-500 rounded-full h-4 w-4"></div>
                </div>
            </div>
            <div class="absolute inset-0 flex items-center justify-center">
                <div class="text-xs text-slate-500 mt-12">${loadingText}</div>
            </div>
        `;
    }

    // Add to pending batch
    pendingPatterns.set(pattern, element);
    
    // Process batch immediately if it's full or if it's a new upload
    if (pendingPatterns.size >= LAZY_BATCH_SIZE || isNewUpload) {
        processPendingBatch();
    }
}

// Update preview element with smooth transition
function updatePreviewElement(element, imageUrl) {
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
    img.src = imageUrl;
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
                
                if (data && !data.error && data.image_data) {
                    // Cache in memory with size limit
                    if (previewCache.size > 100) { // Limit cache size
                        const oldestKey = previewCache.keys().next().value;
                        previewCache.delete(oldestKey);
                    }
                    previewCache.set(pattern, data);
                    
                    // Save to IndexedDB cache for persistence
                    await savePreviewToCache(pattern, data);
                    
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

// Trigger preview loading for currently visible patterns
function triggerPreviewLoadingForVisible() {
    // Get all pattern cards currently in the DOM
    const patternCards = document.querySelectorAll('.pattern-card');
    
    patternCards.forEach(card => {
        const pattern = card.dataset.pattern;
        const previewContainer = card.querySelector('.pattern-preview');
        
        // Check if this pattern needs preview loading
        if (pattern && !previewCache.has(pattern) && !pendingPatterns.has(pattern)) {
            // Add to batch for immediate loading
            addPatternToBatch(pattern, previewContainer);
        }
    });
    
    // Process any pending previews immediately
    if (pendingPatterns.size > 0) {
        processPendingBatch();
    }
}

// Load individual pattern preview (fallback when batch loading fails)
async function loadIndividualPreview(pattern, element) {
    try {
        logMessage(`Loading individual preview for ${pattern}`, LOG_TYPE.DEBUG);
        
        const response = await fetch('/preview_thr_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_names: [pattern] })
        });

        if (response.ok) {
            const results = await response.json();
            const data = results[pattern];
            
            if (data && !data.error && data.image_data) {
                // Cache in memory with size limit
                if (previewCache.size > 100) { // Limit cache size
                    const oldestKey = previewCache.keys().next().value;
                    previewCache.delete(oldestKey);
                }
                previewCache.set(pattern, data);
                
                // Save to IndexedDB cache for persistence
                await savePreviewToCache(pattern, data);
                
                if (element) {
                    updatePreviewElement(element, data.image_data);
                }
                
                logMessage(`Individual preview loaded successfully for ${pattern}`, LOG_TYPE.DEBUG);
            } else {
                throw new Error(data?.error || 'Failed to load preview data');
            }
        } else {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
    } catch (error) {
        logMessage(`Error loading individual preview for ${pattern}: ${error.message}`, LOG_TYPE.ERROR);
        // Continue with normal error handling
        handleLoadError(pattern, element, error.message);
    }
}

// Handle load errors with retry logic
function handleLoadError(pattern, element, error) {
    const retryCount = element.dataset.retryCount || 0;
    const isNewUpload = element.dataset.isNewUpload === 'true';
    const hasTriedIndividual = element.dataset.hasTriedIndividual === 'true';
    
    // Use longer delays for newly uploaded patterns
    const retryDelay = isNewUpload ? RETRY_DELAY * 2 : RETRY_DELAY;
    const maxRetries = isNewUpload ? MAX_RETRIES * 2 : MAX_RETRIES;
    
    if (retryCount < maxRetries) {
        // Update retry count
        element.dataset.retryCount = parseInt(retryCount) + 1;
        
        // Determine retry strategy
        let retryStrategy = 'batch';
        if (retryCount >= 1 && !hasTriedIndividual) {
            // After first batch attempt fails, try individual loading
            retryStrategy = 'individual';
            element.dataset.hasTriedIndividual = 'true';
        }
        
        // Show retry message with different text for new uploads and retry strategies
        let retryText;
        if (isNewUpload) {
            retryText = retryStrategy === 'individual' ? 
                `Trying individual load... (${retryCount + 1}/${maxRetries})` :
                `Generating preview... (${retryCount + 1}/${maxRetries})`;
        } else {
            retryText = retryStrategy === 'individual' ? 
                `Trying individual load... (${retryCount + 1}/${maxRetries})` :
                `Retrying... (${retryCount + 1}/${maxRetries})`;
        }
            
        element.innerHTML = `
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 rounded-full">
                <div class="text-xs text-slate-500 text-center">
                    <div>${isNewUpload ? 'Processing new pattern' : 'Failed to load'}</div>
                    <div>${retryText}</div>
                </div>
            </div>
        `;
        
        // Retry after delay with appropriate strategy
        setTimeout(() => {
            if (retryStrategy === 'individual') {
                loadIndividualPreview(pattern, element);
            } else {
                addPatternToBatch(pattern, element);
            }
        }, retryDelay);
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
            element.dataset.hasTriedIndividual = 'false';
            addPatternToBatch(pattern, element);
        };
    }
    
    previewCache.set(pattern, { error: true });
}

// Load and display patterns
async function loadPatterns(forceRefresh = false) {
    try {
        logMessage('Loading patterns...', LOG_TYPE.INFO);
        
        logMessage('Fetching fresh patterns list from server', LOG_TYPE.DEBUG);
        const response = await fetch('/list_theta_rho_files');
        const allFiles = await response.json();
        logMessage(`Received ${allFiles.length} files from server`, LOG_TYPE.INFO);

        // Filter for .thr files
        let patterns = allFiles.filter(file => file.endsWith('.thr'));
        logMessage(`Filtered to ${patterns.length} .thr files`, LOG_TYPE.INFO);
        if (forceRefresh) {
            showStatusMessage('Patterns list refreshed successfully', 'success');
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
        showStatusMessage('Failed to load patterns', 'error');
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
    previewContainer.className = 'w-32 h-32 rounded-full shadow-md relative pattern-preview group';
    previewContainer.dataset.pattern = pattern;
    
    // Add loading indicator
    previewContainer.innerHTML = '<div class="absolute inset-0 flex items-center justify-center"><div class="bg-slate-200 rounded-full h-8 w-8 flex items-center justify-center"><div class="bg-slate-500 rounded-full h-4 w-4"></div></div></div>';
    
    // Add play button overlay (hidden by default, shown on hover)
    const playOverlay = document.createElement('div');
    playOverlay.className = 'absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 cursor-pointer';
    playOverlay.innerHTML = '<div class="bg-white rounded-full p-2 shadow-lg flex items-center justify-center w-10 h-10"><span class="material-icons text-lg text-gray-800">play_arrow</span></div>';
    
    // Add click handler for play button (separate from card click)
    playOverlay.addEventListener('click', (e) => {
        e.stopPropagation(); // Prevent card selection
        openAnimatedPreview(pattern);
    });
    
    previewContainer.appendChild(playOverlay);
    
    // Create pattern name
    const patternName = document.createElement('p');
    patternName.className = 'text-gray-700 text-sm font-medium text-center truncate w-full';
    patternName.textContent = pattern.replace('.thr', '').split('/').pop();

    // Add click handler
    card.onclick = () => selectPattern(pattern, card);

    // Check if preview is already in cache
    const previewData = previewCache.get(pattern);
    if (previewData && !previewData.error && previewData.image_data) {
        updatePreviewElement(previewContainer, previewData.image_data);
    } else {
        // Start observing the preview container for lazy loading
        previewObserver.observe(previewContainer);
    }

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
    const previewPlayOverlay = document.getElementById('previewPlayOverlay');

    // Close panel when clicking the close button
    closeButton.onclick = () => {
        hidePatternPreview();
        // Remove selected state from all cards when closing
        document.querySelectorAll('.pattern-card').forEach(c => {
            c.classList.remove('selected');
        });
    };

    // Handle play button overlay click in preview panel
    if (previewPlayOverlay) {
        previewPlayOverlay.onclick = () => {
            openAnimatedPreview(pattern);
        };
    }

    // Handle play button click
    playButton.onclick = async () => {
        if (!pattern) {
            showStatusMessage('No pattern selected', 'error');
            return;
        }

        try {
            // Show the preview modal
            if (window.openPlayerPreviewModal) {
                window.openPlayerPreviewModal();
            }

            // Get the selected pre-execution action
            const preExecutionInput = document.querySelector('input[name="preExecutionAction"]:checked');
            const preExecution = preExecutionInput ? preExecutionInput.value : 'none';

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
                let errorMsg = data.detail || 'Failed to run pattern';
                let errorType = 'error';
                
                // Handle specific error cases with appropriate messaging
                if (data.detail === 'Connection not established') {
                    errorMsg = 'Please connect to the device before running a pattern';
                    errorType = 'warning';
                } else if (response.status === 409) {
                    errorMsg = 'Another pattern is already running. Please stop the current pattern first.';
                    errorType = 'warning';
                } else if (response.status === 404) {
                    errorMsg = 'Pattern file not found. Please refresh the page and try again.';
                    errorType = 'error';
                } else if (response.status === 400) {
                    errorMsg = 'Invalid request. Please check your settings and try again.';
                    errorType = 'error';
                } else if (response.status === 500) {
                    errorMsg = 'Server error. Please try again later.';
                    errorType = 'error';
                }
                
                showStatusMessage(errorMsg, errorType);
                return;
            }
        } catch (error) {
            console.error('Error running pattern:', error);
            
            // Handle network errors specifically
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                showStatusMessage('Network error. Please check your connection and try again.', 'error');
            } else if (error.message && error.message.includes('409')) {
                showStatusMessage('Another pattern is already running', 'warning');
            } else if (error.message) {
                showStatusMessage(error.message, 'error');
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

    // Give the browser a chance to render the cards
    requestAnimationFrame(() => {
        // Trigger preview loading for the search results
        triggerPreviewLoadingForVisible();
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
        
        // Initialize IndexedDB preview cache (shared with playlists page)
        await initPreviewCacheDB();
        
        // Setup upload event handlers
        setupUploadEventHandlers();
        
        // Initialize intersection observer for lazy loading
        initPreviewObserver();

        // Setup search functionality
        const searchInput = document.getElementById('patternSearch');
        const searchButton = document.getElementById('searchButton');
        const cacheAllButton = document.getElementById('cacheAllButton');
        
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

        // Setup cache all button
        if (cacheAllButton) {
            cacheAllButton.addEventListener('click', () => cacheAllPreviews());
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
                
                // Clear any existing cache for this pattern to ensure fresh loading
                const newPatternPath = `custom_patterns/${file.name}`;
                previewCache.delete(newPatternPath);
                
                // Add a small delay to allow backend preview generation to complete
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                // Refresh the pattern list (force refresh since new pattern was uploaded)
                await loadPatterns(true);
                
                // Clear the file input
                e.target.value = '';
                
                // Trigger preview loading for newly uploaded patterns with extended retry
                setTimeout(() => {
                    const newPatternCard = document.querySelector(`[data-pattern="${newPatternPath}"]`);
                    if (newPatternCard) {
                        const previewContainer = newPatternCard.querySelector('.pattern-preview');
                        if (previewContainer) {
                            // Clear any existing retry count and force reload
                            previewContainer.dataset.retryCount = '0';
                            previewContainer.dataset.hasTriedIndividual = 'false';
                            previewContainer.dataset.isNewUpload = 'true';
                            addPatternToBatch(newPatternPath, previewContainer);
                        }
                    }
                }, 500);
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

// Cache all pattern previews
async function cacheAllPreviews() {
    const cacheAllButton = document.getElementById('cacheAllButton');
    if (!cacheAllButton) return;

    try {
        // Disable button and show loading state
        cacheAllButton.disabled = true;

        // Get current cache size
        const currentSize = await getPreviewCacheSize();
        const maxSize = MAX_CACHE_SIZE_BYTES || (200 * 1024 * 1024); // 200MB default

        if (currentSize > maxSize) {
            // Clear cache if it's too large
            await clearPreviewCache();
            // Also clear progress since we're starting fresh
            localStorage.removeItem(CACHE_PROGRESS_KEY);
            localStorage.removeItem(CACHE_TIMESTAMP_KEY);
        }

        // Get all patterns that aren't cached yet
        const uncachedPatterns = allPatterns.filter(pattern => !previewCache.has(pattern));
        
        if (uncachedPatterns.length === 0) {
            showStatusMessage('All patterns are already cached!', 'info');
            return;
        }

        // Check for existing progress
        let startIndex = 0;
        const savedProgress = localStorage.getItem(CACHE_PROGRESS_KEY);
        const savedTimestamp = localStorage.getItem(CACHE_TIMESTAMP_KEY);
        
        if (savedProgress && savedTimestamp) {
            const progressAge = Date.now() - parseInt(savedTimestamp);
            if (progressAge < CACHE_PROGRESS_EXPIRY) {
                const lastCachedPattern = savedProgress;
                const lastIndex = uncachedPatterns.findIndex(p => p === lastCachedPattern);
                if (lastIndex !== -1) {
                    startIndex = lastIndex + 1;
                    showStatusMessage('Resuming from previous progress...', 'info');
                }
            } else {
                // Clear expired progress
                localStorage.removeItem(CACHE_PROGRESS_KEY);
                localStorage.removeItem(CACHE_TIMESTAMP_KEY);
            }
        }

        // Process patterns in smaller batches to avoid overwhelming the server
        const BATCH_SIZE = 10;
        const remainingPatterns = uncachedPatterns.slice(startIndex);
        const totalBatches = Math.ceil(remainingPatterns.length / BATCH_SIZE);
        
        for (let i = 0; i < totalBatches; i++) {
            const batchStart = i * BATCH_SIZE;
            const batchEnd = Math.min(batchStart + BATCH_SIZE, remainingPatterns.length);
            const batchPatterns = remainingPatterns.slice(batchStart, batchEnd);
            
            // Update button text with progress
            const overallProgress = Math.round(((startIndex + batchStart + BATCH_SIZE) / uncachedPatterns.length) * 100);
            cacheAllButton.innerHTML = `
                <div class="bg-white bg-opacity-30 rounded-full h-4 w-4 flex items-center justify-center">
                    <div class="bg-white rounded-full h-2 w-2"></div>
                </div>
                <span>Caching ${overallProgress}%</span>
            `;

            try {
                const response = await fetch('/preview_thr_batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_names: batchPatterns })
                });

                if (response.ok) {
                    const results = await response.json();
                    
                    // Cache each preview
                    for (const [pattern, data] of Object.entries(results)) {
                        if (data && !data.error && data.image_data) {
                            previewCache.set(pattern, data);
                            await savePreviewToCache(pattern, data);
                            
                            // Save progress after each successful pattern
                            localStorage.setItem(CACHE_PROGRESS_KEY, pattern);
                            localStorage.setItem(CACHE_TIMESTAMP_KEY, Date.now().toString());
                        }
                    }
                }
            } catch (error) {
                logMessage(`Error caching batch ${i + 1}: ${error.message}`, LOG_TYPE.ERROR);
                // Don't clear progress on error - allows resuming from last successful pattern
            }

            // Small delay between batches to prevent overwhelming the server
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        // Clear progress after successful completion
        localStorage.removeItem(CACHE_PROGRESS_KEY);
        localStorage.removeItem(CACHE_TIMESTAMP_KEY);

        // Show success message
        showStatusMessage('All pattern previews have been cached!', 'success');
    } catch (error) {
        logMessage(`Error caching previews: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to cache all previews. Click again to resume.', 'error');
    } finally {
        // Reset button state
        if (cacheAllButton) {
            cacheAllButton.disabled = false;
            cacheAllButton.innerHTML = `
                <span class="material-icons text-sm">cached</span>
                Cache All Previews
            `;
        }
    }
}

// Open animated preview modal
async function openAnimatedPreview(pattern) {
    try {
        const modal = document.getElementById('animatedPreviewModal');
        const title = document.getElementById('animatedPreviewTitle');
        const canvas = document.getElementById('animatedPreviewCanvas');
        const ctx = canvas.getContext('2d');
        
        // Set title
        title.textContent = pattern.replace('.thr', '').split('/').pop();
        
        // Show modal
        modal.classList.remove('hidden');
        
        // Load pattern coordinates
        const response = await fetch('/get_theta_rho_coordinates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_name: pattern })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        if (data.error) {
            throw new Error(data.error);
        }
        
        animatedPreviewData = data.coordinates;
        
        // Setup canvas
        setupAnimatedPreviewCanvas(ctx);
        
        // Setup controls
        setupAnimatedPreviewControls();
        
        // Draw initial state
        drawAnimatedPreview(ctx, 0);
        
        // Auto-play the animation
        setTimeout(() => {
            playAnimation();
        }, 100); // Small delay to ensure everything is set up
        
    } catch (error) {
        logMessage(`Error opening animated preview: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to load pattern for animation', 'error');
    }
}

// Setup animated preview canvas
function setupAnimatedPreviewCanvas(ctx) {
    const canvas = ctx.canvas;
    const size = canvas.width;
    const center = size / 2;
    const scale = (size / 2) - 30; // Slightly smaller to account for border
    
    // Clear canvas with white background
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, size, size);
    
    // Set drawing style for ultra-high quality lines
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 1; // Thinner line for higher resolution
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    // Enable high quality rendering
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
}

// Setup animated preview controls
function setupAnimatedPreviewControls() {
    const modal = document.getElementById('animatedPreviewModal');
    const closeBtn = document.getElementById('closeAnimatedPreview');
    const playPauseBtn = document.getElementById('playPauseBtn');
    const resetBtn = document.getElementById('resetBtn');
    const speedSlider = document.getElementById('speedSlider');
    const speedValue = document.getElementById('speedValue');
    const progressSlider = document.getElementById('progressSlider');
    const progressValue = document.getElementById('progressValue');
    const canvas = document.getElementById('animatedPreviewCanvas');
    const playPauseOverlay = document.getElementById('playPauseOverlay');
    
    // Set responsive canvas size with ultra-high-DPI support
    const setCanvasSize = () => {
        const isMobile = window.innerWidth < 768;
        const displaySize = isMobile ? Math.min(window.innerWidth - 80, 400) : 800;
        
        // Get device pixel ratio and multiply by 2 for higher resolution
        const pixelRatio = (window.devicePixelRatio || 1) * 2;
        
        // Set the display size (CSS pixels)
        canvas.style.width = displaySize + '%';
        canvas.style.height = displaySize + '%';
        
        // Set the actual canvas size (device pixels) - increased resolution
        canvas.width = displaySize * pixelRatio;
        canvas.height = displaySize * pixelRatio;
        
        // Scale the context to match the increased pixel ratio
        const ctx = canvas.getContext('2d', { alpha: false }); // Disable alpha for better performance
        ctx.scale(pixelRatio, pixelRatio);
        
        // Enable high quality rendering
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        
        // Redraw with new size
        if (animatedPreviewData) {
            setupAnimatedPreviewCanvas(ctx);
            drawAnimatedPreview(ctx, currentProgress / 100);
        }
    };
    
    // Set initial size
    setCanvasSize();
    
    // Handle window resize
    window.addEventListener('resize', setCanvasSize);
    
    // Close modal
    closeBtn.onclick = closeAnimatedPreview;
    modal.onclick = (e) => {
        if (e.target === modal) closeAnimatedPreview();
    };
    
    // Play/Pause button
    playPauseBtn.onclick = toggleAnimation;
    
    // Reset button
    resetBtn.onclick = resetAnimation;
    
    // Speed slider
    speedSlider.oninput = (e) => {
        animationSpeed = parseFloat(e.target.value);
        speedValue.textContent = `${animationSpeed}x`;
    };
    
    // Progress slider
    progressSlider.oninput = (e) => {
        currentProgress = parseFloat(e.target.value);
        progressValue.textContent = `${currentProgress.toFixed(1)}%`;
        drawAnimatedPreview(canvas.getContext('2d'), currentProgress / 100);
        if (isPlaying) {
            // Pause animation when manually adjusting progress
            toggleAnimation();
        }
    };
    
    // Canvas click to play/pause
    canvas.onclick = () => {
        playPauseOverlay.style.opacity = '1';
        setTimeout(() => {
            playPauseOverlay.style.opacity = '0';
        }, 200);
        toggleAnimation();
    };
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (modal.classList.contains('hidden')) return;
        
        switch(e.code) {
            case 'Space':
                e.preventDefault();
                toggleAnimation();
                break;
            case 'Escape':
                closeAnimatedPreview();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                currentProgress = Math.max(0, currentProgress - 5);
                updateProgressUI();
                drawAnimatedPreview(canvas.getContext('2d'), currentProgress / 100);
                break;
            case 'ArrowRight':
                e.preventDefault();
                currentProgress = Math.min(100, currentProgress + 5);
                updateProgressUI();
                drawAnimatedPreview(canvas.getContext('2d'), currentProgress / 100);
                break;
        }
    });
}

// Draw animated preview
function drawAnimatedPreview(ctx, progress) {
    if (!animatedPreviewData || animatedPreviewData.length === 0) return;
    
    const canvas = ctx.canvas;
    const pixelRatio = (window.devicePixelRatio || 1) * 2; // Match the increased ratio
    const displayWidth = parseInt(canvas.style.width);
    const displayHeight = parseInt(canvas.style.height);
    const center = (canvas.width / pixelRatio) / 2;
    const scale = ((canvas.width / pixelRatio) / 2) - 30;
    
    // Clear canvas with white background
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Calculate how many points to draw
    const totalPoints = animatedPreviewData.length;
    const pointsToDraw = Math.floor(totalPoints * progress);
    
    if (pointsToDraw < 2) return;
    
    // Draw the path with ultra-high quality settings
    ctx.beginPath();
    ctx.strokeStyle = '#000000';
    ctx.lineWidth = 1; // Thinner line for higher resolution
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    // Ensure sub-pixel alignment for ultra-high resolution
    for (let i = 0; i < pointsToDraw; i++) {
        const [theta, rho] = animatedPreviewData[i];
        // Round to nearest 0.25 for even more precise lines
        // Mirror both X and Y coordinates
        const x = Math.round((center + rho * scale * Math.cos(theta)) * 4) / 4; // Changed minus to plus
        const y = Math.round((center + rho * scale * Math.sin(theta)) * 4) / 4;
        
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }
    ctx.stroke();
    
    // Draw current position dot
    if (pointsToDraw > 0) {
        const [currentTheta, currentRho] = animatedPreviewData[pointsToDraw - 1];
        const currentX = Math.round((center + currentRho * scale * Math.cos(currentTheta)) * 4) / 4; // Changed minus to plus
        const currentY = Math.round((center + currentRho * scale * Math.sin(currentTheta)) * 4) / 4;
        
        // Draw a filled circle at current position with anti-aliasing
        ctx.fillStyle = '#ff4444'; // Red dot
        ctx.beginPath();
        ctx.arc(currentX, currentY, 6, 0, 2 * Math.PI); // Increased dot size
        ctx.fill();
        
        // Add a subtle white border
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
    }
}

// Toggle animation play/pause
function toggleAnimation() {
    if (isPlaying) {
        pauseAnimation();
    } else {
        playAnimation();
    }
}

// Play animation
function playAnimation() {
    if (!animatedPreviewData) return;
    
    isPlaying = true;
    lastTimestamp = performance.now();
    
    // Update UI
    const playPauseBtn = document.getElementById('playPauseBtn');
    const playPauseBtnIcon = document.getElementById('playPauseBtnIcon');
    const playPauseBtnText = document.getElementById('playPauseBtnText');
    
    if (playPauseBtnIcon) playPauseBtnIcon.textContent = 'pause';
    if (playPauseBtnText) playPauseBtnText.textContent = 'Pause';
    
    // Start animation loop
    animationFrameId = requestAnimationFrame(animate);
}

// Pause animation
function pauseAnimation() {
    isPlaying = false;
    
    // Update UI
    const playPauseBtn = document.getElementById('playPauseBtn');
    const playPauseBtnIcon = document.getElementById('playPauseBtnIcon');
    const playPauseBtnText = document.getElementById('playPauseBtnText');
    
    if (playPauseBtnIcon) playPauseBtnIcon.textContent = 'play_arrow';
    if (playPauseBtnText) playPauseBtnText.textContent = 'Play';
    
    // Cancel animation frame
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
}

// Animation loop
function animate(timestamp) {
    if (!isPlaying) return;
    
    const deltaTime = timestamp - lastTimestamp;
    const progressIncrement = (deltaTime / 1000) * animationSpeed * 2.0; // Much faster base speed
    
    currentProgress = Math.min(100, currentProgress + progressIncrement);
    
    // Update UI
    updateProgressUI();
    
    // Draw frame
    const canvas = document.getElementById('animatedPreviewCanvas');
    if (canvas) {
        drawAnimatedPreview(canvas.getContext('2d'), currentProgress / 100);
    }
    
    // Continue animation
    if (currentProgress < 100) {
        lastTimestamp = timestamp;
        animationFrameId = requestAnimationFrame(animate);
    } else {
        // Animation complete
        pauseAnimation();
    }
}

// Reset animation
function resetAnimation() {
    pauseAnimation();
    currentProgress = 0;
    updateProgressUI();
    
    const canvas = document.getElementById('animatedPreviewCanvas');
    drawAnimatedPreview(canvas.getContext('2d'), 0);
}

// Update progress UI
function updateProgressUI() {
    const progressSlider = document.getElementById('progressSlider');
    const progressValue = document.getElementById('progressValue');
    
    progressSlider.value = currentProgress;
    progressValue.textContent = `${currentProgress.toFixed(1)}%`;
}

// Close animated preview
function closeAnimatedPreview() {
    pauseAnimation();
    
    const modal = document.getElementById('animatedPreviewModal');
    modal.classList.add('hidden');
    
    // Clear data
    animatedPreviewData = null;
    currentProgress = 0;
    animationSpeed = 1;
    
    // Reset UI
    const speedSlider = document.getElementById('speedSlider');
    const speedValue = document.getElementById('speedValue');
    const progressSlider = document.getElementById('progressSlider');
    const progressValue = document.getElementById('progressValue');
    
    speedSlider.value = 1;
    speedValue.textContent = '1x';
    progressSlider.value = 0;
    progressValue.textContent = '0%';
} 