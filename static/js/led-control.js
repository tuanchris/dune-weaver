// LED Control Page - Unified interface for WLED and Hyperion

let ledConfig = null;
let hyperionController = null;

// Utility function to show status messages
function showStatus(message, type = 'info') {
    const statusDiv = document.getElementById('hyperion-status');
    if (!statusDiv) return;

    const iconMap = {
        'success': 'check_circle',
        'error': 'error',
        'warning': 'warning',
        'info': 'info'
    };

    const colorMap = {
        'success': 'text-green-700 bg-green-50 border-green-200',
        'error': 'text-red-700 bg-red-50 border-red-200',
        'warning': 'text-amber-700 bg-amber-50 border-amber-200',
        'info': 'text-gray-700 bg-gray-100 border-slate-200'
    };

    const icon = iconMap[type] || 'info';
    const colorClass = colorMap[type] || colorMap.info;

    statusDiv.className = `p-4 rounded-lg border ${colorClass}`;
    statusDiv.innerHTML = `
        <div class="flex items-center gap-2">
            <span class="material-icons">${icon}</span>
            <span class="text-sm">${message}</span>
        </div>
    `;
}

// Initialize the page based on LED configuration
async function initializeLedPage() {
    try {
        const response = await fetch('/get_led_config');
        if (!response.ok) throw new Error('Failed to fetch LED config');

        ledConfig = await response.json();

        const notConfigured = document.getElementById('led-not-configured');
        const wledContainer = document.getElementById('wled-container');
        const hyperionContainer = document.getElementById('hyperion-container');

        // Hide all containers first
        notConfigured.classList.add('hidden');
        wledContainer.classList.add('hidden');
        hyperionContainer.classList.add('hidden');

        if (ledConfig.provider === 'wled' && ledConfig.wled_ip) {
            // Show WLED iframe
            wledContainer.classList.remove('hidden');
            const wledFrame = document.getElementById('wled-frame');
            if (wledFrame) {
                wledFrame.src = `http://${ledConfig.wled_ip}`;
            }
        } else if (ledConfig.provider === 'hyperion' && ledConfig.hyperion_ip) {
            // Show Hyperion controls
            hyperionContainer.classList.remove('hidden');
            await initializeHyperionControls();
        } else {
            // Show not configured message
            notConfigured.classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error initializing LED page:', error);
        document.getElementById('led-not-configured').classList.remove('hidden');
    }
}

// Initialize Hyperion controls
async function initializeHyperionControls() {
    // Create API helper
    hyperionController = {
        async sendCommand(endpoint, data) {
            try {
                const response = await fetch(`/api/hyperion/${endpoint}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
            } catch (error) {
                throw error;
            }
        }
    };

    // Check connection status and load effects
    await checkHyperionStatus();
    await loadEffectsList();

    // Power toggle button
    document.getElementById('hyperion-power-toggle')?.addEventListener('click', async () => {
        try {
            // Toggle using state 2
            await hyperionController.sendCommand('power', { state: 2 });
            showStatus('Power toggled', 'success');
            await checkHyperionStatus();
        } catch (error) {
            showStatus(`Failed to toggle power: ${error.message}`, 'error');
        }
    });

    // Brightness slider
    const brightnessSlider = document.getElementById('hyperion-brightness');
    const brightnessValue = document.getElementById('brightness-value');

    brightnessSlider?.addEventListener('input', (e) => {
        brightnessValue.textContent = `${e.target.value}%`;
    });

    brightnessSlider?.addEventListener('change', async (e) => {
        try {
            await hyperionController.sendCommand('brightness', { value: parseInt(e.target.value) });
            showStatus(`Brightness set to ${e.target.value}%`, 'success');
        } catch (error) {
            showStatus(`Failed to set brightness: ${error.message}`, 'error');
        }
    });

    // Color picker - update display when color changes
    const colorPicker = document.getElementById('hyperion-color');
    const colorHexDisplay = document.getElementById('color-hex-display');

    colorPicker?.addEventListener('input', (e) => {
        if (colorHexDisplay) {
            colorHexDisplay.textContent = e.target.value.toUpperCase();
        }
    });

    // Color picker - apply button
    document.getElementById('hyperion-set-color')?.addEventListener('click', async () => {
        const hexColor = colorPicker.value;

        try {
            await hyperionController.sendCommand('color', { hex: hexColor });
            showStatus(`Color set to ${hexColor.toUpperCase()}`, 'success');
        } catch (error) {
            showStatus(`Failed to set color: ${error.message}`, 'error');
        }
    });

    // Quick color buttons
    document.querySelectorAll('.quick-color').forEach(button => {
        button.addEventListener('click', async () => {
            const hexColor = button.getAttribute('data-color');

            try {
                await hyperionController.sendCommand('color', { hex: hexColor });
                showStatus(`Color set to ${hexColor.toUpperCase()}`, 'success');

                // Update color picker and hex display to match
                const colorPicker = document.getElementById('hyperion-color');
                const colorHexDisplay = document.getElementById('color-hex-display');
                if (colorPicker) colorPicker.value = hexColor;
                if (colorHexDisplay) colorHexDisplay.textContent = hexColor.toUpperCase();
            } catch (error) {
                showStatus(`Failed to set color: ${error.message}`, 'error');
            }
        });
    });

    // Effects selection
    document.getElementById('hyperion-set-effect')?.addEventListener('click', async () => {
        const effectSelect = document.getElementById('hyperion-effect-select');
        const effectName = effectSelect.value;

        if (!effectName) {
            showStatus('Please select an effect', 'warning');
            return;
        }

        try {
            await hyperionController.sendCommand('effect', { effect_name: effectName });
            showStatus(`Effect '${effectName}' activated`, 'success');
        } catch (error) {
            showStatus(`Failed to set effect: ${error.message}`, 'error');
        }
    });

    // Default (Off) button - clears priority
    document.getElementById('hyperion-clear-priority')?.addEventListener('click', async () => {
        try {
            await hyperionController.sendCommand('clear', {});
            showStatus('Returned to default state (off)', 'success');
        } catch (error) {
            showStatus(`Failed to return to default: ${error.message}`, 'error');
        }
    });

    // Save effect settings button
    document.getElementById('save-hyperion-effects')?.addEventListener('click', async () => {
        try {
            const idleEffect = document.getElementById('hyperion-idle-effect')?.value || '';
            const playingEffect = document.getElementById('hyperion-playing-effect')?.value || '';

            const response = await fetch('/api/hyperion/set_effects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    idle_effect: idleEffect,
                    playing_effect: playingEffect
                })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            await response.json();
            showStatus('Effect settings saved successfully', 'success');
        } catch (error) {
            showStatus(`Failed to save effect settings: ${error.message}`, 'error');
        }
    });
}

// Load available Hyperion effects
async function loadEffectsList() {
    try {
        const response = await fetch('/api/hyperion/effects');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const effectSelect = document.getElementById('hyperion-effect-select');
        const idleEffectSelect = document.getElementById('hyperion-idle-effect');
        const playingEffectSelect = document.getElementById('hyperion-playing-effect');

        if (!effectSelect) return;

        // Clear loading option
        effectSelect.innerHTML = '<option value="">-- Select an effect --</option>';

        // Add "Default (Off)" option to idle and playing effect selectors
        if (idleEffectSelect) {
            idleEffectSelect.innerHTML = '<option value="off">Default (Off)</option>';
        }
        if (playingEffectSelect) {
            playingEffectSelect.innerHTML = '<option value="off">Default (Off)</option>';
        }

        // Add effects to all dropdowns
        if (data.effects && data.effects.length > 0) {
            data.effects.forEach(effect => {
                // Main effect selector
                const option = document.createElement('option');
                option.value = effect.name;
                option.textContent = effect.name;
                effectSelect.appendChild(option);

                // Idle effect selector
                if (idleEffectSelect) {
                    const idleOption = document.createElement('option');
                    idleOption.value = effect.name;
                    idleOption.textContent = effect.name;
                    idleEffectSelect.appendChild(idleOption);
                }

                // Playing effect selector
                if (playingEffectSelect) {
                    const playingOption = document.createElement('option');
                    playingOption.value = effect.name;
                    playingOption.textContent = effect.name;
                    playingEffectSelect.appendChild(playingOption);
                }
            });

            // Load saved settings from config
            const configResponse = await fetch('/get_led_config');
            if (configResponse.ok) {
                const config = await configResponse.json();
                if (idleEffectSelect && config.hyperion_idle_effect) {
                    idleEffectSelect.value = config.hyperion_idle_effect;
                }
                if (playingEffectSelect && config.hyperion_playing_effect) {
                    playingEffectSelect.value = config.hyperion_playing_effect;
                }
            }
        } else {
            effectSelect.innerHTML = '<option value="">No effects available</option>';
        }
    } catch (error) {
        console.error('Failed to load effects:', error);
        const effectSelect = document.getElementById('hyperion-effect-select');
        if (effectSelect) {
            effectSelect.innerHTML = '<option value="">Failed to load effects</option>';
        }
    }
}

// Check Hyperion connection status
async function checkHyperionStatus() {
    try {
        const response = await fetch('/api/hyperion/status');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data.connected) {
            const version = data.version || 'unknown';
            const hostname = data.hostname || 'unknown';
            const isOn = data.is_on;
            const state = isOn ? 'ON' : 'OFF';

            // Update power button appearance - shows current state with appropriate action
            const powerButton = document.getElementById('hyperion-power-toggle');
            const powerButtonText = document.getElementById('power-button-text');

            if (powerButton && powerButtonText) {
                if (isOn) {
                    powerButton.className = 'flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-3 text-sm font-semibold text-white shadow-md hover:bg-red-700 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-2';
                    powerButtonText.textContent = 'Turn OFF';
                } else {
                    powerButton.className = 'flex items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-3 text-sm font-semibold text-white shadow-md hover:bg-green-700 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-green-400 focus:ring-offset-2';
                    powerButtonText.textContent = 'Turn ON';
                }
            }

            showStatus(`Connected to ${hostname} (${version}) - Power: ${state}`, 'success');
        } else {
            showStatus(`Connection failed: ${data.message}`, 'error');
        }
    } catch (error) {
        showStatus(`Cannot connect to Hyperion: ${error.message}`, 'error');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeLedPage);
