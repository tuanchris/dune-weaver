// Constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Global variables
let allPlaylists = [];
let currentPlaylist = null;
let availablePatterns = [];
let filteredPatterns = [];
let selectedPatterns = new Set();
let previewCache = new Map();
let intersectionObserver = null;
let searchTimeout = null;

// Mobile navigation state
let isMobileView = false;

// Global variables for batching lazy loading
let pendingPatterns = new Map(); // pattern -> element mapping
let batchTimeout = null;
const BATCH_SIZE = 40; // Increased batch size for better performance
const BATCH_DELAY = 150; // Wait 150ms to collect more patterns before batching

// Shared caching for patterns list (persistent across sessions)
const PATTERNS_CACHE_KEY = 'dune_weaver_patterns_cache';

// IndexedDB cache for preview images with size management
const PREVIEW_CACHE_DB_NAME = 'dune_weaver_previews';
const PREVIEW_CACHE_DB_VERSION = 1;
const PREVIEW_CACHE_STORE_NAME = 'previews';
const MAX_CACHE_SIZE_MB = 200;
const MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024;

let previewCacheDB = null;

// --- Playback Settings Persistence ---
const PLAYBACK_SETTINGS_KEY = 'dune_weaver_playback_settings';

function savePlaybackSettings() {
    const runMode = document.querySelector('input[name="run_playlist"]:checked')?.value || 'single';
    const shuffle = document.getElementById('shuffleCheckbox')?.checked || false;
    const pauseTime = document.getElementById('pauseTimeInput')?.value || '5';
    const clearPattern = document.getElementById('clearPatternSelect')?.value || 'none';
    const settings = { runMode, shuffle, pauseTime, clearPattern };
    try {
        localStorage.setItem(PLAYBACK_SETTINGS_KEY, JSON.stringify(settings));
    } catch (e) {}
}

function restorePlaybackSettings() {
    try {
        const settings = JSON.parse(localStorage.getItem(PLAYBACK_SETTINGS_KEY));
        if (!settings) return;
        // Run mode
        if (settings.runMode) {
            const radio = document.querySelector(`input[name="run_playlist"][value="${settings.runMode}"]`);
            if (radio) radio.checked = true;
        }
        // Shuffle
        if (typeof settings.shuffle === 'boolean') {
            const shuffleBox = document.getElementById('shuffleCheckbox');
            if (shuffleBox) shuffleBox.checked = settings.shuffle;
        }
        // Pause time
        if (settings.pauseTime) {
            const pauseInput = document.getElementById('pauseTimeInput');
            if (pauseInput) pauseInput.value = settings.pauseTime;
        }
        // Clear pattern
        if (settings.clearPattern) {
            const clearSel = document.getElementById('clearPatternSelect');
            if (clearSel) clearSel.value = settings.clearPattern;
        }
    } catch (e) {}
}

// Attach listeners to save settings on change
function setupPlaybackSettingsPersistence() {
    document.querySelectorAll('input[name="run_playlist"]').forEach(radio => {
        radio.addEventListener('change', savePlaybackSettings);
    });
    const shuffleBox = document.getElementById('shuffleCheckbox');
    if (shuffleBox) shuffleBox.addEventListener('change', savePlaybackSettings);
    const pauseInput = document.getElementById('pauseTimeInput');
    if (pauseInput) pauseInput.addEventListener('input', savePlaybackSettings);
    const clearSel = document.getElementById('clearPatternSelect');
    if (clearSel) clearSel.addEventListener('change', savePlaybackSettings);
}

// --- End Playback Settings Persistence ---

// --- Playlist Selection Persistence ---
const LAST_PLAYLIST_KEY = 'dune_weaver_last_playlist';

function saveLastSelectedPlaylist(playlistName) {
    try {
        localStorage.setItem(LAST_PLAYLIST_KEY, playlistName);
    } catch (e) {}
}

function getLastSelectedPlaylist() {
    try {
        return localStorage.getItem(LAST_PLAYLIST_KEY);
    } catch (e) { return null; }
}
// --- End Playlist Selection Persistence ---

// Initialize IndexedDB for preview caching
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
// Clear a specific pattern from IndexedDB cache
async function clearPatternFromIndexedDB(pattern) {
    try {
        if (!previewCacheDB) await initPreviewCacheDB();
        
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        
        await new Promise((resolve, reject) => {
            const deleteRequest = store.delete(pattern);
            deleteRequest.onsuccess = () => {
                logMessage(`Cleared ${pattern} from IndexedDB cache`, LOG_TYPE.DEBUG);
                resolve();
            };
            deleteRequest.onerror = () => {
                logMessage(`Failed to clear ${pattern} from IndexedDB: ${deleteRequest.error}`, LOG_TYPE.WARNING);
                reject(deleteRequest.error);
            };
        });
    } catch (error) {
        logMessage(`Error clearing pattern from IndexedDB: ${error.message}`, LOG_TYPE.WARNING);
    }
}

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

// Clear preview cache
async function clearPreviewCache() {
    try {
        if (!previewCacheDB) return;
        
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readwrite');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        
        return new Promise((resolve, reject) => {
            const request = store.clear();
            
            request.onsuccess = () => {
                logMessage('Preview cache cleared', LOG_TYPE.DEBUG);
                resolve();
            };
            
            request.onerror = () => reject(request.error);
        });
        
    } catch (error) {
        logMessage(`Error clearing preview cache: ${error.message}`, LOG_TYPE.WARNING);
    }
}

// Get cache statistics
async function getPreviewCacheStats() {
    try {
        const size = await getPreviewCacheSize();
        const transaction = previewCacheDB.transaction([PREVIEW_CACHE_STORE_NAME], 'readonly');
        const store = transaction.objectStore(PREVIEW_CACHE_STORE_NAME);
        
        const count = await new Promise((resolve, reject) => {
            const request = store.count();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
        
        return {
            count,
            size,
            sizeMB: size / 1024 / 1024,
            maxSizeMB: MAX_CACHE_SIZE_MB,
            utilizationPercent: (size / MAX_CACHE_SIZE_BYTES) * 100
        };
        
    } catch (error) {
        logMessage(`Error getting cache stats: ${error.message}`, LOG_TYPE.WARNING);
        return { count: 0, size: 0, sizeMB: 0, maxSizeMB: MAX_CACHE_SIZE_MB, utilizationPercent: 0 };
    }
}

// Initialize Intersection Observer for lazy loading
function initializeIntersectionObserver() {
    intersectionObserver = new IntersectionObserver((entries) => {
        // Get all visible elements
        const visibleElements = entries.filter(entry => entry.isIntersecting);
        if (visibleElements.length === 0) return;

        // Collect all visible patterns
        const visiblePatterns = new Map();
        visibleElements.forEach(entry => {
            const patternElement = entry.target;
            const pattern = patternElement.dataset.pattern;
            if (pattern && !previewCache.has(pattern)) {
                visiblePatterns.set(pattern, patternElement);
                intersectionObserver.unobserve(patternElement);
            }
        });

        // If we have visible patterns that need loading, add them to the batch
        if (visiblePatterns.size > 0) {
            // Add to pending batch
            for (const [pattern, element] of visiblePatterns) {
                pendingPatterns.set(pattern, element);
            }

            // Clear existing timeout and set new one
            if (batchTimeout) {
                clearTimeout(batchTimeout);
            }

            batchTimeout = setTimeout(() => {
                processPendingBatch();
            }, BATCH_DELAY);
        }
    }, {
        rootMargin: '0px 0px 600px 0px', // Large bottom margin to trigger early as element approaches from bottom
        threshold: 0.1
    });
}

// Function to get visible patterns that are still loading
function getVisibleLoadingPatterns() {
    const visibleLoadingPatterns = new Map();
    
    // Get all pattern elements that are currently visible
    const patternElements = document.querySelectorAll('[data-pattern]');
    
    patternElements.forEach(element => {
        const pattern = element.dataset.pattern;
        if (pattern && !previewCache.has(pattern)) {
            // Check if element is visible (intersecting with viewport)
            const rect = element.getBoundingClientRect();
            const isVisible = rect.top < window.innerHeight && rect.bottom > 0;
            
            if (isVisible) {
                visibleLoadingPatterns.set(pattern, element);
            }
        }
    });
    
    return visibleLoadingPatterns;
}

// Modified processPendingBatch to keep polling for loading previews
async function processPendingBatch() {
    if (pendingPatterns.size === 0) return;
    
    // Create a copy of current pending patterns and clear the original
    const currentBatch = new Map(pendingPatterns);
    pendingPatterns.clear();
    batchTimeout = null;
    
    const patternsToLoad = Array.from(currentBatch.keys());
    
    try {
        logMessage(`Loading ${patternsToLoad.length} pattern previews`, LOG_TYPE.DEBUG);
        
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
                const previewContainer = element?.querySelector('.pattern-preview');
                
                if (data && !data.error && data.image_data) {
                    // Cache both in memory and IndexedDB
                    previewCache.set(pattern, data);
                    await savePreviewToCache(pattern, data);
                    
                    if (previewContainer) {
                        previewContainer.innerHTML = ''; // Remove loading indicator
                        previewContainer.innerHTML = `<img src="${data.image_data}" alt="Pattern Preview" class="w-full h-full object-cover rounded-full" />`;
                    }
                } else {
                    previewCache.set(pattern, { error: true });
                }
            }
        } else {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
    } catch (error) {
        logMessage(`Error loading pattern preview batch: ${error.message}`, LOG_TYPE.ERROR);
        // Mark as error in cache
        for (const pattern of patternsToLoad) {
            previewCache.set(pattern, { error: true });
        }
    }

    // After processing, check for any visible loading previews and request them
    const stillLoading = getVisibleLoadingPatterns();
    if (stillLoading.size > 0) {
        // Add to pendingPatterns and immediately process
        for (const [pattern, element] of stillLoading) {
            pendingPatterns.set(pattern, element);
        }
        await processPendingBatch();
    }
}

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

// Load all playlists
async function loadPlaylists() {
    try {
        const response = await fetch('/list_all_playlists');
        if (response.ok) {
            allPlaylists = await response.json();
            displayPlaylists();
            // Auto-select last selected
            const last = getLastSelectedPlaylist();
            if (last && allPlaylists.includes(last)) {
                setTimeout(() => {
                    const nav = document.getElementById('playlistsNav');
                    const el = Array.from(nav.querySelectorAll('a')).find(a => a.textContent.trim() === last);
                    if (el) el.click();
                }, 0);
            }
        } else {
            throw new Error('Failed to load playlists');
        }
    } catch (error) {
        logMessage(`Error loading playlists: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to load playlists', 'error');
    }
}

// Display playlists in sidebar
function displayPlaylists() {
    const playlistsNav = document.getElementById('playlistsNav');
    playlistsNav.innerHTML = '';

    if (allPlaylists.length === 0) {
        playlistsNav.innerHTML = `
            <div class="flex items-center justify-center py-8 text-gray-500 dark:text-gray-400">
                <span class="text-sm">No playlists found</span>
            </div>
        `;
        return;
    }

    allPlaylists.forEach(playlist => {
        const playlistItem = document.createElement('a');
        playlistItem.className = 'flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-gray-100 transition-colors duration-150 cursor-pointer';
        playlistItem.innerHTML = `
            <span class="material-icons text-lg text-gray-500 dark:text-gray-400">queue_music</span>
            <span class="text-sm font-medium flex-1 truncate">${playlist}</span>
            <span class="material-icons text-lg text-gray-400 dark:text-gray-500">chevron_right</span>
        `;
        
        playlistItem.addEventListener('click', () => selectPlaylist(playlist, playlistItem));
        playlistsNav.appendChild(playlistItem);
    });
}

// Select a playlist
async function selectPlaylist(playlistName, element) {
    // Remove active state from all playlist items
    document.querySelectorAll('#playlistsNav a').forEach(item => {
        item.classList.remove('text-gray-900', 'dark:text-gray-100', 'bg-gray-100', 'dark:bg-gray-700', 'font-semibold');
        item.classList.add('text-gray-700', 'dark:text-gray-300', 'font-medium');
    });

    // Add active state to selected item
    element.classList.remove('text-gray-700', 'dark:text-gray-300', 'font-medium');
    element.classList.add('text-gray-900', 'dark:text-gray-100', 'bg-gray-100', 'dark:bg-gray-700', 'font-semibold');

    // Update current playlist
    currentPlaylist = playlistName;
    
    // Update header with playlist name and delete button
    const header = document.getElementById('currentPlaylistTitle');
    header.innerHTML = `
        <h1 class="text-gray-900 dark:text-gray-100 text-2xl font-semibold leading-tight truncate">${playlistName}</h1>
        <button id="deletePlaylistBtn" class="p-1 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/20 text-gray-500 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 transition-all duration-150 flex-shrink-0" title="Delete playlist">
            <span class="material-icons text-lg">delete</span>
        </button>
    `;
    
    // Add delete button event listener
    document.getElementById('deletePlaylistBtn').addEventListener('click', () => deletePlaylist(playlistName));

    // Enable buttons
    document.getElementById('addPatternsBtn').disabled = false;
    document.getElementById('runPlaylistBtn').disabled = false;

    // Save last selected
    saveLastSelectedPlaylist(playlistName);

    // Show playlist details on mobile
    showPlaylistDetails();

    // Load playlist patterns
    await loadPlaylistPatterns(playlistName);
}

// Load patterns for selected playlist
async function loadPlaylistPatterns(playlistName) {
    try {
        const response = await fetch(`/get_playlist?name=${encodeURIComponent(playlistName)}`);
        if (response.ok) {
            const playlistData = await response.json();
            displayPlaylistPatterns(playlistData.files || []);
            
            // Show playback settings
            document.getElementById('playbackSettings').classList.remove('hidden');
        } else {
            throw new Error('Failed to load playlist patterns');
        }
    } catch (error) {
        logMessage(`Error loading playlist patterns: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to load playlist patterns', 'error');
    }
}

// Display patterns in the current playlist
async function displayPlaylistPatterns(patterns) {
    const patternsGrid = document.getElementById('patternsGrid');
    
    if (patterns.length === 0) {
        patternsGrid.innerHTML = `
            <div class="flex items-center justify-center col-span-full py-12 text-gray-500 dark:text-gray-400">
                <span class="text-sm">No patterns in this playlist</span>
            </div>
        `;
        return;
    }

    // No more pre-loading - all patterns will use lazy loading
    patternsGrid.innerHTML = '';
    patterns.forEach(pattern => {
        const patternCard = createPatternCard(pattern, true);
        patternsGrid.appendChild(patternCard);
        
        // Set up lazy loading for ALL patterns
        patternCard.dataset.pattern = pattern;
        intersectionObserver.observe(patternCard);
    });
}

// Create a pattern card
function createPatternCard(pattern, showRemove = false) {
    const card = document.createElement('div');
    card.className = 'flex flex-col gap-3 group cursor-pointer relative';
    
    const previewContainer = document.createElement('div');
    previewContainer.className = 'w-full aspect-square bg-cover rounded-full shadow-sm group-hover:shadow-md transition-shadow duration-150 border border-gray-200 dark:border-gray-700 pattern-preview relative';
    
    // Only set preview image if already available in memory cache
    const previewData = previewCache.get(pattern);
    if (previewData && !previewData.error && previewData.image_data) {
        previewContainer.innerHTML = `<img src="${previewData.image_data}" alt="Pattern Preview" class="w-full h-full object-cover rounded-full" />`;
    }

    const patternName = document.createElement('p');
    patternName.className = 'text-sm text-gray-800 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100 font-medium truncate text-center';
    patternName.textContent = pattern.replace('.thr', '').split('/').pop();

    card.appendChild(previewContainer);
    card.appendChild(patternName);

    if (showRemove) {
        const removeBtn = document.createElement('button');
        removeBtn.className = 'absolute top-2 right-2 size-6 rounded-full bg-red-500 hover:bg-red-600 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-150 flex items-center justify-center text-xs';
        removeBtn.innerHTML = '<span class="material-icons text-sm">close</span>';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            removePatternFromPlaylist(pattern);
        });
        card.appendChild(removeBtn);
    }

    return card;
}

// Search and filter patterns
function searchPatterns(query) {
    const normalizedQuery = query.toLowerCase().trim();
    
    if (!normalizedQuery) {
        filteredPatterns = [...availablePatterns];
    } else {
        filteredPatterns = availablePatterns.filter(pattern => {
            const patternName = pattern.replace('.thr', '').split('/').pop().toLowerCase();
            return patternName.includes(normalizedQuery);
        });
    }
    
    displayAvailablePatterns();
}

// Handle search input
function handleSearchInput() {
    const searchInput = document.getElementById('patternSearchInput');
    const clearBtn = document.getElementById('clearSearchBtn');
    const query = searchInput.value;
    
    // Show/hide clear button
    if (query) {
        clearBtn.classList.remove('hidden');
    } else {
        clearBtn.classList.add('hidden');
    }
    
    // Debounce search
    if (searchTimeout) {
        clearTimeout(searchTimeout);
    }
    
    searchTimeout = setTimeout(() => {
        searchPatterns(query);
    }, 300);
}

// Clear search
function clearSearch() {
    const searchInput = document.getElementById('patternSearchInput');
    const clearBtn = document.getElementById('clearSearchBtn');
    
    searchInput.value = '';
    clearBtn.classList.add('hidden');
    searchPatterns('');
}

// Remove pattern from playlist
async function removePatternFromPlaylist(pattern) {
    if (!currentPlaylist) return;

    if (confirm(`Remove "${pattern.split('/').pop()}" from playlist?`)) {
        try {
            // Get current playlist data
            const response = await fetch(`/get_playlist?name=${encodeURIComponent(currentPlaylist)}`);
            if (response.ok) {
                const playlistData = await response.json();
                const updatedFiles = playlistData.files.filter(file => file !== pattern);
                
                // Update playlist
                const updateResponse = await fetch('/modify_playlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        playlist_name: currentPlaylist,
                        files: updatedFiles
                    })
                });

                if (updateResponse.ok) {
                    showStatusMessage('Pattern removed from playlist', 'success');
                    await loadPlaylistPatterns(currentPlaylist);
                } else {
                    throw new Error('Failed to update playlist');
                }
            }
        } catch (error) {
            logMessage(`Error removing pattern: ${error.message}`, LOG_TYPE.ERROR);
            showStatusMessage('Failed to remove pattern', 'error');
        }
    }
}

// Load available patterns for adding (no caching)
async function loadAvailablePatterns(forceRefresh = false) {
    const loadingIndicator = document.getElementById('patternsLoadingIndicator');
    const grid = document.getElementById('availablePatternsGrid');
    const noResultsMessage = document.getElementById('noResultsMessage');
    
    // Always fetch from backend
    loadingIndicator.classList.remove('hidden');
    grid.classList.add('hidden');
    noResultsMessage.classList.add('hidden');
    
    try {
        logMessage('Fetching fresh patterns list from server', LOG_TYPE.DEBUG);
        const response = await fetch('/list_theta_rho_files');
        if (response.ok) {
            const patterns = await response.json();
            const thrPatterns = patterns.filter(file => file.endsWith('.thr'));
            availablePatterns = [...thrPatterns];
            filteredPatterns = [...availablePatterns];
            // Show patterns immediately - all lazy loading now
            displayAvailablePatterns();
            if (forceRefresh) {
                showStatusMessage('Patterns list refreshed successfully', 'success');
            }
        } else {
            throw new Error('Failed to load available patterns');
        }
    } catch (error) {
        logMessage(`Error loading available patterns: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to load available patterns', 'error');
    } finally {
        loadingIndicator.classList.add('hidden');
    }
}

// Update selection count display
function updateSelectionCount() {
    const countElement = document.getElementById('selectionCount');
    if (countElement) {
        const count = selectedPatterns.size;
        countElement.textContent = `${count} selected`;
    }
}

// Select all visible patterns
function selectAllPatterns() {
    const patterns = filteredPatterns.length > 0 ? filteredPatterns : availablePatterns;
    patterns.forEach(pattern => {
        selectedPatterns.add(pattern);
    });
    updatePatternSelection();
    updateSelectionCount();
}

// Deselect all patterns
function deselectAllPatterns() {
    selectedPatterns.clear();
    updatePatternSelection();
    updateSelectionCount();
}

// Update visual selection state for all pattern cards
function updatePatternSelection() {
    const cards = document.querySelectorAll('#availablePatternsGrid .group');
    cards.forEach(card => {
        const patternName = card.dataset.pattern;
        const addBtn = card.querySelector('.absolute.top-2.right-2');
        
        if (selectedPatterns.has(patternName)) {
            card.classList.add('ring-2', 'ring-blue-500');
            if (addBtn) {
                addBtn.classList.remove('opacity-0', 'bg-white', 'dark:bg-gray-700');
                addBtn.classList.add('opacity-100', 'bg-blue-500', 'text-white');
                addBtn.querySelector('.material-icons').textContent = 'check';
            }
        } else {
            card.classList.remove('ring-2', 'ring-blue-500');
            if (addBtn) {
                addBtn.classList.remove('opacity-100', 'bg-blue-500', 'text-white');
                addBtn.classList.add('opacity-0', 'bg-white', 'dark:bg-gray-700');
                addBtn.querySelector('.material-icons').textContent = 'add';
            }
        }
    });
}

// Display available patterns in modal
function displayAvailablePatterns() {
    const grid = document.getElementById('availablePatternsGrid');
    const noResultsMessage = document.getElementById('noResultsMessage');
    
    grid.classList.remove('hidden');
    noResultsMessage.classList.add('hidden');
    grid.innerHTML = '';

    if (filteredPatterns.length === 0) {
        grid.classList.add('hidden');
        noResultsMessage.classList.remove('hidden');
        return;
    }

    filteredPatterns.forEach((pattern, index) => {
        const card = document.createElement('div');
        card.className = 'flex flex-col gap-2 cursor-pointer transition-all duration-150 hover:scale-105';
        card.dataset.pattern = pattern;
        
        card.innerHTML = `
            <div class="w-full bg-center aspect-square bg-cover rounded-full border border-gray-200 dark:border-gray-700 relative pattern-preview">
                <div class="absolute top-2 right-2 size-6 rounded-full shadow-md opacity-0 transition-opacity duration-150 flex items-center justify-center">
                    <span class="material-icons text-sm text-gray-600 dark:text-gray-300">add</span>
                </div>
            </div>
            <p class="text-xs text-gray-700 dark:text-gray-300 font-medium truncate text-center">${pattern.replace('.thr', '').split('/').pop()}</p>
        `;

        const previewContainer = card.querySelector('.pattern-preview');
        const addBtn = card.querySelector('.absolute.top-2');
        
        // Only set preview image if already available in memory cache
        const previewData = previewCache.get(pattern);
        if (previewData && !previewData.error && previewData.image_data) {
            previewContainer.innerHTML = `<img src="${previewData.image_data}" alt="Pattern Preview" class="w-full h-full object-cover rounded-full" />`;
            // Re-add the add button
            const addBtnContainer = document.createElement('div');
            addBtnContainer.className = 'absolute top-2 right-2 size-6 rounded-full bg-white dark:bg-gray-700 shadow-md opacity-0 transition-opacity duration-150 flex items-center justify-center';
            addBtnContainer.innerHTML = '<span class="material-icons text-sm text-gray-600 dark:text-gray-300">add</span>';
            previewContainer.appendChild(addBtnContainer);
        }
        
        // Set up lazy loading for ALL patterns
        intersectionObserver.observe(card);

        // Handle selection
        card.addEventListener('click', () => {
            if (selectedPatterns.has(pattern)) {
                selectedPatterns.delete(pattern);
                card.classList.remove('ring-2', 'ring-blue-500');
                addBtn.classList.remove('opacity-100', 'bg-blue-500', 'text-white');
                addBtn.classList.add('opacity-0', 'bg-white', 'dark:bg-gray-700');
                addBtn.querySelector('.material-icons').textContent = 'add';
            } else {
                selectedPatterns.add(pattern);
                card.classList.add('ring-2', 'ring-blue-500');
                addBtn.classList.remove('opacity-0', 'bg-white', 'dark:bg-gray-700');
                addBtn.classList.add('opacity-100', 'bg-blue-500', 'text-white');
                addBtn.querySelector('.material-icons').textContent = 'check';
            }
            updateSelectionCount();
        });

        // Show add button on hover
        card.addEventListener('mouseenter', () => {
            if (!selectedPatterns.has(pattern)) {
                addBtn.classList.remove('opacity-0');
                addBtn.classList.add('opacity-100');
            }
        });

        card.addEventListener('mouseleave', () => {
            if (!selectedPatterns.has(pattern)) {
                addBtn.classList.remove('opacity-100');
                addBtn.classList.add('opacity-0');
            }
        });

        grid.appendChild(card);
    });
    
    // Trigger preview loading for visible patterns after displaying
    triggerPreviewLoadingForVisible();
}

// Trigger preview loading for currently visible patterns
function triggerPreviewLoadingForVisible() {
    // Get all pattern cards currently in the DOM
    const patternCards = document.querySelectorAll('[data-pattern]');
    
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
    
    // Add loading indicator with better styling
    if (element && !element.querySelector('img')) {
        element.innerHTML = `
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 rounded-full">
                <div class="bg-slate-200 rounded-full h-8 w-8 flex items-center justify-center">
                    <div class="bg-slate-500 rounded-full h-4 w-4"></div>
                </div>
            </div>
            <div class="absolute inset-0 flex items-center justify-center">
                <div class="text-xs text-slate-500 mt-12">Loading...</div>
            </div>
        `;
    }

    // Add to pending batch
    pendingPatterns.set(pattern, element);
    
    // Process batch immediately if it's full
    if (pendingPatterns.size >= BATCH_SIZE) {
        processPendingBatch();
    }
}

// Update preview element with image
function updatePreviewElement(element, imageData) {
    if (element) {
        element.innerHTML = `<img src="${imageData}" alt="Pattern Preview" class="w-full h-full object-cover rounded-full" />`;
        
        // Re-add the add button if it exists in the parent card
        const card = element.closest('[data-pattern]');
        if (card && !selectedPatterns.has(card.dataset.pattern)) {
            const addBtnContainer = document.createElement('div');
            addBtnContainer.className = 'absolute top-2 right-2 size-6 rounded-full bg-white dark:bg-gray-700 shadow-md opacity-0 transition-opacity duration-150 flex items-center justify-center';
            addBtnContainer.innerHTML = '<span class="material-icons text-sm text-gray-600 dark:text-gray-300">add</span>';
            element.appendChild(addBtnContainer);
        }
    }
}

// Add selected patterns to playlist
async function addSelectedPatternsToPlaylist() {
    if (selectedPatterns.size === 0 || !currentPlaylist) return;

    try {
        // Get current playlist data
        const response = await fetch(`/get_playlist?name=${encodeURIComponent(currentPlaylist)}`);
        if (response.ok) {
            const playlistData = await response.json();
            const currentFiles = playlistData.files || [];
            const newFiles = Array.from(selectedPatterns).filter(pattern => !currentFiles.includes(pattern));
            const updatedFiles = [...currentFiles, ...newFiles];
            
            // Update playlist
            const updateResponse = await fetch('/modify_playlist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    playlist_name: currentPlaylist,
                    files: updatedFiles
                })
            });

            if (updateResponse.ok) {
                showStatusMessage(`Added ${newFiles.length} patterns to playlist`, 'success');
                selectedPatterns.clear();
                document.getElementById('addPatternsModal').classList.add('hidden');
                await loadPlaylistPatterns(currentPlaylist);
            } else {
                throw new Error('Failed to update playlist');
            }
        }
    } catch (error) {
        logMessage(`Error adding patterns: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to add patterns', 'error');
    }
}

// Run playlist
async function runPlaylist() {
    if (!currentPlaylist) return;

    const runMode = document.querySelector('input[name="run_playlist"]:checked')?.value || 'single';
    const pauseTime = parseInt(document.getElementById('pauseTimeInput').value) || 0;
    const clearPattern = document.getElementById('clearPatternSelect').value;
    const shuffle = document.getElementById('shuffleCheckbox')?.checked || false;

    try {
        const response = await fetch('/run_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_name: currentPlaylist,
                run_mode: runMode,
                pause_time: pauseTime,
                clear_pattern: clearPattern === 'none' ? null : clearPattern,
                shuffle: shuffle
            })
        });

        if (response.ok) {
            showStatusMessage(`Started playlist: ${currentPlaylist}`, 'success');
            // Show the preview modal when a playlist starts
            if (typeof setModalVisibility === 'function') {
                setModalVisibility(true, false);
            } else if (window.openPlayerPreviewModal) {
                window.openPlayerPreviewModal();
            }
        } else {
            let errorMsg = 'Failed to run playlist';
            let errorType = 'error';
            
            try {
                const data = await response.json();
                if (data.detail) {
                    errorMsg = data.detail;
                    
                    // Handle specific error cases with appropriate messaging
                    if (data.detail === 'Connection not established') {
                        errorMsg = 'Please connect to the device before running a playlist';
                        errorType = 'warning';
                    } else if (response.status === 409) {
                        errorMsg = 'Another pattern is already running. Please stop the current pattern first.';
                        errorType = 'warning';
                    } else if (response.status === 404) {
                        errorMsg = 'Playlist not found. Please refresh the page and try again.';
                        errorType = 'error';
                    }
                }
            } catch (e) {
                // If we can't parse the JSON, use status-based messaging
                if (response.status === 400) {
                    errorMsg = 'Invalid request. Please check your settings and try again.';
                } else if (response.status === 500) {
                    errorMsg = 'Server error. Please try again later.';
                }
            }
            
            showStatusMessage(errorMsg, errorType);
        }
    } catch (error) {
        logMessage(`Error running playlist: ${error.message}`, LOG_TYPE.ERROR);
        
        // Handle network errors specifically
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            showStatusMessage('Network error. Please check your connection and try again.', 'error');
        } else {
            showStatusMessage('Failed to run playlist', 'error');
        }
    }
}

// Create new playlist
async function createNewPlaylist() {
    const playlistName = document.getElementById('newPlaylistName').value.trim();
    
    if (!playlistName) {
        showStatusMessage('Please enter a playlist name', 'warning');
        return;
    }

    try {
        const response = await fetch('/create_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_name: playlistName,
                files: []
            })
        });

        if (response.ok) {
            showStatusMessage('Playlist created successfully', 'success');
            document.getElementById('addPlaylistModal').classList.add('hidden');
            document.getElementById('newPlaylistName').value = '';
            await loadPlaylists();
        } else {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to create playlist');
        }
    } catch (error) {
        logMessage(`Error creating playlist: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to create playlist', 'error');
    }
}

// Delete playlist
async function deletePlaylist(playlistName) {
    if (!confirm(`Are you sure you want to delete the playlist "${playlistName}"?`)) {
        return;
    }

    try {
        const response = await fetch('/delete_playlist', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_name: playlistName
            })
        });

        if (response.ok) {
            showStatusMessage(`Playlist "${playlistName}" deleted successfully`, 'success');
            
            // If the deleted playlist was selected, clear the selection
            if (currentPlaylist === playlistName) {
                currentPlaylist = null;
                const header = document.getElementById('currentPlaylistTitle');
                header.innerHTML = '<h1 class="text-gray-900 text-2xl font-semibold leading-tight truncate">Select a Playlist</h1>';
                document.getElementById('addPatternsBtn').disabled = true;
                document.getElementById('runPlaylistBtn').disabled = true;
                document.getElementById('playbackSettings').classList.add('hidden');
                document.getElementById('patternsGrid').innerHTML = `
                    <div class="flex items-center justify-center col-span-full py-12 text-gray-500 dark:text-gray-400">
                        <span class="text-sm text-center">Select a playlist to view its patterns</span>
                    </div>
                `;
                
                // Return to playlists list on mobile
                showPlaylistsList();
            }
            
            // Reload playlists
            await loadPlaylists();
        } else {
            const data = await response.json();
            throw new Error(data.detail || 'Failed to delete playlist');
        }
    } catch (error) {
        logMessage(`Error deleting playlist: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to delete playlist', 'error');
    }
}

// Setup event listeners
function setupEventListeners() {
    // Mobile back button event listeners
    document.getElementById('mobileBackBtn').addEventListener('click', () => {
        showPlaylistsList();
    });

    // Add playlist button
    document.getElementById('addPlaylistBtn').addEventListener('click', () => {
        const modal = document.getElementById('addPlaylistModal');
        const input = document.getElementById('newPlaylistName');
        
        // Show modal first
        modal.classList.remove('hidden');
        
        // Focus handling
        const focusInput = () => {
            if (input) {
                input.focus();
                input.select();
            }
        };

        // Try multiple approaches to ensure focus
        focusInput();
        requestAnimationFrame(focusInput);
        setTimeout(focusInput, 50);
        setTimeout(focusInput, 100);
    });

    // Add patterns button
    document.getElementById('addPatternsBtn').addEventListener('click', async () => {
        await loadAvailablePatterns();
        updateSelectionCount();
        document.getElementById('addPatternsModal').classList.remove('hidden');
        // Focus search input when modal opens
        setTimeout(() => {
            document.getElementById('patternSearchInput').focus();
        }, 100);
    });

    // Search functionality
    document.getElementById('patternSearchInput').addEventListener('input', handleSearchInput);
    document.getElementById('clearSearchBtn').addEventListener('click', clearSearch);
    
    // Handle Enter key in search input
    document.getElementById('patternSearchInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
        }
    });
    
    // Run playlist button
    document.getElementById('runPlaylistBtn').addEventListener('click', runPlaylist);

    // Modal controls
    document.getElementById('cancelPlaylistBtn').addEventListener('click', () => {
        document.getElementById('addPlaylistModal').classList.add('hidden');
    });

    document.getElementById('createPlaylistBtn').addEventListener('click', createNewPlaylist);

    document.getElementById('cancelAddPatternsBtn').addEventListener('click', () => {
        selectedPatterns.clear();
        clearSearch();
        updateSelectionCount();
        document.getElementById('addPatternsModal').classList.add('hidden');
    });

    document.getElementById('confirmAddPatternsBtn').addEventListener('click', addSelectedPatternsToPlaylist);
    
    // Select All and Deselect All buttons
    document.getElementById('selectAllBtn').addEventListener('click', selectAllPatterns);
    document.getElementById('deselectAllBtn').addEventListener('click', deselectAllPatterns);

    // Handle Enter key in new playlist name input
    document.getElementById('newPlaylistName').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            createNewPlaylist();
        }
    });

    // Close modals when clicking outside
    document.getElementById('addPlaylistModal').addEventListener('click', (e) => {
        if (e.target.id === 'addPlaylistModal') {
            document.getElementById('addPlaylistModal').classList.add('hidden');
        }
    });

    document.getElementById('addPatternsModal').addEventListener('click', (e) => {
        if (e.target.id === 'addPatternsModal') {
            selectedPatterns.clear();
            clearSearch();
            document.getElementById('addPatternsModal').classList.add('hidden');
        }
    });
}

// Initialize playlists page
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Initialize intersection observer for lazy loading
        initializeIntersectionObserver();
        
        // Initialize IndexedDB preview cache
        await initPreviewCacheDB();
        
        // Setup event listeners
        setupEventListeners();
        
        // Initialize mobile view state
        isMobileView = isMobile();
        if (isMobileView) {
            initMobileLayout();
        } else {
            initDesktopLayout();
        }
        
        // Add window resize listener for responsive behavior
        window.addEventListener('resize', updateMobileView);
        
        // Restore playback settings
        restorePlaybackSettings();
        setupPlaybackSettingsPersistence();
        
        // Load playlists
        await loadPlaylists();
        
        // Check serial connection status
        await checkSerialStatus();
        
        logMessage('Playlists page initialized successfully', LOG_TYPE.SUCCESS);
    } catch (error) {
        logMessage(`Error during initialization: ${error.message}`, LOG_TYPE.ERROR);
        showStatusMessage('Failed to initialize playlists page', 'error');
    }
});

// Check serial connection status
async function checkSerialStatus() {
    try {
        const response = await fetch('/serial_status');
        if (response.ok) {
            const data = await response.json();
            const statusDot = document.getElementById('connectionStatusDot');
            if (statusDot) {
                statusDot.className = `inline-block size-2 rounded-full ml-2 align-middle ${
                    data.connected ? 'bg-green-500' : 'bg-red-500'
                }`;
            }
        }
    } catch (error) {
        logMessage(`Error checking serial status: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Mobile utility functions
function isMobile() {
    return window.innerWidth <= 768;
}

function updateMobileView() {
    const wasMobile = isMobileView;
    isMobileView = isMobile();
    
    if (wasMobile !== isMobileView) {
        // Mobile state changed, update layout
        if (isMobileView) {
            initMobileLayout();
        } else {
            initDesktopLayout();
        }
    }
}

function initMobileLayout() {
    const sidebar = document.getElementById('playlistsSidebar');
    const details = document.getElementById('playlistDetails');
    const mobileBackBtn = document.getElementById('mobileBackBtn');
    
    if (!currentPlaylist) {
        // Show playlists list, hide details
        sidebar.classList.remove('mobile-hidden');
        details.classList.add('mobile-hidden');
        mobileBackBtn.classList.add('mobile-hidden');
    } else {
        // Show details, hide playlists list
        sidebar.classList.add('mobile-hidden');
        details.classList.remove('mobile-hidden');
        mobileBackBtn.classList.remove('mobile-hidden');
        mobileBackBtn.classList.add('mobile-flex');
    }
}

function initDesktopLayout() {
    const sidebar = document.getElementById('playlistsSidebar');
    const details = document.getElementById('playlistDetails');
    const mobileBackBtn = document.getElementById('mobileBackBtn');
    
    // Show both sidebar and details on desktop
    sidebar.classList.remove('mobile-hidden');
    details.classList.remove('mobile-hidden');
    mobileBackBtn.classList.add('mobile-hidden');
    mobileBackBtn.classList.remove('mobile-flex');
}

function showPlaylistDetails() {
    if (isMobileView) {
        const sidebar = document.getElementById('playlistsSidebar');
        const details = document.getElementById('playlistDetails');
        const mobileBackBtn = document.getElementById('mobileBackBtn');
        
        sidebar.classList.add('mobile-hidden');
        details.classList.remove('mobile-hidden');
        mobileBackBtn.classList.remove('mobile-hidden');
        mobileBackBtn.classList.add('mobile-flex');
    }
}

function showPlaylistsList() {
    if (isMobileView) {
        const sidebar = document.getElementById('playlistsSidebar');
        const details = document.getElementById('playlistDetails');
        const mobileBackBtn = document.getElementById('mobileBackBtn');
        
        sidebar.classList.remove('mobile-hidden');
        details.classList.add('mobile-hidden');
        mobileBackBtn.classList.add('mobile-hidden');
        mobileBackBtn.classList.remove('mobile-flex');
    }
} 