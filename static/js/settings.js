// Constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Helper function to convert provider name to camelCase for ID lookup
// e.g., "dw_leds" -> "DwLeds", "wled" -> "Wled", "none" -> "None"
function providerToCamelCase(provider) {
    return provider.split('_').map(word =>
        word.charAt(0).toUpperCase() + word.slice(1)
    ).join('');
}

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

// Handle LED provider selection and show/hide appropriate config sections
function updateLedProviderUI() {
    const provider = document.querySelector('input[name="ledProvider"]:checked')?.value || 'none';
    const wledConfig = document.getElementById('wledConfig');
    const dwLedsConfig = document.getElementById('dwLedsConfig');

    if (wledConfig && dwLedsConfig) {
        if (provider === 'wled') {
            wledConfig.classList.remove('hidden');
            dwLedsConfig.classList.add('hidden');
        } else if (provider === 'dw_leds') {
            wledConfig.classList.add('hidden');
            dwLedsConfig.classList.remove('hidden');
        } else {
            wledConfig.classList.add('hidden');
            dwLedsConfig.classList.add('hidden');
        }
    }
}

// Load LED configuration from server
async function loadLedConfig() {
    try {
        const response = await fetch('/get_led_config');
        if (response.ok) {
            const data = await response.json();

            // Set provider radio button
            const providerRadio = document.getElementById(`ledProvider${providerToCamelCase(data.provider)}`);
            if (providerRadio) {
                providerRadio.checked = true;
            } else {
                document.getElementById('ledProviderNone').checked = true;
            }

            // Set WLED IP if configured
            if (data.wled_ip) {
                const wledIpInput = document.getElementById('wledIpInput');
                if (wledIpInput) {
                    wledIpInput.value = data.wled_ip;
                }
            }

            // Set DW LED configuration if configured
            if (data.dw_led_num_leds) {
                const numLedsInput = document.getElementById('dwLedNumLeds');
                if (numLedsInput) {
                    numLedsInput.value = data.dw_led_num_leds;
                }
            }
            if (data.dw_led_gpio_pin) {
                const gpioPinInput = document.getElementById('dwLedGpioPin');
                if (gpioPinInput) {
                    gpioPinInput.value = data.dw_led_gpio_pin;
                }
            }
            if (data.dw_led_pixel_order) {
                const pixelOrderInput = document.getElementById('dwLedPixelOrder');
                if (pixelOrderInput) {
                    pixelOrderInput.value = data.dw_led_pixel_order;
                }
            }

            // Update UI to show correct config section
            updateLedProviderUI();
        }
    } catch (error) {
        logMessage(`Error loading LED config: ${error.message}`, LOG_TYPE.ERROR);
    }
}

// Initialize settings page
document.addEventListener('DOMContentLoaded', async () => {
    // Initialize UI with default disconnected state
    updateConnectionUI({ connected: false });

    // Handle scroll to section if hash is present in URL
    if (window.location.hash) {
        setTimeout(() => {
            const targetSection = document.querySelector(window.location.hash);
            if (targetSection) {
                targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                // Add a subtle highlight animation
                targetSection.style.transition = 'background-color 0.5s ease';
                const originalBg = targetSection.style.backgroundColor;
                targetSection.style.backgroundColor = 'rgba(14, 165, 233, 0.1)';
                setTimeout(() => {
                    targetSection.style.backgroundColor = originalBg;
                }, 2000);
            }
        }, 300); // Delay to ensure page is fully loaded
    }
    
    // Load all data asynchronously
    Promise.all([
        // Check connection status
        fetch('/serial_status').then(response => response.json()).catch(() => ({ connected: false })),

        // Load LED configuration (replaces old WLED-only loading)
        fetch('/get_led_config').then(response => response.json()).catch(() => ({ provider: 'none', wled_ip: null })),
        
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
    ]).then(([statusData, ledConfigData, updateData, ports, patterns, clearPatterns, clearSpeedData, appNameData, scheduledPauseData]) => {
        // Update connection status
        setCachedConnectionStatus(statusData);
        updateConnectionUI(statusData);

        // Update LED configuration
        const providerRadio = document.getElementById(`ledProvider${providerToCamelCase(ledConfigData.provider)}`);
        if (providerRadio) {
            providerRadio.checked = true;
        } else {
            document.getElementById('ledProviderNone').checked = true;
        }

        if (ledConfigData.wled_ip) {
            const wledIpInput = document.getElementById('wledIpInput');
            if (wledIpInput) wledIpInput.value = ledConfigData.wled_ip;
        }

        // Load DW LED settings
        if (ledConfigData.dw_led_num_leds) {
            const numLedsInput = document.getElementById('dwLedNumLeds');
            if (numLedsInput) numLedsInput.value = ledConfigData.dw_led_num_leds;
        }
        if (ledConfigData.dw_led_gpio_pin) {
            const gpioPinInput = document.getElementById('dwLedGpioPin');
            if (gpioPinInput) gpioPinInput.value = ledConfigData.dw_led_gpio_pin;
        }
        if (ledConfigData.dw_led_pixel_order) {
            const pixelOrderInput = document.getElementById('dwLedPixelOrder');
            if (pixelOrderInput) pixelOrderInput.value = ledConfigData.dw_led_pixel_order;
        }

        updateLedProviderUI()
        
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
    
    // LED provider selection change handlers
    const ledProviderRadios = document.querySelectorAll('input[name="ledProvider"]');
    ledProviderRadios.forEach(radio => {
        radio.addEventListener('change', updateLedProviderUI);
    });

    // Save LED configuration
    const saveLedConfig = document.getElementById('saveLedConfig');
    if (saveLedConfig) {
        saveLedConfig.addEventListener('click', async () => {
            const provider = document.querySelector('input[name="ledProvider"]:checked')?.value || 'none';

            let requestBody = { provider };

            if (provider === 'wled') {
                const wledIp = document.getElementById('wledIpInput')?.value;
                if (!wledIp) {
                    showStatusMessage('Please enter a WLED IP address', 'error');
                    return;
                }
                requestBody.ip_address = wledIp;
            } else if (provider === 'dw_leds') {
                const numLeds = parseInt(document.getElementById('dwLedNumLeds')?.value) || 60;
                const gpioPin = parseInt(document.getElementById('dwLedGpioPin')?.value) || 12;
                const pixelOrder = document.getElementById('dwLedPixelOrder')?.value || 'GRB';

                requestBody.num_leds = numLeds;
                requestBody.gpio_pin = gpioPin;
                requestBody.pixel_order = pixelOrder;
            }

            try {
                const response = await fetch('/set_led_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (response.ok) {
                    const data = await response.json();

                    if (provider === 'wled' && data.wled_ip) {
                        localStorage.setItem('wled_ip', data.wled_ip);
                        showStatusMessage('WLED configured successfully', 'success');
                    } else if (provider === 'dw_leds') {
                        // Check if there's a warning (hardware not available but settings saved)
                        if (data.warning) {
                            showStatusMessage(
                                `Settings saved for testing. Hardware issue: ${data.warning}`,
                                'warning'
                            );
                        } else {
                            showStatusMessage(
                                `DW LEDs configured: ${data.dw_led_num_leds} LEDs on GPIO${data.dw_led_gpio_pin}`,
                                'success'
                            );
                        }
                    } else if (provider === 'none') {
                        localStorage.removeItem('wled_ip');
                        showStatusMessage('LED controller disabled', 'success');
                    }
                } else {
                    // Extract error detail from response
                    const errorData = await response.json().catch(() => ({}));
                    const errorMessage = errorData.detail || 'Failed to save LED configuration';
                    showStatusMessage(errorMessage, 'error');
                }
            } catch (error) {
                showStatusMessage(`Failed to save LED configuration: ${error.message}`, 'error');
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
    initializeHomingConfig();
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

// Homing Configuration
async function initializeHomingConfig() {
    logMessage('Initializing homing configuration', LOG_TYPE.INFO);

    const homingModeCrash = document.getElementById('homingModeCrash');
    const homingModeSensor = document.getElementById('homingModeSensor');
    const angularOffsetInput = document.getElementById('angularOffsetInput');
    const compassOffsetContainer = document.getElementById('compassOffsetContainer');
    const saveHomingConfigButton = document.getElementById('saveHomingConfig');
    const homingInfoContent = document.getElementById('homingInfoContent');

    // Check if elements exist
    if (!homingModeCrash || !homingModeSensor || !angularOffsetInput || !saveHomingConfigButton || !homingInfoContent || !compassOffsetContainer) {
        logMessage('Homing configuration elements not found, skipping initialization', LOG_TYPE.WARNING);
        return;
    }

    logMessage('Homing configuration elements found successfully', LOG_TYPE.INFO);

    // Function to get selected homing mode
    function getSelectedMode() {
        return homingModeCrash.checked ? 0 : 1;
    }

    // Function to update info box and visibility based on selected mode
    function updateHomingInfo() {
        const mode = getSelectedMode();

        // Show/hide compass offset based on mode
        if (mode === 0) {
            compassOffsetContainer.style.display = 'none';
            homingInfoContent.innerHTML = `
                <p class="font-medium text-blue-800">Crash Homing Mode:</p>
                <ul class="mt-1 space-y-1 text-blue-700">
                    <li>• Y axis moves -22mm (or -30mm for mini) until physical stop</li>
                    <li>• Theta set to 0, rho set to 0</li>
                    <li>• No x0 y0 command sent</li>
                    <li>• No hardware sensors required</li>
                </ul>
            `;
        } else {
            compassOffsetContainer.style.display = 'block';
            homingInfoContent.innerHTML = `
                <p class="font-medium text-blue-800">Sensor Homing Mode:</p>
                <ul class="mt-1 space-y-1 text-blue-700">
                    <li>• Requires hardware limit switches</li>
                    <li>• Requires additional configuration</li>
                </ul>
            `;
        }
    }

    // Load current homing configuration
    try {
        const response = await fetch('/api/homing-config');
        const data = await response.json();

        // Set radio button based on mode
        if (data.homing_mode === 1) {
            homingModeSensor.checked = true;
        } else {
            homingModeCrash.checked = true;
        }

        angularOffsetInput.value = data.angular_homing_offset_degrees || 0;
        updateHomingInfo();

        logMessage(`Loaded homing config: mode=${data.homing_mode}, offset=${data.angular_homing_offset_degrees}°`, LOG_TYPE.INFO);
    } catch (error) {
        logMessage(`Error loading homing configuration: ${error.message}`, LOG_TYPE.ERROR);
        // Initialize with defaults if load fails
        homingModeCrash.checked = true;
        angularOffsetInput.value = 0;
        updateHomingInfo();
    }

    // Function to save homing configuration
    async function saveHomingConfig() {
        // Update button UI to show loading state
        const originalButtonHTML = saveHomingConfigButton.innerHTML;
        saveHomingConfigButton.disabled = true;
        saveHomingConfigButton.innerHTML = '<span class="material-icons text-lg animate-spin">refresh</span><span class="truncate">Saving...</span>';

        try {
            const response = await fetch('/api/homing-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    homing_mode: getSelectedMode(),
                    angular_homing_offset_degrees: parseFloat(angularOffsetInput.value) || 0
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save homing configuration');
            }

            // Show success state temporarily
            saveHomingConfigButton.innerHTML = '<span class="material-icons text-lg">check</span><span class="truncate">Saved!</span>';
            showStatusMessage('Homing configuration saved successfully', 'success');

            // Restore button after 2 seconds
            setTimeout(() => {
                saveHomingConfigButton.innerHTML = originalButtonHTML;
                saveHomingConfigButton.disabled = false;
            }, 2000);
        } catch (error) {
            logMessage(`Error saving homing configuration: ${error.message}`, LOG_TYPE.ERROR);
            showStatusMessage(`Failed to save homing configuration: ${error.message}`, 'error');

            // Restore button immediately on error
            saveHomingConfigButton.innerHTML = originalButtonHTML;
            saveHomingConfigButton.disabled = false;
        }
    }

    // Event listeners
    homingModeCrash.addEventListener('change', updateHomingInfo);
    homingModeSensor.addEventListener('change', updateHomingInfo);
    saveHomingConfigButton.addEventListener('click', saveHomingConfig);
}

// ==================== Ball Tracking Configuration ====================

async function initBallTracking() {
    // Elements
    const ballTrackingEnabled = document.getElementById('ballTrackingEnabled');
    const ballTrackingSettings = document.getElementById('ballTrackingSettings');
    const ballTrackingMode = document.getElementById('ballTrackingMode');
    const ballTrackingSpread = document.getElementById('ballTrackingSpread');
    const ballTrackingSpreadValue = document.getElementById('ballTrackingSpreadValue');
    const ballTrackingBrightness = document.getElementById('ballTrackingBrightness');
    const ballTrackingBrightnessValue = document.getElementById('ballTrackingBrightnessValue');
    const ballTrackingColor = document.getElementById('ballTrackingColor');
    const saveBallTrackingConfig = document.getElementById('saveBallTrackingConfig');

    // Load current settings
    try {
        const response = await fetch('/api/ball_tracking/status');
        const data = await response.json();

        if (data.success) {
            ballTrackingEnabled.checked = data.enabled;
            ballTrackingMode.value = data.mode;
            ballTrackingSpread.value = data.config.spread;
            ballTrackingSpreadValue.textContent = `${data.config.spread} LED${data.config.spread > 1 ? 's' : ''}`;
            ballTrackingBrightness.value = data.config.brightness;
            ballTrackingBrightnessValue.textContent = `${data.config.brightness}%`;
            ballTrackingColor.value = data.config.color;

            // Show settings if enabled
            if (data.enabled) {
                ballTrackingSettings.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Failed to load ball tracking settings:', error);
    }

    // Enable/Disable toggle
    ballTrackingEnabled.addEventListener('change', () => {
        if (ballTrackingEnabled.checked) {
            ballTrackingSettings.style.display = 'block';
        } else {
            ballTrackingSettings.style.display = 'none';
        }
    });

    // Slider value updates
    ballTrackingSpread.addEventListener('input', () => {
        const value = parseInt(ballTrackingSpread.value);
        ballTrackingSpreadValue.textContent = `${value} LED${value > 1 ? 's' : ''}`;
    });

    ballTrackingBrightness.addEventListener('input', () => {
        const value = parseInt(ballTrackingBrightness.value);
        ballTrackingBrightnessValue.textContent = `${value}%`;
    });

    // Save configuration
    saveBallTrackingConfig.addEventListener('click', async () => {
        const originalHTML = saveBallTrackingConfig.innerHTML;
        saveBallTrackingConfig.innerHTML = '<span class="material-icons animate-spin">refresh</span><span>Saving...</span>';
        saveBallTrackingConfig.disabled = true;

        try {
            const config = {
                enabled: ballTrackingEnabled.checked,
                mode: ballTrackingMode.value,
                spread: parseInt(ballTrackingSpread.value),
                lookback: 0,  // Lookback disabled - always use instant tracking
                brightness: parseInt(ballTrackingBrightness.value),
                color: ballTrackingColor.value
            };

            const response = await fetch('/api/ball_tracking/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });

            const data = await response.json();

            if (data.success) {
                showStatusMessage('Ball tracking configuration saved!', 'success');
            } else {
                throw new Error(data.message || 'Failed to save configuration');
            }
        } catch (error) {
            console.error('Error saving ball tracking config:', error);
            showStatusMessage(`Failed to save: ${error.message}`, 'error');
        } finally {
            saveBallTrackingConfig.innerHTML = originalHTML;
            saveBallTrackingConfig.disabled = false;
        }
    });
}

// ==================== Calibration Wizard ====================

function initCalibrationWizard() {
    // Modal elements
    const openWizardBtn = document.getElementById('openCalibrationWizard');
    const calibrationModal = document.getElementById('calibrationModal');
    const closeModalBtn = document.getElementById('closeCalibrationModal');
    const closeCompleteBtn = document.getElementById('closeCalibrationComplete');

    // Step elements
    const step1 = document.getElementById('calibrationStep1');
    const step2 = document.getElementById('calibrationStep2');
    const complete = document.getElementById('calibrationComplete');

    // Step indicators
    const step1Indicator = document.getElementById('step1Indicator');
    const step2Indicator = document.getElementById('step2Indicator');
    const line1 = document.getElementById('line1');

    // Action buttons
    const startMoveBtn = document.getElementById('startCalibrationMove');
    const moveStatus = document.getElementById('calibrationMoveStatus');
    const confirmCalibrationBtn = document.getElementById('confirmCalibration');

    // LED navigation buttons
    const ledPrev1 = document.getElementById('ledPrev1');
    const ledNext1 = document.getElementById('ledNext1');
    const ledPrev5 = document.getElementById('ledPrev5');
    const ledNext5 = document.getElementById('ledNext5');
    const currentLedNumber = document.getElementById('currentLedNumber');
    const ledStatusText = document.getElementById('ledStatusText');
    const reverseDirectionToggle = document.getElementById('reverseDirectionToggle');

    // State
    let numLeds = 60;
    let currentLed = 0;
    let reversed = false;

    // Open wizard
    openWizardBtn.addEventListener('click', () => {
        calibrationModal.classList.remove('hidden');
        resetWizard();
    });

    // Close wizard
    function closeWizard() {
        calibrationModal.classList.add('hidden');
        resetWizard();
    }

    closeModalBtn.addEventListener('click', closeWizard);
    closeCompleteBtn.addEventListener('click', closeWizard);

    // Reset wizard to step 1
    function resetWizard() {
        showStep(1);
        currentLed = 0;
        reversed = false;
        moveStatus.classList.add('hidden');
        reverseDirectionToggle.checked = false;
    }

    // Show specific step
    function showStep(stepNum) {
        // Hide all steps
        step1.classList.add('hidden');
        step2.classList.add('hidden');
        complete.classList.add('hidden');

        // Reset indicators
        [step1Indicator, step2Indicator].forEach(ind => {
            ind.classList.remove('bg-sky-600', 'text-white', 'bg-green-600');
            ind.classList.add('bg-slate-200', 'text-slate-500');
        });
        line1.classList.remove('bg-sky-600');

        // Show active step
        if (stepNum === 1) {
            step1.classList.remove('hidden');
            step1Indicator.classList.remove('bg-slate-200', 'text-slate-500');
            step1Indicator.classList.add('bg-sky-600', 'text-white');
        } else if (stepNum === 2) {
            step2.classList.remove('hidden');
            step1Indicator.classList.remove('bg-slate-200', 'text-slate-500');
            step1Indicator.classList.add('bg-green-600', 'text-white');
            step2Indicator.classList.remove('bg-slate-200', 'text-slate-500');
            step2Indicator.classList.add('bg-sky-600', 'text-white');
            line1.classList.add('bg-sky-600');
        } else if (stepNum === 'complete') {
            complete.classList.remove('hidden');
            [step1Indicator, step2Indicator].forEach(ind => {
                ind.classList.remove('bg-slate-200', 'text-slate-500');
                ind.classList.add('bg-green-600', 'text-white');
            });
            line1.classList.add('bg-sky-600');
        }
    }

    // Step 1: Move to reference
    startMoveBtn.addEventListener('click', async () => {
        startMoveBtn.disabled = true;
        moveStatus.classList.remove('hidden');

        try {
            const response = await fetch('/api/ball_tracking/calibrate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            });

            const data = await response.json();

            if (data.success) {
                numLeds = data.num_leds;
                currentLed = 0;
                showStatusMessage('Ball moved to reference position!', 'success');
                updateLEDDisplay();
                showStep(2);
            } else {
                throw new Error(data.detail || 'Calibration failed');
            }
        } catch (error) {
            console.error('Calibration error:', error);
            showStatusMessage(`Calibration failed: ${error.message}`, 'error');
            startMoveBtn.disabled = false;
            moveStatus.classList.add('hidden');
        }
    });

    // Update LED display
    function updateLEDDisplay() {
        currentLedNumber.textContent = currentLed;
        ledStatusText.textContent = 'This LED is now lit on your strip';
    }

    // Navigate to specific LED and light it
    async function navigateToLED(newLedIndex) {
        // Wrap around LED count
        currentLed = ((newLedIndex % numLeds) + numLeds) % numLeds;

        // Update UI
        updateLEDDisplay();

        // Light up the physical LED
        try {
            const response = await fetch('/api/ball_tracking/test_led', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ led_index: currentLed })
            });

            const data = await response.json();
            if (!data.success) {
                ledStatusText.textContent = 'Failed to light LED';
            }
        } catch (error) {
            console.error('Failed to light LED:', error);
            ledStatusText.textContent = 'Error lighting LED';
        }
    }

    // LED navigation button handlers (direction reverses when toggle is on)
    ledPrev1.addEventListener('click', () => {
        const direction = reversed ? 1 : -1;  // Reverse button direction if toggle is on
        navigateToLED(currentLed + direction);
    });
    ledNext1.addEventListener('click', () => {
        const direction = reversed ? -1 : 1;  // Reverse button direction if toggle is on
        navigateToLED(currentLed + direction);
    });
    ledPrev5.addEventListener('click', () => {
        const direction = reversed ? 5 : -5;  // Reverse button direction if toggle is on
        navigateToLED(currentLed + direction);
    });
    ledNext5.addEventListener('click', () => {
        const direction = reversed ? -5 : 5;  // Reverse button direction if toggle is on
        navigateToLED(currentLed + direction);
    });

    // Reverse direction toggle
    reverseDirectionToggle.addEventListener('change', () => {
        reversed = reverseDirectionToggle.checked;
        console.log('Toggle changed! Reversed:', reversed);

        // Visual feedback - find the <p> element more robustly
        const container = reverseDirectionToggle.closest('.flex');
        console.log('Found container:', container);

        if (container) {
            const directionLabel = container.querySelector('p');
            console.log('Found label:', directionLabel);

            if (directionLabel) {
                if (reversed) {
                    directionLabel.textContent = 'LED strip runs counter-clockwise (REVERSED)';
                    directionLabel.classList.add('font-semibold', 'text-orange-600');
                } else {
                    directionLabel.textContent = 'Enable if your LED strip runs counter-clockwise';
                    directionLabel.classList.remove('font-semibold', 'text-orange-600');
                }
                console.log('Label updated successfully');
            } else {
                console.error('Could not find label element');
            }
        } else {
            console.error('Could not find container element');
        }
    });

    // Confirm calibration
    confirmCalibrationBtn.addEventListener('click', async () => {
        await completeCalibration();
    });

    // Complete calibration
    async function completeCalibration() {
        try {
            // Save calibration settings
            const config = {
                led_offset: currentLed,
                reversed: reversed
            };

            console.log('=== CALIBRATION COMPLETION ===');
            console.log('Current LED:', currentLed);
            console.log('Reversed flag:', reversed);
            console.log('Toggle checked state:', reverseDirectionToggle.checked);
            console.log('Sending config:', JSON.stringify(config));

            const response = await fetch('/api/ball_tracking/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });

            const data = await response.json();
            console.log('Backend response:', data);
            console.log('=== END CALIBRATION ===');

            if (data.success) {
                // Show completion
                document.getElementById('finalLedOffset').textContent = currentLed;
                document.getElementById('finalDirection').textContent = reversed ? 'Reversed (Counter-Clockwise)' : 'Normal (Clockwise)';
                showStep('complete');
                showStatusMessage('Calibration complete!', 'success');
            } else {
                throw new Error(data.message || 'Failed to save calibration');
            }
        } catch (error) {
            console.error('Failed to save calibration:', error);
            showStatusMessage(`Failed to save: ${error.message}`, 'error');
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initBallTracking();
    initCalibrationWizard();
});
