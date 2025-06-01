// Constants for log message types
const LOG_TYPE = {
    SUCCESS: 'success',
    WARNING: 'warning',
    ERROR: 'error',
    INFO: 'info',
    DEBUG: 'debug'
};

// Function to log messages
function logMessage(message, type = LOG_TYPE.DEBUG) {
    console.log(`[${type}] ${message}`);
}

// Initialize playlists page
document.addEventListener('DOMContentLoaded', async () => {
    // Hide the entire content until we have the initial data
    const contentContainer = document.querySelector('.layout-content-container');
    if (contentContainer) {
        contentContainer.style.visibility = 'hidden';
    }

    try {
        // TODO: Load playlists data
        // const response = await fetch('/playlists');
        // if (response.ok) {
        //     const playlists = await response.json();
        //     // Populate playlists
        // }

        // Setup event listeners
        setupEventListeners();

        // Show the content
        if (contentContainer) {
            contentContainer.style.visibility = 'visible';
        }
    } catch (error) {
        logMessage(`Error during initialization: ${error.message}`, LOG_TYPE.ERROR);
        // Show the content even if there's an error
        if (contentContainer) {
            contentContainer.style.visibility = 'visible';
        }
    }
});

// Setup event listeners
function setupEventListeners() {
    // New playlist button
    const newPlaylistButton = document.querySelector('button.flex.items-center.justify-center.gap-2');
    if (newPlaylistButton) {
        newPlaylistButton.addEventListener('click', () => {
            // TODO: Show new playlist dialog
            logMessage('New playlist button clicked', LOG_TYPE.INFO);
        });
    }
} 