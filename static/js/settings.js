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
        fetch('/check_software_update').then(response => response.json()).catch(() => ({ current_version: '1.0.0', update_available: false })),
        
        // Load available serial ports
        fetch('/list_serial_ports').then(response => response.json()).catch(() => [])
    ]).then(([statusData, wledData, updateData, ports]) => {
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
        document.querySelector('.text-slate-500.text-sm.font-normal.leading-normal').textContent = updateData.current_version;
        
        // Show/hide update button
        const updateButton = document.getElementById('updateSoftware');
        if (updateButton) {
            updateButton.style.display = updateData.update_available ? 'flex' : 'none';
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
    }).catch(error => {
        logMessage(`Error initializing settings page: ${error.message}`, LOG_TYPE.ERROR);
    });

    // Set up event listeners
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
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
            try {
                const response = await fetch('/update_software', {
                    method: 'POST'
                });
                if (response.ok) {
                    logMessage('Software update started successfully', LOG_TYPE.SUCCESS);
                } else {
                    throw new Error('Failed to start software update');
                }
            } catch (error) {
                logMessage(`Error updating software: ${error.message}`, LOG_TYPE.ERROR);
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
}

// Button click handlers
document.addEventListener('DOMContentLoaded', function() {
    // Home button
    const homeButton = document.getElementById('homeButton');
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

    // Stop button
    const stopButton = document.getElementById('stopButton');
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

    // Move to Center button
    const centerButton = document.getElementById('centerButton');
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

    // Move to Perimeter button
    const perimeterButton = document.getElementById('perimeterButton');
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