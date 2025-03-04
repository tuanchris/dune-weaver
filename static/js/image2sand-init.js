/**
 * Image2Sand (https://github.com/orionwc/Image2Sand) Initialization
 * 
 * This script handles the initialization of the Image2Sand converter.
 * 
 */

// Global variables for the image converter
let convertedFileName = '';
let convertedCoordinates = null;
let currentImageData = null;

/**
 * Open the image converter dialog with the selected image
 * @param {File} file - The image file to convert
 */
function openImageConverter(file) {
    if (!file) {
        logMessage('No file selected for conversion.', LOG_TYPE.ERROR);
        return;
    }

    // Check if the file is an image
    if (!file.type.startsWith('image/')) {
        // If not an image, let the original uploadThetaRho handle it
        return;
    }

    convertedFileName = file.name.split('.')[0]; // Remove extension
    // clear the canvases
    clearAllCanvases();
    // Show the converter dialog
    showImageConverter();
    // Show processing indicator
    const processingIndicator = document.getElementById('processing-indicator');
    const processingMessage = document.getElementById('processing-message');
    if (processingMessage) {
        processingMessage.textContent = `Converting image...`;
    }
    processingIndicator.classList.add('visible');                
    
    // Create an image element to load the file
    const img = new Image();
    img.onload = function() {
        // Draw the image on the canvas
        originalImageElement = img;
        logMessage(`Image loaded: ${file.name}. Converting...`, LOG_TYPE.INFO);
        drawAndPrepImage(img);
        
        convertImage();
        waitForConversion()
            .then(() => {
                // Hide processing indicator
                document.getElementById('processing-indicator').classList.remove('visible');
                logMessage(`Image converted.`, LOG_TYPE.SUCCESS);
            })
            .catch(error => {
                // Hide processing indicator on error
                document.getElementById('processing-indicator').classList.remove('visible');
                logMessage("Error during conversion process: " + error, LOG_TYPE.ERROR);
            });
    };
    
    img.onerror = function() {
        logMessage(`Failed to load image: ${file.name}`, LOG_TYPE.ERROR);
    };
    
    // Load the image from the file
    img.src = URL.createObjectURL(file);
}

/**
 * Save the converted pattern as a .thr file
 */
async function saveConvertedPattern() {
    convertedCoordinates = document.getElementById('polar-coordinates-textarea').value;
    if (!convertedCoordinates) {
        logMessage('No converted coordinates to save.', LOG_TYPE.ERROR);
        return;
    }
    
    try {
        // Create a safe filename (replace spaces and special characters)
        const safeFileName = convertedFileName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
        const thrFileName = `${safeFileName}.thr`;
        
        // Create a Blob with the coordinates
        const blob = new Blob([convertedCoordinates], { type: 'text/plain' });
        
        // Create a FormData object
        const formData = new FormData();
        formData.append('file', new File([blob], thrFileName, { type: 'text/plain' }));
        
        // Show processing indicator
        const processingIndicator = document.getElementById('processing-indicator');
        const processingMessage = document.getElementById('processing-message');
        if (processingMessage) {
            processingMessage.textContent = `Saving pattern as ${thrFileName}...`;
        }
        processingIndicator.classList.add('visible');
        
        // Upload the file
        const response = await fetch('/upload_theta_rho', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        if (result.success) {
            const fileInput = document.getElementById('upload_file');
            // Use forward slashes for path consistency
            const finalFileName = 'custom_patterns/' + thrFileName;
            logMessage(`Image converted and saved as ${finalFileName}`, LOG_TYPE.SUCCESS);
            
            // Close the converter dialog
            closeImageConverter();

            // clear the file input
            fileInput.value = '';

            // Refresh the file list
            await loadThetaRhoFiles();
            
            // Select the newly created file
            const fileList = document.getElementById('theta_rho_files');
            const listItems = fileList.querySelectorAll('li');
            for (const item of listItems) {
                // Normalize path comparison
                const normalizedItemPath = item.textContent.replace(/\\/g, '/');
                if (normalizedItemPath === finalFileName) {
                    selectFile(finalFileName, item);
                    break;
                }
            }
        } else {
            logMessage(`Failed to save pattern: ${result.error || 'Unknown error'}`, LOG_TYPE.ERROR);
        }
    } catch (error) {
        logMessage(`Error saving pattern: ${error.message}`, LOG_TYPE.ERROR);
    } finally {
        // Hide processing indicator
        document.getElementById('processing-indicator').classList.remove('visible');
    }
}

/**
 * Clear a canvas
 * @param {string} canvasId - The ID of the canvas element to clear
 */
function clearCanvas(canvasId) {
    const canvas = document.getElementById(canvasId);
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function clearAllCanvases() {
    clearCanvas('original-image');
    clearCanvas('edge-image');
    clearCanvas('dot-image');
    clearCanvas('connect-image');
}

/**
 * Show the image converter dialog
 */
function showImageConverter() {
    const overlay = document.getElementById('image-converter');
    overlay.classList.add('visible');
    overlay.classList.remove('hidden');
}

/**
 * Close the image converter dialog
 */
function closeImageConverter() {
    const overlay = document.getElementById('image-converter');
    overlay.classList.remove('visible');
    overlay.classList.add('hidden');

    // Clear the canvases
    clearAllCanvases();
    
    // Reset variables
    originalImageElement = null;
    convertedFileName = '';
    convertedCoordinates = null;
    currentImageData = null;
    
    // Disable the save button
    //document.getElementById('save-pattern-button').disabled = true;
}

async function generateImage(apiKey, prompt, runPattern) {
    if (isGeneratingImage) {
        logMessage("Image is still generating - please don't press the button.", LOG_TYPE.INFO);
        return;
    } else {
        isGeneratingImage = true;
        clearAllCanvases();
        document.getElementById('generate-image-button').disabled = true;
        // Show the converter dialog
        showImageConverter();
        // Show processing indicator
        logMessage("Generating image...", LOG_TYPE.INFO);
        const processingIndicator = document.getElementById('processing-indicator');
        const processingMessage = document.getElementById('processing-message');
        if (processingMessage) {
            processingMessage.textContent = `Generating image...`;
        }
        processingIndicator.classList.add('visible');
        try {
            const response = await fetch('/generate_image', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    apiKey: apiKey,
                    prompt: prompt
                })
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Failed to generate image');
            }

            const imageData = data.data[0].b64_json;
            const imgElement = new Image();
            imgElement.onload = function() {
                // Draw the image on the canvas
                originalImageElement = imgElement;
                drawAndPrepImage(imgElement);
                
                convertImage();
                if (!runPattern) return;
                waitForConversion()
                    .then(() => {
                        // set convertedFileName to the prompt name with no special characters and max 20 characters
                        convertedFileName = prompt.replace(/[^a-z0-9]/gi, '_').toLowerCase().substring(0, 20);
                        saveConvertedPattern();
                        // wait for the file to be uploaded
                        waitForSelectedFile()
                            .then(() => {
                                // set pre_execution to clear_sideway before starting the pattern run
                                pre_execution.value = 'clear_sideway';
                                runThetaRho();
                            })
                            .catch(error => {
                                logMessage("Conversion timeout or error: " + error, LOG_TYPE.ERROR);
                            });
                    })
                    .catch(error => {
                        logMessage("Conversion timeout or error: " + error, LOG_TYPE.ERROR);
                    });
            };
            imgElement.src = `data:image/png;base64,${imageData}`;

            logMessage('Image generated successfully', LOG_TYPE.SUCCESS);
        } catch (error) {
            logMessage('Image generation error: ' + error, LOG_TYPE.ERROR);
        }
        isGeneratingImage = false;
        document.getElementById('generate-image-button').disabled = false;
        document.getElementById('processing-indicator').classList.remove('visible');
    }
}

/**
 * Wait for the conversion to complete
 * @param {number} timeout - The timeout for the conversion
 * @returns {Promise} A promise that resolves when the conversion is complete
 */
function waitForConversion(timeout = 20000) {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        
        function checkConversion() {
            convertedCoordinates = document.getElementById('polar-coordinates-textarea').value;
            if (convertedCoordinates && convertedCoordinates.trim().length > 0) {
                resolve();
            } else if (Date.now() - startTime > timeout) {
                reject('Timeout waiting for conversion');
            } else {
                setTimeout(checkConversion, 500); // Check every 500ms
            }
        }
        
        checkConversion();
    });
}


/**
 * Wait for the save to complete
 * @param {number} timeout - The timeout for the save
 * @returns {Promise} A promise that resolves when the save is complete
 */
function waitForSelectedFile(timeout = 20000) {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        
        function checkSelectedFile() {
            if (selectedFile) {
                resolve();
            } else if (Date.now() - startTime > timeout) {
                reject('Timeout waiting for save');
            } else {
                setTimeout(checkSelectedFile, 500); // Check every 500ms
            }
        }
        
        checkSelectedFile();
    });
}


/**
 * Wait for the dialog to be visible
 * @param {number} timeout - The timeout for the dialog
 * @returns {Promise} A promise that resolves when the dialog is visible
 */
function waitForDialog(timeout = 20000) {
    return new Promise((resolve, reject) => {   
        const startTime = Date.now();
        
        function checkDialog() {
            if (document.getElementById('image-converter').classList.contains('visible')) {
                resolve();
            } else if (Date.now() - startTime > timeout) {
                reject('Timeout waiting for dialog');
            } else {
                setTimeout(checkDialog, 500); // Check every 500ms
            }
        }
        
        checkDialog();  
    });
}

// Function to get URL parameters
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        apikey: params.get('apikey'),
        prompt: params.get('prompt'),
        runPattern: params.get('runPattern')
    };
}


// Override the uploadThetaRho function to handle image files
const originalUploadThetaRho = window.uploadThetaRho;

window.uploadThetaRho = async function() {
    const fileInput = document.getElementById('upload_file');
    const file = fileInput.files[0];
    
    if (!file) {
        logMessage('No file selected for upload.', LOG_TYPE.ERROR);
        return;
    }
    
    // Check if the file is an image
    if (file.type.startsWith('image/')) {
        // Handle image files with the converter
        openImageConverter(file);
        return;
    }
    
    // For non-image files, use the original function
    await originalUploadThetaRho();
};

function hiddenResponse() {
    return;
}

// override the DOMContentLoaded event to handle the image generation

document.addEventListener('DOMContentLoaded', function() {
    const epsilonSlider = document.getElementById('epsilon-slider');
    const epsilonValueDisplay = document.getElementById('epsilon-value-display');
    const pre_execution = document.getElementById('pre_execution');

    document.getElementById('plotButton').addEventListener('click', plotNextContour);

    epsilonSlider.addEventListener('input', function() {
        epsilonValueDisplay.textContent = epsilonSlider.value;
    });

    const { apikey, prompt, runPattern } = getUrlParams();

    // Fill inputs with URL parameters if they exist
    fillInputsFromParams({ apikey, prompt });

    // Generate image if all parameters are present
    if (apikey && prompt) {
        setDefaultsForAutoGenerate();
        showImageConverter();
        generateImage(apikey, prompt, runPattern);
    }

    // Add event listener to the button inside the DOMContentLoaded event
    document.getElementById('generate-image-button').addEventListener('click', function() {    
        let apiKey = document.getElementById('api-key').value;
        const prompt = document.getElementById('prompt').value + (document.getElementById('googly-eyes').checked ? ' with disproportionately large googly eyes' : '');
        generateImage(apiKey, prompt);
    });
});