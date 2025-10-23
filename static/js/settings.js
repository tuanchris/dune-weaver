// Constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Constants for cache
const CACHE_KEYS = {
    CONNECTION_STATUS: 'connection_status',
    LAST_UPDATE: 'last_status_update'
};
const CACHE_DURATION = 5000; // 5 seconds cache duration

// Function to log messages
function logMessage(message, type = LOG_TYPE.DEBUG) {
    console.log(`[${type}] ${message}`);
}

// Function to get cached connection status
function getCachedConnectionStatus() {
    const cachedData = localStorage.getItem(CACHE_KEYS.CONNECTION_STATUS);
    const lastUpdate = localStorage.getItem(CACHE_KEYS.LAST_UPDATE);
    
    if (cachedData && lastUpdate) {
        const now = Date.now();
        const cacheAge = now - parseInt(lastUpdate);
        
        if (cacheAge < CACHE_DURATION) {
            return JSON.parse(cachedData);
        }
    }
    return null;
}

// Function to set cached connection status
function setCachedConnectionStatus(data) {
    localStorage.setItem(CACHE_KEYS.CONNECTION_STATUS, JSON.stringify(data));
    localStorage.setItem(CACHE_KEYS.LAST_UPDATE, Date.now().toString());
}

// Function to update serial connection status
async function updateSerialStatus(forceUpdate = false) {
    try {
        // Check cache first unless force update is requested
        if (!forceUpdate) {
            const cachedData = getCachedConnectionStatus();
            if (cachedData) {
                updateConnectionUI(cachedData);
                return;
            }
        }

        const response = await fetch('/serial_status');
        if (response.ok) {
            const data = await response.json();
            setCachedConnectionStatus(data);
            updateConnectionUI(data);
        }
    } catch (error) {
        logMessage(`Error checking serial status: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Function to update UI based on connection status
function updateConnectionUI(data) {
    const statusElement = document.getElementById('serialStatus');
    const iconElement = document.querySelector('.material-icons.text-3xl');
    const disconnectButton = document.getElementById('disconnectButton');
    const portSelectionDiv = document.getElementById('portSelectionDiv');
    
    if (statusElement && iconElement) {
        if (data.connected) {
            statusElement.textContent = `Connected to ${data.port || 'unknown port'}`;
            statusElement.className = 'text-green-500 text-sm font-medium leading-normal';
            iconElement.textContent = 'usb';
            if (disconnectButton) {
                disconnectButton.hidden = false;
            }
            if (portSelectionDiv) {
                portSelectionDiv.hidden = true;
            }
        } else {
            statusElement.textContent = 'Disconnected';
            statusElement.className = 'text-red-500 text-sm font-medium leading-normal';
            iconElement.textContent = 'usb_off';
            if (disconnectButton) {
                disconnectButton.hidden = true;
            }
            if (portSelectionDiv) {
                portSelectionDiv.hidden = false;
            }
        }
    }
}

// Function to update available serial ports
async function updateSerialPorts() {
    try {
        const response = await fetch('/list_serial_ports');
        if (response.ok) {
            const ports = await response.json();
            const portsElement = document.getElementById('availablePorts');
            const portSelect = document.getElementById('portSelect');
            
            if (portsElement) {
                portsElement.textContent = ports.length > 0 ? ports.join(', ') : 'No ports available';
            }
            
            if (portSelect) {
                // Clear existing options except the first one
                while (portSelect.options.length > 1) {
                    portSelect.remove(1);
                }
                
                // Add new options
                ports.forEach(port => {
                    const option = document.createElement('option');
                    option.value = port;
                    option.textContent = port;
                    portSelect.appendChild(option);
                });

                // If there's exactly one port available, select and connect to it
                if (ports.length === 1) {
                    portSelect.value = ports[0];
                    // Trigger connect button click
                    const connectButton = document.getElementById('connectButton');
                    if (connectButton) {
                        connectButton.click();
                    }
                }
            }
        }
    } catch (error) {
        logMessage(`Error fetching serial ports: ${error.message}`, LOG_TYPE.ERROR);
    }
}

function setWledButtonState(isSet) {
    const saveWledConfig = document.getElementById('saveWledConfig');
    if (!saveWledConfig) return;
    if (isSet) {
        saveWledConfig.className = 'flex items-center justify-center gap-2 min-w-[100px] max-w-[480px] cursor-pointer rounded-lg h-10 px-4 bg-red-600 hover:bg-red-700 text-white text-sm font-medium leading-normal tracking-[0.015em] transition-colors';
        saveWledConfig.innerHTML = '<span class="material-icons text-lg">close</span><span class="truncate">Clear WLED IP</span>';
    } else {
        saveWledConfig.className = 'flex items-center justify-center gap-2 min-w-[100px] max-w-[480px] cursor-pointer rounded-lg h-10 px-4 bg-sky-600 hover:bg-sky-700 text-white text-sm font-medium leading-normal tracking-[0.015em] transition-colors';
        saveWledConfig.innerHTML = '<span class="material-icons text-lg">save</span><span class="truncate">Save Configuration</span>';
    }
}

// Initialize settings page
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize UI with default disconnected state
    updateConnectionUI({ connected: false });
    
    // Load all data asynchronously
    Promise.all([
        // Check connection status
        fetch('/serial_status').then(response => response.json()).catch(() => ({ connected: false })),
        
        // Load current WLED IP
        fetch('/get_wled_ip').then(response => response.json()).catch(() => ({ wled_ip: null })),
        
        // Load current version and check for updates
        fetch('/api/version').then(response => response.json()).catch(() => ({ current: '1.0.0', latest: '1.0.0', update_available: false })),
        
        // Load available serial ports
        fetch('/list_serial_ports').then(response => response.json()).catch(() => []),
        
        // Load available pattern files for clear pattern selection
        getCachedPatternFiles().catch(() => []),
        
        // Load current custom clear patterns
        fetch('/api/custom_clear_patterns').then(response => response.json()).catch(() => ({ custom_clear_from_in: null, custom_clear_from_out: null })),
        
        // Load current clear pattern speed
        fetch('/api/clear_pattern_speed').then(response => response.json()).catch(() => ({ clear_pattern_speed: 200 })),
        
        // Load current app name
        fetch('/api/app-name').then(response => response.json()).catch(() => ({ app_name: 'Dune Weaver' })),

        // Load Still Sands settings
        fetch('/api/scheduled-pause').then(response => response.json()).catch(() => ({ enabled: false, time_slots: [] }))
    ]).then(([statusData, wledData, updateData, ports, patterns, clearPatterns, clearSpeedData, appNameData, scheduledPauseData]) => {
        // Update connection status
        setCachedConnectionStatus(statusData);
        updateConnectionUI(statusData);
        
        // Update WLED IP
        if (wledData.wled_ip) {
            document.getElementById('wledIpInput').value = wledData.wled_ip;
            setWledButtonState(true);
        } else {
            setWledButtonState(false);
        }
        
        // Update version display
        const currentVersionText = document.getElementById('currentVersionText');
        const latestVersionText = document.getElementById('latestVersionText');
        const updateButton = document.getElementById('updateSoftware');
        const updateIcon = document.getElementById('updateIcon');
        const updateText = document.getElementById('updateText');
        
        if (currentVersionText) {
            currentVersionText.textContent = updateData.current;
        }
        
        if (latestVersionText) {
            if (updateData.error) {
                latestVersionText.textContent = 'Error checking updates';
                latestVersionText.className = 'text-red-500 text-sm font-normal leading-normal';
            } else {
                latestVersionText.textContent = updateData.latest;
                latestVersionText.className = 'text-slate-500 text-sm font-normal leading-normal';
            }
        }
        
        // Update button state
        if (updateButton && updateIcon && updateText) {
            if (updateData.update_available) {
                updateButton.disabled = false;
                updateButton.className = 'flex items-center justify-center gap-1.5 min-w-[84px] cursor-pointer rounded-lg h-9 px-3 bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium leading-normal tracking-[0.015em] transition-colors';
                updateIcon.textContent = 'download';
                updateText.textContent = 'Update';
            } else {
                updateButton.disabled = true;
                updateButton.className = 'flex items-center justify-center gap-1.5 min-w-[84px] cursor-pointer rounded-lg h-9 px-3 bg-gray-400 text-white text-xs font-medium leading-normal tracking-[0.015em] transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
                updateIcon.textContent = 'check';
                updateText.textContent = 'Up to date';
            }
        }
        
        // Update port selection
        const portSelect = document.getElementById('portSelect');
        if (portSelect) {
            // Clear existing options except the first one
            while (portSelect.options.length > 1) {
                portSelect.remove(1);
            }
            
            // Add new options
            ports.forEach(port => {
                const option = document.createElement('option');
                option.value = port;
                option.textContent = port;
                portSelect.appendChild(option);
            });

            // If there's exactly one port available, select it
            if (ports.length === 1) {
                portSelect.value = ports[0];
            }
        }
        
        // Initialize autocomplete for clear patterns
        const clearFromInInput = document.getElementById('customClearFromInInput');
        const clearFromOutInput = document.getElementById('customClearFromOutInput');
        
        if (clearFromInInput && clearFromOutInput && patterns && Array.isArray(patterns)) {
            // Store patterns globally for autocomplete
            window.availablePatterns = patterns;
            
            // Set current values if they exist
            if (clearPatterns && clearPatterns.custom_clear_from_in) {
                clearFromInInput.value = clearPatterns.custom_clear_from_in;
            }
            if (clearPatterns && clearPatterns.custom_clear_from_out) {
                clearFromOutInput.value = clearPatterns.custom_clear_from_out;
            }
            
            // Initialize autocomplete for both inputs
            initializeAutocomplete('customClearFromInInput', 'clearFromInSuggestions', 'clearFromInClear', patterns);
            initializeAutocomplete('customClearFromOutInput', 'clearFromOutSuggestions', 'clearFromOutClear', patterns);
            
            console.log('Autocomplete initialized with', patterns.length, 'patterns');
        }
        
        // Set clear pattern speed
        const clearPatternSpeedInput = document.getElementById('clearPatternSpeedInput');
        const effectiveClearSpeed = document.getElementById('effectiveClearSpeed');
        if (clearPatternSpeedInput && clearSpeedData) {
            // Only set value if clear_pattern_speed is not null
            if (clearSpeedData.clear_pattern_speed !== null && clearSpeedData.clear_pattern_speed !== undefined) {
                clearPatternSpeedInput.value = clearSpeedData.clear_pattern_speed;
                if (effectiveClearSpeed) {
                    effectiveClearSpeed.textContent = `Current: ${clearSpeedData.clear_pattern_speed} steps/min`;
                }
            } else {
                // Leave empty to show placeholder for default
                clearPatternSpeedInput.value = '';
                if (effectiveClearSpeed && clearSpeedData.effective_speed) {
                    effectiveClearSpeed.textContent = `Using default pattern speed: ${clearSpeedData.effective_speed} steps/min`;
                }
            }
        }
        
        // Update app name
        const appNameInput = document.getElementById('appNameInput');
        if (appNameInput && appNameData.app_name) {
            appNameInput.value = appNameData.app_name;
        }

        // Store Still Sands data for later initialization
        window.initialStillSandsData = scheduledPauseData;
    }).catch(error => {
        logMessage(`Error initializing settings page: ${error.message}`, LOG_TYPE.ERROR);
    });

    // Set up event listeners
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // Save App Name
    const saveAppNameButton = document.getElementById('saveAppName');
    const appNameInput = document.getElementById('appNameInput');
    if (saveAppNameButton && appNameInput) {
        saveAppNameButton.addEventListener('click', async () => {
            const appName = appNameInput.value.trim() || 'Dune Weaver';
            
            try {
                const response = await fetch('/api/app-name', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ app_name: appName })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    showStatusMessage('Application name updated successfully. Refresh the page to see changes.', 'success');
                    
                    // Update the page title and header immediately
                    document.title = `Settings - ${data.app_name}`;
                    const headerTitle = document.querySelector('h1.text-gray-800');
                    if (headerTitle) {
                        // Update just the text content, preserving the connection status dot
                        const textNode = headerTitle.childNodes[0];
                        if (textNode && textNode.nodeType === Node.TEXT_NODE) {
                            textNode.textContent = data.app_name;
                        }
                    }
                } else {
                    throw new Error('Failed to save application name');
                }
            } catch (error) {
                showStatusMessage(`Failed to save application name: ${error.message}`, 'error');
            }
        });
        
        // Handle Enter key in app name input
        appNameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                saveAppNameButton.click();
            }
        });
    }
    
    // Save/Clear WLED configuration
    const saveWledConfig = document.getElementById('saveWledConfig');
    const wledIpInput = document.getElementById('wledIpInput');
    if (saveWledConfig && wledIpInput) {
        saveWledConfig.addEventListener('click', async () => {
            if (saveWledConfig.textContent.includes('Clear')) {
                // Clear WLED IP
                wledIpInput.value = '';
                try {
                    const response = await fetch('/set_wled_ip', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ wled_ip: '' })
                    });
                    if (response.ok) {
                        setWledButtonState(false);
                        localStorage.removeItem('wled_ip');
                        showStatusMessage('WLED IP cleared successfully', 'success');
                    } else {
                        throw new Error('Failed to clear WLED IP');
                    }
                } catch (error) {
                    showStatusMessage(`Failed to clear WLED IP: ${error.message}`, 'error');
                }
            } else {
                // Save WLED IP
                const wledIp = wledIpInput.value;
                try {
                    const response = await fetch('/set_wled_ip', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ wled_ip: wledIp })
                    });
                    if (response.ok && wledIp) {
                        setWledButtonState(true);
                        localStorage.setItem('wled_ip', wledIp);
                        showStatusMessage('WLED IP configured successfully', 'success');
                    } else {
                        setWledButtonState(false);
                        throw new Error('Failed to save WLED configuration');
                    }
                } catch (error) {
                    showStatusMessage(`Failed to save WLED IP: ${error.message}`, 'error');
                }
            }
        });
    }

    // Update software
    const updateSoftware = document.getElementById('updateSoftware');
    if (updateSoftware) {
        updateSoftware.addEventListener('click', async () => {
            if (updateSoftware.disabled) {
                return;
            }
            
            try {
                const response = await fetch('/api/update', {
                    method: 'POST'
                });
                const data = await response.json();
                
                if (data.success) {
                    showStatusMessage('Software update started successfully', 'success');
                } else if (data.manual_update_url) {
                    // Show modal with manual update instructions, but use wiki link
                    const wikiData = {
                        ...data,
                        manual_update_url: 'https://github.com/tuanchris/dune-weaver/wiki/Updating-software'
                    };
                    showUpdateInstructionsModal(wikiData);
                } else {
                    showStatusMessage(data.message || 'No updates available', 'info');
                }
            } catch (error) {
                logMessage(`Error updating software: ${error.message}`, LOG_TYPE.ERROR);
                showStatusMessage('Failed to check for updates', 'error');
            }
        });
    }

    // Connect button
    const connectButton = document.getElementById('connectButton');
    if (connectButton) {
        connectButton.addEventListener('click', async () => {
            const portSelect = document.getElementById('portSelect');
            if (!portSelect || !portSelect.value) {
                logMessage('Please select a port first', LOG_TYPE.WARNING);
                return;
            }

            try {
                const response = await fetch('/connect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ port: portSelect.value })
                });
                
                if (response.ok) {
                    logMessage('Connected successfully', LOG_TYPE.SUCCESS);
                    await updateSerialStatus(true); // Force update after connecting
                } else {
                    throw new Error('Failed to connect');
                }
            } catch (error) {
                logMessage(`Error connecting to device: ${error.message}`, LOG_TYPE.ERROR);
            }
        });
    }

    // Disconnect button
    const disconnectButton = document.getElementById('disconnectButton');
    if (disconnectButton) {
        disconnectButton.addEventListener('click', async () => {
            try {
                const response = await fetch('/disconnect', {
                    method: 'POST'
                });
                if (response.ok) {
                    logMessage('Device disconnected successfully', LOG_TYPE.SUCCESS);
                    await updateSerialStatus(true); // Force update after disconnecting
                } else {
                    throw new Error('Failed to disconnect device');
                }
            } catch (error) {
                logMessage(`Error disconnecting device: ${error.message}`, LOG_TYPE.ERROR);
            }
        });
    }
    
    // Save custom clear patterns button
    const saveClearPatterns = document.getElementById('saveClearPatterns');
    if (saveClearPatterns) {
        saveClearPatterns.addEventListener('click', async () => {
            const clearFromInInput = document.getElementById('customClearFromInInput');
            const clearFromOutInput = document.getElementById('customClearFromOutInput');
            
            if (!clearFromInInput || !clearFromOutInput) {
                return;
            }
            
            // Validate that the entered patterns exist (if not empty)
            const inValue = clearFromInInput.value.trim();
            const outValue = clearFromOutInput.value.trim();
            
            if (inValue && window.availablePatterns && !window.availablePatterns.includes(inValue)) {
                showStatusMessage(`Pattern not found: ${inValue}`, 'error');
                return;
            }
            
            if (outValue && window.availablePatterns && !window.availablePatterns.includes(outValue)) {
                showStatusMessage(`Pattern not found: ${outValue}`, 'error');
                return;
            }
            
            try {
                const response = await fetch('/api/custom_clear_patterns', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        custom_clear_from_in: inValue || null,
                        custom_clear_from_out: outValue || null
                    })
                });
                
                if (response.ok) {
                    showStatusMessage('Clear patterns saved successfully', 'success');
                } else {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to save clear patterns');
                }
            } catch (error) {
                showStatusMessage(`Failed to save clear patterns: ${error.message}`, 'error');
            }
        });
    }
    
    // Save clear pattern speed button
    const saveClearSpeed = document.getElementById('saveClearSpeed');
    if (saveClearSpeed) {
        saveClearSpeed.addEventListener('click', async () => {
            const clearPatternSpeedInput = document.getElementById('clearPatternSpeedInput');
            
            if (!clearPatternSpeedInput) {
                return;
            }
            
            let speed;
            if (clearPatternSpeedInput.value === '' || clearPatternSpeedInput.value === null) {
                // Empty value means use default (None)
                speed = null;
            } else {
                speed = parseInt(clearPatternSpeedInput.value);
                
                // Validate speed only if it's not null
                if (isNaN(speed) || speed < 50 || speed > 2000) {
                    showStatusMessage('Clear pattern speed must be between 50 and 2000, or leave empty for default', 'error');
                    return;
                }
            }
            
            try {
                const response = await fetch('/api/clear_pattern_speed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ clear_pattern_speed: speed })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    if (speed === null) {
                        showStatusMessage(`Clear pattern speed set to default (${data.effective_speed} steps/min)`, 'success');
                    } else {
                        showStatusMessage(`Clear pattern speed set to ${speed} steps/min`, 'success');
                    }
                    
                    // Update the effective speed display
                    const effectiveClearSpeed = document.getElementById('effectiveClearSpeed');
                    if (effectiveClearSpeed) {
                        if (speed === null) {
                            effectiveClearSpeed.textContent = `Using default pattern speed: ${data.effective_speed} steps/min`;
                        } else {
                            effectiveClearSpeed.textContent = `Current: ${speed} steps/min`;
                        }
                    }
                } else {
                    const error = await response.json();
                    throw new Error(error.detail || 'Failed to save clear pattern speed');
                }
            } catch (error) {
                showStatusMessage(`Failed to save clear pattern speed: ${error.message}`, 'error');
            }
        });
    }
}

// Button click handlers
document.addEventListener('DOMContentLoaded', function() {
    // Home button
    const homeButton = document.getElementById('homeButton');
    if (homeButton) {
        homeButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/send_home', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (data.success) {
                updateStatus('Moving to home position...');
            }
        } catch (error) {
            console.error('Error sending home command:', error);
            updateStatus('Error: Failed to move to home position');
        }
        });
    }

    // Stop button
    const stopButton = document.getElementById('stopButton');
    if (stopButton) {
        stopButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/stop_execution', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (data.success) {
                updateStatus('Execution stopped');
            }
        } catch (error) {
            console.error('Error stopping execution:', error);
            updateStatus('Error: Failed to stop execution');
        }
        });
    }

    // Move to Center button
    const centerButton = document.getElementById('centerButton');
    if (centerButton) {
        centerButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/move_to_center', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (data.success) {
                updateStatus('Moving to center position...');
            }
        } catch (error) {
            console.error('Error moving to center:', error);
            updateStatus('Error: Failed to move to center');
        }
        });
    }

    // Move to Perimeter button
    const perimeterButton = document.getElementById('perimeterButton');
    if (perimeterButton) {
        perimeterButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/move_to_perimeter', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            const data = await response.json();
            if (data.success) {
                updateStatus('Moving to perimeter position...');
            }
        } catch (error) {
            console.error('Error moving to perimeter:', error);
            updateStatus('Error: Failed to move to perimeter');
        }
        });
    }
});

// Function to update status
function updateStatus(message) {
    const statusElement = document.querySelector('.text-slate-800.text-base.font-medium.leading-normal');
    if (statusElement) {
        statusElement.textContent = message;
        // Reset status after 3 seconds if it's a temporary message
        if (message.includes('Moving') || message.includes('Execution')) {
            setTimeout(() => {
                statusElement.textContent = 'Status';
            }, 3000);
        }
    }
}

// Function to show status messages (using existing base.js showStatusMessage if available)
function showStatusMessage(message, type) {
    if (typeof window.showStatusMessage === 'function') {
        window.showStatusMessage(message, type);
    } else {
        // Fallback to console logging
        console.log(`[${type}] ${message}`);
    }
}

// Function to show update instructions modal
function showUpdateInstructionsModal(data) {
    // Create modal HTML
    const modal = document.createElement('div');
    modal.id = 'updateInstructionsModal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4';
    modal.innerHTML = `
        <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md">
            <div class="p-6">
                <div class="text-center mb-4">
                    <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-200 mb-2">Manual Update Required</h2>
                    <p class="text-gray-600 dark:text-gray-400 text-sm">
                        ${data.message}
                    </p>
                </div>
                
                <div class="text-gray-700 dark:text-gray-300 text-sm mb-6">
                    <p class="mb-3">${data.instructions}</p>
                </div>
                
                <div class="flex gap-3 justify-center">
                    <button id="openGitHubRelease" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors">
                        View Update Instructions
                    </button>
                    <button id="closeUpdateModal" class="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-lg transition-colors">
                        Close
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Add event listeners
    const openGitHubButton = modal.querySelector('#openGitHubRelease');
    const closeButton = modal.querySelector('#closeUpdateModal');
    
    openGitHubButton.addEventListener('click', () => {
        window.open(data.manual_update_url, '_blank');
        document.body.removeChild(modal);
    });
    
    closeButton.addEventListener('click', () => {
        document.body.removeChild(modal);
    });
    
    // Close on outside click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            document.body.removeChild(modal);
        }
    });
}

// Autocomplete functionality
function initializeAutocomplete(inputId, suggestionsId, clearButtonId, patterns) {
    const input = document.getElementById(inputId);
    const suggestionsDiv = document.getElementById(suggestionsId);
    const clearButton = document.getElementById(clearButtonId);
    let selectedIndex = -1;
    
    if (!input || !suggestionsDiv) return;
    
    // Function to update clear button visibility
    function updateClearButton() {
        if (clearButton) {
            if (input.value.trim()) {
                clearButton.classList.remove('hidden');
            } else {
                clearButton.classList.add('hidden');
            }
        }
    }
    
    // Format pattern name for display
    function formatPatternName(pattern) {
        return pattern.replace('.thr', '').replace(/_/g, ' ');
    }
    
    // Filter patterns based on input
    function filterPatterns(searchTerm) {
        if (!searchTerm) return patterns.slice(0, 20); // Show first 20 when empty
        
        const term = searchTerm.toLowerCase();
        return patterns.filter(pattern => {
            const name = pattern.toLowerCase();
            return name.includes(term);
        }).sort((a, b) => {
            // Prioritize patterns that start with the search term
            const aStarts = a.toLowerCase().startsWith(term);
            const bStarts = b.toLowerCase().startsWith(term);
            if (aStarts && !bStarts) return -1;
            if (!aStarts && bStarts) return 1;
            return a.localeCompare(b);
        }).slice(0, 20); // Limit to 20 results
    }
    
    // Highlight matching text
    function highlightMatch(text, searchTerm) {
        if (!searchTerm) return text;
        
        const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }
    
    // Show suggestions
    function showSuggestions(searchTerm) {
        const filtered = filterPatterns(searchTerm);
        
        if (filtered.length === 0 && searchTerm) {
            suggestionsDiv.innerHTML = '<div class="suggestion-item" style="cursor: default; color: #9ca3af;">No patterns found</div>';
            suggestionsDiv.classList.remove('hidden');
            return;
        }
        
        suggestionsDiv.innerHTML = filtered.map((pattern, index) => {
            const displayName = formatPatternName(pattern);
            const highlighted = highlightMatch(displayName, searchTerm);
            return `<div class="suggestion-item" data-value="${pattern}" data-index="${index}">${highlighted}</div>`;
        }).join('');
        
        suggestionsDiv.classList.remove('hidden');
        selectedIndex = -1;
    }
    
    // Hide suggestions
    function hideSuggestions() {
        setTimeout(() => {
            suggestionsDiv.classList.add('hidden');
            selectedIndex = -1;
        }, 200);
    }
    
    // Select suggestion
    function selectSuggestion(value) {
        input.value = value;
        hideSuggestions();
        updateClearButton();
    }
    
    // Handle keyboard navigation
    function handleKeyboard(e) {
        const items = suggestionsDiv.querySelectorAll('.suggestion-item[data-value]');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
            updateSelection(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, -1);
            updateSelection(items);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (selectedIndex >= 0 && items[selectedIndex]) {
                selectSuggestion(items[selectedIndex].dataset.value);
            } else if (items.length === 1) {
                selectSuggestion(items[0].dataset.value);
            }
        } else if (e.key === 'Escape') {
            hideSuggestions();
        }
    }
    
    // Update visual selection
    function updateSelection(items) {
        items.forEach((item, index) => {
            if (index === selectedIndex) {
                item.classList.add('selected');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('selected');
            }
        });
    }
    
    // Event listeners
    input.addEventListener('input', (e) => {
        const value = e.target.value.trim();
        updateClearButton();
        if (value.length > 0 || e.target === document.activeElement) {
            showSuggestions(value);
        } else {
            hideSuggestions();
        }
    });
    
    input.addEventListener('focus', () => {
        const value = input.value.trim();
        showSuggestions(value);
    });
    
    input.addEventListener('blur', hideSuggestions);
    
    input.addEventListener('keydown', handleKeyboard);
    
    // Click handler for suggestions
    suggestionsDiv.addEventListener('click', (e) => {
        const item = e.target.closest('.suggestion-item[data-value]');
        if (item) {
            selectSuggestion(item.dataset.value);
        }
    });
    
    // Mouse hover handler
    suggestionsDiv.addEventListener('mouseover', (e) => {
        const item = e.target.closest('.suggestion-item[data-value]');
        if (item) {
            selectedIndex = parseInt(item.dataset.index);
            const items = suggestionsDiv.querySelectorAll('.suggestion-item[data-value]');
            updateSelection(items);
        }
    });
    
    // Clear button handler
    if (clearButton) {
        clearButton.addEventListener('click', () => {
            input.value = '';
            updateClearButton();
            hideSuggestions();
            input.focus();
        });
    }
    
    // Initialize clear button visibility
    updateClearButton();
} 

// auto_play Mode Functions
async function initializeauto_playMode() {
    const auto_playToggle = document.getElementById('auto_playModeToggle');
    const auto_playSettings = document.getElementById('auto_playSettings');
    const auto_playPlaylistSelect = document.getElementById('auto_playPlaylistSelect');
    const auto_playRunModeSelect = document.getElementById('auto_playRunModeSelect');
    const auto_playPauseTimeInput = document.getElementById('auto_playPauseTimeInput');
    const auto_playClearPatternSelect = document.getElementById('auto_playClearPatternSelect');
    const auto_playShuffleToggle = document.getElementById('auto_playShuffleToggle');
    
    // Load current auto_play settings
    try {
        const response = await fetch('/api/auto_play-mode');
        const data = await response.json();
        
        auto_playToggle.checked = data.enabled;
        if (data.enabled) {
            auto_playSettings.style.display = 'block';
        }
        
        // Set current values
        auto_playRunModeSelect.value = data.run_mode || 'loop';
        auto_playPauseTimeInput.value = data.pause_time || 5.0;
        auto_playClearPatternSelect.value = data.clear_pattern || 'adaptive';
        auto_playShuffleToggle.checked = data.shuffle || false;
        
        // Load playlists for selection
        const playlistsResponse = await fetch('/list_all_playlists');
        const playlists = await playlistsResponse.json();
        
        // Clear and populate playlist select
        auto_playPlaylistSelect.innerHTML = '<option value="">Select a playlist...</option>';
        playlists.forEach(playlist => {
            const option = document.createElement('option');
            option.value = playlist;
            option.textContent = playlist;
            if (playlist === data.playlist) {
                option.selected = true;
            }
            auto_playPlaylistSelect.appendChild(option);
        });
    } catch (error) {
        logMessage(`Error loading auto_play settings: ${error.message}`, LOG_TYPE.ERROR);
    }
    
    // Function to save settings
    async function saveSettings() {
        try {
            const response = await fetch('/api/auto_play-mode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: auto_playToggle.checked,
                    playlist: auto_playPlaylistSelect.value || null,
                    run_mode: auto_playRunModeSelect.value,
                    pause_time: parseFloat(auto_playPauseTimeInput.value) || 0,
                    clear_pattern: auto_playClearPatternSelect.value,
                    shuffle: auto_playShuffleToggle.checked
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to save settings');
            }
        } catch (error) {
            logMessage(`Error saving auto_play settings: ${error.message}`, LOG_TYPE.ERROR);
        }
    }
    
    // Toggle auto_play settings visibility and save
    auto_playToggle.addEventListener('change', async () => {
        auto_playSettings.style.display = auto_playToggle.checked ? 'block' : 'none';
        await saveSettings();
    });
    
    // Save when any setting changes
    auto_playPlaylistSelect.addEventListener('change', saveSettings);
    auto_playRunModeSelect.addEventListener('change', saveSettings);
    auto_playPauseTimeInput.addEventListener('change', saveSettings);
    auto_playPauseTimeInput.addEventListener('input', saveSettings); // Save as user types
    auto_playClearPatternSelect.addEventListener('change', saveSettings);
    auto_playShuffleToggle.addEventListener('change', saveSettings);
}

// Initialize auto_play mode when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeauto_playMode();
    initializeStillSandsMode();
    initializeAngularHomingConfig();
});

// Still Sands Mode Functions
async function initializeStillSandsMode() {
    logMessage('Initializing Still Sands mode', LOG_TYPE.INFO);

    const stillSandsToggle = document.getElementById('scheduledPauseToggle');
    const stillSandsSettings = document.getElementById('scheduledPauseSettings');
    const addTimeSlotButton = document.getElementById('addTimeSlotButton');
    const saveStillSandsButton = document.getElementById('savePauseSettings');
    const timeSlotsContainer = document.getElementById('timeSlotsContainer');
    const wledControlToggle = document.getElementById('stillSandsWledControl');

    // Check if elements exist
    if (!stillSandsToggle || !stillSandsSettings || !addTimeSlotButton || !saveStillSandsButton || !timeSlotsContainer) {
        logMessage('Still Sands elements not found, skipping initialization', LOG_TYPE.WARNING);
        logMessage(`Found elements: toggle=${!!stillSandsToggle}, settings=${!!stillSandsSettings}, addBtn=${!!addTimeSlotButton}, saveBtn=${!!saveStillSandsButton}, container=${!!timeSlotsContainer}`, LOG_TYPE.WARNING);
        return;
    }

    logMessage('All Still Sands elements found successfully', LOG_TYPE.INFO);

    // Track time slots
    let timeSlots = [];
    let slotIdCounter = 0;

    // Load current Still Sands settings from initial data
    try {
        // Use the data loaded during page initialization, fallback to API if not available
        let data;
        if (window.initialStillSandsData) {
            data = window.initialStillSandsData;
            // Clear the global variable after use
            delete window.initialStillSandsData;
        } else {
            // Fallback to API call if initial data not available
            const response = await fetch('/api/scheduled-pause');
            data = await response.json();
        }

        stillSandsToggle.checked = data.enabled || false;
        if (data.enabled) {
            stillSandsSettings.style.display = 'block';
        }

        // Load WLED control setting
        if (wledControlToggle) {
            wledControlToggle.checked = data.control_wled || false;
        }

        // Load existing time slots
        timeSlots = data.time_slots || [];

        // Assign IDs to loaded slots BEFORE rendering
        if (timeSlots.length > 0) {
            slotIdCounter = 0;
            timeSlots.forEach(slot => {
                slot.id = ++slotIdCounter;
            });
        }

        renderTimeSlots();
    } catch (error) {
        logMessage(`Error loading Still Sands settings: ${error.message}`, LOG_TYPE.ERROR);
        // Initialize with empty settings if load fails
        timeSlots = [];
        renderTimeSlots();
    }

    // Function to validate time format (HH:MM)
    function isValidTime(timeString) {
        const timeRegex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/;
        return timeRegex.test(timeString);
    }

    // Function to create a new time slot element
    function createTimeSlotElement(slot) {
        const slotDiv = document.createElement('div');
        slotDiv.className = 'time-slot-item';
        slotDiv.dataset.slotId = slot.id;

        slotDiv.innerHTML = `
            <div class="flex items-center gap-3">
                <div class="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div class="flex flex-col gap-1">
                        <label class="text-slate-700 dark:text-slate-300 text-xs font-medium">Start Time</label>
                        <input
                            type="time"
                            class="start-time form-input resize-none overflow-hidden rounded-lg text-slate-900 focus:outline-0 focus:ring-2 focus:ring-sky-500 border border-slate-300 bg-white focus:border-sky-500 h-9 px-3 text-sm font-normal leading-normal transition-colors"
                            value="${slot.start_time || ''}"
                            required
                        />
                    </div>
                    <div class="flex flex-col gap-1">
                        <label class="text-slate-700 dark:text-slate-300 text-xs font-medium">End Time</label>
                        <input
                            type="time"
                            class="end-time form-input resize-none overflow-hidden rounded-lg text-slate-900 focus:outline-0 focus:ring-2 focus:ring-sky-500 border border-slate-300 bg-white focus:border-sky-500 h-9 px-3 text-sm font-normal leading-normal transition-colors"
                            value="${slot.end_time || ''}"
                            required
                        />
                    </div>
                </div>
                <div class="flex flex-col gap-1">
                    <label class="text-slate-700 dark:text-slate-300 text-xs font-medium">Days</label>
                    <select class="days-select form-select resize-none overflow-hidden rounded-lg text-slate-900 focus:outline-0 focus:ring-2 focus:ring-sky-500 border border-slate-300 bg-white focus:border-sky-500 h-9 px-3 text-sm font-normal transition-colors">
                        <option value="daily" ${slot.days === 'daily' ? 'selected' : ''}>Daily</option>
                        <option value="weekdays" ${slot.days === 'weekdays' ? 'selected' : ''}>Weekdays</option>
                        <option value="weekends" ${slot.days === 'weekends' ? 'selected' : ''}>Weekends</option>
                        <option value="custom" ${slot.days === 'custom' ? 'selected' : ''}>Custom</option>
                    </select>
                </div>
                <button
                    type="button"
                    class="remove-slot-btn flex items-center justify-center w-9 h-9 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                    title="Remove time slot"
                >
                    <span class="material-icons text-base">delete</span>
                </button>
            </div>
            <div class="custom-days-container mt-2" style="display: ${slot.days === 'custom' ? 'block' : 'none'};">
                <label class="text-slate-700 dark:text-slate-300 text-xs font-medium mb-1 block">Select Days</label>
                <div class="flex flex-wrap gap-2">
                    ${['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(day => `
                        <label class="flex items-center gap-1 text-xs">
                            <input
                                type="checkbox"
                                name="custom-days-${slot.id}"
                                value="${day}"
                                ${slot.custom_days && slot.custom_days.includes(day) ? 'checked' : ''}
                                class="rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                            />
                            <span class="text-slate-700 dark:text-slate-300 capitalize">${day.substring(0, 3)}</span>
                        </label>
                    `).join('')}
                </div>
            </div>
        `;

        // Add event listeners for this slot
        const startTimeInput = slotDiv.querySelector('.start-time');
        const endTimeInput = slotDiv.querySelector('.end-time');
        const daysSelect = slotDiv.querySelector('.days-select');
        const customDaysContainer = slotDiv.querySelector('.custom-days-container');
        const removeButton = slotDiv.querySelector('.remove-slot-btn');

        // Show/hide custom days based on selection
        daysSelect.addEventListener('change', () => {
            customDaysContainer.style.display = daysSelect.value === 'custom' ? 'block' : 'none';
            updateTimeSlot(slot.id);
        });

        // Update slot data when inputs change
        startTimeInput.addEventListener('change', () => updateTimeSlot(slot.id));
        endTimeInput.addEventListener('change', () => updateTimeSlot(slot.id));

        // Handle custom day checkboxes
        customDaysContainer.addEventListener('change', () => updateTimeSlot(slot.id));

        // Remove slot button
        removeButton.addEventListener('click', () => {
            removeTimeSlot(slot.id);
        });

        return slotDiv;
    }

    // Function to render all time slots
    function renderTimeSlots() {
        timeSlotsContainer.innerHTML = '';

        if (timeSlots.length === 0) {
            timeSlotsContainer.innerHTML = `
                <div class="text-center py-8 text-slate-500 dark:text-slate-400">
                    <span class="material-icons text-4xl mb-2 block">schedule</span>
                    <p>No time slots configured</p>
                    <p class="text-xs mt-1">Click "Add Time Slot" to create a pause schedule</p>
                </div>
            `;
            return;
        }

        timeSlots.forEach(slot => {
            const slotElement = createTimeSlotElement(slot);
            timeSlotsContainer.appendChild(slotElement);
        });
    }

    // Function to add a new time slot
    function addTimeSlot() {
        const newSlot = {
            id: ++slotIdCounter,
            start_time: '22:00',
            end_time: '08:00',
            days: 'daily',
            custom_days: []
        };

        timeSlots.push(newSlot);
        renderTimeSlots();
    }

    // Function to remove a time slot
    function removeTimeSlot(slotId) {
        timeSlots = timeSlots.filter(slot => slot.id !== slotId);
        renderTimeSlots();
    }

    // Function to update a time slot's data
    function updateTimeSlot(slotId) {
        const slotElement = timeSlotsContainer.querySelector(`[data-slot-id="${slotId}"]`);
        if (!slotElement) return;

        const slot = timeSlots.find(s => s.id === slotId);
        if (!slot) return;

        // Update slot data from inputs
        slot.start_time = slotElement.querySelector('.start-time').value;
        slot.end_time = slotElement.querySelector('.end-time').value;
        slot.days = slotElement.querySelector('.days-select').value;

        // Update custom days if applicable
        if (slot.days === 'custom') {
            const checkedDays = Array.from(slotElement.querySelectorAll(`input[name="custom-days-${slotId}"]:checked`))
                .map(cb => cb.value);
            slot.custom_days = checkedDays;
        } else {
            slot.custom_days = [];
        }
    }

    // Function to validate all time slots
    function validateTimeSlots() {
        const errors = [];

        timeSlots.forEach((slot, index) => {
            if (!slot.start_time || !isValidTime(slot.start_time)) {
                errors.push(`Time slot ${index + 1}: Invalid start time`);
            }
            if (!slot.end_time || !isValidTime(slot.end_time)) {
                errors.push(`Time slot ${index + 1}: Invalid end time`);
            }
            if (slot.days === 'custom' && (!slot.custom_days || slot.custom_days.length === 0)) {
                errors.push(`Time slot ${index + 1}: Please select at least one day for custom schedule`);
            }
        });

        return errors;
    }

    // Function to save settings
    async function saveStillSandsSettings() {
        // Update all slots from current form values
        timeSlots.forEach(slot => updateTimeSlot(slot.id));

        // Validate time slots
        const validationErrors = validateTimeSlots();
        if (validationErrors.length > 0) {
            showStatusMessage(`Validation errors: ${validationErrors.join(', ')}`, 'error');
            return;
        }

        // Update button UI to show loading state
        const originalButtonHTML = saveStillSandsButton.innerHTML;
        saveStillSandsButton.disabled = true;
        saveStillSandsButton.innerHTML = '<span class="material-icons text-lg animate-spin">refresh</span><span class="truncate">Saving...</span>';

        try {
            const response = await fetch('/api/scheduled-pause', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: stillSandsToggle.checked,
                    control_wled: wledControlToggle ? wledControlToggle.checked : false,
                    time_slots: timeSlots.map(slot => ({
                        start_time: slot.start_time,
                        end_time: slot.end_time,
                        days: slot.days,
                        custom_days: slot.custom_days
                    }))
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save Still Sands settings');
            }

            // Show success state temporarily
            saveStillSandsButton.innerHTML = '<span class="material-icons text-lg">check</span><span class="truncate">Saved!</span>';
            showStatusMessage('Still Sands settings saved successfully', 'success');

            // Restore button after 2 seconds
            setTimeout(() => {
                saveStillSandsButton.innerHTML = originalButtonHTML;
                saveStillSandsButton.disabled = false;
            }, 2000);
        } catch (error) {
            logMessage(`Error saving Still Sands settings: ${error.message}`, LOG_TYPE.ERROR);
            showStatusMessage(`Failed to save settings: ${error.message}`, 'error');

            // Restore button immediately on error
            saveStillSandsButton.innerHTML = originalButtonHTML;
            saveStillSandsButton.disabled = false;
        }
    }

    // Note: Slot IDs are now assigned during initialization above, before first render

    // Event listeners
    stillSandsToggle.addEventListener('change', async () => {
        logMessage(`Still Sands toggle changed: ${stillSandsToggle.checked}`, LOG_TYPE.INFO);
        stillSandsSettings.style.display = stillSandsToggle.checked ? 'block' : 'none';
        logMessage(`Settings display set to: ${stillSandsSettings.style.display}`, LOG_TYPE.INFO);

        // Auto-save when toggle changes
        try {
            await saveStillSandsSettings();
            const statusText = stillSandsToggle.checked ? 'enabled' : 'disabled';
            showStatusMessage(`Still Sands ${statusText} successfully`, 'success');
        } catch (error) {
            logMessage(`Error saving Still Sands toggle: ${error.message}`, LOG_TYPE.ERROR);
            showStatusMessage(`Failed to save Still Sands setting: ${error.message}`, 'error');
        }
    });

    addTimeSlotButton.addEventListener('click', addTimeSlot);
    saveStillSandsButton.addEventListener('click', saveStillSandsSettings);

    // Add listener for WLED control toggle
    if (wledControlToggle) {
        wledControlToggle.addEventListener('change', async () => {
            logMessage(`WLED control toggle changed: ${wledControlToggle.checked}`, LOG_TYPE.INFO);
            // Auto-save when WLED control changes
            await saveStillSandsSettings();
        });
    }
}

// Desert Compass Configuration Functions
async function initializeAngularHomingConfig() {
    logMessage('Initializing Desert Compass configuration', LOG_TYPE.INFO);

    const angularHomingToggle = document.getElementById('angularHomingToggle');
    const angularHomingInfo = document.getElementById('angularHomingInfo');
    const gpioSelectionContainer = document.getElementById('gpioSelectionContainer');
    const gpioInput = document.getElementById('gpioInput');
    const invertStateContainer = document.getElementById('invertStateContainer');
    const invertStateToggle = document.getElementById('invertStateToggle');
    const angularOffsetContainer = document.getElementById('angularOffsetContainer');
    const angularOffsetInput = document.getElementById('angularOffsetInput');
    const saveHomingConfigButton = document.getElementById('saveHomingConfig');

    // Check if elements exist
    if (!angularHomingToggle || !angularHomingInfo || !saveHomingConfigButton ||
        !gpioSelectionContainer || !gpioInput || !invertStateContainer ||
        !invertStateToggle || !angularOffsetContainer || !angularOffsetInput) {
        logMessage('Desert Compass elements not found, skipping initialization', LOG_TYPE.WARNING);
        return;
    }

    logMessage('All Desert Compass elements found successfully', LOG_TYPE.INFO);

    // Load current Desert Compass settings
    try {
        const response = await fetch('/api/angular-homing');
        const data = await response.json();

        angularHomingToggle.checked = data.angular_homing_enabled || false;
        gpioInput.value = data.angular_homing_gpio_pin || 18;
        invertStateToggle.checked = data.angular_homing_invert_state || false;
        angularOffsetInput.value = data.angular_homing_offset_degrees || 0;

        if (data.angular_homing_enabled) {
            angularHomingInfo.style.display = 'block';
            gpioSelectionContainer.style.display = 'block';
            invertStateContainer.style.display = 'block';
            angularOffsetContainer.style.display = 'block';
        }
    } catch (error) {
        logMessage(`Error loading Desert Compass settings: ${error.message}`, LOG_TYPE.ERROR);
        // Initialize with defaults if load fails
        angularHomingToggle.checked = false;
        gpioInput.value = 18;
        invertStateToggle.checked = false;
        angularOffsetInput.value = 0;
        angularHomingInfo.style.display = 'none';
        gpioSelectionContainer.style.display = 'none';
        invertStateContainer.style.display = 'none';
        angularOffsetContainer.style.display = 'none';
    }

    // Function to save Desert Compass settings
    async function saveAngularHomingSettings() {
        // Validate GPIO pin
        const gpioPin = parseInt(gpioInput.value);
        if (isNaN(gpioPin) || gpioPin < 2 || gpioPin > 27) {
            showStatusMessage('GPIO pin must be between 2 and 27', 'error');
            return;
        }

        // Update button UI to show loading state
        const originalButtonHTML = saveHomingConfigButton.innerHTML;
        saveHomingConfigButton.disabled = true;
        saveHomingConfigButton.innerHTML = '<span class="material-icons text-lg animate-spin">refresh</span><span class="truncate">Saving...</span>';

        try {
            const response = await fetch('/api/angular-homing', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    angular_homing_enabled: angularHomingToggle.checked,
                    angular_homing_gpio_pin: gpioPin,
                    angular_homing_invert_state: invertStateToggle.checked,
                    angular_homing_offset_degrees: parseFloat(angularOffsetInput.value) || 0
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save Desert Compass settings');
            }

            // Show success state temporarily
            saveHomingConfigButton.innerHTML = '<span class="material-icons text-lg">check</span><span class="truncate">Saved!</span>';
            showStatusMessage('Desert Compass configuration saved successfully', 'success');

            // Restore button after 2 seconds
            setTimeout(() => {
                saveHomingConfigButton.innerHTML = originalButtonHTML;
                saveHomingConfigButton.disabled = false;
            }, 2000);
        } catch (error) {
            logMessage(`Error saving Desert Compass settings: ${error.message}`, LOG_TYPE.ERROR);
            showStatusMessage(`Failed to save settings: ${error.message}`, 'error');

            // Restore button immediately on error
            saveHomingConfigButton.innerHTML = originalButtonHTML;
            saveHomingConfigButton.disabled = false;
        }
    }

    // Event listeners
    angularHomingToggle.addEventListener('change', () => {
        logMessage(`Desert Compass toggle changed: ${angularHomingToggle.checked}`, LOG_TYPE.INFO);
        const isEnabled = angularHomingToggle.checked;
        angularHomingInfo.style.display = isEnabled ? 'block' : 'none';
        gpioSelectionContainer.style.display = isEnabled ? 'block' : 'none';
        invertStateContainer.style.display = isEnabled ? 'block' : 'none';
        angularOffsetContainer.style.display = isEnabled ? 'block' : 'none';
        logMessage(`Info display set to: ${angularHomingInfo.style.display}`, LOG_TYPE.INFO);
    });

    saveHomingConfigButton.addEventListener('click', saveAngularHomingSettings);
}
