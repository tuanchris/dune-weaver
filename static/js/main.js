// Global variables
let selectedFile = null;
let playlist = [];
let selectedPlaylistIndex = null;
let allFiles = [];

// Define constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Enhanced logMessage with notification system
function logMessage(message, type = LOG_TYPE.DEBUG, clickTargetId = null) {
    const log = document.getElementById('status_log');
    const header = document.querySelector('header');

    if (!header) {
        console.error('Error: <header> element not found');
        return;
    }

    // Debug messages only go to the status log
    if (type === LOG_TYPE.DEBUG) {
        if (!log) {
            console.error('Error: #status_log element not found');
            return;
        }
        const entry = document.createElement('p');
        entry.textContent = message;
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight; // Scroll to the bottom of the log
        return;
    }

    // Clear any existing notifications
    const existingNotification = header.querySelector('.notification');
    if (existingNotification) {
        existingNotification.remove();
    }

    // Create a notification for other message types
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;

    // Add a close button
    const closeButton = document.createElement('button');
    closeButton.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    closeButton.className = 'close-button no-bg';
    closeButton.onclick = (e) => {
        e.stopPropagation(); // Prevent triggering the clickTarget when the close button is clicked
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 250); // Match transition duration
    };
    notification.appendChild(closeButton);

    // Attach click event to the notification if a clickTargetId is provided
    if (clickTargetId) {
        notification.onclick = () => {
            const target = document.getElementById(clickTargetId);
            if (target) {
                // Find the closest <main> parent
                const parentMain = target.closest('main');
                if (parentMain) {
                    // Remove 'active' class from all <main> elements
                    document.querySelectorAll('main').forEach((main) => {
                        main.classList.remove('active');
                    });
                    // Add 'active' class to the parent <main>
                    parentMain.classList.add('active');
                    target.click();

                    // Update tab buttons based on the parent <main> ID
                    const parentId = parentMain.id; // e.g., "patterns-tab"
                    const tabId = `nav-${parentId.replace('-tab', '')}`; // e.g., "nav-patterns"
                    document.querySelectorAll('.tab-button').forEach((button) => {
                        button.classList.remove('active');
                    });
                    const tabButton = document.getElementById(tabId);
                    if (tabButton) {
                        tabButton.classList.add('active');
                    }
                }
            }
        };
    }

    // Append the notification to the header
    header.appendChild(notification);

    // Trigger the transition
    requestAnimationFrame(() => {
        notification.classList.add('show');
    });

    // Auto-remove the notification after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 250); // Match transition duration
        }
    }, 5000);

    // Also log the message to the status log if available
    if (log) {
        const entry = document.createElement('p');
        entry.textContent = message;
        log.appendChild(entry);
        log.scrollTop = log.scrollHeight; // Scroll to the bottom of the log
    }
}

function toggleDebugLog() {
    const statusLog = document.getElementById('status_log');
    const debugButton = document.getElementById('debug_button');

    if (statusLog.style.display === 'block') {
        statusLog.style.display = 'none';
        debugButton.classList.remove('active');
    } else {
        statusLog.style.display = 'block';
        debugButton.classList.add( 'active');
        statusLog.scrollIntoView({ behavior: 'smooth', block: 'start' }); // Smooth scrolling to the log
    }
}

// File selection logic
async function selectFile(file, listItem) {
    selectedFile = file;

    // Highlight the selected file
    document.querySelectorAll('#theta_rho_files li').forEach(li => li.classList.remove('selected'));
    listItem.classList.add('selected');

    // Update the Remove button visibility
    const removeButton = document.querySelector('#pattern-preview-container .remove-button');
    if (file.startsWith('custom_patterns/')) {
        removeButton.classList.remove('hidden');
    } else {
        removeButton.classList.add('hidden');
    }

    logMessage(`Selected file: ${file}`);
    
    // Show the preview container
    const previewContainer = document.getElementById('pattern-preview-container');
    if (previewContainer) {
        previewContainer.classList.remove('hidden');
        previewContainer.classList.add('visible');
    }
    
    // Update the preview
    await previewPattern(file);
}

// Fetch and display Theta-Rho files
async function loadThetaRhoFiles() {
    try {
        logMessage('Loading Theta-Rho files...');
        const response = await fetch('/list_theta_rho_files');
        let files = await response.json();

        files = files.filter(file => file.endsWith('.thr'));
        // Sort files with custom_patterns on top and all alphabetically sorted
        const sortedFiles = files.sort((a, b) => {
            const isCustomA = a.startsWith('custom_patterns/');
            const isCustomB = b.startsWith('custom_patterns/');

            if (isCustomA && !isCustomB) return -1; // a comes first
            if (!isCustomA && isCustomB) return 1;  // b comes first
            return a.localeCompare(b);             // Alphabetical comparison
        });

        allFiles = sortedFiles; // Update global files
        displayFiles(sortedFiles); // Display sorted files

        logMessage('Theta-Rho files loaded and sorted successfully.');
    } catch (error) {
        logMessage(`Error loading Theta-Rho files: ${error.message}`, 'error');
    }
}

// Display files in the UI
function displayFiles(files) {
    const ul = document.getElementById('theta_rho_files');
    if (!ul) {
        logMessage('Error: File list container not found');
        return;
    }
    ul.innerHTML = ''; // Clear existing list

    files.forEach(file => {
        const li = document.createElement('li');
        li.textContent = file;
        li.classList.add('file-item');

        // Attach file selection handler
        li.onclick = () => selectFile(file, li);

        ul.appendChild(li);
    });
}

// Filter files by search input
function searchPatternFiles() {
    const searchInput = document.getElementById('search_pattern').value.toLowerCase();
    const filteredFiles = allFiles.filter(file => file.toLowerCase().includes(searchInput));
    displayFiles(filteredFiles);
}

// Upload a new Theta-Rho file
async function uploadThetaRho() {
    const fileInput = document.getElementById('upload_file');
    const file = fileInput.files[0];
    if (!file) {
        logMessage('No file selected for upload.', LOG_TYPE.ERROR);
        return;
    }

    try {
        logMessage(`Uploading file: ${file.name}...`);
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/upload_theta_rho', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();
        if (result.success) {
            logMessage(`File uploaded successfully: ${file.name}`, LOG_TYPE.SUCCESS);
            fileInput.value = '';
            await loadThetaRhoFiles();
        } else {
            logMessage(`Failed to upload file: ${file.name}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error uploading file: ${error.message}`);
    }
}

async function runThetaRho() {
    if (!selectedFile) {
        logMessage("No file selected to run.");
        return;
    }

    // Get the selected pre-execution action
    const preExecutionAction = document.getElementById('pre_execution').value;

    logMessage(`Running file: ${selectedFile} with pre-execution action: ${preExecutionAction}...`);
    try {
        const response = await fetch('/run_theta_rho', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                file_name: selectedFile, 
                pre_execution: preExecutionAction 
            })
        });

        const result = await response.json();
        if (response.ok) {
            // Connect WebSocket when starting a pattern
            connectStatusWebSocket();
            
            // Show the currently playing UI immediately
            document.body.classList.add('playing');
            const currentlyPlayingFile = document.getElementById('currently-playing-file');
            if (currentlyPlayingFile) {
                currentlyPlayingFile.textContent = selectedFile.replace('./patterns/', '');
            }
            // Show initial preview
            updateCurrentlyPlayingPattern(selectedFile.replace('./patterns/', ''));
            logMessage(`Pattern running: ${selectedFile}`, LOG_TYPE.SUCCESS);
        } else {
            if (response.status === 409) {
                logMessage("Cannot start pattern: Another pattern is already running", LOG_TYPE.WARNING);
            } else {
                logMessage(`Failed to run file: ${result.detail || 'Unknown error'}`, LOG_TYPE.ERROR);
            }
        }
    } catch (error) {
        logMessage(`Error running pattern: ${error.message}`, LOG_TYPE.ERROR);
    }
}

async function stopExecution() {
    logMessage('Stopping execution...');
    const response = await fetch('/stop_execution', { method: 'POST' });
    const result = await response.json();
    if (result.success) {
        logMessage('Execution stopped.',LOG_TYPE.SUCCESS);
    } else {
        logMessage('Failed to stop execution.',LOG_TYPE.ERROR);
    }
}

async function ShutDown() {
    logMessage('Shutting down the system...');
}

let isPaused = false;

function togglePausePlay() {
    const button = document.getElementById("pausePlayCurrent");

    if (isPaused) {
        // Resume execution
        fetch('/resume_execution', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    isPaused = false;
                    button.innerHTML = "<i class=\"fa-solid fa-pause\"></i>"; // Change to pause icon
                }
            })
            .catch(error => console.error("Error resuming execution:", error));
    } else {
        // Pause execution
        fetch('/pause_execution', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    isPaused = true;
                    button.innerHTML = "<i class=\"fa-solid fa-play\"></i>"; // Change to play icon
                }
            })
            .catch(error => console.error("Error pausing execution:", error));
    }
}

function removeCurrentPattern() {
    if (!selectedFile) {
        logMessage('No file selected to remove.', LOG_TYPE.ERROR);
        return;
    }

    if (!selectedFile.startsWith('custom_patterns/')) {
        logMessage('Only custom patterns can be removed.', LOG_TYPE.WARNING);
        return;
    }

    removeCustomPattern(selectedFile);
}

// Delete the selected file
async function removeCustomPattern(fileName) {
    const userConfirmed = confirm(`Are you sure you want to delete the pattern "${fileName}"?`);
    if (!userConfirmed) return;

    try {
        logMessage(`Deleting pattern: ${fileName}...`);
        const response = await fetch('/delete_theta_rho_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_name: fileName })
        });

        const result = await response.json();
        if (result.success) {
            logMessage(`File deleted successfully: ${selectedFile}`, LOG_TYPE.SUCCESS);

            // Close the preview container
            const previewContainer = document.getElementById('pattern-preview-container');
            if (previewContainer) {
                previewContainer.classList.add('hidden');
                previewContainer.classList.remove('visible');
            }

            // Clear the selected file and refresh the file list
            selectedFile = null;
            await loadThetaRhoFiles(); // Refresh the file list
        } else {
            logMessage(`Failed to delete pattern "${fileName}": ${result.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error deleting pattern: ${error.message}`);
    }
}

// Preview Cache
const previewCache = new Map();

// Function to get preview from cache or fetch it
async function getPreview(fileName) {
    // Check if preview is in cache
    if (previewCache.has(fileName)) {
        return previewCache.get(fileName);
    }

    // If not in cache, fetch it
    try {
        const response = await fetch('/preview_thr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_name: fileName })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        // Store in cache
        previewCache.set(fileName, data);
        return data;
    } catch (error) {
        logMessage(`Error fetching preview: ${error.message}`, LOG_TYPE.ERROR);
        throw error;
    }
}

// Function to clear preview cache
function clearPreviewCache() {
    previewCache.clear();
}

// Update previewPattern function to handle PNG
async function previewPattern(fileName, containerId = 'pattern-preview-container') {
    try {
        logMessage(`Fetching data to preview file: ${fileName}...`);
        const data = await getPreview(fileName);
        
        // Get the preview container
        const previewContainer = document.getElementById(containerId);
        if (!previewContainer) {
            logMessage(`Preview container not found: ${containerId}`, LOG_TYPE.ERROR);
            return;
        }

        // Get the pattern preview section
        const patternPreview = previewContainer.querySelector('#pattern-preview');
        if (!patternPreview) {
            logMessage('Pattern preview section not found', LOG_TYPE.ERROR);
            return;
        }

        // Clear existing content
        patternPreview.innerHTML = '';

        // Create image container
        const imgContainer = document.createElement('div');
        imgContainer.className = 'preview-container';
        
        // Create and set up the image
        const img = document.createElement('img');
        img.src = data.preview_url;
        img.alt = `Preview of ${fileName}`;
        img.className = 'pattern-preview-image';
        
        // Add loading state
        img.onload = () => {
            img.classList.add('loaded');
        };
        
        imgContainer.appendChild(img);

        // Create coordinate display
        const coordDisplay = document.createElement('div');
        coordDisplay.className = 'coordinate-display';

        // Update coordinate text
        if (data.first_coordinate && data.last_coordinate) {
            coordDisplay.innerHTML = `
                <div>First Coordinate: θ=${data.first_coordinate[0].toFixed(2)}, ρ=${data.first_coordinate[1].toFixed(2)}</div>
                <div>Last Coordinate: θ=${data.last_coordinate[0].toFixed(2)}, ρ=${data.last_coordinate[1].toFixed(2)}</div>
            `;
        } else {
            coordDisplay.innerHTML = 'No coordinates available';
        }

        // Add elements to preview
        patternPreview.appendChild(imgContainer);
        patternPreview.appendChild(coordDisplay);

    } catch (error) {
        logMessage(`Error previewing pattern: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Update the currently playing preview to use PNG
async function updateCurrentlyPlayingPattern(fileName) {
    try {
        const data = await getPreview(fileName);
        
        // Get the currently playing container
        const container = document.getElementById('currently-playing-container');
        if (!container) {
            logMessage('Currently playing container not found', LOG_TYPE.ERROR);
            return;
        }

        // Get the currently playing preview div
        const previewDiv = container.querySelector('#currently-playing-preview');
        if (!previewDiv) {
            logMessage('Currently playing preview div not found', LOG_TYPE.ERROR);
            return;
        }

        // Clear existing content
        previewDiv.innerHTML = '';

        // Create image container
        const imgContainer = document.createElement('div');
        imgContainer.className = 'preview-container';
        
        // Create and set up the image
        const img = document.createElement('img');
        img.src = data.preview_url;
        img.alt = `Currently playing: ${fileName}`;
        img.className = 'pattern-preview-image';
        
        // Add loading state
        img.onload = () => {
            img.classList.add('loaded');
        };
        
        imgContainer.appendChild(img);

        // Add image to the preview div
        previewDiv.appendChild(imgContainer);

    } catch (error) {
        logMessage(`Error updating currently playing pattern: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Render the pattern on a canvas
function renderPattern(coordinates, canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        logMessage(`Canvas element not found: ${canvasId}`, LOG_TYPE.ERROR);
        return;
    }

    if (!(canvas instanceof HTMLCanvasElement)) {
        logMessage(`Element with ID "${canvasId}" is not a canvas.`, LOG_TYPE.ERROR);
        return;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) {
        logMessage(`Could not get 2D context for canvas: ${canvasId}`, LOG_TYPE.ERROR);
        return;
    }

    // Account for device pixel ratio
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;  // Scale canvas width for high DPI
    canvas.height = rect.height * dpr;  // Scale canvas height for high DPI

    ctx.scale(dpr, dpr);  // Scale drawing context

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const centerX = rect.width / 2;  // Use bounding client rect dimensions
    const centerY = rect.height / 2;
    const maxRho = Math.max(...coordinates.map(coord => coord[1]));
    const scale = Math.min(rect.width, rect.height) / (2 * maxRho); // Scale to fit

    ctx.beginPath();
    ctx.strokeStyle = 'white';
    coordinates.forEach(([theta, rho], index) => {
        const x = centerX + rho * Math.cos(theta) * scale;
        const y = centerY - rho * Math.sin(theta) * scale;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
}


async function moveToCenter() {
    logMessage('Moving to center...', LOG_TYPE.INFO);
    const response = await fetch('/move_to_center', { method: 'POST' });
    const result = await response.json();
    if (result.success) {
        logMessage('Moved to center successfully.', LOG_TYPE.SUCCESS);
    } else {
        logMessage(`Failed to move to center: ${result.error}`, LOG_TYPE.ERROR);
    }
}

async function moveToPerimeter() {
    logMessage('Moving to perimeter...', LOG_TYPE.INFO);
    const response = await fetch('/move_to_perimeter', { method: 'POST' });
    const result = await response.json();
    if (result.success) {
        logMessage('Moved to perimeter successfully.', LOG_TYPE.SUCCESS);
    } else {
        logMessage(`Failed to move to perimeter: ${result.error}`, LOG_TYPE.ERROR);
    }
}

async function sendCoordinate() {
    const theta = parseFloat(document.getElementById('theta_input').value);
    const rho = parseFloat(document.getElementById('rho_input').value);

    if (isNaN(theta) || isNaN(rho)) {
        logMessage('Invalid input: θ and ρ must be numbers.', LOG_TYPE.ERROR);
        return;
    }

    logMessage(`Sending coordinate: θ=${theta}, ρ=${rho}...`);
    const response = await fetch('/send_coordinate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theta, rho })
    });

    const result = await response.json();
    if (result.success) {
        logMessage(`Coordinate executed successfully: θ=${theta}, ρ=${rho}`, LOG_TYPE.SUCCESS);
    } else {
        logMessage(`Failed to execute coordinate: ${result.error}`, LOG_TYPE.ERROR);
    }
}

async function sendHomeCommand() {
    const response = await fetch('/send_home', { method: 'POST' });
    const result = await response.json();
    if (result.success) {
        logMessage('HOME command sent successfully.', LOG_TYPE.SUCCESS);
    } else {
        logMessage('Failed to send HOME command.', LOG_TYPE.ERROR);
    }
}

async function runClearIn() {
    logMessage('Running clear from center pattern...', LOG_TYPE.INFO);
    try {
        const response = await fetch('/run_theta_rho', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_name: 'clear_from_in.thr',
                pre_execution: 'none'
            })
        });
        
        if (!response.ok) {
            if (response.status === 409) {
                logMessage('Cannot start pattern: Another pattern is already running', LOG_TYPE.WARNING);
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        if (result.success) {
            connectStatusWebSocket();
            document.body.classList.add('playing');
            logMessage('Clear from center pattern started', LOG_TYPE.SUCCESS);
        } else {
            logMessage('Failed to run clear pattern', LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error running clear pattern: ${error}`, LOG_TYPE.ERROR);
    }
}

async function runClearOut() {
    logMessage('Running clear from perimeter pattern...', LOG_TYPE.INFO);
    try {
        const response = await fetch('/run_theta_rho', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_name: 'clear_from_out.thr',
                pre_execution: 'none'
            })
        });
        
        if (!response.ok) {
            if (response.status === 409) {
                logMessage('Cannot start pattern: Another pattern is already running', LOG_TYPE.WARNING);
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        if (result.success) {
            connectStatusWebSocket();
            document.body.classList.add('playing');
            logMessage('Clear from perimeter pattern started', LOG_TYPE.SUCCESS);
        } else {
            logMessage('Failed to run clear pattern', LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error running clear pattern: ${error}`, LOG_TYPE.ERROR);
    }
}

async function runClearSide() {
    logMessage('Running clear sideways pattern...', LOG_TYPE.INFO);
    try {
        const response = await fetch('/run_theta_rho', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_name: 'clear_sideway.thr',
                pre_execution: 'none'
            })
        });
        
        if (!response.ok) {
            if (response.status === 409) {
                logMessage('Cannot start pattern: Another pattern is already running', LOG_TYPE.WARNING);
                return;
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        if (result.success) {
            connectStatusWebSocket();
            document.body.classList.add('playing');
            logMessage('Clear sideways pattern started', LOG_TYPE.SUCCESS);
        } else {
            logMessage('Failed to run clear pattern', LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error running clear pattern: ${error}`, LOG_TYPE.ERROR);
    }
}

let scrollPosition = 0;

function scrollSelection(direction) {
    const container = document.getElementById('clear_selection');
    const itemHeight = 50; // Adjust based on CSS height
    const maxScroll = container.children.length - 1;

    // Update scroll position
    scrollPosition += direction;
    scrollPosition = Math.max(0, Math.min(scrollPosition, maxScroll));

    // Update the transform to scroll items
    container.style.transform = `translateY(-${scrollPosition * itemHeight}px)`;
    setCookie('clear_action_index', scrollPosition, 365);
}

function executeClearAction(actionFunction) {
    // Save the new action to a cookie (optional)
    setCookie('clear_action', actionFunction, 365);

    if (actionFunction && typeof window[actionFunction] === 'function') {
        window[actionFunction](); // Execute the selected clear action
    } else {
        logMessage('No clear action selected or function not found.', LOG_TYPE.ERROR);
    }
}

async function runFile(fileName) {
    const response = await fetch(`/run_theta_rho_file/${fileName}`, { method: 'POST' });
    const result = await response.json();
    if (result.success) {
        logMessage(`Running file: ${fileName}`, LOG_TYPE.SUCCESS);
    } else {
        logMessage(`Failed to run file: ${fileName}`, LOG_TYPE.ERROR);
    }
}

// Connection Status
async function checkSerialStatus() {
    const response = await fetch('/serial_status');
    const status = await response.json();
    const statusElement = document.getElementById('serial_status');
    const statusHeaderElement = document.getElementById('connection_status_header');
    const serialPortsContainer = document.getElementById('serial_ports_container');
    const selectElement = document.getElementById('serial_ports');

    const connectButton = document.querySelector('button[onclick="connectSerial()"]');
    const disconnectButton = document.querySelector('button[onclick="disconnectSerial()"]');
    const restartButton = document.querySelector('button[onclick="restartSerial()"]');

    if (status.connected) {
        const port = status.port || 'Unknown'; // Fallback if port is undefined
        statusElement.textContent = `Connected to ${port}`;
        statusElement.classList.add('connected');
        statusElement.classList.remove('not-connected');
        logMessage(`Connected to serial port: ${port}`);

        // Update header status
        statusHeaderElement.classList.add('connected');
        statusHeaderElement.classList.remove('not-connected');

        // Hide Available Ports and show disconnect/restart buttons
        serialPortsContainer.style.display = 'none';
        connectButton.style.display = 'none';
        disconnectButton.style.display = 'flex';
        restartButton.style.display = 'flex';

        // Preselect the connected port in the dropdown
        const newOption = document.createElement('option');
        newOption.value = port;
        newOption.textContent = port;
        selectElement.appendChild(newOption);
        selectElement.value = port;
    } else {
        statusElement.textContent = 'Not connected';
        statusElement.classList.add('not-connected');
        statusElement.classList.remove('connected');
        logMessage('No active connection.');

        // Update header status
        statusHeaderElement.classList.add('not-connected');
        statusHeaderElement.classList.remove('connected');

        // Show Available Ports and the connect button
        serialPortsContainer.style.display = 'block';
        connectButton.style.display = 'flex';
        disconnectButton.style.display = 'none';
        restartButton.style.display = 'none';

        // Attempt to auto-load available ports
        await loadSerialPorts();
    }
}

async function loadSerialPorts() {
    const response = await fetch('/list_serial_ports');
    const ports = await response.json();
    const select = document.getElementById('serial_ports');
    select.innerHTML = '';
    ports.forEach(port => {
        const option = document.createElement('option');
        option.value = port;
        option.textContent = port;
        select.appendChild(option);
    });
    logMessage('Serial ports loaded.');
}

async function connectSerial() {
    const port = document.getElementById('serial_ports').value;
    const response = await fetch('/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port })
    });
    const result = await response.json();
    if (result.success) {
        logMessage(`Connected to serial port: ${port}`, LOG_TYPE.SUCCESS);

        // Refresh the status
        await checkSerialStatus();
    } else {
        logMessage(`Error connecting to serial port: ${result.error}`, LOG_TYPE.ERROR);
    }
}

async function disconnectSerial() {
    const response = await fetch('/disconnect', { method: 'POST' });
    const result = await response.json();
    if (result.success) {
        logMessage('Serial port disconnected.', LOG_TYPE.SUCCESS);
        // Refresh the status
        await checkSerialStatus();
    } else {
        logMessage(`Error disconnecting: ${result.error}`, LOG_TYPE.ERROR);
    }
}

async function restartSerial() {
    const port = document.getElementById('serial_ports').value;
    const response = await fetch('/restart_connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port })
    });
    const result = await response.json();
    if (result.success) {
        document.getElementById('serial_status').textContent = `Restarted connection to ${port}`;
        logMessage('Connection restarted.', LOG_TYPE.SUCCESS);

        // No need to change visibility for restart
    } else {
        logMessage(`Error restarting Connection: ${result.error}`, LOG_TYPE.ERROR);
    }
}

// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
//  Firmware / Software Updater
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
async function checkForUpdates() {
    try {
        const response = await fetch('/check_software_update');
        const data = await response.json();

        // Handle updates available logic
        // if (data.updates_available) {
        //     const updateButton = document.getElementById('update-software-btn');
        //     const updateLinkElement = document.getElementById('update_link');
        //     const tagLink = `https://github.com/tuanchris/dune-weaver/releases/tag/${data.latest_remote_tag}`;

        //     updateButton.classList.remove('hidden'); // Show the button
        //     logMessage("Software Update Available", LOG_TYPE.INFO, 'open-settings-button')

        //     updateLinkElement.innerHTML = `<a href="${tagLink}" target="_blank">View Release Notes </a>`;
        //     updateLinkElement.classList.remove('hidden'); // Show the link
        // }

        // Update current and latest version in the UI
        const currentVersionElem = document.getElementById('current_git_version');
        const latestVersionElem = document.getElementById('latest_git_version');

        currentVersionElem.textContent = `Current Version: ${data.latest_local_tag || 'Unknown'}`;
        latestVersionElem.textContent = data.updates_available
            ? `Latest Version: ${data.latest_remote_tag}`
            : 'You are up to date!';

    } catch (error) {
        console.error('Error checking for updates:', error);
    }
}

async function updateSoftware() {
    const updateButton = document.getElementById('update-software-btn');

    try {
        // Disable the button and update the text
        updateButton.disabled = true;
        updateButton.querySelector('span').textContent = 'Updating...';

        const response = await fetch('/update_software', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            logMessage('Software updated successfully!', LOG_TYPE.SUCCESS);
            window.location.reload(); // Reload the page after update
        } else {
            logMessage('Failed to update software: ' + data.error, LOG_TYPE.ERROR);
        }
    } catch (error) {
        console.error('Error updating software:', error);
        logMessage('Failed to update software', LOG_TYPE.ERROR);
    } finally {
        // Re-enable the button and reset the text
        updateButton.disabled = false;
        updateButton.textContent = 'Update Software'; // Adjust to the original text
    }
}

// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
//  PART A: Loading / listing playlists from the server
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

async function loadAllPlaylists() {
    try {
        const response = await fetch('/list_all_playlists'); // GET
        const allPlaylists = await response.json();          // e.g. ["My Playlist", "Summer", ...]
        displayAllPlaylists(allPlaylists);
    } catch (err) {
        logMessage(`Error loading playlists: ${err}`, LOG_TYPE.ERROR);
    }
}

// Function to display all playlists with Load, Run, and Delete buttons
function displayAllPlaylists(playlists) {
    const ul = document.getElementById('all_playlists');
    ul.innerHTML = ''; // Clear current list

    if (playlists.length === 0) {
        // Add a placeholder if the list is empty
        const emptyLi = document.createElement('li');
        emptyLi.textContent = "You don't have any playlists yet.";
        emptyLi.classList.add('empty-placeholder'); // Optional: Add a class for styling
        ul.appendChild(emptyLi);
        return;
    }

    playlists.forEach(playlistName => {
        const li = document.createElement('li');
        li.textContent = playlistName;
        li.classList.add('playlist-item'); // Add a class for styling

        // Attach click event to handle selection
        li.onclick = () => {
            // Remove 'selected' class from all items
            document.querySelectorAll('#all_playlists li').forEach(item => {
                item.classList.remove('selected');
            });

            // Add 'selected' class to the clicked item
            li.classList.add('selected');

            // Open the playlist editor for the selected playlist
            openPlaylistEditor(playlistName);
        };

        ul.appendChild(li);
    });
}

// Cancel changes and close the editor
function cancelPlaylistChanges() {
    playlist = [...originalPlaylist]; // Revert to the original playlist
    isPlaylistChanged = false;
    toggleSaveCancelButtons(false); // Hide the save and cancel buttons
    refreshPlaylistUI(); // Refresh the UI with the original state
    closeStickySection('playlist-editor'); // Close the editor
}

// Open the playlist editor
function openPlaylistEditor(playlistName) {
    logMessage(`Opening editor for playlist: ${playlistName}`);
    const editorSection = document.getElementById('playlist-editor');

    // Update the displayed playlist name
    document.getElementById('playlist_name_display').textContent = playlistName;

    // Store the current playlist name for renaming
    document.getElementById('playlist_name_input').value = playlistName;

    editorSection.classList.remove('hidden');
    editorSection.classList.add('visible');

    loadPlaylist(playlistName);
}

function clearSchedule() {
    document.getElementById("start_time").value = "";
    document.getElementById("end_time").value = "";
    document.getElementById('clear_time').style.display = 'none';
    setCookie('start_time', '', 365);
    setCookie('end_time', '', 365);
}

// Function to run the selected playlist with specified parameters
async function runPlaylist() {
    const playlistName = document.getElementById('playlist_name_display').textContent;
    if (!playlistName) {
        logMessage('No playlist selected', 'error');
        return;
    }

    const pauseTime = parseFloat(document.getElementById('pause_time').value) || 0;
    const clearPattern = document.getElementById('clear_pattern').value;
    const runMode = document.querySelector('input[name="run_mode"]:checked').value;
    const shuffle = document.getElementById('shuffle_playlist').checked;

    try {
        const response = await fetch('/run_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                playlist_name: playlistName,
                pause_time: pauseTime,
                clear_pattern: clearPattern,
                run_mode: runMode,
                shuffle: shuffle
            })
        });

        if (!response.ok) {
            if (response.status === 409) {
                logMessage('Another pattern is already running', 'warning');
            } else {
                const errorData = await response.json();
                logMessage(errorData.detail || 'Failed to run playlist', 'error');
            }
            return;
        }

        // Connect WebSocket when starting a playlist
        connectStatusWebSocket();
        
        logMessage(`Started playlist: ${playlistName}`, 'success');
        // Close the playlist editor container after successfully starting the playlist
        closeStickySection('playlist-editor');
    } catch (error) {
        logMessage('Error running playlist: ' + error, 'error');
    }
}

// Track changes in the playlist
let originalPlaylist = [];
let isPlaylistChanged = false;

// Load playlist and set the original state
async function loadPlaylist(playlistName) {
    try {
        logMessage(`Loading playlist: ${playlistName}`);
        const response = await fetch(`/get_playlist?name=${encodeURIComponent(playlistName)}`);

        const data = await response.json();

        if (!data.name) {
            throw new Error('Playlist name is missing in the response.');
        }

        // Populate playlist items and set original state
        playlist = data.files || [];
        originalPlaylist = [...playlist]; // Clone the playlist as the original
        isPlaylistChanged = false; // Reset change tracking
        toggleSaveCancelButtons(false); // Hide the save and cancel buttons initially
        refreshPlaylistUI();
        logMessage(`Loaded playlist: "${playlistName}" with ${playlist.length} file(s).`);
    } catch (err) {
        logMessage(`Error loading playlist: ${err.message}`, LOG_TYPE.ERROR);
        console.error('Error details:', err);
    }
}

// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
//  PART B: Creating or Saving (Overwriting) a Playlist
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

// Instead of separate create/modify functions, we'll unify them:
async function savePlaylist() {
    const name =  document.getElementById('playlist_name_display').textContent
    if (!name) {
        logMessage("Please enter a playlist name.");
        return;
    }
    if (playlist.length === 0) {
        logMessage("No files in this playlist. Add files first.");
        return;
    }

    logMessage(`Saving playlist "${name}" with ${playlist.length} file(s)...`);

    try {
        // We can use /create_playlist or /modify_playlist. They do roughly the same in our single-file approach.
        // Let's use /create_playlist to always overwrite or create anew.
        const response = await fetch('/create_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_name: name,
                files: playlist
            })
        });
        const result = await response.json();
        if (result.success) {
            logMessage(`Playlist "${name}" with ${playlist.length} patterns saved`, LOG_TYPE.SUCCESS);
            // Reload the entire list of playlists to reflect changes
            // Check for changes and refresh the UI
            detectPlaylistChanges();
            refreshPlaylistUI();

            // Restore default action buttons
            toggleSaveCancelButtons(false);
        } else {
            logMessage(`Failed to save playlist: ${result.error}`, LOG_TYPE.ERROR);
        }
    } catch (err) {
        logMessage(`Error saving playlist: ${err}`);
    }
}

// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
//  PART C: Renaming and Deleting a playlist
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
// Toggle the rename playlist input
function populatePlaylistDropdown() {
    return fetch('/list_all_playlists')
        .then(response => response.json())
        .then(playlists => {
            const select = document.getElementById('select-playlist');
            select.innerHTML = ''; // Clear existing options

            // Retrieve the saved playlist from the cookie
            const savedPlaylist = getCookie('selected_playlist');

            // Check if there are playlists available
            if (playlists.length === 0) {
                // Add a placeholder option if no playlists are available
                const placeholderOption = document.createElement('option');
                placeholderOption.value = '';
                placeholderOption.textContent = 'No playlists available';
                placeholderOption.disabled = true; // Prevent selection
                placeholderOption.selected = true; // Set as default
                select.appendChild(placeholderOption);
                return;
            }

            playlists.forEach(playlist => {
                const option = document.createElement('option');
                option.value = playlist;
                option.textContent = playlist;

                // Mark the saved playlist as selected
                if (playlist === savedPlaylist) {
                    option.selected = true;
                }

                select.appendChild(option);
            });

            // Attach the onchange event listener after populating the dropdown
            select.addEventListener('change', function () {
                const selectedPlaylist = this.value;
                setCookie('selected_playlist', selectedPlaylist, 365); // Save to cookie
                logMessage(`Selected playlist saved: ${selectedPlaylist}`);
            });

            logMessage('Playlist dropdown populated, event listener attached, and saved playlist restored.');
        })
        .catch(error => logMessage(`Error fetching playlists: ${error.message}`));
}
populatePlaylistDropdown().then(() => {
    loadSettingsFromCookies(); // Restore selected playlist after populating the dropdown
});

// Confirm and save the renamed playlist
async function confirmAddPlaylist() {
    const playlistNameInput = document.getElementById('new_playlist_name');
    const playlistName = playlistNameInput.value.trim();

    if (!playlistName) {
        logMessage('Playlist name cannot be empty.', LOG_TYPE.ERROR);
        return;
    }

    try {
        logMessage(`Adding new playlist: "${playlistName}"...`);
        const response = await fetch('/create_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_name: playlistName,
                files: [] // New playlist starts empty
            })
        });

        const result = await response.json();
        if (result.success) {
            logMessage(`Playlist "${playlistName}" created successfully.`,  LOG_TYPE.SUCCESS);

            // Clear the input field
            playlistNameInput.value = '';

            // Refresh the playlist list
            loadAllPlaylists();
            populatePlaylistDropdown();
            populateStartupPlaylistDropdown();

            // Hide the add playlist container
            toggleSecondaryButtons('add-playlist-container');
        } else {
            logMessage(`Failed to create playlist: ${result.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error creating playlist: ${error.message}`);
    }
}


async function confirmRenamePlaylist() {
    const newName = document.getElementById('playlist_name_input').value.trim();
    const currentName = document.getElementById('playlist_name_display').textContent;

    if (!newName) {
        logMessage("New playlist name cannot be empty.", LOG_TYPE.ERROR);
        return;
    }

    if (newName === currentName) {
        logMessage("New playlist name is the same as the current name. No changes made.",  LOG_TYPE.WARNING);
        toggleSecondaryButtons('rename-playlist-container'); // Close the rename container
        return;
    }

    try {
        // Step 1: Create/Modify the playlist with the new name
        const createResponse = await fetch('/modify_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                playlist_name: newName,
                files: playlist // Ensure `playlist` contains the current list of files
            })
        });

        const createResult = await createResponse.json();
        if (createResult.success) {
            logMessage(createResult.message, LOG_TYPE.SUCCESS);

            // Step 2: Delete the old playlist
            const deleteResponse = await fetch('/delete_playlist', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ playlist_name: currentName })
            });

            const deleteResult = await deleteResponse.json();
            if (deleteResult.success) {
                logMessage(deleteResult.message);

                // Update the UI with the new name
                document.getElementById('playlist_name_display').textContent = newName;

                // Refresh playlists list
                loadAllPlaylists();

                // Close the rename container and restore original action buttons
                toggleSecondaryButtons('rename-playlist-container');
            } else {
                logMessage(`Failed to delete old playlist: ${deleteResult.error}`, LOG_TYPE.ERROR);
            }
        } else {
            logMessage(`Failed to rename playlist: ${createResult.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error renaming playlist: ${error.message}`);
    }
}

// Delete the currently opened playlist
async function deleteCurrentPlaylist() {
    const playlistName = document.getElementById('playlist_name_display').textContent;

    if (!confirm(`Are you sure you want to delete the playlist "${playlistName}"? This action cannot be undone.`)) {
        return;
    }

    try {
        const response = await fetch('/delete_playlist', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playlist_name: playlistName })
        });

        const result = await response.json();
        if (result.success) {
            logMessage(`Playlist "${playlistName}" deleted.`, LOG_TYPE.INFO);
            closeStickySection('playlist-editor');
            loadAllPlaylists();
            populatePlaylistDropdown();
            populateStartupPlaylistDropdown();
        } else {
            logMessage(`Failed to delete playlist: ${result.error}`,  LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error deleting playlist: ${error.message}`);
    }
}

// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
//  PART D: Local playlist array UI
// ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

// Refresh the playlist UI and detect changes
function refreshPlaylistUI() {
    const ul = document.getElementById('playlist_items');
    if (!ul) {
        logMessage('Error: Playlist container not found');
        return;
    }
    ul.innerHTML = ''; // Clear existing items

    if (playlist.length === 0) {
        // Add a placeholder if the playlist is empty
        const emptyLi = document.createElement('li');
        emptyLi.textContent = 'No items in the playlist.';
        emptyLi.classList.add('empty-placeholder'); // Optional: Add a class for styling
        ul.appendChild(emptyLi);
        return;
    }

    playlist.forEach((file, index) => {
        const li = document.createElement('li');

        // Add filename in a span
        const filenameSpan = document.createElement('span');
        filenameSpan.textContent = file;
        filenameSpan.classList.add('filename'); // Add a class for styling
        li.appendChild(filenameSpan);

        // Move Up button
        const moveUpBtn = document.createElement('button');
        moveUpBtn.innerHTML = '<i class="fa-solid fa-turn-up"></i>'; // Up arrow symbol
        moveUpBtn.classList.add('move-button');
        moveUpBtn.onclick = () => {
            if (index > 0) {
                const temp = playlist[index - 1];
                playlist[index - 1] = playlist[index];
                playlist[index] = temp;
                detectPlaylistChanges(); // Check for changes
                refreshPlaylistUI();
            }
        };
        li.appendChild(moveUpBtn);

        // Move Down button
        const moveDownBtn = document.createElement('button');
        moveDownBtn.innerHTML = '<i class="fa-solid fa-turn-down"></i>'; // Down arrow symbol
        moveDownBtn.classList.add('move-button');
        moveDownBtn.onclick = () => {
            if (index < playlist.length - 1) {
                const temp = playlist[index + 1];
                playlist[index + 1] = playlist[index];
                playlist[index] = temp;
                detectPlaylistChanges(); // Check for changes
                refreshPlaylistUI();
            }
        };
        li.appendChild(moveDownBtn);

        // Remove button
        const removeBtn = document.createElement('button');
        removeBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
        removeBtn.classList.add('remove-button');
        removeBtn.onclick = () => {
            playlist.splice(index, 1);
            detectPlaylistChanges(); // Check for changes
            refreshPlaylistUI();
        };
        li.appendChild(removeBtn);

        ul.appendChild(li);
    });
}

// Toggle the visibility of the save and cancel buttons
function toggleSaveCancelButtons(show) {
    const actionButtons = document.querySelector('#playlist-editor .action-buttons');
    if (actionButtons) {
        // Show/hide all buttons except Save and Cancel
        actionButtons.querySelectorAll('button:not(.save-cancel)').forEach(button => {
            button.style.display = show ? 'none' : 'flex';
        });

        // Show/hide Save and Cancel buttons
        actionButtons.querySelectorAll('.save-cancel').forEach(button => {
            button.style.display = show ? 'flex' : 'none';
        });
    } else {
        logMessage('Error: Action buttons container not found.', LOG_TYPE.ERROR);
    }
}

// Detect changes in the playlist
function detectPlaylistChanges() {
    isPlaylistChanged = JSON.stringify(originalPlaylist) !== JSON.stringify(playlist);
    toggleSaveCancelButtons(isPlaylistChanged);
}


// Toggle the "Add to Playlist" section
function toggleSecondaryButtons(containerId, onShowCallback = null) {
    const container = document.getElementById(containerId);
    if (!container) {
        logMessage(`Error: Element with ID "${containerId}" not found`);
        return;
    }

    // Find the .action-buttons element preceding the container
    const previousActionButtons = container.previousElementSibling?.classList.contains('action-buttons')
        ? container.previousElementSibling
        : null;

    if (container.classList.contains('hidden')) {
        // Show the container
        container.classList.remove('hidden');

        // Hide the previous .action-buttons element
        if (previousActionButtons) {
            previousActionButtons.style.display = 'none';
        }

        // Optional callback for custom logic when showing the container
        if (onShowCallback) {
            onShowCallback();
        }
    } else {
        // Hide the container
        container.classList.add('hidden');

        // Restore the previous .action-buttons element
        if (previousActionButtons) {
            previousActionButtons.style.display = 'flex';
        }
    }
}

// Add the selected pattern to the selected playlist
async function saveToPlaylist() {
    const playlist = document.getElementById('select-playlist').value;
    if (!playlist) {
        logMessage('No playlist selected.', LOG_TYPE.ERROR);
        return;
    }
    if (!selectedFile) {
        logMessage('No pattern selected to add.', LOG_TYPE.ERROR);
        return;
    }

    try {
        logMessage(`Adding pattern "${selectedFile}" to playlist "${playlist}"...`);
        const response = await fetch('/add_to_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playlist_name: playlist, pattern: selectedFile })
        });

        const result = await response.json();
        if (result.success) {
            logMessage(`Pattern "${selectedFile}" successfully added to playlist "${playlist}".`, LOG_TYPE.SUCCESS);

            // Reset the UI state via toggleSecondaryButtons
            toggleSecondaryButtons('add-to-playlist-container', () => {
                const selectPlaylist = document.getElementById('select-playlist');
                selectPlaylist.value = ''; // Clear the selection
            });
        } else {
            logMessage(`Failed to add pattern to playlist: ${result.error}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error adding pattern to playlist: ${error.message}`);
    }
}

async function changeSpeed() {
    const speedInput = document.getElementById('speed_input');
    const speed = parseFloat(speedInput.value);

    if (isNaN(speed) || speed <= 0) {
        logMessage('Invalid speed. Please enter a positive number.');
        return;
    }

    logMessage(`Setting speed to: ${speed}...`);
    const response = await fetch('/set_speed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed })
    });

    const result = await response.json();
    if (result.success) {
        document.getElementById('current_speed_display').textContent = `Current Speed: ${speed}`;
        logMessage(`Speed set to: ${speed}`, LOG_TYPE.SUCCESS);
    } else {
        logMessage(`Failed to set speed: ${result.error}`, LOG_TYPE.ERROR);
    }
}

// Function to close any sticky section
function closeStickySection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.remove('visible');
        section.classList.remove('fullscreen');
        section.classList.add('hidden');
        // Reset the fullscreen button text if it exists
        const fullscreenButton = section.querySelector('.fullscreen-button');
        if (fullscreenButton) {
            fullscreenButton.innerHtml = '<i class="fa-solid fa-compress"></i>'; // Reset to enter fullscreen icon/text
        }

        logMessage(`Closed section: ${sectionId}`);

        if(sectionId === 'playlist-editor') {
            document.querySelectorAll('#all_playlists .playlist-item').forEach(item => {
                item.classList.remove('selected');
            });
        }

        if(sectionId === 'pattern-preview-container') {
            document.querySelectorAll('#theta_rho_files .file-item').forEach(item => {
                item.classList.remove('selected');
            });
        }

    } else {
        logMessage(`Error: Section with ID "${sectionId}" not found`);
    }
}

// Function to open any sticky section
function openStickySection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        // Toggle the 'open' class
        section.classList.toggle('open');
    } else {
        logMessage(`Error: Section with ID "${sectionId}" not found`);
    }
}

function attachFullScreenListeners() {
    // Add event listener to all fullscreen buttons
    document.querySelectorAll('.fullscreen-button').forEach(button => {
        button.addEventListener('click', function () {
            const stickySection = this.closest('.sticky'); // Find the closest sticky section
            if (stickySection) {
                // Close all other sections
                document.querySelectorAll('.sticky:not(#currently-playing-container):not(#image-converter)').forEach(section => {
                    if (section !== stickySection) {
                        section.classList.remove('fullscreen');
                        section.classList.remove('visible');
                        section.classList.add('hidden');

                        // Reset the fullscreen button text for other sections
                        const otherFullscreenButton = section.querySelector('.fullscreen-button');
                        if (otherFullscreenButton) {
                            otherFullscreenButton.innerHTML = '<i class="fa-solid fa-expand"></i>'; // Enter fullscreen icon/text
                        }
                    }
                });

                stickySection.classList.toggle('fullscreen'); // Toggle fullscreen class

                // Update button icon or text
                if (stickySection.classList.contains('fullscreen')) {
                    this.innerHTML = '<i class="fa-solid fa-compress"></i>'; // Exit fullscreen icon/text
                } else {
                    this.innerHTML = '<i class="fa-solid fa-expand"></i>'; // Enter fullscreen icon/text
                }
            } else {
                console.error('Error: Fullscreen button is not inside a sticky section.');
            }
        });
    });
}

let lastPreviewedFile = null; // Track the last previewed file



function formatSecondsToHMS(seconds) {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

// Function to start or stop updates based on visibility
function toggleSettings() {
    const settingsContainer = document.getElementById('settings-container');
    console.log('setttings')
    if (settingsContainer) {
        settingsContainer.classList.toggle('open');
        console.log('populating')
        populateStartupPlaylistDropdown();
    }
}

// Utility function to manage cookies
function setCookie(name, value, days) {
    const date = new Date();
    date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = `${name}=${value};expires=${date.toUTCString()};path=/`;
}

function getCookie(name) {
    const nameEQ = `${name}=`;
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
        let cookie = cookies[i].trim();
        if (cookie.startsWith(nameEQ)) {
            return cookie.substring(nameEQ.length);
        }
    }
    return null;
}

// Save settings to cookies
function saveSettingsToCookies() {
    const pauseTime = document.getElementById('pause_time').value;
    const clearPattern = document.getElementById('clear_pattern').value;
    const runMode = document.querySelector('input[name="run_mode"]:checked').value;
    const shuffle = document.getElementById('shuffle_playlist').checked;
    const apiKey = document.getElementById('api-key').value;

    setCookie('pause_time', pauseTime, 365);
    setCookie('clear_pattern', clearPattern, 365);
    setCookie('run_mode', runMode, 365);
    setCookie('shuffle', shuffle, 365);
    setCookie('api_key', apiKey, 365);
}

// Load settings from cookies
function loadSettingsFromCookies() {
    const pauseTime = getCookie('pause_time');
    if (pauseTime !== '') {
        const pauseTimeElement = document.getElementById('pause_time');
        if (pauseTimeElement) {
            pauseTimeElement.value = pauseTime;
        }
    }

    const clearPattern = getCookie('clear_pattern');
    if (clearPattern !== '') {
        const clearPatternElement = document.getElementById('clear_pattern');
        if (clearPatternElement) {
            clearPatternElement.value = clearPattern;
        }
    }

    const runMode = getCookie('run_mode');
    if (runMode !== '') {
        const runModeElement = document.querySelector(`input[name="run_mode"][value="${runMode}"]`);
        if (runModeElement) {
            runModeElement.checked = true;
        }
    }

    const shuffle = getCookie('shuffle');
    if (shuffle !== '') {
        const shuffleElement = document.getElementById('shuffle_playlist');
        if (shuffleElement) {
            shuffleElement.checked = shuffle === 'true';
        }
    }

    const apiKey = getCookie('api_key');
    if (apiKey !== '') {
        const apiKeyElement = document.getElementById('api-key');
        if (apiKeyElement) {
            apiKeyElement.value = apiKey;
        }
    }

    logMessage('Settings loaded from cookies.');
}

// Call this function to save settings when a value is changed
function attachSettingsSaveListeners() {
    // Add event listeners to inputs
    document.getElementById('pause_time').addEventListener('change', saveSettingsToCookies);
    document.getElementById('clear_pattern').addEventListener('change', saveSettingsToCookies);
    document.querySelectorAll('input[name="run_mode"]').forEach(input => {
        input.addEventListener('change', saveSettingsToCookies);
    });
    document.getElementById('shuffle_playlist').addEventListener('change', saveSettingsToCookies);
    document.getElementById('api-key').addEventListener('change', saveSettingsToCookies);
}


// Tab switching logic with cookie storage
function switchTab(tabName, tabGroup = 'main') {
    // Store the active tab in a cookie (per tab group)
    setCookie(`activeTab-${tabGroup}`, tabName, 365);

    // Deactivate all tab content in the specific group
    document.querySelectorAll(`.tab-content[data-group="${tabGroup}"]`).forEach(tab => {
        tab.classList.remove('active');
    });

    // Activate the selected tab content
    const activeTab = document.getElementById(`${tabName}-tab`);
    if (activeTab) {
        activeTab.classList.add('active');
    } else {
        console.error(`Error: Tab "${tabName}" not found.`);
    }

    // Deactivate all buttons in this group
    document.querySelectorAll(`.tab-button[data-group="${tabGroup}"]`).forEach(button => {
        button.classList.remove('active');
    });

    // Activate the selected nav button
    const activeNavButton = document.getElementById(`nav-${tabName}`);
    if (activeNavButton) {
        activeNavButton.classList.add('active');
    } else {
        console.error(`Error: Nav button for "${tabName}" not found.`);
    }
}

// Update the small UI segment to show the IP or hide it if none
function updateWledUI() {
    const wledIp = localStorage.getItem('wled_ip');
    const wledContainer = document.getElementById('wled-container');
    const wledFrame = document.getElementById('wled-frame');
    const wledStatus = document.getElementById('wled-status');

    if (!wledIp) {
        wledContainer.classList.add('hidden');
        return;
    }

    // Show the container and load WLED UI
    wledContainer.classList.remove('hidden');
    wledFrame.src = `http://${wledIp}`;

}

// Save the startup time
async function setStartupTime() {
    logMessage('Saving startup time...');
    const hour = document.getElementById('startup_hour');
    const minute = document.getElementById('startup_minute');
    const saveButton = document.querySelector('.startup_time button.cta');

    logMessage(`Startup time: ${hour.value}:${minute.value}`);
    console.log(`Startup time: ${hour.value}:${minute.value}`);
    
    //if inputs disabled, clear the startup time
    if (hour.disabled && minute.disabled) {
        
        //Clear the front-end inputs
        logMessage('Clearing startup time...');
        console.log('Clearing startup time...');
        hour.value = "";
        minute.value = "";
        hour.disabled = false;
        minute.disabled = false;
        saveButton.innerHTML = '<i class="fa-solid fa-save"></i><span>Save</span>';

        //Clear Backend startup time
        try {
            const response = await fetch('/set_startup_time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ startup_hour: "", startup_minute: ""})
            });
            const result = await response.json();
            if (result.success) {
                logMessage('Startup time cleared!', LOG_TYPE.SUCCESS);
            } else {
                logMessage('Failed to clear startup time: ' + result.error, LOG_TYPE.ERROR);
            }
        } catch (error) {
            logMessage('Error saving startup time: ' + error.message, LOG_TYPE.ERROR);
        }
    
    //if inputs enabled, save the startup time
    }else{

        // Validate hour and minute inputs
        const hourVal = parseInt(hour.value, 10);
        const minuteVal = parseInt(minute.value, 10);
        if (isNaN(hourVal) || isNaN(minuteVal) || hourVal < 0 || hourVal > 23 || minuteVal < 0 || minuteVal> 59) {
            logMessage('Invalid startup time.', LOG_TYPE.ERROR);
            return;
        }

        // Save the startup time to backend
        try {
            const response = await fetch('/set_startup_time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ startup_hour: hourVal, startup_minute: minuteVal })
            });
            const result = await response.json();
            if (result.success) {
                logMessage('Startup time saved!', LOG_TYPE.SUCCESS);
                logMessage('Loading Startup Time...');
                // Update the UI to reflect the saved time
                loadStartupTime()
            } else {
                logMessage('Failed to save startup time: ' + result.error, LOG_TYPE.ERROR);
            }
        } catch (error) {
            logMessage('Error saving startup time: ' + error.message, LOG_TYPE.ERROR);
        }
    }
}

async function loadStartupTime() {
    const hourInput = document.getElementById('startup_hour');
    const minuteInput = document.getElementById('startup_minute');
    const saveButton = document.querySelector('.startup_time button.cta');
    try {
        const response = await fetch('/get_startup_time');
        const data = await response.json();
        if ((data.startup_hour && data.startup_minute) || (data.startup_hour === "" && data.startup_minute === "")) {
            console.log(`Fetched startup time: ${data.startup_hour}:${data.startup_minute}`);
            var startup_hour = data.startup_hour;
            var startup_minute = data.startup_minute;
        }
    } catch (error) {
            logMessage(`Error fetching startup time from backend: ${error.message}`, LOG_TYPE.ERROR);
    }
    console.log(`Loaded startup time: ${startup_hour}:${startup_minute}`);
    if (startup_hour !== "" && startup_minute !== "") {
        hourInput.value = startup_hour;
        minuteInput.value = startup_minute;
        hourInput.disabled = true;
        minuteInput.disabled = true;
        saveButton.innerHTML = '<i class="fa-solid fa-xmark"></i><span>Clear</span>';
    }
}

// Save Startup Days
async function setStartupDays() {
    const days = [];
    if (document.getElementById('Weekdays').checked){
        days.push('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday');
    }
    if (document.getElementById('Weekend').checked) {
        days.push('Saturday', 'Sunday');
    }
    try {
        const response = await fetch('/set_startup_days', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ startup_days: days })
        });
        const result = await response.json();
        if (result.success) {
            logMessage('Startup days saved!', LOG_TYPE.SUCCESS);
        } else {
            logMessage('Failed to save startup days: ' + result.error, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage('Error saving startup days: ' + error.message, LOG_TYPE.ERROR);
    }
}

// Populate the playlist dropdown with all playlists
async function populateStartupPlaylistDropdown() {
    console.log('Populating startup playlist dropdown...');
    const select = document.getElementById('startup_playlist');
    if (!select) return;
    select.innerHTML = '<option value="none">None</option>';
    try {
        const response = await fetch('/list_all_playlists');
        const playlists = await response.json();
        playlists.forEach(playlist => {
            const option = document.createElement('option');
            option.value = playlist;
            option.textContent = playlist;
            select.appendChild(option);
        });
    } catch (error) {
        logMessage('Failed to load playlists: ' + error, LOG_TYPE.ERROR);
    }
}

// Save Startup Playlist
async function setStartupPlaylist() {
    const select = document.getElementById('startup_playlist');
    const playlist = select.value;
    try {
        const response = await fetch('/set_startup_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ startup_playlist: playlist })
        });
        const result = await response.json();
        if (result.success) {
            logMessage('Startup playlist saved!', LOG_TYPE.SUCCESS);
        } else {
            logMessage('Failed to save startup playlist: ' + result.error, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage('Error saving startup playlist: ' + error.message, LOG_TYPE.ERROR);
    }
}

// Save the shutdown time
async function setShutdownTime() {
    logMessage('Saving shutdown time...');
    const hour = document.getElementById('shutdown_hour');
    const minute = document.getElementById('shutdown_minute');
    const saveButton = document.querySelector('.shutdown_time button.cta');

    logMessage(`Shutdown time: ${hour.value}:${minute.value}`);
    console.log(`Shutdown time: ${hour.value}:${minute.value}`);
    
    //if inputs disabled, clear the startup time
    if (hour.disabled && minute.disabled) {
        
        //Clear the front-end inputs
        logMessage('Clearing shutdown time...');
        console.log('Clearing shutdown time...');
        hour.value = "";
        minute.value = "";
        hour.disabled = false;
        minute.disabled = false;
        saveButton.innerHTML = '<i class="fa-solid fa-save"></i><span>Save</span>';

        //Clear Backend shutdown time
        try {
            const response = await fetch('/set_shutdown_time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shutdown_hour: "", shutdown_minute: ""})
            });
            const result = await response.json();
            if (result.success) {
                logMessage('Shutdown time cleared!', LOG_TYPE.SUCCESS);
            } else {
                logMessage('Failed to clear shutdown time: ' + result.error, LOG_TYPE.ERROR);
            }
        } catch (error) {
            logMessage('Error saving shutdown time: ' + error.message, LOG_TYPE.ERROR);
        }
    
    //if inputs enabled, save the shutdown time
    }else{

        // Validate hour and minute inputs
        const hourVal = parseInt(hour.value, 10);
        const minuteVal = parseInt(minute.value, 10);
        if (isNaN(hourVal) || isNaN(minuteVal) || hourVal < 0 || hourVal > 23 || minuteVal < 0 || minuteVal> 59) {
            logMessage('Invalid startup time.', LOG_TYPE.ERROR);
            return;
        }

        // Save the shutdown time to backend
        try {
            const response = await fetch('/set_shutdown_time', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ shutdown_hour: hourVal, shutdown_minute: minuteVal })
            });
            const result = await response.json();
            if (result.success) {
                logMessage('Shutdown time saved!', LOG_TYPE.SUCCESS);
                logMessage('Loading Shutdown Time...');
                // Update the UI to reflect the saved time
                loadShutdownTime()
            } else {
                logMessage('Failed to save shutdown time: ' + result.error, LOG_TYPE.ERROR);
            }
        } catch (error) {
            logMessage('Error saving shutdown time: ' + error.message, LOG_TYPE.ERROR);
        }
    }
}

async function startLedTest() {
    try {
        logMessage('Starting LED test...');
        const response = await fetch('/start_led_test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();
        if (result.success) {
            logMessage('LED test started successfully!', LOG_TYPE.SUCCESS);
        } else {
            logMessage('Failed to start LED test: ' + result.error, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage('Error starting LED test: ' + error.message, LOG_TYPE.ERROR);
    }
}

async function loadShutdownTime() {
    const hourInput = document.getElementById('shutdown_hour');
    const minuteInput = document.getElementById('shutdown_minute');
    const saveButton = document.querySelector('.shutdown_time button.cta');
    try {
        const response = await fetch('/get_shutdown_time');
        const data = await response.json();
        if ((data.shutdown_hour && data.shutdown_minute) || (data.shutdown_hour === "" && data.shutdown_minute === "")) {
            console.log(`Fetched shutdown time: ${data.shutdown_hour}:${data.shutdown_minute}`);
            var shutdown_hour = data.shutdown_hour;
            var shutdown_minute = data.shutdown_minute;
        }
    } catch (error) {
            logMessage(`Error fetching shutdown time from backend: ${error.message}`, LOG_TYPE.ERROR);
    }
    console.log(`Loaded shutdown time: ${shutdown_hour}:${shutdown_minute}`);

    if (shutdown_hour !== "" && shutdown_minute !== "") {
        hourInput.value = shutdown_hour;
        minuteInput.value = shutdown_minute;
        hourInput.disabled = true;
        minuteInput.disabled = true;
        saveButton.innerHTML = '<i class="fa-solid fa-xmark"></i><span>Clear</span>';
    }
}

// Save or clear the WLED IP, updating both the browser and backend
async function saveWledIp() {
    const ipInput = document.getElementById('wled_ip');
    const saveButton = document.querySelector('.wled-settings button.cta');
    const currentIp = localStorage.getItem('wled_ip');

    if (currentIp) {
        // Clear the saved IP if one is already set
        localStorage.removeItem('wled_ip');
        ipInput.disabled = false;
        ipInput.value = '';
        saveButton.innerHTML = '<i class="fa-solid fa-save"></i><span>Save</span>';
        logMessage('WLED IP cleared.', LOG_TYPE.INFO);

        // Also clear the IP on the backend
        try {
            const response = await fetch('/set_wled_ip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wled_ip: null })
            });
            const data = await response.json();
            if (data.success) {
                logMessage('Backend IP cleared successfully.', LOG_TYPE.INFO);
            } else {
                logMessage('Failed to clear backend IP.', LOG_TYPE.ERROR);
            }
        } catch (error) {
            logMessage(`Error clearing backend IP: ${error.message}`, LOG_TYPE.ERROR);
        }
    } else {
        // Validate and save the new IP
        const ip = ipInput.value.trim();
        if (!validateIp(ip)) {
            logMessage('Invalid IP address format.', LOG_TYPE.ERROR);
            return;
        }
        localStorage.setItem('wled_ip', ip);
        ipInput.disabled = true;
        saveButton.innerHTML = '<i class="fa-solid fa-xmark"></i><span>Clear</span>';
        logMessage(`WLED IP saved: ${ip}`, LOG_TYPE.SUCCESS);

        // Also save the IP to the backend
        try {
            const response = await fetch('/set_wled_ip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ wled_ip: ip })
            });
            const data = await response.json();
            if (data.success) {
                logMessage('Backend IP saved successfully.', LOG_TYPE.SUCCESS);
            } else {
                logMessage('Failed to save backend IP.', LOG_TYPE.ERROR);
            }
        } catch (error) {
            logMessage(`Error saving backend IP: ${error.message}`, LOG_TYPE.ERROR);
        }
    }
    
    updateWledUI(); // Refresh any UI elements that depend on the IP
}

// Load the WLED IP from localStorage; if not available, retrieve it from the backend
async function loadWledIp() {
    const ipInput = document.getElementById('wled_ip');
    const saveButton = document.querySelector('.wled-settings button.cta');
    let savedIp = localStorage.getItem('wled_ip');

    if (!savedIp) {
        // Attempt to load from the backend if not found in localStorage
        try {
            const response = await fetch('/get_wled_ip');
            const data = await response.json();
            if (data.wled_ip) {
                savedIp = data.wled_ip;
                localStorage.setItem('wled_ip', savedIp);
            }
        } catch (error) {
            logMessage(`Error fetching WLED IP from backend: ${error.message}`, LOG_TYPE.ERROR);
        }
    }

    if (savedIp) {
        ipInput.value = savedIp;
        ipInput.disabled = true;
        saveButton.innerHTML = '<i class="fa-solid fa-xmark"></i><span>Clear</span>';
    } else {
        ipInput.disabled = false;
        saveButton.innerHTML = '<i class="fa-solid fa-save"></i><span>Save</span>';
    }
    
    updateWledUI(); // Update any dependent UI segments
}

function validateIp(ip) {
    const ipRegex = /^(25[0-5]|2[0-4]\d|1\d\d|\d?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|\d?\d)){3}$/;
    return ipRegex.test(ip);
  }

// Theme toggle functionality
const themeToggle = document.getElementById('theme-toggle');
const themeIcon = themeToggle.querySelector('i');

themeToggle.addEventListener('click', () => {
    const root = document.documentElement;
    const currentTheme = root.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    root.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    // Toggle the icon
    themeIcon.className = newTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
});

// Set initial theme and icon based on saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', savedTheme);
themeIcon.className = savedTheme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';


// Add WebSocket connection for status updates
let statusSocket = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
let statusUpdateInterval = null;
let wsConnected = false;

function connectStatusWebSocket() {
    // Don't create a new connection if one already exists
    if (wsConnected) {
        console.log('WebSocket already connected');
        return;
    }

    // Close existing connection and clear interval if any
    if (statusSocket) {
        statusSocket.close();
    }
    if (statusUpdateInterval) {
        clearInterval(statusUpdateInterval);
    }

    // Create WebSocket connection
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    statusSocket = new WebSocket(`${protocol}//${window.location.host}/ws/status`);

    statusSocket.onopen = () => {
        console.log('Status WebSocket connected');
        wsConnected = true;
        reconnectAttempts = 0; // Reset reconnect attempts on successful connection
    };

    statusSocket.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            if (message.type === 'status_update' && message.data) {
                updateCurrentlyPlayingUI(message.data);
                
                // Disconnect WebSocket if no pattern is running
                if (!message.data.is_running) {
                    console.log('No pattern running, disconnecting WebSocket');
                    disconnectStatusWebSocket();
                }
            }
        } catch (error) {
            console.error('Error processing status update:', error);
            console.error('Raw data that caused error:', event.data);
        }
    };

    statusSocket.onclose = () => {
        console.log('Status WebSocket disconnected');
        wsConnected = false;
        clearInterval(statusUpdateInterval);
        
        // Only attempt to reconnect if we're supposed to be connected
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS && document.body.classList.contains('playing')) {
            reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
            console.log(`Reconnecting in ${delay/1000}s (Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
            setTimeout(connectStatusWebSocket, delay);
        }
    };

    statusSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function disconnectStatusWebSocket() {
    if (statusSocket && wsConnected) {
        wsConnected = false;
        statusSocket.close();
        statusSocket = null;
        reconnectAttempts = 0;
    }
}

// Replace the polling mechanism with WebSocket
document.addEventListener('DOMContentLoaded', () => {
    const activeMainTab = getCookie('activeTab-main') || 'patterns';
    switchTab(activeMainTab, 'main');
    const activeImageConverterTab = getCookie('activeTab-image-converter') || 'dot';
    switchTab(activeImageConverterTab, 'image-converter');
    checkSerialStatus(); // Check connection status
    loadThetaRhoFiles(); // Load files on page load
    loadAllPlaylists(); // Load all playlists on page load
    attachSettingsSaveListeners(); // Attach event listeners to save changes
    attachFullScreenListeners();
    loadWledIp();
    updateWledUI();
    loadStartupTime(); // Load startup time
    loadShutdownTime(); // Load shutdown time

    // Initialize WebSocket connection for status updates
    connectStatusWebSocket();

    // Handle visibility change
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && statusSocket && statusSocket.readyState !== WebSocket.OPEN) {
            connectStatusWebSocket();
        }
    });

    checkForUpdates();
});

// Track the last time we had a file playing
let lastPlayingTime = 0;
const HIDE_DELAY = 5000; // 1 second delay before hiding

// Update the updateCurrentlyPlayingUI function to handle WebSocket updates
// Track the last played file to detect when a new pattern starts
let lastPlayedFile = null;

function updateCurrentlyPlayingUI(status) {
    // Get all required DOM elements once
    const container = document.getElementById('currently-playing-container');
    const fileNameElement = document.getElementById('currently-playing-file');
    const progressBar = document.getElementById('play_progress');
    const progressText = document.getElementById('play_progress_text');
    const pausePlayButton = document.getElementById('pausePlayCurrent');
    const speedDisplay = document.getElementById('current_speed_display');

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

    // Update speed display if it exists
    if (speedDisplay && status.speed) {
        speedDisplay.textContent = `Current Speed: ${status.speed}`;
    }

    // Update pattern preview if it's a new pattern
    if (status.current_file && lastPlayedFile !== status.current_file) {
        lastPlayedFile = status.current_file;
        const cleanFileName = status.current_file.replace('./patterns/', '');
        updateCurrentlyPlayingPattern(cleanFileName);
    }

    // Update progress information
    if (status.progress) {
        const { percentage, remaining_time, elapsed_time } = status.progress;
        const formattedPercentage = percentage.toFixed(1);
        const remainingText = remaining_time === null ? 'calculating...' : formatSecondsToHMS(remaining_time);
        const elapsedText = formatSecondsToHMS(elapsed_time);

        progressBar.value = formattedPercentage;
        progressText.textContent = `${formattedPercentage}% (Elapsed: ${elapsedText} | Remaining: ${remainingText})`;
    } else {
        progressBar.value = 0;
        progressText.textContent = '0%';
    }

    // Update pause/play button if it exists
    if (pausePlayButton) {
        pausePlayButton.innerHTML = status.is_paused ? 
            '<i class="fa-solid fa-play"></i>' : 
            '<i class="fa-solid fa-pause"></i>';
    }

    // Update playlist UI if the function exists
    if (typeof updatePlaylistUI === 'function') {
        updatePlaylistUI(status);
    }

    // Update skip button visibility based on playlist status
    updateSkipButtonVisibility(status);
}

// Add these functions to handle the skip button

function updateSkipButtonVisibility(status) {
    const skipButton = document.getElementById('skipCurrent');
    if (skipButton) {
        // Check if a playlist is playing using the correct status properties
        console.log('status', status);
        const isPlaylistPlaying = status && status.playlist && status.playlist.next_file;
        if (isPlaylistPlaying) {
            skipButton.classList.remove('hidden');
        } else {
            skipButton.classList.add('hidden');
        }
    }
}

async function skipPattern() {
    try {
        const response = await fetch('/skip_pattern', {
            method: 'POST',
        });
        const data = await response.json();
        
        if (data.success) {
            logMessage('Skipping to next pattern', LOG_TYPE.INFO);
        } else {
            logMessage(data.message, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage('Error skipping pattern', 'error');
    }
}