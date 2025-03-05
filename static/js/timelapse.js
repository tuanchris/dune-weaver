/**
 * Timelapse functionality for Dune Weaver Controller
 */

// Global variables
let selectedSession = null;
let timelapseStatus = {
    is_capturing: false,
    current_session: null,
    interval: 5,
    auto_mode: false,
    selected_camera: null,
    available_cameras: []
};
let lastCameraSelection = null; // Track the last camera selection
let statusUpdateTimer = null; // Timer for status updates

// Initialize timelapse functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize timelapse UI
    initTimelapseUI();
    
    // Attach fullscreen listener to timelapse container
    attachFullscreenListenerToTimelapse();
    
    // Load initial status
    refreshTimelapseStatus();
    
    // Load available cameras without pre-initializing
    refreshCameras(false);
    
    // Load timelapse sessions
    loadTimelapsesSessions();
    
    // Set up periodic status refresh with a slower interval to prevent camera selection issues
    statusUpdateTimer = setInterval(refreshTimelapseStatus, 10000); // 10 seconds
    
    // When the timelapse container is shown, refresh data
    const timelapseContainer = document.getElementById('timelapse-container');
    if (timelapseContainer) {
        // Use MutationObserver to detect when the container becomes visible
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'class') {
                    const isHidden = timelapseContainer.classList.contains('hidden');
                    if (!isHidden) {
                        // Container is now visible, refresh data with pre-initialization
                        refreshCameras(true);
                        loadTimelapsesSessions();
                    }
                }
            });
        });
        
        observer.observe(timelapseContainer, { attributes: true });
    }
    
    // Add event listener for camera selection change to pre-initialize the camera
    const cameraSelect = document.getElementById('timelapse-camera');
    if (cameraSelect) {
        cameraSelect.addEventListener('change', function() {
            const selectedCamera = cameraSelect.value;
            if (selectedCamera) {
                // Pre-initialize the selected camera
                preInitializeCamera(selectedCamera);
                // Save the selection to localStorage
                localStorage.setItem('selectedCamera', selectedCamera);
                lastCameraSelection = selectedCamera;
            }
        });
    }
});

/**
 * Initialize the timelapse UI
 */
function initTimelapseUI() {
    // Ensure the timelapse container has the fullscreen class when initialized
    const container = document.getElementById('timelapse-container');
    if (container) {
        // Make sure it's hidden initially but has the fullscreen class
        container.classList.add('hidden');
        container.classList.add('fullscreen');
    }
    
    // Set up event listeners for timelapse preview image
    const previewImage = document.getElementById('timelapse-preview-image');
    previewImage.addEventListener('load', function() {
        previewImage.style.display = 'block';
    });
    
    previewImage.addEventListener('error', function() {
        previewImage.style.display = 'none';
    });
    
    // Add event listener for auto mode checkbox
    const autoModeCheckbox = document.getElementById('timelapse-auto-mode');
    autoModeCheckbox.addEventListener('change', updateAutoMode);
    
    // Add event listener for test capture button
    const testCaptureButton = document.getElementById('timelapse-test-capture');
    if (testCaptureButton) {
        testCaptureButton.addEventListener('click', testCameraCapture);
    }
    
    // Load saved settings from localStorage
    const savedAutoMode = localStorage.getItem('timelapseAutoMode');
    if (savedAutoMode !== null) {
        autoModeCheckbox.checked = savedAutoMode === 'true';
        // Update the server with the saved setting
        updateAutoMode();
    }
    
    // Set up camera adjustment controls
    setupCameraAdjustments();
}

/**
 * Set up camera adjustment controls
 */
function setupCameraAdjustments() {
    // Toggle camera adjustment controls
    const toggleButton = document.getElementById('toggle-camera-adjustments');
    const adjustmentControls = document.getElementById('camera-adjustment-controls');
    
    if (toggleButton && adjustmentControls) {
        toggleButton.addEventListener('click', function() {
            adjustmentControls.classList.toggle('hidden');
        });
    }
    
    // Set up range input event listeners
    setupRangeInput('camera-brightness', 'brightness-value');
    setupRangeInput('camera-contrast', 'contrast-value');
    setupRangeInput('camera-exposure', 'exposure-value');
    
    // Load saved camera settings from localStorage
    loadCameraSettings();
    
    // Apply camera settings button
    const applyButton = document.getElementById('apply-camera-settings');
    if (applyButton) {
        applyButton.addEventListener('click', applyCameraSettings);
    }
    
    // Reset camera settings button
    const resetButton = document.getElementById('reset-camera-settings');
    if (resetButton) {
        resetButton.addEventListener('click', resetCameraSettings);
    }
    
    // Test camera settings button
    const testButton = document.getElementById('test-camera-settings');
    if (testButton) {
        testButton.addEventListener('click', testCameraCapture);
    }
}

/**
 * Set up a range input with live value display
 */
function setupRangeInput(inputId, valueId) {
    const input = document.getElementById(inputId);
    const valueDisplay = document.getElementById(valueId);
    
    if (input && valueDisplay) {
        // Update value display on input change
        input.addEventListener('input', function() {
            valueDisplay.textContent = input.value;
        });
        
        // Load saved value from localStorage
        const savedValue = localStorage.getItem(inputId);
        if (savedValue !== null) {
            input.value = savedValue;
            valueDisplay.textContent = savedValue;
        }
    }
}

/**
 * Load camera settings from localStorage
 */
function loadCameraSettings() {
    const brightnessInput = document.getElementById('camera-brightness');
    const contrastInput = document.getElementById('camera-contrast');
    const exposureInput = document.getElementById('camera-exposure');
    
    // Load saved values
    const savedBrightness = localStorage.getItem('camera-brightness');
    const savedContrast = localStorage.getItem('camera-contrast');
    const savedExposure = localStorage.getItem('camera-exposure');
    
    // Apply saved values if they exist
    if (savedBrightness !== null && brightnessInput) {
        brightnessInput.value = savedBrightness;
        document.getElementById('brightness-value').textContent = savedBrightness;
    }
    
    if (savedContrast !== null && contrastInput) {
        contrastInput.value = savedContrast;
        document.getElementById('contrast-value').textContent = savedContrast;
    }
    
    if (savedExposure !== null && exposureInput) {
        exposureInput.value = savedExposure;
        document.getElementById('exposure-value').textContent = savedExposure;
    }
}

/**
 * Apply camera settings
 */
async function applyCameraSettings() {
    const brightness = document.getElementById('camera-brightness').value;
    const contrast = document.getElementById('camera-contrast').value;
    const exposure = document.getElementById('camera-exposure').value;
    
    // Log the values being sent
    console.log(`Applying camera settings - brightness: ${brightness}, contrast: ${contrast}, exposure: ${exposure}`);
    
    // Save settings to localStorage
    localStorage.setItem('camera-brightness', brightness);
    localStorage.setItem('camera-contrast', contrast);
    localStorage.setItem('camera-exposure', exposure);
    
    try {
        // Send settings to server
        const response = await fetch('/timelapse/update_camera_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                brightness: parseFloat(brightness),
                contrast: parseFloat(contrast),
                exposure: parseFloat(exposure)
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage('Camera settings updated', LOG_TYPE.SUCCESS);
        } else {
            logMessage(`Failed to update camera settings: ${data.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error updating camera settings: ${error.message}`, LOG_TYPE.ERROR);
    }
}

/**
 * Reset camera settings to defaults
 */
function resetCameraSettings() {
    // Default values - using neutral values to enable auto mode
    const defaultBrightness = 0.5;  // Changed from 0.4 to 0.5 as neutral value
    const defaultContrast = 1.0;    // Changed from 1.2 to 1.0 as neutral value
    const defaultExposure = 0.5;    // Changed from 0.1 to 0.5 as neutral value
    
    // Reset input values
    const brightnessInput = document.getElementById('camera-brightness');
    const contrastInput = document.getElementById('camera-contrast');
    const exposureInput = document.getElementById('camera-exposure');
    
    brightnessInput.value = defaultBrightness;
    contrastInput.value = defaultContrast;
    exposureInput.value = defaultExposure;
    
    // Reset value displays
    document.getElementById('brightness-value').textContent = defaultBrightness;
    document.getElementById('contrast-value').textContent = defaultContrast;
    document.getElementById('exposure-value').textContent = defaultExposure;
    
    // Apply the reset settings
    applyCameraSettings();
}

/**
 * Test camera capture
 */
async function testCameraCapture() {
    const cameraSelect = document.getElementById('timelapse-camera');
    const camera = cameraSelect.value;
    
    if (!camera) {
        logMessage('No camera selected', LOG_TYPE.ERROR);
        return;
    }
    
    // Get UI elements
    const refreshButton = cameraSelect.nextElementSibling; // The refresh button next to the select
    const testCaptureButton = document.getElementById('timelapse-test-capture');
    
    try {
        // Show loading indicator
        const loadingIndicator = document.getElementById('timelapse-loading');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'flex';
            
            // Update loading message
            const loadingMessage = loadingIndicator.querySelector('span');
            if (loadingMessage) {
                loadingMessage.textContent = 'Capturing test image...';
            }
        }
        
        // Disable camera controls during capture
        if (cameraSelect) cameraSelect.disabled = true;
        if (refreshButton) refreshButton.disabled = true;
        if (testCaptureButton) testCaptureButton.disabled = true;
        
        const response = await fetch('/timelapse/test_capture', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                camera
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage('Test capture successful', LOG_TYPE.SUCCESS);
            
            // Display the captured image from base64 data
            const previewImage = document.getElementById('timelapse-preview-image');
            previewImage.src = data.image_data; // Use the base64 data directly
            previewImage.style.display = 'block';
        } else {
            logMessage(`Test capture failed: ${data.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error during test capture: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator
        const loadingIndicator = document.getElementById('timelapse-loading');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
            
            // Reset loading message
            const loadingMessage = loadingIndicator.querySelector('span');
            if (loadingMessage) {
                loadingMessage.textContent = 'Processing...';
            }
        }
        
        // Re-enable camera controls
        if (cameraSelect) cameraSelect.disabled = false;
        if (refreshButton) refreshButton.disabled = false;
        if (testCaptureButton) testCaptureButton.disabled = false;
    }
}

/**
 * Attach fullscreen listener to timelapse container
 */
function attachFullscreenListenerToTimelapse() {
    const container = document.getElementById('timelapse-container');
    if (!container) return;
    
    const fullscreenButton = container.querySelector('.fullscreen-button');
    if (!fullscreenButton) return;
    
    fullscreenButton.addEventListener('click', function() {
        container.classList.toggle('fullscreen');
    });
}

/**
 * Refresh the timelapse status
 */
async function refreshTimelapseStatus() {
    try {
        const response = await fetch('/timelapse/status');
        const data = await response.json();
        
        // Update global status but preserve camera selection
        const previousCamera = timelapseStatus.selected_camera;
        timelapseStatus = data;
        
        // If we have a last camera selection, prioritize it
        if (lastCameraSelection) {
            timelapseStatus.selected_camera = lastCameraSelection;
        } 
        // Otherwise, if we had a previous camera selection, keep it
        else if (previousCamera && (!timelapseStatus.selected_camera || timelapseStatus.selected_camera === '')) {
            timelapseStatus.selected_camera = previousCamera;
        }
        
        // Update UI
        updateTimelapseStatusUI();
    } catch (error) {
        console.error(`Error refreshing timelapse status: ${error.message}`);
        // Don't show error in log to avoid spamming
    }
}

/**
 * Update the timelapse status UI
 */
function updateTimelapseStatusUI() {
    const statusIndicator = document.getElementById('timelapse-status-indicator');
    const statusText = document.getElementById('timelapse-status-text');
    const startButton = document.getElementById('timelapse-start-button');
    const stopButton = document.getElementById('timelapse-stop-button');
    const autoModeCheckbox = document.getElementById('timelapse-auto-mode');
    const intervalInput = document.getElementById('timelapse-interval');
    const cameraSelect = document.getElementById('timelapse-camera');
    
    // Update status indicator and text
    if (timelapseStatus.is_capturing) {
        statusIndicator.classList.add('active');
        statusText.textContent = `Capturing (Session: ${timelapseStatus.current_session})`;
        startButton.disabled = true;
        stopButton.disabled = false;
    } else {
        statusIndicator.classList.remove('active');
        statusText.textContent = 'Not capturing';
        startButton.disabled = false;
        stopButton.disabled = true;
    }
    
    // Update auto mode checkbox
    autoModeCheckbox.checked = timelapseStatus.auto_mode;
    
    // Update interval input
    intervalInput.value = timelapseStatus.interval;
    
    // Only update camera select if it's empty or if the user hasn't made a selection
    if (cameraSelect && (!cameraSelect.value || cameraSelect.value === '') && timelapseStatus.selected_camera) {
        cameraSelect.value = timelapseStatus.selected_camera;
        lastCameraSelection = timelapseStatus.selected_camera;
    }
}

/**
 * Refresh the list of available cameras
 * @param {boolean} shouldPreInitialize - Whether to pre-initialize the camera after refresh (default: true)
 */
async function refreshCameras(shouldPreInitialize = true) {
    // Get UI elements
    const cameraSelect = document.getElementById('timelapse-camera');
    const refreshButton = cameraSelect.nextElementSibling; // The refresh button next to the select
    const testCaptureButton = document.getElementById('timelapse-test-capture');
    
    try {
        // Show loading indicator
        const loadingIndicator = document.getElementById('timelapse-loading');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'flex';
            
            // Update loading message
            const loadingMessage = loadingIndicator.querySelector('span');
            if (loadingMessage) {
                loadingMessage.textContent = 'Scanning for cameras...';
            }
        }
        
        // Disable camera controls during refresh
        if (cameraSelect) cameraSelect.disabled = true;
        if (refreshButton) refreshButton.disabled = true;
        if (testCaptureButton) testCaptureButton.disabled = true;
        
        const response = await fetch('/timelapse/cameras');
        const data = await response.json();
        
        if (data.cameras && Array.isArray(data.cameras)) {
            // Update global status
            timelapseStatus.available_cameras = data.cameras;
            
            // Remember the current selection
            const currentSelection = cameraSelect.value;
            
            // Clear existing options
            cameraSelect.innerHTML = '';
            
            if (data.cameras.length === 0) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No cameras found';
                cameraSelect.appendChild(option);
                logMessage('No cameras found. Please check your camera connection.', LOG_TYPE.WARNING);
            } else {
                // Add a blank option first
                const blankOption = document.createElement('option');
                blankOption.value = '';
                blankOption.textContent = 'Select a camera...';
                cameraSelect.appendChild(blankOption);
                
                // Add cameras to select
                data.cameras.forEach(camera => {
                    const option = document.createElement('option');
                    option.value = camera;
                    option.textContent = camera;
                    cameraSelect.appendChild(option);
                });
                
                // Try to restore the previous selection
                let selectedCamera = null;
                
                // Selection priority:
                // 1. Current selection if it's still in the list
                // 2. Camera being used for active timelapse
                // 3. Saved camera from localStorage
                
                // First try to use the current selection if it's still available
                if (currentSelection && data.cameras.includes(currentSelection)) {
                    cameraSelect.value = currentSelection;
                    selectedCamera = currentSelection;
                    lastCameraSelection = currentSelection;
                } else if (timelapseStatus.is_capturing && timelapseStatus.selected_camera) {
                    // If a timelapse is running, use that camera
                    cameraSelect.value = timelapseStatus.selected_camera;
                    selectedCamera = timelapseStatus.selected_camera;
                    lastCameraSelection = timelapseStatus.selected_camera;
                } else {
                    // Try to use the previously selected camera from localStorage
                    const savedCamera = localStorage.getItem('selectedCamera');
                    if (savedCamera && data.cameras.includes(savedCamera)) {
                        cameraSelect.value = savedCamera;
                        selectedCamera = savedCamera;
                        lastCameraSelection = savedCamera;
                    }
                }
                
                // Pre-initialize the selected camera if one was chosen and pre-initialization is requested
                if (selectedCamera && shouldPreInitialize) {
                    // Don't need to disable controls again as they're already disabled
                    await preInitializeCamera(selectedCamera);
                }
                
                logMessage(`Found ${data.cameras.length} camera(s)`, LOG_TYPE.DEBUG);
            }
        }
    } catch (error) {
        logMessage(`Error refreshing cameras: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator if we're not pre-initializing
        // (if pre-initializing, the preInitializeCamera function will handle this)
        if (!shouldPreInitialize) {
            const loadingIndicator = document.getElementById('timelapse-loading');
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
                
                // Reset loading message
                const loadingMessage = loadingIndicator.querySelector('span');
                if (loadingMessage) {
                    loadingMessage.textContent = 'Processing...';
                }
            }
            
            // Re-enable camera controls
            if (cameraSelect) cameraSelect.disabled = false;
            if (refreshButton) refreshButton.disabled = false;
            if (testCaptureButton) testCaptureButton.disabled = false;
        }
    }
}

/**
 * Pre-initialize a camera to make the first capture faster
 * @param {string} camera - The camera to initialize
 */
async function preInitializeCamera(camera) {
    if (!camera) return;
    
    // Get UI elements
    const cameraSelect = document.getElementById('timelapse-camera');
    const refreshButton = cameraSelect.nextElementSibling; // The refresh button next to the select
    const testCaptureButton = document.getElementById('timelapse-test-capture');
    
    try {
        // Show loading indicator
        const loadingIndicator = document.getElementById('timelapse-loading');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'flex';
        }
        
        // Disable camera controls during initialization
        if (cameraSelect) cameraSelect.disabled = true;
        if (refreshButton) refreshButton.disabled = true;
        if (testCaptureButton) testCaptureButton.disabled = true;
        
        // Add a message to the loading indicator
        const loadingMessage = loadingIndicator.querySelector('span');
        if (loadingMessage) {
            loadingMessage.textContent = 'Initializing camera...';
        }
        
        // Call the pre-initialize endpoint
        const response = await fetch('/timelapse/pre_initialize_camera', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ camera: camera })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage(`Camera ${camera} pre-initialized successfully`, LOG_TYPE.DEBUG);
        } else {
            logMessage(`Failed to pre-initialize camera ${camera}`, LOG_TYPE.WARNING);
        }
    } catch (error) {
        logMessage(`Error pre-initializing camera: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator
        const loadingIndicator = document.getElementById('timelapse-loading');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
            
            // Reset the loading message
            const loadingMessage = loadingIndicator.querySelector('span');
            if (loadingMessage) {
                loadingMessage.textContent = 'Processing...';
            }
        }
        
        // Re-enable camera controls
        if (cameraSelect) cameraSelect.disabled = false;
        if (refreshButton) refreshButton.disabled = false;
        if (testCaptureButton) testCaptureButton.disabled = false;
    }
}

/**
 * Start timelapse capture
 */
async function startTimelapse() {
    try {
        const cameraSelect = document.getElementById('timelapse-camera');
        const intervalInput = document.getElementById('timelapse-interval');
        const autoModeCheckbox = document.getElementById('timelapse-auto-mode');
        
        const camera = cameraSelect.value;
        const interval = parseFloat(intervalInput.value);
        const autoMode = autoModeCheckbox.checked;
        
        if (!camera) {
            logMessage('No camera selected', LOG_TYPE.ERROR);
            return;
        }
        
        if (isNaN(interval) || interval <= 0) {
            logMessage('Invalid interval', LOG_TYPE.ERROR);
            return;
        }
        
        // Save settings to localStorage
        localStorage.setItem('selectedCamera', camera);
        localStorage.setItem('timelapseInterval', interval);
        localStorage.setItem('timelapseAutoMode', autoMode);
        
        // Update last camera selection
        lastCameraSelection = camera;
        
        // Show loading indicator
        document.getElementById('timelapse-loading').style.display = 'flex';
        
        const response = await fetch('/timelapse/start', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                camera,
                interval,
                auto_mode: autoMode
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage('Timelapse capture started', LOG_TYPE.SUCCESS);
            
            // Refresh status
            await refreshTimelapseStatus();
        } else {
            logMessage(`Failed to start timelapse: ${data.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error starting timelapse: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator
        document.getElementById('timelapse-loading').style.display = 'none';
    }
}

/**
 * Stop timelapse capture
 */
async function stopTimelapse() {
    try {
        // Show loading indicator
        document.getElementById('timelapse-loading').style.display = 'flex';
        
        const response = await fetch('/timelapse/stop', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage('Timelapse capture stopped', LOG_TYPE.SUCCESS);
            
            // Refresh status
            await refreshTimelapseStatus();
            
            // Refresh sessions
            await loadTimelapsesSessions();
        } else {
            logMessage(`Failed to stop timelapse: ${data.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error stopping timelapse: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator
        document.getElementById('timelapse-loading').style.display = 'none';
    }
}

/**
 * Load timelapse sessions
 */
async function loadTimelapsesSessions() {
    try {
        const response = await fetch('/timelapse/sessions');
        const data = await response.json();
        
        if (data.sessions && Array.isArray(data.sessions)) {
            // Update sessions list
            const sessionsContainer = document.getElementById('timelapse-sessions');
            sessionsContainer.innerHTML = '';
            
            if (data.sessions.length === 0) {
                const emptyMessage = document.createElement('div');
                emptyMessage.className = 'empty-placeholder';
                emptyMessage.textContent = 'No timelapse sessions found';
                sessionsContainer.appendChild(emptyMessage);
            } else {
                data.sessions.forEach(session => {
                    const sessionElement = createSessionElement(session);
                    sessionsContainer.appendChild(sessionElement);
                });
                
                // If we have a selected session, select it again
                if (selectedSession) {
                    const sessionElement = document.querySelector(`[data-session-id="${selectedSession}"]`);
                    if (sessionElement) {
                        sessionElement.click();
                    } else {
                        // If the selected session is no longer available, clear selection
                        selectedSession = null;
                        document.getElementById('timelapse-session-details').style.display = 'none';
                    }
                }
            }
        }
    } catch (error) {
        logMessage(`Error loading timelapse sessions: ${error.message}`, LOG_TYPE.ERROR);
    }
}

/**
 * Create a session element
 */
function createSessionElement(session) {
    const sessionElement = document.createElement('div');
    sessionElement.className = 'timelapse-session';
    sessionElement.dataset.sessionId = session.id;
    
    // Add thumbnail if available
    const thumbnailContainer = document.createElement('div');
    thumbnailContainer.className = 'timelapse-session-thumbnail';
    
    if (session.thumbnail) {
        const thumbnail = document.createElement('img');
        thumbnail.src = `/timelapse/image/${session.thumbnail}`;
        thumbnail.alt = 'Thumbnail';
        thumbnailContainer.appendChild(thumbnail);
    }
    
    sessionElement.appendChild(thumbnailContainer);
    
    // Add session info
    const infoContainer = document.createElement('div');
    infoContainer.className = 'timelapse-session-info';
    
    const title = document.createElement('div');
    title.className = 'timelapse-session-title';
    
    // Format the session ID (which is a timestamp) into a readable date
    let sessionDate = session.id.replace('timelapse_', '');
    sessionDate = `${sessionDate.substring(0, 4)}-${sessionDate.substring(4, 6)}-${sessionDate.substring(6, 8)} ${sessionDate.substring(9, 11)}:${sessionDate.substring(11, 13)}:${sessionDate.substring(13, 15)}`;
    
    title.textContent = sessionDate;
    infoContainer.appendChild(title);
    
    const details = document.createElement('div');
    details.className = 'timelapse-session-details';
    details.textContent = `${session.frame_count} frames${session.has_video ? ' | Video available' : ''}`;
    infoContainer.appendChild(details);
    
    sessionElement.appendChild(infoContainer);
    
    // Add delete button
    const deleteButton = document.createElement('button');
    deleteButton.className = 'delete-button cancel';
    deleteButton.innerHTML = '<i class="fa-solid fa-trash"></i>';
    deleteButton.title = 'Delete session';
    deleteButton.addEventListener('click', (e) => {
        e.stopPropagation(); // Prevent session selection when clicking delete
        deleteTimelapseSession(session.id);
    });
    
    sessionElement.appendChild(deleteButton);
    
    // Add click handler
    sessionElement.addEventListener('click', () => {
        // Deselect all sessions
        document.querySelectorAll('.timelapse-session').forEach(el => {
            el.classList.remove('selected');
        });
        
        // Select this session
        sessionElement.classList.add('selected');
        selectedSession = session.id;
        
        // Load session details
        loadSessionDetails(session);
    });
    
    return sessionElement;
}

/**
 * Delete a timelapse session
 */
async function deleteTimelapseSession(sessionId) {
    if (!confirm(`Are you sure you want to delete this timelapse session? This cannot be undone.`)) {
        return;
    }
    
    try {
        // Show loading indicator
        document.getElementById('timelapse-loading').style.display = 'flex';
        
        const response = await fetch(`/timelapse/delete/${sessionId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage('Timelapse session deleted', LOG_TYPE.SUCCESS);
            
            // If this was the selected session, clear selection
            if (selectedSession === sessionId) {
                selectedSession = null;
                document.getElementById('timelapse-session-details').style.display = 'none';
            }
            
            // Refresh sessions
            await loadTimelapsesSessions();
        } else {
            logMessage(`Failed to delete timelapse session: ${data.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error deleting timelapse session: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator
        document.getElementById('timelapse-loading').style.display = 'none';
    }
}

/**
 * Load session details
 */
async function loadSessionDetails(session) {
    try {
        // Store selected session ID, not the entire object
        selectedSession = session.id;
        
        // Hide sessions list for cleaner UI
        document.getElementById('timelapse-sessions').style.display = 'none';
        
        // Show session details
        const sessionDetails = document.getElementById('timelapse-session-details');
        sessionDetails.style.display = 'block';
        
        // Update session name
        document.getElementById('timelapse-session-name').textContent = session.id;
        
        // Load frames
        const response = await fetch(`/timelapse/frames/${session.id}`);
        const data = await response.json();
        
        if (data.frames && Array.isArray(data.frames)) {
            // Update frames list
            const framesContainer = document.getElementById('timelapse-frames');
            framesContainer.innerHTML = '';
            
            if (data.frames.length === 0) {
                const emptyMessage = document.createElement('div');
                emptyMessage.className = 'empty-placeholder';
                emptyMessage.textContent = 'No frames found';
                framesContainer.appendChild(emptyMessage);
            } else {
                // Only show a subset of frames if there are many
                const framesToShow = data.frames.length > 20 
                    ? data.frames.filter((_, i) => i % Math.ceil(data.frames.length / 20) === 0) 
                    : data.frames;
                
                framesToShow.forEach(frame => {
                    const frameElement = createFrameElement(frame);
                    framesContainer.appendChild(frameElement);
                });
            }
        }
        
        // Check if video exists
        if (session.has_video) {
            const videoContainer = document.getElementById('timelapse-video-container');
            videoContainer.style.display = 'block';
            
            const video = document.getElementById('timelapse-video');
            video.src = `/timelapse/video/${session.id}`;
        } else {
            document.getElementById('timelapse-video-container').style.display = 'none';
        }
    } catch (error) {
        logMessage(`Error loading session details: ${error.message}`, LOG_TYPE.ERROR);
    }
}

/**
 * Create a frame element
 */
function createFrameElement(frame) {
    const frameElement = document.createElement('div');
    frameElement.className = 'timelapse-frame';
    
    const image = document.createElement('img');
    image.src = `/timelapse/image/${frame.path}`;
    image.alt = 'Frame';
    
    // Add click handler to show the frame in the preview
    frameElement.addEventListener('click', () => {
        const previewImage = document.getElementById('timelapse-preview-image');
        previewImage.src = `/timelapse/image/${frame.path}`;
    });
    
    frameElement.appendChild(image);
    
    return frameElement;
}

/**
 * Create a timelapse video
 */
async function createTimelapseVideo() {
    if (!selectedSession) {
        logMessage('No session selected', LOG_TYPE.ERROR);
        return;
    }
    
    try {
        // Show loading indicator
        document.getElementById('timelapse-loading').style.display = 'flex';
        
        const fps = parseInt(document.getElementById('timelapse-fps').value) || 10;
        
        // Make sure we're using the session ID, not the entire session object
        const sessionId = typeof selectedSession === 'object' ? selectedSession.id : selectedSession;
        
        const response = await fetch('/timelapse/create_video', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId,
                fps
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage(`Timelapse video created with ${data.frame_count} frames`, LOG_TYPE.SUCCESS);
            
            // Refresh sessions to update video status
            await loadTimelapsesSessions();
            
            // Show the video
            const videoContainer = document.getElementById('timelapse-video-container');
            videoContainer.style.display = 'block';
            
            const video = document.getElementById('timelapse-video');
            video.src = `/timelapse/video/${sessionId}`;
        } else {
            logMessage(`Failed to create video: ${data.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error creating video: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide loading indicator
        document.getElementById('timelapse-loading').style.display = 'none';
    }
}

/**
 * Go back to the sessions list from session details
 */
function backToSessionsList() {
    // Hide session details
    document.getElementById('timelapse-session-details').style.display = 'none';
    
    // Clear selected session
    selectedSession = null;
    
    // Ensure sessions list is visible
    document.getElementById('timelapse-sessions').style.display = 'block';
    
    // Clear any selected session styling
    const sessionElements = document.querySelectorAll('.timelapse-session');
    sessionElements.forEach(el => el.classList.remove('selected'));
}

/**
 * Close the timelapse container without removing the fullscreen class
 */
function closeTimelapseContainer() {
    const container = document.getElementById('timelapse-container');
    if (!container) return;
    
    container.classList.remove('visible');
    // Don't remove the fullscreen class
    container.classList.add('hidden');
    
    // Hide session details if visible
    document.getElementById('timelapse-session-details').style.display = 'none';
    
    // Ensure sessions list is visible for next time
    document.getElementById('timelapse-sessions').style.display = 'block';
    
    // Clear any selected session styling
    const sessionElements = document.querySelectorAll('.timelapse-session');
    sessionElements.forEach(el => el.classList.remove('selected'));
    
    logMessage('Closed timelapse container');
}

/**
 * Update the auto mode setting
 */
async function updateAutoMode() {
    const autoModeCheckbox = document.getElementById('timelapse-auto-mode');
    const autoMode = autoModeCheckbox.checked;
    
    try {
        // Save to localStorage
        localStorage.setItem('timelapseAutoMode', autoMode);
        
        // Send to server
        const response = await fetch('/timelapse/update_auto_mode', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                auto_mode: autoMode
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            logMessage(`Auto mode ${autoMode ? 'enabled' : 'disabled'}`, LOG_TYPE.SUCCESS);
            // Update local status
            timelapseStatus.auto_mode = autoMode;
        } else {
            logMessage(`Failed to update auto mode: ${data.error}`, LOG_TYPE.ERROR);
            // Revert checkbox if there was an error
            autoModeCheckbox.checked = timelapseStatus.auto_mode;
        }
    } catch (error) {
        logMessage(`Error updating auto mode: ${error.message}`, LOG_TYPE.ERROR);
        // Revert checkbox if there was an error
        autoModeCheckbox.checked = timelapseStatus.auto_mode;
    }
} 