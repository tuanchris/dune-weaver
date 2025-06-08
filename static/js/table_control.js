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

    // Set Speed button
    const setSpeedButton = document.getElementById('setSpeedButton');
    const speedInput = document.getElementById('speedInput');
    setSpeedButton.addEventListener('click', async () => {
        const speed = parseFloat(speedInput.value);
        if (isNaN(speed) || speed <= 0) {
            updateStatus('Error: Please enter a valid speed value');
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
                updateStatus(`Speed set to ${speed} mm/s`);
            }
        } catch (error) {
            console.error('Error setting speed:', error);
            updateStatus('Error: Failed to set speed');
        }
    });

    // Clear from Center button
    const clearCenterButton = document.getElementById('clearCenterButton');
    clearCenterButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/run_theta_rho', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_name: 'clear_from_in.thr',
                    pre_execution: 'none'
                })
            });
            const data = await response.json();
            if (response.ok) {
                updateStatus('Running clear from center pattern...');
            } else {
                throw new Error(data.detail || 'Failed to run clear pattern');
            }
        } catch (error) {
            console.error('Error running clear from center pattern:', error);
            if (error.message.includes('409')) {
                updateStatus('Error: Another pattern is already running');
            } else {
                updateStatus('Error: Failed to run clear pattern');
            }
        }
    });

    // Clear from Perimeter button
    const clearPerimeterButton = document.getElementById('clearPerimeterButton');
    clearPerimeterButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/run_theta_rho', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_name: 'clear_from_out.thr',
                    pre_execution: 'none'
                })
            });
            const data = await response.json();
            if (response.ok) {
                updateStatus('Running clear from perimeter pattern...');
            } else {
                throw new Error(data.detail || 'Failed to run clear pattern');
            }
        } catch (error) {
            console.error('Error running clear from perimeter pattern:', error);
            if (error.message.includes('409')) {
                updateStatus('Error: Another pattern is already running');
            } else {
                updateStatus('Error: Failed to run clear pattern');
            }
        }
    });

    // Clear Sideways button
    const clearSidewaysButton = document.getElementById('clearSidewaysButton');
    clearSidewaysButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/run_theta_rho', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_name: 'clear_sideway.thr',
                    pre_execution: 'none'
                })
            });
            const data = await response.json();
            if (response.ok) {
                updateStatus('Running clear sideways pattern...');
            } else {
                throw new Error(data.detail || 'Failed to run clear pattern');
            }
        } catch (error) {
            console.error('Error running clear sideways pattern:', error);
            if (error.message.includes('409')) {
                updateStatus('Error: Another pattern is already running');
            } else {
                updateStatus('Error: Failed to run clear pattern');
            }
        }
    });
});

// Function to update status
function updateStatus(message) {
    if (message.startsWith('Error:')) {
        showStatusMessage(message.substring(7), 'error');
    } else {
        showStatusMessage(message, 'success');
    }
} 