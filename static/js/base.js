// Player status bar functionality - Updated to fix logMessage errors
let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000; // 3 seconds
let isEditingSpeed = false; // Track if user is editing speed
let playerBarVisible = true; // Track player bar visibility
let playerPreviewData = null; // Store the current pattern's preview data
let playerPreviewCtx = null; // Store the canvas context for player preview

// Utility: Save/restore player bar visibility
function savePlayerBarVisibility(visible) {
    try {
        localStorage.setItem('playerBarVisible', visible ? '1' : '0');
    } catch (e) {}
}
function loadPlayerBarVisibility() {
    try {
        return localStorage.getItem('playerBarVisible') === '0' ? false : true;
    } catch (e) { return true; }
}

function setPlayerBarVisibility(visible, force = false) {
    const playerBar = document.getElementById('player-status-bar-container');
    const toggleBtn = document.getElementById('toggle-player-bar-btn');
    if (!playerBar || !toggleBtn) return;
    
    playerBarVisible = visible;
    savePlayerBarVisibility(visible);
    
    // Show/hide bar based on visibility setting and whether something is playing
    const isPlaying = playerBar.dataset.isPlaying === '1';
    
    if (isPlaying) {
        // If something is playing, respect the visibility setting
        playerBar.style.display = visible ? '' : 'none';
        toggleBtn.style.display = 'flex'; // Always show toggle if playing
    } else {
        // If nothing is playing, hide the bar but still show toggle for testing
        playerBar.style.display = 'none';
        toggleBtn.style.display = force ? 'flex' : 'none'; // Show toggle only on force (initial load)
    }
    
    // Change icon
    const toggleIcon = document.getElementById('toggle-player-bar-icon');
    if (toggleIcon) toggleIcon.textContent = visible ? 'expand_more' : 'expand_less';
}

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
                // Update player status with the full data
                updatePlayerStatus(data.data);
                
                // Update speed input field on table control page if it exists
                if (data.data && data.data.speed) {
                    const currentSpeedDisplay = document.getElementById('currentSpeedDisplay');
                    if (currentSpeedDisplay) {
                        currentSpeedDisplay.textContent = `${data.data.speed} mm/s`;
                    }
                    
                    // Update player speed display only if not currently editing
                    if (!isEditingSpeed) {
                        const playerSpeedDisplay = document.getElementById('player-speed-display');
                        if (playerSpeedDisplay) {
                            playerSpeedDisplay.textContent = data.data.speed;
                        }
                    }
                }
                
                // Update connection status dot using 'connection_status' or fallback to 'connected'
                if (data.data.hasOwnProperty('connection_status')) {
                    updateConnectionStatus(data.data.connection_status);
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
        // Do not update status message
    }
}

// Setup player preview canvas
function setupPlayerPreviewCanvas() {
    const previewContainer = document.getElementById('player-pattern-preview');
    if (!previewContainer) return;

    // Remove any existing canvas
    const existingCanvas = previewContainer.querySelector('canvas');
    if (existingCanvas) existingCanvas.remove();

    // Create and setup canvas
    const canvas = document.createElement('canvas');
    canvas.className = 'w-full h-full rounded-full';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    
    // Set high-DPI canvas size
    const size = 800;
    canvas.width = size * (window.devicePixelRatio || 1) * 2;
    canvas.height = size * (window.devicePixelRatio || 1) * 2;
    
    // Get context and store it
    playerPreviewCtx = canvas.getContext('2d');
    
    // Clear container and add canvas
    previewContainer.innerHTML = '';
    previewContainer.appendChild(canvas);
    
    // Setup initial canvas state
    if (playerPreviewCtx) {
        const pixelRatio = (window.devicePixelRatio || 1) * 2;
        playerPreviewCtx.scale(pixelRatio, pixelRatio);
        playerPreviewCtx.translate(size/2, size/2);
        playerPreviewCtx.rotate(-Math.PI);
        playerPreviewCtx.translate(-size/2, -size/2);
    }
}

// Draw player preview
function drawPlayerPreview(progress) {
    if (!playerPreviewCtx || !playerPreviewData || playerPreviewData.length === 0) return;
    
    const canvas = playerPreviewCtx.canvas;
    const pixelRatio = (window.devicePixelRatio || 1) * 2;
    const displayWidth = parseInt(canvas.style.width);
    const displayHeight = parseInt(canvas.style.height);
    const center = (canvas.width / pixelRatio) / 2;
    const scale = ((canvas.width / pixelRatio) / 2) - 30;
    
    // Clear canvas with white background
    playerPreviewCtx.fillStyle = '#ffffff';
    playerPreviewCtx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Calculate how many points to draw
    const totalPoints = playerPreviewData.length;
    const pointsToDraw = Math.floor(totalPoints * progress);
    
    if (pointsToDraw < 2) return;
    
    // Draw the pattern
    playerPreviewCtx.beginPath();
    playerPreviewCtx.strokeStyle = '#000000';
    playerPreviewCtx.lineWidth = 0.75;
    playerPreviewCtx.lineCap = 'round';
    playerPreviewCtx.lineJoin = 'round';
    
    // Enable high quality rendering
    playerPreviewCtx.imageSmoothingEnabled = true;
    playerPreviewCtx.imageSmoothingQuality = 'high';
    
    // Draw pattern lines
    for (let i = 0; i < pointsToDraw - 1; i++) {
        const [theta1, rho1] = playerPreviewData[i];
        const [theta2, rho2] = playerPreviewData[i + 1];
        
        const x1 = center + rho1 * scale * Math.cos(theta1);
        const y1 = center + rho1 * scale * Math.sin(theta1);
        const x2 = center + rho2 * scale * Math.cos(theta2);
        const y2 = center + rho2 * scale * Math.sin(theta2);
        
        if (i === 0) {
            playerPreviewCtx.moveTo(x1, y1);
        }
        playerPreviewCtx.lineTo(x2, y2);
    }
    playerPreviewCtx.stroke();
    
    // Draw current position dot
    if (pointsToDraw > 0) {
        const [theta, rho] = playerPreviewData[pointsToDraw - 1];
        const x = center + rho * scale * Math.cos(theta);
        const y = center + rho * scale * Math.sin(theta);
        
        // Draw white border
        playerPreviewCtx.beginPath();
        playerPreviewCtx.fillStyle = '#ffffff';
        playerPreviewCtx.arc(x, y, 7.5, 0, Math.PI * 2);
        playerPreviewCtx.fill();
        
        // Draw red dot
        playerPreviewCtx.beginPath();
        playerPreviewCtx.fillStyle = '#ff0000';
        playerPreviewCtx.arc(x, y, 6, 0, Math.PI * 2);
        playerPreviewCtx.fill();
    }
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
        
        // Setup canvas if needed
        setupPlayerPreviewCanvas();
        
        // Draw initial state
        drawPlayerPreview(0);
        
    } catch (error) {
        console.error(`Error loading player preview data: ${error.message}`);
        playerPreviewData = null;
    }
}

function updatePlayerStatus(status) {
    const playerBar = document.getElementById('player-status-bar-container');
    const patternName = document.getElementById('player-pattern-name');
    const patternPreview = document.getElementById('player-pattern-preview');
    const eta = document.getElementById('player-eta');
    const nextPattern = document.getElementById('player-next-pattern');
    const pauseButton = document.getElementById('player-pause-button');
    const skipButton = document.getElementById('player-skip-button');
    const stopButton = document.getElementById('player-stop-button');
    const progressBar = document.getElementById('player-progress-bar');
    const toggleBtn = document.getElementById('toggle-player-bar-btn');

    if (status.current_file && status.is_running) {
        // Mark as playing
        if (playerBar) playerBar.dataset.isPlaying = '1';
        // Show/hide bar based on toggle state
        setPlayerBarVisibility(loadPlayerBarVisibility());
        
        // Update pattern name
        const fileName = status.current_file.replace('./patterns/', '');
        patternName.textContent = fileName.replace('.thr', '');

        // Update pattern preview
        if (!playerPreviewData) {
            // Load preview data if not loaded
            loadPlayerPreviewData(status.current_file);
        }
        
        // Update preview animation if we have data
        if (playerPreviewData && status.progress && status.progress.percentage !== null) {
            drawPlayerPreview(status.progress.percentage / 100);
        }

        // Update ETA
        if (status.progress && status.progress.remaining_time !== null) {
            const minutes = Math.floor(status.progress.remaining_time / 60);
            const seconds = Math.floor(status.progress.remaining_time % 60);
            eta.textContent = `ETA: ${minutes}:${seconds.toString().padStart(2, '0')}`;
        } else {
            eta.textContent = 'ETA: calculating...';
        }

        // Update progress bar
        if (status.progress && status.progress.percentage !== null) {
            progressBar.style.width = `${status.progress.percentage}%`;
        } else {
            progressBar.style.width = '0%';
        }

        // Update next pattern
        if (status.playlist && status.playlist.next_file) {
            const nextFileName = status.playlist.next_file.replace('./patterns/', '').replace('.thr', '');
            nextPattern.textContent = nextFileName;
        } else {
            nextPattern.textContent = 'None';
        }

        // Update pause button
        const pauseIcon = pauseButton.querySelector('.material-icons');
        if (status.is_paused) {
            pauseIcon.textContent = 'play_arrow';
        } else {
            pauseIcon.textContent = 'pause';
        }

        // Show/hide skip button based on playlist status
        if (status.playlist && status.playlist.next_file) {
            skipButton.classList.remove('invisible');
        } else {
            skipButton.classList.add('invisible');
        }

        // Handle pause time remaining
        if (status.pause_time_remaining && status.pause_time_remaining > 0) {
            patternName.textContent = 'Pausing...';
            // Show ETA as pause countdown in 0:00 format
            if (eta) {
                const mins = Math.floor(status.pause_time_remaining / 60);
                const secs = Math.ceil(status.pause_time_remaining % 60);
                eta.textContent = `ETA: ${mins}:${secs.toString().padStart(2, '0')}`;
            }
            // Show preview and name of next pattern if available
            if (status.playlist && status.playlist.next_file) {
                const nextFileName = status.playlist.next_file.replace('./patterns/', '').replace('.thr', '');
                // Update preview image
                const encodedFilename = status.playlist.next_file.replace('./patterns/', '').replace(/\//g, '--');
                if (patternPreview) {
                    patternPreview.style.backgroundImage = `url('/preview/${encodedFilename}')`;
                }
                // Update pattern name below preview (if you have such an element)
                // patternName.textContent = nextFileName; // Uncomment if you want to show next pattern name
            }
            // Show progress bar as pause countdown
            const totalPause = status.original_pause_time || status.pause_time_remaining;
            const percent = totalPause
                ? ((totalPause - status.pause_time_remaining) / totalPause) * 100
                : 100;
            progressBar.style.width = `${percent}%`;
            progressBar.style.backgroundColor = '#fbbf24'; // amber-400 for pause
        } else {
            if (progressBar) progressBar.style.backgroundColor = '';
        }
    } else {
        // Mark as not playing
        if (playerBar) playerBar.dataset.isPlaying = '0';
        // Hide both bar and toggle button
        setPlayerBarVisibility(false);
        // Clear preview data
        playerPreviewData = null;
        playerPreviewCtx = null;
    }
}

// Button event handlers
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Initialize WebSocket connection
        initializeWebSocket();
        
        // Restore player bar visibility
        restorePlayerBarVisibility();
        
        console.log('Player initialized successfully');
    } catch (error) {
        console.error(`Error during initialization: ${error.message}`);
    }
});

// Initialize WebSocket connection
function initializeWebSocket() {
    connectWebSocket();
}

// Restore player bar visibility
function restorePlayerBarVisibility() {
    setPlayerBarVisibility(loadPlayerBarVisibility());
}

// Button event handlers
document.addEventListener('DOMContentLoaded', function() {
    const pauseButton = document.getElementById('player-pause-button');
    const skipButton = document.getElementById('player-skip-button');
    const stopButton = document.getElementById('player-stop-button');
    const speedContainer = document.getElementById('player-speed-container');
    const speedDisplay = document.getElementById('player-speed-display');
    const speedInput = document.getElementById('player-speed-input');

    pauseButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/pause_execution', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.detail || 'Failed to toggle pause');
            }
        } catch (error) {
            console.error('Error toggling pause:', error);
        }
    });

    skipButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/skip_pattern', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.detail || 'Failed to skip pattern');
            }
        } catch (error) {
            console.error('Error skipping pattern:', error);
        }
    });

    stopButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/stop_execution', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.detail || 'Failed to stop execution');
            }
        } catch (error) {
            console.error('Error stopping execution:', error);
        }
    });

    // Combined speed display/input functionality
    function enterEditMode() {
        if (!speedDisplay || !speedInput) return;
        
        isEditingSpeed = true;
        const currentValue = speedDisplay.textContent;
        
        // Set input value to current speed (if it's a number)
        if (currentValue !== '--' && !isNaN(parseInt(currentValue))) {
            speedInput.value = currentValue;
        } else {
            speedInput.value = '';
        }
        
        // Switch to edit mode
        speedDisplay.classList.add('hidden');
        speedInput.classList.remove('hidden');
        speedInput.focus();
        speedInput.select(); // Select all text for easy replacement
    }

    function exitEditMode(save = false) {
        if (!speedDisplay || !speedInput) return;
        
        if (save) {
            setSpeed();
        }
        
        isEditingSpeed = false;
        speedInput.classList.add('hidden');
        speedDisplay.classList.remove('hidden');
        speedInput.value = '';
    }

    async function setSpeed() {
        const speed = parseInt(speedInput.value);
        if (isNaN(speed) || speed < 1 || speed > 5000) {
            showStatusMessage('Please enter a valid speed (1-5000)', 'error');
            return;
        }

        try {
            const response = await fetch('/set_speed', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ speed: speed })
            });
            const data = await response.json();
            if (data.success) {
                showStatusMessage(`Speed set to ${speed} mm/s`, 'success');
                // Update display immediately
                speedDisplay.textContent = speed;
            } else {
                throw new Error(data.detail || 'Failed to set speed');
            }
        } catch (error) {
            console.error('Error setting speed:', error);
            showStatusMessage('Failed to set speed', 'error');
        }
    }

    // Speed display click to edit
    if (speedDisplay) {
        speedDisplay.addEventListener('click', enterEditMode);
    }

    // Speed input event handlers
    if (speedInput) {
        // Enter key to save
        speedInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                exitEditMode(true);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                exitEditMode(false);
            }
        });

        // Blur to save (when clicking away)
        speedInput.addEventListener('blur', () => {
            exitEditMode(true);
        });
    }

    // Player bar toggle logic
    const playerBar = document.getElementById('player-status-bar-container');
    const toggleBtn = document.getElementById('toggle-player-bar-btn');
    const toggleIcon = document.getElementById('toggle-player-bar-icon');
    if (playerBar && toggleBtn) {
        // Restore state
        playerBarVisible = loadPlayerBarVisibility();
        setPlayerBarVisibility(playerBarVisible, true);
        // Toggle button click
        toggleBtn.addEventListener('click', () => {
            playerBarVisible = !playerBarVisible;
            setPlayerBarVisibility(playerBarVisible);
        });
    }
}); 