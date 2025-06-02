// Player status bar functionality
let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000; // 3 seconds
let isEditingSpeed = false; // Track if user is editing speed
let playerBarVisible = true; // Track player bar visibility

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
    // Only show/hide bar if something is playing (force = true for initial load)
    if (playerBar.dataset.isPlaying === '1' || force) {
        playerBar.style.display = visible ? '' : 'none';
        toggleBtn.style.display = visible ? 'flex' : 'flex'; // Always show toggle if playing
        // Change icon
        const toggleIcon = document.getElementById('toggle-player-bar-icon');
        if (toggleIcon) toggleIcon.textContent = visible ? 'expand_more' : 'expand_less';
    } else {
        playerBar.style.display = 'none';
        toggleBtn.style.display = 'none';
    }
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
                
                // Only update connection status if the data includes connection information
                if (data.data.hasOwnProperty('connected')) {
                    console.log('Connection status from data:', data.data.connected);
                    updateConnectionStatus(data.data.connected);
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
        const wasConnected = statusDot.classList.contains("bg-green-500");
        
        // Update dot color
        statusDot.className = `inline-block size-2 rounded-full ml-2 align-middle ${
            isConnected ? "bg-green-500" : "bg-red-500"
        }`;

        // Show status message if connection state changed
        if (wasConnected !== isConnected) {
            if (isConnected) {
                showStatusMessage("Serial connection established", "success");
            } else {
                showStatusMessage("Serial connection lost", "error");
            }
        }
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
        const encodedFilename = fileName.replace(/\//g, '--');
        patternPreview.style.backgroundImage = `url('/preview/${encodedFilename}')`;

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
    } else {
        // Mark as not playing
        if (playerBar) playerBar.dataset.isPlaying = '0';
        // Hide both bar and toggle button
        setPlayerBarVisibility(false);
    }
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

    // Connect to WebSocket
    connectWebSocket();
}); 