// Player status bar functionality - Updated to fix logMessage errors

// Update LED nav label based on provider
async function updateLedNavLabel() {
    try {
        const response = await fetch('/get_led_config');
        if (response.ok) {
            const data = await response.json();
            const navLabel = document.getElementById('led-nav-label');
            if (navLabel) {
                if (data.provider === 'wled') {
                    navLabel.textContent = 'WLED';
                } else if (data.provider === 'dw_leds') {
                    navLabel.textContent = 'DW LEDs';
                } else {
                    navLabel.textContent = 'LED';
                }
            }
        }
    } catch (error) {
        console.error('Error updating LED nav label:', error);
    }
}

// Call on page load
document.addEventListener('DOMContentLoaded', updateLedNavLabel);

// Pattern files cache for improved performance with localStorage persistence
const PATTERN_CACHE_KEY = 'dune_weaver_pattern_files_cache';
const PATTERN_CACHE_EXPIRY = 30 * 60 * 1000; // 30 minutes cache (longer since it persists)

// Function to get cached pattern files or fetch fresh data
async function getCachedPatternFiles(forceRefresh = false) {
    const now = Date.now();

    // Try to load from localStorage first
    if (!forceRefresh) {
        try {
            const cachedData = localStorage.getItem(PATTERN_CACHE_KEY);
            if (cachedData) {
                const { files, timestamp } = JSON.parse(cachedData);
                if (files && timestamp && (now - timestamp) < PATTERN_CACHE_EXPIRY) {
                    console.log('Using cached pattern files from localStorage');
                    return files;
                }
            }
        } catch (error) {
            console.warn('Error reading pattern files cache from localStorage:', error);
        }
    }

    try {
        console.log('Fetching fresh pattern files from server');
        const response = await fetch('/list_theta_rho_files');
        if (!response.ok) {
            throw new Error(`Failed to fetch pattern files: ${response.status}`);
        }

        const files = await response.json();

        // Store in localStorage
        try {
            const cacheData = { files, timestamp: now };
            localStorage.setItem(PATTERN_CACHE_KEY, JSON.stringify(cacheData));
        } catch (error) {
            console.warn('Error storing pattern files cache in localStorage:', error);
        }

        return files;
    } catch (error) {
        console.error('Error fetching pattern files:', error);

        // Try to return any cached data as fallback, even if expired
        try {
            const cachedData = localStorage.getItem(PATTERN_CACHE_KEY);
            if (cachedData) {
                const { files } = JSON.parse(cachedData);
                if (files) {
                    console.log('Using expired cached pattern files as fallback');
                    return files;
                }
            }
        } catch (fallbackError) {
            console.warn('Error reading fallback cache:', fallbackError);
        }

        return [];
    }
}

// Function to invalidate pattern files cache
function invalidatePatternFilesCache() {
    try {
        localStorage.removeItem(PATTERN_CACHE_KEY);
        console.log('Pattern files cache invalidated');
    } catch (error) {
        console.warn('Error invalidating pattern files cache:', error);
    }
}

// Helper function to normalize file paths for cross-platform compatibility
function normalizeFilePath(filePath) {
    if (!filePath) return '';
    // First normalize path separators
    let normalized = filePath.replace(/\\/g, '/');
    
    // Remove only the patterns directory prefix, not patterns within the path
    if (normalized.startsWith('./patterns/')) {
        normalized = normalized.substring(11);
    } else if (normalized.startsWith('patterns/')) {
        normalized = normalized.substring(9);
    }
    
    return normalized;
}

let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000; // 3 seconds
let isEditingSpeed = false; // Track if user is editing speed

// WebSocket UI update throttling for Pi performance
let lastUIUpdate = 0;
const UI_UPDATE_INTERVAL = 100; // Minimum ms between UI updates (10 updates/sec max)
let playerPreviewData = null; // Store the current pattern's preview data for modal
let playerPreviewCtx = null; // Store the canvas context for modal preview
let playerAnimationId = null; // Store animation frame ID for modal
let lastProgress = 0; // Last known progress from backend
let targetProgress = 0; // Target progress to animate towards
let animationStartTime = 0; // Start time of current animation
let animationDuration = 1000; // Duration of interpolation in ms
let smoothAnimationStartTime = 0; // Start time for smooth coordinate animation
let smoothAnimationActive = false; // Whether smooth animation is running
let modalAnimationId = null; // Store animation frame ID for modal
let modalLastProgress = 0; // Last known progress for modal
let modalTargetProgress = 0; // Target progress for modal
let modalAnimationStartTime = 0; // Start time for modal animation
let userDismissedModal = false; // Track if user has manually dismissed the modal

// Function to set modal visibility
function setModalVisibility(show, userAction = false) {
    const modal = document.getElementById('playerPreviewModal');
    if (!modal) return;
    
    if (show) {
        modal.classList.remove('hidden');
    } else {
        modal.classList.add('hidden');
    }
    
    if (userAction) {
        userDismissedModal = !show;
    }
}
let currentPreviewFile = null; // Track the current file for preview data

// Global playback status for cross-file access
window.currentPlaybackStatus = {
    is_running: false,
    current_file: null
};

function connectWebSocket() {
    if (ws) {
        ws.close();
    }

    ws = new WebSocket(`ws://${window.location.host}/ws/status`);
    
    ws.onopen = function() {
        console.log("WebSocket connection established");
        reconnectAttempts = 0;
    };

    ws.onclose = function() {
        console.log("WebSocket connection closed");
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(connectWebSocket, reconnectDelay);
        }
    };

    ws.onerror = function(error) {
        console.error("WebSocket error:", error);
    };

    ws.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'status_update') {
                // Throttle UI updates for better Pi performance
                const now = Date.now();
                if (now - lastUIUpdate < UI_UPDATE_INTERVAL) {
                    return; // Skip this update, too soon
                }
                lastUIUpdate = now;

                // Update global playback status
                window.currentPlaybackStatus = {
                    is_running: data.data.is_running || false,
                    current_file: data.data.current_file || null
                };

                // Update modal status with the full data
                syncModalControls(data.data);
                
                // Update speed input field on table control page if it exists
                if (data.data && data.data.speed) {
                    const currentSpeedDisplay = document.getElementById('currentSpeedDisplay');
                    if (currentSpeedDisplay) {
                        currentSpeedDisplay.textContent = `${data.data.speed} mm/s`;
                    }
                }
                
                // Update connection status dot using 'connection_status' or fallback to 'connected'
                if (data.data.hasOwnProperty('connection_status')) {
                    updateConnectionStatus(data.data.connection_status);
                }
                
                // Check if current file has changed and reload preview data if needed
                if (data.data.current_file) {
                    const newFile = normalizeFilePath(data.data.current_file);
                    if (newFile !== currentPreviewFile) {
                        currentPreviewFile = newFile;

                        // Only preload if we're on the browse page (index.html)
                        // Other pages (playlists, table_control, LED, settings) will load on-demand
                        const modal = document.getElementById('playerPreviewModal');
                        const browsePage = document.getElementById('browseSortFieldSelect');

                        if (modal && browsePage) {
                            // We're on the browse page with the modal - preload coordinates
                            loadPlayerPreviewData(data.data.current_file);
                        }
                    }
                } else {
                    currentPreviewFile = null;
                    playerPreviewData = null;
                }
                
                // Update progress for modal animation with smooth interpolation
                if (playerPreviewData && data.data.progress && data.data.progress.percentage !== null) {
                    const newProgress = data.data.progress.percentage / 100;
                    targetProgress = newProgress;
                    
                    // Update modal if open with smooth animation
                    const modal = document.getElementById('playerPreviewModal');
                    if (modal && !modal.classList.contains('hidden')) {
                        updateModalPreviewSmooth(newProgress);
                    }
                }
                
                // Reset userDismissedModal flag if no pattern is playing
                if (!data.data.current_file || !data.data.is_running) {
                    userDismissedModal = false;
                }
            }
        } catch (error) {
            console.error("Error processing WebSocket message:", error);
        }
    };
}

function updateConnectionStatus(isConnected) {
    const statusDot = document.getElementById("connectionStatusDot");
    if (statusDot) {
        // Update dot color
        statusDot.className = `inline-block size-2 rounded-full ml-2 align-middle ${
            isConnected ? "bg-green-500" : "bg-red-500"
        }`;
    }
}

// Setup player preview with expand button
function setupPlayerPreview() {
    const previewContainer = document.getElementById('player-pattern-preview');
    if (!previewContainer) return;

    // Get current background image URL
    const currentBgImage = previewContainer.style.backgroundImage;
    
    // Clear container
    previewContainer.innerHTML = '';
    previewContainer.style.backgroundImage = '';
    
    // Create preview image container
    const imageContainer = document.createElement('div');
    imageContainer.className = 'relative aspect-square rounded-full overflow-hidden w-full h-full';
    
    // Create image element
    const img = document.createElement('img');
    img.className = 'w-full h-full object-cover';
    // img.alt = 'Pattern Preview';
    // Extract URL from background-image CSS
    img.src = currentBgImage.replace(/^url\(['"](.+)['"]\)$/, '$1');
    
    // Add expand button overlay
    const expandOverlay = document.createElement('div');
    expandOverlay.className = 'absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity duration-200 cursor-pointer z-20 bg-black bg-opacity-20 hover:bg-opacity-30';
    expandOverlay.innerHTML = '<div class="bg-white rounded-full p-3 shadow-lg flex items-center justify-center w-12 h-12"><span class="material-icons text-xl text-gray-800">fullscreen</span></div>';
    
    // Add click handler for expand button
    expandOverlay.addEventListener('click', (e) => {
        e.stopPropagation();
        openPlayerPreviewModal();
    });
    
    // Add image and overlay to image container
    imageContainer.appendChild(img);
    imageContainer.appendChild(expandOverlay);
    
    // Add image container to preview container
    previewContainer.appendChild(imageContainer);
}

// Open player preview modal
async function openPlayerPreviewModal() {
    try {
        const modal = document.getElementById('playerPreviewModal');
        const title = document.getElementById('playerPreviewTitle');
        const canvas = document.getElementById('playerPreviewCanvas');
        const ctx = canvas.getContext('2d');
        const toggleBtn = document.getElementById('toggle-preview-modal-btn');

        // Show modal immediately for instant feedback
        modal.classList.remove('hidden');

        // Setup canvas (so it's ready to display loading state)
        setupPlayerPreviewCanvas(ctx);

        // Load preview data on-demand if not already loaded
        if (!playerPreviewData && currentPreviewFile) {
            // Show loading state
            title.textContent = 'Loading pattern...';
            drawLoadingState(ctx);

            // Load data in background
            await loadPlayerPreviewData(`./patterns/${currentPreviewFile}`);

            // Update title when loaded
            title.textContent = 'Live Pattern Preview';
        } else {
            // Data already loaded
            title.textContent = 'Live Pattern Preview';
        }

        // Draw the pattern (either immediately if cached, or after loading)
        drawPlayerPreview(ctx, targetProgress);

    } catch (error) {
        console.error(`Error opening player preview modal: ${error.message}`);
        showStatusMessage('Failed to load pattern for animation', 'error');
    }
}

// Setup player preview canvas for modal
function setupPlayerPreviewCanvas(ctx) {
    const canvas = ctx.canvas;
    const container = canvas.parentElement; // This is the div with max-w and max-h constraints
    const modal = document.getElementById('playerPreviewModal');
    
    if (!container || !modal) return;
    
    // Calculate available viewport space directly
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    // Calculate maximum canvas size based on viewport and fixed estimates
    // Modal uses max-w-5xl (1024px) but we want to be responsive to actual viewport
    const modalMaxWidth = Math.min(1024, viewportWidth * 0.9); // Account for modal padding
    const modalMaxHeight = viewportHeight * 0.95; // max-h-[95vh]
    
    // Reserve space for modal header (~80px) and controls (~200px) and padding
    const reservedSpace = 320; // Header + controls + padding
    const availableModalHeight = modalMaxHeight - reservedSpace;
    
    // Calculate canvas constraints (stay within original 800px max, but be responsive)
    const maxCanvasSize = Math.min(800, modalMaxWidth - 64, availableModalHeight); // 64px for canvas area padding
    
    // Ensure minimum size
    const finalSize = Math.max(200, maxCanvasSize);
    
    // Update container to exact size (override CSS constraints)
    container.style.width = `${finalSize}px`;
    container.style.height = `${finalSize}px`;
    container.style.maxWidth = `${finalSize}px`;
    container.style.maxHeight = `${finalSize}px`;
    container.style.minWidth = `${finalSize}px`;
    container.style.minHeight = `${finalSize}px`;
    
    // Set the internal canvas size for high-DPI rendering
    // Cap at 1.5x for better Pi performance (was 2x forced)
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = finalSize * pixelRatio;
    canvas.height = finalSize * pixelRatio;
    
    // Set the display size (canvas fills its container)
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    
    console.log('Canvas resized:', {
        viewport: `${viewportWidth}x${viewportHeight}`,
        modalMaxWidth,
        availableModalHeight,
        finalSize: finalSize
    });
}

// Get interpolated coordinate at specific progress
function getInterpolatedCoordinate(progress) {
    if (!playerPreviewData || playerPreviewData.length === 0) return null;
    
    const totalPoints = playerPreviewData.length;
    const exactIndex = progress * (totalPoints - 1);
    const index = Math.floor(exactIndex);
    const fraction = exactIndex - index;
    
    // Ensure we don't go out of bounds
    if (index >= totalPoints - 1) {
        return playerPreviewData[totalPoints - 1];
    }
    
    if (index < 0) {
        return playerPreviewData[0];
    }
    
    // Get the two coordinates to interpolate between
    const [theta1, rho1] = playerPreviewData[index];
    const [theta2, rho2] = playerPreviewData[index + 1];
    
    // Interpolate theta (handle angle wrapping)
    let deltaTheta = theta2 - theta1;
    if (deltaTheta > Math.PI) deltaTheta -= 2 * Math.PI;
    if (deltaTheta < -Math.PI) deltaTheta += 2 * Math.PI;
    
    const interpolatedTheta = theta1 + deltaTheta * fraction;
    const interpolatedRho = rho1 + (rho2 - rho1) * fraction;
    
    return [interpolatedTheta, interpolatedRho];
}

// Draw loading state on canvas
function drawLoadingState(ctx) {
    if (!ctx) return;

    const canvas = ctx.canvas;
    // Must match the pixelRatio used when setting canvas size
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
    const containerSize = canvas.width / pixelRatio;
    const center = containerSize / 2;

    ctx.save();

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Create circular clipping path
    ctx.beginPath();
    ctx.arc(canvas.width/2, canvas.height/2, canvas.width/2, 0, Math.PI * 2);
    ctx.clip();

    // Setup coordinate system
    ctx.scale(pixelRatio, pixelRatio);

    // Draw loading text only
    ctx.fillStyle = '#9ca3af';
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Loading pattern...', center, center);

    ctx.restore();
}

// Draw player preview for modal
function drawPlayerPreview(ctx, progress) {
    if (!ctx || !playerPreviewData || playerPreviewData.length === 0) return;
    
    const canvas = ctx.canvas;
    // Must match the pixelRatio used when setting canvas size
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
    const containerSize = canvas.width / pixelRatio;
    const center = containerSize / 2;
    const scale = (containerSize / 2) - 30;
    
    ctx.save();

    // Clear canvas for fresh drawing
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Create circular clipping path
    ctx.beginPath();
    ctx.arc(canvas.width/2, canvas.height/2, canvas.width/2, 0, Math.PI * 2);
    ctx.clip();
    
    // Setup coordinate system for drawing
    ctx.scale(pixelRatio, pixelRatio);
    
    // Calculate how many points to draw
    const totalPoints = playerPreviewData.length;
    const pointsToDraw = Math.floor(totalPoints * progress);
    
    if (pointsToDraw < 2) {
        ctx.restore();
        return;
    }
    
    // Draw the pattern
    ctx.beginPath();
    ctx.strokeStyle = '#808080';
    ctx.lineWidth = 1;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    // Enable high quality rendering
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    
    // Draw pattern lines up to the last complete segment
    for (let i = 0; i < pointsToDraw - 1; i++) {
        const [theta1, rho1] = playerPreviewData[i];
        const [theta2, rho2] = playerPreviewData[i + 1];
        
        const x1 = center + rho1 * scale * Math.cos(theta1);
        const y1 = center + rho1 * scale * Math.sin(theta1);
        const x2 = center + rho2 * scale * Math.cos(theta2);
        const y2 = center + rho2 * scale * Math.sin(theta2);
        
        if (i === 0) {
            ctx.moveTo(x1, y1);
        }
        ctx.lineTo(x2, y2);
    }
    
    // Draw the final partial segment to the interpolated position
    if (pointsToDraw > 0) {
        const interpolatedCoord = getInterpolatedCoordinate(progress);
        
        if (interpolatedCoord && pointsToDraw > 1) {
            // Get the last complete coordinate
            const [lastTheta, lastRho] = playerPreviewData[pointsToDraw - 1];
            const lastX = center + lastRho * scale * Math.cos(lastTheta);
            const lastY = center + lastRho * scale * Math.sin(lastTheta);
            
            // Draw line to interpolated position
            const [interpTheta, interpRho] = interpolatedCoord;
            const interpX = center + interpRho * scale * Math.cos(interpTheta);
            const interpY = center + interpRho * scale * Math.sin(interpTheta);
            
            ctx.lineTo(interpX, interpY);
        }
    }
    
    ctx.stroke();
    
    // Draw current position dot with interpolated position
    if (pointsToDraw > 0) {
        const interpolatedCoord = getInterpolatedCoordinate(progress);
        
        if (interpolatedCoord) {
            const [theta, rho] = interpolatedCoord;
            const x = center + rho * scale * Math.cos(theta);
            const y = center + rho * scale * Math.sin(theta);
            
            // Draw white border
            ctx.beginPath();
            ctx.fillStyle = '#ffffff';
            ctx.arc(x, y, 7.5, 0, Math.PI * 2);
            ctx.fill();
            
            // Draw red dot
            ctx.beginPath();
            ctx.fillStyle = '#ff0000';
            ctx.arc(x, y, 6, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    ctx.restore();
}

// Load pattern coordinates for player preview
async function loadPlayerPreviewData(pattern) {
    try {
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
        
        playerPreviewData = data.coordinates;
        // Store the filename for comparison
        playerPreviewData.fileName = normalizeFilePath(pattern);
        
    } catch (error) {
        console.error(`Error loading player preview data: ${error.message}`);
        playerPreviewData = null;
    }
}

// Ultra-smooth animation function for modal
function animateModalPreview() {
    const modal = document.getElementById('playerPreviewModal');
    if (!modal || modal.classList.contains('hidden')) return;
    
    const canvas = document.getElementById('playerPreviewCanvas');
    const ctx = canvas.getContext('2d');
    if (!ctx || !playerPreviewData) return;
    
    const currentTime = Date.now();
    const elapsed = currentTime - modalAnimationStartTime;
    const totalDuration = animationDuration;
    
    // Calculate smooth progress with easing
    const rawProgress = Math.min(elapsed / totalDuration, 1);
    const easeProgress = rawProgress < 0.5 
        ? 2 * rawProgress * rawProgress 
        : 1 - Math.pow(-2 * rawProgress + 2, 2) / 2;
    
    // Interpolate between last and target progress
    const currentProgress = modalLastProgress + (modalTargetProgress - modalLastProgress) * easeProgress;
    
    // Draw the pattern up to current progress
    drawPlayerPreview(ctx, currentProgress);
    
    // Continue animation if not at target
    if (rawProgress < 1) {
        modalAnimationId = requestAnimationFrame(animateModalPreview);
    }
}

// Update modal preview with smooth animation
function updateModalPreviewSmooth(newProgress) {
    if (newProgress === modalTargetProgress) return; // No change needed
    
    // Stop any existing animation
    if (modalAnimationId) {
        cancelAnimationFrame(modalAnimationId);
    }
    
    // Update animation parameters
    modalLastProgress = modalTargetProgress;
    modalTargetProgress = newProgress;
    modalAnimationStartTime = Date.now();
    
    // Start smooth animation
    animateModalPreview();
}

// Setup player preview modal events
function setupPlayerPreviewModalEvents() {
    const modal = document.getElementById('playerPreviewModal');
    const closeBtn = document.getElementById('closePlayerPreview');
    const toggleBtn = document.getElementById('toggle-preview-modal-btn');
    
    if (!modal || !closeBtn || !toggleBtn) return;
    
    // Remove any existing event listeners to prevent conflicts
    const newToggleBtn = toggleBtn.cloneNode(true);
    toggleBtn.parentNode.replaceChild(newToggleBtn, toggleBtn);
    
    // Toggle button click handler
    newToggleBtn.addEventListener('click', () => {
        const isHidden = modal.classList.contains('hidden');
        if (isHidden) {
            openPlayerPreviewModal();

        } else {
            modal.classList.add('hidden');
        }
    });
    
    // Close modal when clicking close button
    closeBtn.addEventListener('click', () => {
        setModalVisibility(false, true);
    });
    
    // Close modal when clicking outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            setModalVisibility(false, true);
        }
    });
    
    // Close modal with Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            setModalVisibility(false, true);
        }
    });
    
    // Setup modal control buttons
    setupModalControls();
}

// Handle pause/resume toggle
async function togglePauseResume() {
    const pauseButton = document.getElementById('modal-pause-button');
    if (!pauseButton) return;

    try {
        const pauseIcon = pauseButton.querySelector('.material-icons');
        const isCurrentlyPaused = pauseIcon.textContent === 'play_arrow';

        // Show immediate feedback
        showStatusMessage(isCurrentlyPaused ? 'Resuming...' : 'Pausing...', 'info');

        const endpoint = isCurrentlyPaused ? '/resume_execution' : '/pause_execution';
        const response = await fetch(endpoint, { method: 'POST' });

        if (!response.ok) throw new Error(`Failed to ${isCurrentlyPaused ? 'resume' : 'pause'}`);

        // Show success message
        showStatusMessage(isCurrentlyPaused ? 'Pattern resumed' : 'Pattern paused', 'success');
    } catch (error) {
        console.error('Error toggling pause:', error);
        showStatusMessage('Failed to pause/resume pattern', 'error');
    }
}

// Setup modal controls
function setupModalControls() {
    const pauseButton = document.getElementById('modal-pause-button');
    const skipButton = document.getElementById('modal-skip-button');
    const stopButton = document.getElementById('modal-stop-button');
    const speedDisplay = document.getElementById('modal-speed-display');
    const speedInput = document.getElementById('modal-speed-input');
    
    if (!pauseButton || !skipButton || !stopButton || !speedDisplay || !speedInput) return;
    
    // Pause button click handler
    pauseButton.addEventListener('click', togglePauseResume);
    
    // Skip button click handler
    skipButton.addEventListener('click', async () => {
        try {
            // Show immediate feedback
            showStatusMessage('Skipping to next pattern...', 'info');

            const response = await fetch('/skip_pattern', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to skip pattern');

            // Show success message
            showStatusMessage('Skipped to next pattern', 'success');
        } catch (error) {
            console.error('Error skipping pattern:', error);
            showStatusMessage('Failed to skip pattern', 'error');
        }
    });
    
    // Stop button click handler
    stopButton.addEventListener('click', async () => {
        try {
            // Show immediate feedback
            showStatusMessage('Stopping...', 'info');

            const response = await fetch('/stop_execution', { method: 'POST' });
            if (!response.ok) throw new Error('Failed to stop pattern');
            else {
                // Show success message
                showStatusMessage('Pattern stopped', 'success');

                // Hide modal when stopping
                const modal = document.getElementById('playerPreviewModal');
                if (modal) modal.classList.add('hidden');
            }
        } catch (error) {
            console.error('Error stopping pattern:', error);
            showStatusMessage('Failed to stop pattern', 'error');
        }
    });
    
    // Speed display click to edit
    speedDisplay.addEventListener('click', () => {
        isEditingSpeed = true;
        speedDisplay.classList.add('hidden');
        speedInput.value = speedDisplay.textContent;
        speedInput.classList.remove('hidden');
        speedInput.focus();
        speedInput.select();
    });
    
    // Speed input handlers
    speedInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            exitModalSpeedEditMode(true);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            exitModalSpeedEditMode(false);
        }
    });
    
    speedInput.addEventListener('blur', () => {
        exitModalSpeedEditMode(true);
    });
}

// Exit modal speed edit mode
async function exitModalSpeedEditMode(save = false) {
    const speedDisplay = document.getElementById('modal-speed-display');
    const speedInput = document.getElementById('modal-speed-input');
    
    if (!speedDisplay || !speedInput) return;
    
    isEditingSpeed = false;
    speedInput.classList.add('hidden');
    speedDisplay.classList.remove('hidden');
    
    if (save) {
        const speed = parseInt(speedInput.value);
        if (!isNaN(speed) && speed >= 1 && speed <= 5000) {
            try {
                const response = await fetch('/set_speed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ speed: speed })
                });
                const data = await response.json();
                if (data.success) {
                    speedDisplay.textContent = speed;
                    showStatusMessage(`Speed set to ${speed} mm/s`, 'success');
                } else {
                    throw new Error(data.detail || 'Failed to set speed');
                }
            } catch (error) {
                console.error('Error setting speed:', error);
                showStatusMessage('Failed to set speed', 'error');
            }
        } else {
            showStatusMessage('Please enter a valid speed (1-5000)', 'error');
        }
    }
}

// Helper function to clean up pattern names
function getCleanPatternName(filePath) {
    if (!filePath) return '';
    const fileName = normalizeFilePath(filePath);
    return fileName.split('/').pop().replace('.thr', '');
}

// Sync modal controls with player status
function syncModalControls(status) {
    // Pattern name - clean up to show only filename
    const modalPatternName = document.getElementById('modal-pattern-name');
    if (modalPatternName && status.current_file) {
        modalPatternName.textContent = getCleanPatternName(status.current_file);
    }
    
    // Pattern preview image
    const modalPatternPreviewImg = document.getElementById('modal-pattern-preview-img');
    if (modalPatternPreviewImg && status.current_file) {
        const encodedFilename = normalizeFilePath(status.current_file).replace(/[\\/]/g, '--');
        const previewUrl = `/preview/${encodedFilename}`;
        modalPatternPreviewImg.src = previewUrl;
    }
    
    // ETA or Pause Countdown
    const modalEta = document.getElementById('modal-eta');
    if (modalEta) {
        // Check if we're in a pause between patterns
        if (status.pause_time_remaining && status.pause_time_remaining > 0) {
            const minutes = Math.floor(status.pause_time_remaining / 60);
            const seconds = Math.floor(status.pause_time_remaining % 60);
            modalEta.textContent = `Next in: ${minutes}:${seconds.toString().padStart(2, '0')}`;
        } else if (status.progress && status.progress.remaining_time !== null) {
            const minutes = Math.floor(status.progress.remaining_time / 60);
            const seconds = Math.floor(status.progress.remaining_time % 60);
            modalEta.textContent = `ETA: ${minutes}:${seconds.toString().padStart(2, '0')}`;
        } else {
            modalEta.textContent = 'ETA: calculating...';
        }
    }
    
    // Progress bar
    const modalProgressBar = document.getElementById('modal-progress-bar');
    if (modalProgressBar) {
        if (status.progress && status.progress.percentage !== null) {
            modalProgressBar.style.width = `${status.progress.percentage}%`;
        } else {
            modalProgressBar.style.width = '0%';
        }
    }
    
    // Next pattern - clean up to show only filename
    const modalNextPattern = document.getElementById('modal-next-pattern');
    if (modalNextPattern) {
        if (status.playlist && status.playlist.next_file) {
            modalNextPattern.textContent = getCleanPatternName(status.playlist.next_file);
        } else {
            modalNextPattern.textContent = 'None';
        }
    }
    
    // Pause button
    const modalPauseBtn = document.getElementById('modal-pause-button');
    if (modalPauseBtn) {
        const pauseIcon = modalPauseBtn.querySelector('.material-icons');
        if (status.is_paused) {
            pauseIcon.textContent = 'play_arrow';
        } else {
            pauseIcon.textContent = 'pause';
        }
    }
    
    // Skip button visibility
    const modalSkipBtn = document.getElementById('modal-skip-button');
    if (modalSkipBtn) {
        if (status.playlist && status.playlist.next_file) {
            modalSkipBtn.classList.remove('invisible');
        } else {
            modalSkipBtn.classList.add('invisible');
        }
    }
    
    // Speed display
    const modalSpeedDisplay = document.getElementById('modal-speed-display');
    if (modalSpeedDisplay && status.speed && !isEditingSpeed) {
        modalSpeedDisplay.textContent = status.speed;
    }
}

// Toggle modal visibility
function togglePreviewModal() {
    const modal = document.getElementById('playerPreviewModal');
    const toggleBtn = document.getElementById('toggle-preview-modal-btn');
    
    if (!modal || !toggleBtn) return;
    
    const isHidden = modal.classList.contains('hidden');
    if (isHidden) {
        openPlayerPreviewModal();
    } else {
        setModalVisibility(false, true);
        toggleBtn.classList.remove('active-tab');
        toggleBtn.classList.add('inactive-tab');
    }
}

// Button event handlers
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Initialize WebSocket connection
        initializeWebSocket();
        
        // Setup player preview modal events
        setupPlayerPreviewModalEvents();
        
        console.log('Player initialized successfully');
    } catch (error) {
        console.error(`Error during initialization: ${error.message}`);
    }
});

// Initialize WebSocket connection
function initializeWebSocket() {
    connectWebSocket();
}

// Clean up WebSocket when page unloads to prevent memory leaks
window.addEventListener('beforeunload', () => {
    if (ws) {
        // Disable reconnection before closing
        ws.onclose = null;
        ws.close();
        ws = null;
    }
});

// Add resize handler for responsive canvas with debouncing
let resizeTimeout;
window.addEventListener('resize', () => {
    const canvas = document.getElementById('playerPreviewCanvas');
    const modal = document.getElementById('playerPreviewModal');
    
    if (canvas && modal && !modal.classList.contains('hidden')) {
        // Clear previous timeout
        clearTimeout(resizeTimeout);
        
        // Debounce resize calls to avoid excessive updates
        resizeTimeout = setTimeout(() => {
            const ctx = canvas.getContext('2d');
            setupPlayerPreviewCanvas(ctx);
            drawPlayerPreview(ctx, targetProgress);
        }, 16); // ~60fps update rate
    }
});

// Handle file changes and reload preview data
function handleFileChange(newFile) {
    if (newFile !== currentPreviewFile) {
        currentPreviewFile = newFile;
        if (newFile) {
            loadPlayerPreviewData(`./patterns/${newFile}`);
        } else {
            playerPreviewData = null;
        }
    }
}

// Cache All Previews Prompt functionality
let cacheAllInProgress = false;

function shouldShowCacheAllPrompt() {
    // Check if we've already shown the prompt
    const promptShown = localStorage.getItem('cacheAllPromptShown');
    console.log('shouldShowCacheAllPrompt - promptShown:', promptShown);
    return !promptShown;
}

function showCacheAllPrompt(forceShow = false) {
    console.log('showCacheAllPrompt called, forceShow:', forceShow);
    if (!forceShow && !shouldShowCacheAllPrompt()) {
        console.log('Cache all prompt already shown, skipping');
        return;
    }
    
    const modal = document.getElementById('cacheAllPromptModal');
    if (modal) {
        console.log('Showing cache all prompt modal');
        modal.classList.remove('hidden');
        // Store whether this was forced (manually triggered)
        modal.dataset.manuallyTriggered = forceShow.toString();
    } else {
        console.log('Cache all prompt modal not found');
    }
}

function hideCacheAllPrompt() {
    const modal = document.getElementById('cacheAllPromptModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

function markCacheAllPromptAsShown() {
    localStorage.setItem('cacheAllPromptShown', 'true');
}

function initializeCacheAllPrompt() {
    const modal = document.getElementById('cacheAllPromptModal');
    const skipBtn = document.getElementById('skipCacheAllBtn');
    const startBtn = document.getElementById('startCacheAllBtn');
    const closeBtn = document.getElementById('closeCacheAllBtn');
    
    if (!modal || !skipBtn || !startBtn || !closeBtn) {
        return;
    }

    // Skip button handler
    skipBtn.addEventListener('click', () => {
        const wasManuallyTriggered = modal.dataset.manuallyTriggered === 'true';
        hideCacheAllPrompt();
        
        // Only mark as shown if it was automatically shown (not manually triggered)
        if (!wasManuallyTriggered) {
            markCacheAllPromptAsShown();
        }
    });

    // Close button handler (after completion)
    closeBtn.addEventListener('click', () => {
        const wasManuallyTriggered = modal.dataset.manuallyTriggered === 'true';
        hideCacheAllPrompt();
        
        // Always mark as shown after successful completion
        if (!wasManuallyTriggered) {
            markCacheAllPromptAsShown();
        }
    });

    // Start caching button handler
    startBtn.addEventListener('click', async () => {
        if (cacheAllInProgress) {
            return;
        }

        cacheAllInProgress = true;
        
        // Hide buttons and show progress
        document.getElementById('cacheAllButtons').classList.add('hidden');
        document.getElementById('cacheAllProgress').classList.remove('hidden');

        try {
            await startCacheAllProcess();
            
            // Show completion message
            document.getElementById('cacheAllProgress').classList.add('hidden');
            document.getElementById('cacheAllComplete').classList.remove('hidden');
        } catch (error) {
            console.error('Error caching all previews:', error);
            
            // Show error and reset
            document.getElementById('cacheAllProgressText').textContent = 'Error occurred during caching';
            setTimeout(() => {
                hideCacheAllPrompt();
                markCacheAllPromptAsShown();
            }, 3000);
        } finally {
            cacheAllInProgress = false;
        }
    });
}

async function startCacheAllProcess() {
    try {
        // Get list of patterns using cached function
        const patterns = await getCachedPatternFiles();
        
        if (!patterns || patterns.length === 0) {
            throw new Error('No patterns found');
        }

        const progressBar = document.getElementById('cacheAllProgressBar');
        const progressText = document.getElementById('cacheAllProgressText');
        const progressPercentage = document.getElementById('cacheAllProgressPercentage');
        
        let completed = 0;
        const batchSize = 5; // Process in small batches to avoid overwhelming the server

        for (let i = 0; i < patterns.length; i += batchSize) {
            const batch = patterns.slice(i, i + batchSize);
            
            // Update progress text
            progressText.textContent = `Caching previews... (${Math.min(i + batchSize, patterns.length)}/${patterns.length})`;
            
            // Process batch
            const batchPromises = batch.map(async (pattern) => {
                try {
                    const previewResponse = await fetch('/preview_thr', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ file_name: pattern })
                    });
                    
                    if (previewResponse.ok) {
                        const data = await previewResponse.json();
                        if (data.preview_url) {
                            // Pre-load the image to cache it
                            return new Promise((resolve) => {
                                const img = new Image();
                                img.onload = () => resolve();
                                img.onerror = () => resolve(); // Continue even if image fails
                                img.src = data.preview_url;
                            });
                        }
                    }
                    return Promise.resolve();
                } catch (error) {
                    console.warn(`Failed to cache preview for ${pattern}:`, error);
                    return Promise.resolve(); // Continue with other patterns
                }
            });

            await Promise.all(batchPromises);
            completed += batch.length;

            // Update progress bar
            const progress = Math.round((completed / patterns.length) * 100);
            progressBar.style.width = `${progress}%`;
            progressPercentage.textContent = `${progress}%`;

            // Small delay between batches to prevent overwhelming the server
            if (i + batchSize < patterns.length) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }

        progressText.textContent = `Completed! Cached ${patterns.length} previews.`;
        
    } catch (error) {
        throw error;
    }
}

// Function to be called after initial cache generation completes
function onInitialCacheComplete() {
    console.log('onInitialCacheComplete called');
    // Show the cache all prompt after a short delay
    setTimeout(() => {
        console.log('Triggering cache all prompt after delay');
        showCacheAllPrompt();
    }, 1000);
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    initializeCacheAllPrompt();
});

// Make functions available globally for debugging
window.onInitialCacheComplete = onInitialCacheComplete;
window.showCacheAllPrompt = showCacheAllPrompt;
window.testCacheAllPrompt = function() {
    console.log('Manual test trigger');
    // Clear localStorage for testing
    localStorage.removeItem('cacheAllPromptShown');
    showCacheAllPrompt();
}; 