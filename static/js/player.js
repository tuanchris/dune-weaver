// Player status bar functionality
let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000; // 3 seconds

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

    if (status.current_file && status.is_running) {
        // Show the player bar
        playerBar.classList.remove('hidden');
        
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
        // Hide the player bar
        playerBar.classList.add('hidden');
    }
}

// Button event handlers
document.addEventListener('DOMContentLoaded', function() {
    const pauseButton = document.getElementById('player-pause-button');
    const skipButton = document.getElementById('player-skip-button');
    const stopButton = document.getElementById('player-stop-button');

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

    // Connect to WebSocket
    connectWebSocket();
}); 