// LED Strip Control Functions

function hexToRgb(hex) {
    // Remove the '#' if present
    hex = hex.replace('#', '');

    // Parse the hex values
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);

    return [r, g, b];
}

function updateLEDStatus() {
    fetch('/api/led/status')
        .then(response => response.json())
        .then(data => {
            document.getElementById('led_mode').textContent = data.mode;
            document.getElementById('led_current_animation').textContent = data.current_animation || 'None';
            document.getElementById('led_power').checked = data.is_on;

            // Update controls to match current state
            document.getElementById('led_brightness').value = data.brightness;
            document.getElementById('led_speed').value = data.animation_speed;

            if (data.current_animation) {
                document.getElementById('led_animation').value = data.current_animation;
            }
        })
        .catch(error => {
            console.error('Error fetching LED status:', error);
        });
}

function setLEDColor(colorHex) {
    const rgb = hexToRgb(colorHex);
    fetch('/api/led/color', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            color: rgb
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error setting LED color:', data.error);
            }
            updateLEDStatus();
        })
        .catch(error => {
            console.error('Error setting LED color:', error);
        });
}

function setLEDBrightness(brightness) {
    fetch('/api/led/brightness', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            brightness: parseInt(brightness)
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error setting LED brightness:', data.error);
            }
            updateLEDStatus();
        })
        .catch(error => {
            console.error('Error setting LED brightness:', error);
        });
}

function setLEDAnimation(animation) {
    if (animation === 'none') {
        fetch('/api/led/animation/stop', {
            method: 'POST'
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Error stopping LED animation:', data.error);
                }
                updateLEDStatus();
            })
            .catch(error => {
                console.error('Error stopping LED animation:', error);
            });
    } else {
        fetch('/api/led/animation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                animation: animation
            })
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Error setting LED animation:', data.error);
                }
                updateLEDStatus();
            })
            .catch(error => {
                console.error('Error setting LED animation:', error);
            });
    }
}

function setLEDSpeed(speed) {
    fetch('/api/led/speed', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            speed: parseInt(speed)
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error setting LED speed:', data.error);
            }
            updateLEDStatus();
        })
        .catch(error => {
            console.error('Error setting LED speed:', error);
        });
}

function setLEDPower(state) {
    fetch('/api/led/power', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            state: state
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error setting LED power:', data.error);
            }
            updateLEDStatus();
        })
        .catch(error => {
            console.error('Error setting LED power:', error);
        });
}

// Update LED status every 5 seconds
setInterval(updateLEDStatus, 5000);

// Initial status update
document.addEventListener('DOMContentLoaded', function () {
    updateLEDStatus();
});