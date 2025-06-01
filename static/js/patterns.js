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
}

// Load batch of pattern previews
async function loadPatternPreviewsBatch(patterns) {
    try {
        const response = await fetch('/preview_thr_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_names: patterns })
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

        // Update visible previews
        patterns.forEach(pattern => {
            const previewContainer = document.querySelector(`[data-pattern="${pattern}"]`);
            if (previewContainer && !previewContainer.style.backgroundImage) {
                const data = results[pattern];
                if (data && !data.error) {
                    const img = imageCache.get(data.preview_url);
                    if (img) {
                        previewContainer.style.backgroundImage = `url('${data.preview_url}')`;
                    }
                }
            }
        });
    } catch (error) {
        logMessage(`Error fetching batch previews: ${error.message}`, LOG_TYPE.ERROR);
    }
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
        document.getElementById('firstCoordinate').textContent = `(${data.first_coordinate?.x || 0}, ${data.first_coordinate?.y || 0})`;
        document.getElementById('lastCoordinate').textContent = `(${data.last_coordinate?.x || 0}, ${data.last_coordinate?.y || 0})`;
        
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
    layoutContainer.parentElement.classList.remove('preview-open');
    if (window.innerWidth >= 1024) {
        previewPanel.classList.add('lg:opacity-0', 'lg:pointer-events-none');
    }
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
        panel.classList.add('translate-x-full');
        // Remove selected state from all cards when closing
        document.querySelectorAll('.pattern-card').forEach(c => {
            c.classList.remove('selected');
        });
    };

    // Handle play button click
    playButton.onclick = () => {
        const selectedAction = document.querySelector('input[name="preExecutionAction"]:checked').parentElement.textContent.trim();
        logMessage(`Playing pattern: ${pattern} with action: ${selectedAction}`, LOG_TYPE.INFO);
        // TODO: Implement play functionality
    };

    // Handle delete button click
    deleteButton.onclick = () => {
        if (confirm('Are you sure you want to delete this pattern?')) {
            logMessage(`Deleting pattern: ${pattern}`, LOG_TYPE.INFO);
            // TODO: Implement delete functionality
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
    const searchInput = query.toLowerCase();
    const filteredPatterns = allPatterns.filter(pattern => 
        pattern.toLowerCase().includes(searchInput)
    );
    displayPatterns(filteredPatterns);
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
    
    // Add search input handler
    const searchInput = document.querySelector('input[type="search"]');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchPatterns(e.target.value);
        });
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
}); 