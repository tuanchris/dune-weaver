// Global variables
let allPatterns = [];
let selectedPattern = null;
let previewObserver = null;
let currentBatch = 0;
const BATCH_SIZE = 20; // Number of patterns to load per batch
let previewCache = new Map(); // Cache for preview data
let imageCache = new Map(); // Cache for preloaded images

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
                if (pattern && !previewContainer.style.backgroundImage) {
                    const data = previewCache.get(pattern);
                    if (data) {
                        const img = imageCache.get(data.preview_url);
                        if (img) {
                            previewContainer.style.backgroundImage = `url('${data.preview_url}')`;
                        }
                    }
                }
                previewObserver.unobserve(previewContainer);
            }
        });
    }, {
        rootMargin: '50px 0px',
        threshold: 0.1
    });

    // Observe all existing preview containers
    document.querySelectorAll('[data-pattern]').forEach(container => {
        previewObserver.observe(container);
    });
}

// Load batch of pattern previews
async function loadPatternPreviewsBatch(patterns) {
    try {
        // Filter out patterns that already have previews in cache
        const patternsToLoad = patterns.filter(pattern => !previewCache.has(pattern));
        
        if (patternsToLoad.length === 0) {
            // If all patterns are cached, just update the display
            updatePatternPreviews(patterns);
            return;
        }

        const response = await fetch('/preview_thr_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_names: patternsToLoad })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const results = await response.json();
        
        // Update cache with batch results
        Object.entries(results).forEach(([pattern, data]) => {
            if (!data.error) {
                previewCache.set(pattern, data);
            }
        });

        // Preload images for this batch
        const urlsToPreload = Object.values(results)
            .filter(data => !data.error)
            .map(data => data.preview_url);
        await preloadImages(urlsToPreload);

        // Update all pattern previews
        updatePatternPreviews(patterns);
    } catch (error) {
        logMessage(`Error fetching batch previews: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Update pattern previews display
function updatePatternPreviews(patterns) {
    patterns.forEach(pattern => {
        const previewContainer = document.querySelector(`[data-pattern="${pattern}"]`);
        if (previewContainer && !previewContainer.style.backgroundImage) {
            const data = previewCache.get(pattern);
            if (data && !data.error) {
                const img = imageCache.get(data.preview_url);
                if (img) {
                    previewContainer.style.backgroundImage = `url('${data.preview_url}')`;
                }
            }
        }
    });
}

// Load and display patterns
async function loadPatterns() {
    try {
        logMessage('Loading patterns...', LOG_TYPE.INFO);
        const response = await fetch('/list_theta_rho_files');
        let patterns = await response.json();
        logMessage(`Received ${patterns.length} patterns from server`, LOG_TYPE.INFO);

        // Filter for .thr files
        patterns = patterns.filter(file => file.endsWith('.thr'));
        logMessage(`Filtered to ${patterns.length} .thr files`, LOG_TYPE.INFO);
        
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
    }
}

// Display a batch of patterns
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

    // Load previews for the batch
    loadPatternPreviewsBatch(batchPatterns);

    // If there are more patterns to load, set up the observer for the last card
    if (end < allPatterns.length) {
        const lastCard = patternGrid.lastElementChild;
        if (lastCard) {
            const observer = new IntersectionObserver((entries) => {
                if (entries[0].isIntersecting) {
                    currentBatch++;
                    displayPatternBatch();
                    observer.disconnect();
                }
            }, {
                rootMargin: '100px 0px',
                threshold: 0.1
            });
            observer.observe(lastCard);
        }
    }
}

// Create a pattern card element
function createPatternCard(pattern) {
    const card = document.createElement('div');
    card.className = 'pattern-card flex flex-col items-center gap-3';
    
    // Create preview container
    const previewContainer = document.createElement('div');
    previewContainer.className = 'w-32 h-32 rounded-full bg-center bg-no-repeat bg-cover shadow-md overflow-hidden';
    previewContainer.dataset.pattern = pattern;
    
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
        // Check cache first
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
                previewCache.set(pattern, data);
                // Preload the image
                await preloadImages([data.preview_url]);
            } else {
                throw new Error(data?.error || 'Failed to get preview data');
            }
        }

        const previewPanel = document.getElementById('patternPreviewPanel');
        const layoutContainer = document.querySelector('.layout-content-container');
        
        // Update preview content
        const img = imageCache.get(data.preview_url);
        if (img) {
            document.getElementById('patternPreviewImage').src = data.preview_url;
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
                    // Refresh the pattern list
                    await loadPatterns();
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
        // If search is empty, show all patterns
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

    // Reinitialize preview observer for new cards
    if (previewObserver) {
        previewObserver.disconnect();
    }
    initPreviewObserver();

    // Load previews only for filtered patterns
    loadPatternPreviewsBatch(filteredPatterns);
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

// Initialize patterns functionality
document.addEventListener('DOMContentLoaded', () => {
    // Initialize the preview observer
    initPreviewObserver();
    
    // Load patterns
    loadPatterns();

    // Fetch initial speed value
    fetch('/get_speed')
        .then(response => response.json())
        .then(data => {
            if (data.speed) {
                const speedInput = document.getElementById('speedInput');
                if (speedInput) {
                    speedInput.value = data.speed;
                }
            }
        })
        .catch(error => {
            console.error('Error fetching initial speed:', error);
        });
    
    // Add search input handler
    const searchInput = document.getElementById('patternSearch');
    const searchButton = document.getElementById('searchButton');
    
    if (searchInput) {
        // Handle Enter key
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                searchPatterns(searchInput.value);
            }
        });

        // Handle search input clearing
        searchInput.addEventListener('input', (e) => {
            if (e.target.value === '') {
                // Reset to initial state
                currentBatch = 0;
                const patternGrid = document.querySelector('.grid');
                if (patternGrid) {
                    patternGrid.innerHTML = '';
                }
                displayPatternBatch();
            }
        });

        // Handle search button click
        if (searchButton) {
            searchButton.addEventListener('click', () => {
                searchPatterns(searchInput.value);
            });
        }
    }
    
    // Add category filter handler
    const categoryFilter = document.getElementById('category-filter');
    if (categoryFilter) {
        categoryFilter.addEventListener('change', (e) => {
            filterPatternsByCategory(e.target.value);
        });
    }
    
    // Add tag filter handler
    const tagFilter = document.getElementById('tag-filter');
    if (tagFilter) {
        tagFilter.addEventListener('change', (e) => {
            filterPatternsByTag(e.target.value);
        });
    }

    // Update the file input change handler
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
                // Refresh the pattern list
                loadPatterns();
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