/**
 * Image2Sand (https://github.com/orionwc/Image2Sand) Initialization
 * 
 * This script handles the initialization of the Image2Sand converter.
 * 
 */

// Global variables for the image converter
let originalImage = null;
let fileName = '';
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

    fileName = file.name.split('.')[0]; // Remove extension
    
    // Create an image element to load the file
    const img = new Image();
    img.onload = function() {
        // Draw the image on the canvas
        originalImage = img;
        drawAndPrepImage(img);
        
        // Show the converter dialog
        const overlay = document.getElementById('image-converter');
        overlay.classList.remove('hidden');
        overlay.classList.add('visible');

        // Initialize the UI elements
        initializeUI();
        
        // Convert the image with default settings
        convertImage();
    };
    
    img.onerror = function() {
        logMessage(`Failed to load image: ${file.name}`, LOG_TYPE.ERROR);
    };
    
    // Load the image from the file
    img.src = URL.createObjectURL(file);
}

/**
 * Initialize UI elements for the image converter
 */
function initializeUI() {
    // Set up event listeners for UI controls
    const epsilonSlider = document.getElementById('epsilon-slider');
    const epsilonValueDisplay = document.getElementById('epsilon-value-display');
    
    epsilonSlider.addEventListener('input', function() {
        epsilonValueDisplay.textContent = this.value;
    });
    
    // Set up event listeners for other controls
    //document.getElementById('epsilon-slider').addEventListener('change', convertImage);
    //document.getElementById('dot-number').addEventListener('change', convertImage);
    //document.getElementById('contour-mode').addEventListener('change', convertImage);
    //document.getElementById('is-loop').addEventListener('change', convertImage);
    //document.getElementById('no-shortcuts').addEventListener('change', convertImage);
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
        const safeFileName = fileName.replace(/[^a-z0-9]/gi, '_').toLowerCase();
        const thrFileName = `${safeFileName}.thr`;
        
        // Create a Blob with the coordinates
        const blob = new Blob([convertedCoordinates], { type: 'text/plain' });
        
        // Create a FormData object
        const formData = new FormData();
        formData.append('file', new File([blob], thrFileName, { type: 'text/plain' }));
        
        // Show processing indicator
        const processingIndicator = document.getElementById('processing-status');
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
                if (item.textContent === finalFileName) {
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
        document.getElementById('processing-status').classList.remove('visible');
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

/**
 * Close the image converter dialog
 */
function closeImageConverter() {
    const overlay = document.getElementById('image-converter');
    overlay.classList.remove('visible');
    overlay.classList.add('hidden');

    // Clear the canvases
    clearCanvas('original-image');
    clearCanvas('edge-image');
    clearCanvas('dot-image');
    clearCanvas('connect-image');
    
    // Reset variables
    originalImage = null;
    fileName = '';
    convertedCoordinates = null;
    currentImageData = null;
    
    // Disable the save button
    //document.getElementById('save-pattern-button').disabled = true;
}

async function generateOpenAIImage(apiKey, prompt) {
    if (isGeneratingImage) {
        logMessage("Image is still generating - please don't press the button.", LOG_TYPE.INFO);
    } else {
        isGeneratingImage = true;
        clearCanvas('original-image');
        clearCanvas('edge-image');
        clearCanvas('dot-image');
        clearCanvas('connect-image');
        document.getElementById('gen-image-button').disabled = true;
        // Show processing indicator
        const processingIndicator = document.getElementById('processing-status');
        const processingMessage = document.getElementById('processing-message');
        if (processingMessage) {
            processingMessage.textContent = `Generating image...`;
        }
        processingIndicator.classList.add('visible');
        try {

            const fullPrompt = `Draw an image of the following: ${prompt}. Make the line black and the background white. The drawing should be a single line, don't add any additional details to the image.`;

            const response = await fetch('https://api.openai.com/v1/images/generations', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${apiKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    model: 'dall-e-3',
                    prompt: fullPrompt,
                    size: '1024x1024',
                    quality: 'standard',
                    response_format: 'b64_json', // Specify base64 encoding
                    n: 1
                })
            });

            const data = await response.json();
            //const imageUrl = data.data[0].url;
            if ('error' in data) {
                throw new Error(data.error.message);
            }
            const imageData = data.data[0].b64_json;

            //console.log("Image Data: ", imageData);

            const imgElement = new Image();
            imgElement.onload = function() {
                // Draw the image on the canvas
                originalImage = imgElement;
                drawAndPrepImage(imgElement);
                
                // Convert the image with default settings
                convertImage();
            };
            imgElement.src = `data:image/png;base64,${imageData}`;

            //console.log(`Image generated successfully`);
            logMessage('Image generated successfully', LOG_TYPE.SUCCESS);
        } catch (error) {
            //console.error('Image generation error:', error);
            logMessage('Image generation error: ' + error, LOG_TYPE.ERROR);
        }
        isGeneratingImage = false;
        document.getElementById('gen-image-button').disabled = false;
        document.getElementById('processing-status').classList.remove('visible');
    }

}

function regeneratePattern() {
    const generateButton = document.getElementById('generate-button');

    // Disable button & show existing loader
    generateButton.disabled = true;
    generateButton.classList.add('loading');
    // Wrap convertImage() in a Promise
    new Promise((resolve, reject) => {
        try {
            convertImage();
            setTimeout(resolve, 1000);
        } catch (error) {
            reject(error);
        }
    })
        .then(() => {
            logMessage("Pattern regenerated successfully.", LOG_TYPE.SUCCESS);
        })
        .catch(error => {
            logMessage("Error regenerating pattern: " + error.message, LOG_TYPE.ERROR);
        })
        .finally(() => {
            // Re-enable button & hide loader
            generateButton.disabled = false;
            generateButton.classList.remove('loading');
        });
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

// Remove existing event listener and add a new one
document.getElementById('gen-image-button')?.addEventListener('click', function() {    
    let apiKey = document.getElementById('api-key')?.value || '';
    const googlyEyes = document.getElementById('googly-eyes');
    const promptElement = document.getElementById('prompt');
    
    // Add null checks
    const promptValue = promptElement?.value || '';
    const googlyEyesChecked = googlyEyes?.checked || false;
    
    const prompt = promptValue + (googlyEyesChecked ? ' with disproportionately large googly eyes' : '');
    
    // Show the converter dialog
    const overlay = document.getElementById('image-converter');
    if (overlay) {
        overlay.classList.remove('hidden');
        // Initialize the UI elements
        initializeUI();
        generateOpenAIImage(apiKey, prompt);
    }
});