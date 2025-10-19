// LED Control Page - Unified interface for WLED and DW LEDs

let ledConfig = null;

// Utility function to show status messages
function showStatus(message, type = 'info') {
    const statusDiv = document.getElementById('dw-leds-status');
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
        const dwLedsContainer = document.getElementById('dw-leds-container');

        // Hide all containers first
        notConfigured.classList.add('hidden');
        wledContainer.classList.add('hidden');
        dwLedsContainer.classList.add('hidden');

        if (ledConfig.provider === 'wled' && ledConfig.wled_ip) {
            // Show WLED iframe
            wledContainer.classList.remove('hidden');
            const wledFrame = document.getElementById('wled-frame');
            if (wledFrame) {
                wledFrame.src = `http://${ledConfig.wled_ip}`;
            }
        } else if (ledConfig.provider === 'dw_leds') {
            // Show DW LEDs controls
            dwLedsContainer.classList.remove('hidden');
            await initializeDWLedsControls();
        } else {
            // Show not configured message
            notConfigured.classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error initializing LED page:', error);
        document.getElementById('led-not-configured').classList.remove('hidden');
    }
}

// Initialize DW LEDs controls
async function initializeDWLedsControls() {
    // Check status and load available effects/palettes
    await checkDWLedsStatus();
    await loadEffectsAndPalettes();

    // Power toggle button
    document.getElementById('dw-leds-power-toggle')?.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/dw_leds/power', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ state: 2 })  // Toggle
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            if (data.connected) {
                showStatus(`Power ${data.power_on ? 'ON' : 'OFF'}`, 'success');
                await checkDWLedsStatus();
            } else {
                showStatus(data.error || 'Failed to toggle power', 'error');
            }
        } catch (error) {
            showStatus(`Failed to toggle power: ${error.message}`, 'error');
        }
    });

    // Brightness slider
    const brightnessSlider = document.getElementById('dw-leds-brightness');
    const brightnessValue = document.getElementById('dw-leds-brightness-value');

    brightnessSlider?.addEventListener('input', (e) => {
        brightnessValue.textContent = `${e.target.value}%`;
    });

    brightnessSlider?.addEventListener('change', async (e) => {
        try {
            const response = await fetch('/api/dw_leds/brightness', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: parseInt(e.target.value) })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            if (data.connected) {
                showStatus(`Brightness set to ${e.target.value}%`, 'success');
            } else {
                showStatus(data.error || 'Failed to set brightness', 'error');
            }
        } catch (error) {
            showStatus(`Failed to set brightness: ${error.message}`, 'error');
        }
    });

    // Color picker - update display when color changes
    const colorPicker = document.getElementById('dw-leds-color');
    const colorHexDisplay = document.getElementById('dw-leds-color-hex');

    colorPicker?.addEventListener('input', (e) => {
        if (colorHexDisplay) {
            colorHexDisplay.textContent = e.target.value.toUpperCase();
        }
    });

    // Color picker - apply button
    document.getElementById('dw-leds-set-color')?.addEventListener('click', async () => {
        await applyColor(colorPicker.value);
    });

    // Quick color buttons
    document.querySelectorAll('.dw-leds-quick-color').forEach(button => {
        button.addEventListener('click', async () => {
            const hexColor = button.getAttribute('data-color');
            await applyColor(hexColor);

            // Update color picker and hex display to match
            if (colorPicker) colorPicker.value = hexColor;
            if (colorHexDisplay) colorHexDisplay.textContent = hexColor.toUpperCase();
        });
    });

    // Effect selector
    document.getElementById('dw-leds-effect-select')?.addEventListener('change', async (e) => {
        const effectId = parseInt(e.target.value);
        if (isNaN(effectId)) return;

        try {
            const response = await fetch('/api/dw_leds/effect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ effect_id: effectId })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            if (data.connected) {
                showStatus(`Effect changed`, 'success');
            } else {
                showStatus(data.error || 'Failed to set effect', 'error');
            }
        } catch (error) {
            showStatus(`Failed to set effect: ${error.message}`, 'error');
        }
    });

    // Palette selector
    document.getElementById('dw-leds-palette-select')?.addEventListener('change', async (e) => {
        const paletteId = parseInt(e.target.value);
        if (isNaN(paletteId)) return;

        try {
            const response = await fetch('/api/dw_leds/palette', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ palette_id: paletteId })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            if (data.connected) {
                showStatus(`Palette changed`, 'success');
            } else {
                showStatus(data.error || 'Failed to set palette', 'error');
            }
        } catch (error) {
            showStatus(`Failed to set palette: ${error.message}`, 'error');
        }
    });

    // Speed slider
    const speedSlider = document.getElementById('dw-leds-speed');
    const speedValue = document.getElementById('dw-leds-speed-value');

    speedSlider?.addEventListener('input', (e) => {
        speedValue.textContent = e.target.value;
    });

    speedSlider?.addEventListener('change', async (e) => {
        try {
            const response = await fetch('/api/dw_leds/speed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speed: parseInt(e.target.value) })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            if (data.connected) {
                showStatus(`Speed updated`, 'success');
            } else {
                showStatus(data.error || 'Failed to set speed', 'error');
            }
        } catch (error) {
            showStatus(`Failed to set speed: ${error.message}`, 'error');
        }
    });

    // Intensity slider
    const intensitySlider = document.getElementById('dw-leds-intensity');
    const intensityValue = document.getElementById('dw-leds-intensity-value');

    intensitySlider?.addEventListener('input', (e) => {
        intensityValue.textContent = e.target.value;
    });

    intensitySlider?.addEventListener('change', async (e) => {
        try {
            const response = await fetch('/api/dw_leds/intensity', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ intensity: parseInt(e.target.value) })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();

            if (data.connected) {
                showStatus(`Intensity updated`, 'success');
            } else {
                showStatus(data.error || 'Failed to set intensity', 'error');
            }
        } catch (error) {
            showStatus(`Failed to set intensity: ${error.message}`, 'error');
        }
    });

    // Save automation effects button
    document.getElementById('dw-leds-save-effects')?.addEventListener('click', async () => {
        try {
            const idleEffect = document.getElementById('dw-leds-idle-effect')?.value || 'off';
            const playingEffect = document.getElementById('dw-leds-playing-effect')?.value || 'off';

            const response = await fetch('/api/dw_leds/set_effects', {
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

// Helper function to apply color
async function applyColor(hexColor) {
    try {
        // Convert hex to RGB
        const r = parseInt(hexColor.slice(1, 3), 16);
        const g = parseInt(hexColor.slice(3, 5), 16);
        const b = parseInt(hexColor.slice(5, 7), 16);

        const response = await fetch('/api/dw_leds/color', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ r, g, b })
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.connected) {
            showStatus(`Color set to ${hexColor.toUpperCase()}`, 'success');
        } else {
            showStatus(data.error || 'Failed to set color', 'error');
        }
    } catch (error) {
        showStatus(`Failed to set color: ${error.message}`, 'error');
    }
}

// Load available effects and palettes
async function loadEffectsAndPalettes() {
    try {
        // Load effects
        const effectsResponse = await fetch('/api/dw_leds/effects');
        if (effectsResponse.ok) {
            const effectsData = await effectsResponse.json();
            const effectSelect = document.getElementById('dw-leds-effect-select');
            const idleEffectSelect = document.getElementById('dw-leds-idle-effect');
            const playingEffectSelect = document.getElementById('dw-leds-playing-effect');

            if (effectSelect && effectsData.effects) {
                effectSelect.innerHTML = '';
                effectsData.effects.forEach(([id, name]) => {
                    const option = document.createElement('option');
                    option.value = id;
                    option.textContent = name;
                    effectSelect.appendChild(option);
                });
            }

            // Add effects to automation selectors
            if (idleEffectSelect && effectsData.effects) {
                idleEffectSelect.innerHTML = '<option value="off">Off</option>';
                effectsData.effects.forEach(([id, name]) => {
                    const option = document.createElement('option');
                    option.value = name.toLowerCase();
                    option.textContent = name;
                    idleEffectSelect.appendChild(option);
                });
            }

            if (playingEffectSelect && effectsData.effects) {
                playingEffectSelect.innerHTML = '<option value="off">Off</option>';
                effectsData.effects.forEach(([id, name]) => {
                    const option = document.createElement('option');
                    option.value = name.toLowerCase();
                    option.textContent = name;
                    playingEffectSelect.appendChild(option);
                });
            }

            // Load saved automation settings
            const configResponse = await fetch('/get_led_config');
            if (configResponse.ok) {
                const config = await configResponse.json();
                if (idleEffectSelect && config.dw_led_idle_effect) {
                    idleEffectSelect.value = config.dw_led_idle_effect;
                }
                if (playingEffectSelect && config.dw_led_playing_effect) {
                    playingEffectSelect.value = config.dw_led_playing_effect;
                }
            }
        }

        // Load palettes
        const palettesResponse = await fetch('/api/dw_leds/palettes');
        if (palettesResponse.ok) {
            const palettesData = await palettesResponse.json();
            const paletteSelect = document.getElementById('dw-leds-palette-select');

            if (paletteSelect && palettesData.palettes) {
                paletteSelect.innerHTML = '';
                palettesData.palettes.forEach(([id, name]) => {
                    const option = document.createElement('option');
                    option.value = id;
                    option.textContent = name;
                    paletteSelect.appendChild(option);
                });
            }
        }
    } catch (error) {
        console.error('Failed to load effects and palettes:', error);
        showStatus('Failed to load effects and palettes', 'error');
    }
}

// Check DW LEDs connection status
async function checkDWLedsStatus() {
    try {
        const response = await fetch('/api/dw_leds/status');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (data.connected) {
            const powerState = data.power_on ? 'ON' : 'OFF';
            showStatus(`Connected: ${data.num_leds} LEDs on GPIO ${data.gpio_pin} - Power: ${powerState}`, 'success');

            // Update power button appearance
            const powerButton = document.getElementById('dw-leds-power-toggle');
            const powerButtonText = document.getElementById('dw-leds-power-text');

            if (powerButton && powerButtonText) {
                if (data.power_on) {
                    powerButton.className = 'flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-3 text-sm font-semibold text-white shadow-md hover:bg-red-700 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-red-400 focus:ring-offset-2';
                    powerButtonText.textContent = 'Turn OFF';
                } else {
                    powerButton.className = 'flex items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-3 text-sm font-semibold text-white shadow-md hover:bg-green-700 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-green-400 focus:ring-offset-2';
                    powerButtonText.textContent = 'Turn ON';
                }
            }

            // Update slider values
            const brightnessSlider = document.getElementById('dw-leds-brightness');
            const brightnessValue = document.getElementById('dw-leds-brightness-value');
            if (brightnessSlider && data.brightness !== undefined) {
                brightnessSlider.value = data.brightness;
                if (brightnessValue) brightnessValue.textContent = `${data.brightness}%`;
            }

            const speedSlider = document.getElementById('dw-leds-speed');
            const speedValue = document.getElementById('dw-leds-speed-value');
            if (speedSlider && data.speed !== undefined) {
                speedSlider.value = data.speed;
                if (speedValue) speedValue.textContent = data.speed;
            }

            const intensitySlider = document.getElementById('dw-leds-intensity');
            const intensityValue = document.getElementById('dw-leds-intensity-value');
            if (intensitySlider && data.intensity !== undefined) {
                intensitySlider.value = data.intensity;
                if (intensityValue) intensityValue.textContent = data.intensity;
            }

            // Update effect and palette selectors
            const effectSelect = document.getElementById('dw-leds-effect-select');
            if (effectSelect && data.current_effect !== undefined) {
                effectSelect.value = data.current_effect;
            }

            const paletteSelect = document.getElementById('dw-leds-palette-select');
            if (paletteSelect && data.current_palette !== undefined) {
                paletteSelect.value = data.current_palette;
            }
        } else {
            // Show error message from controller
            const errorMsg = data.error || 'Connection failed';
            showStatus(errorMsg, 'error');
        }
    } catch (error) {
        showStatus(`Cannot connect to DW LEDs: ${error.message}`, 'error');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeLedPage);
