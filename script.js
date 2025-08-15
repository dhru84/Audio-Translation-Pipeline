// DOM Elements
const form = document.getElementById('translationForm');
const fileInput = document.getElementById('audio_file');
const fileDisplay = document.querySelector('.file-input-display');
const convertBtn = document.getElementById('convertBtn');
const progressSection = document.getElementById('progressSection');
const successSection = document.getElementById('successSection');
const errorSection = document.getElementById('errorSection');
const progressStatus = document.getElementById('progressStatus');
const progressFill = document.getElementById('progressFill');
const progressDetails = document.getElementById('progressDetails');
const errorMessage = document.getElementById('errorMessage');
const successDetails = document.getElementById('successDetails');

// Global variables
let currentTaskId = null;
let pollingInterval = null;

// File input handling
fileInput.addEventListener('change', handleFileSelect);
fileDisplay.addEventListener('click', () => fileInput.click());
fileDisplay.addEventListener('dragover', handleDragOver);
fileDisplay.addEventListener('dragleave', handleDragLeave);
fileDisplay.addEventListener('drop', handleFileDrop);

// Form submission
form.addEventListener('submit', handleFormSubmit);

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        updateFileDisplay(file);
    }
}

function handleDragOver(event) {
    event.preventDefault();
    fileDisplay.classList.add('dragover');
}

function handleDragLeave(event) {
    event.preventDefault();
    fileDisplay.classList.remove('dragover');
}

function handleFileDrop(event) {
    event.preventDefault();
    fileDisplay.classList.remove('dragover');
    
    const files = event.dataTransfer.files;
    if (files.length > 0) {
        const file = files[0];
        fileInput.files = files;
        updateFileDisplay(file);
    }
}

function updateFileDisplay(file) {
    const icon = fileDisplay.querySelector('i');
    const text = fileDisplay.querySelector('span');
    
    fileDisplay.classList.add('file-selected');
    icon.className = 'fas fa-file-audio';
    text.textContent = `Selected: ${file.name} (${formatFileSize(file.size)})`;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

async function handleFormSubmit(event) {
    event.preventDefault();
    
    // Validate form
    if (!validateForm()) {
        return;
    }
    
    // Show progress section
    hideAllSections();
    progressSection.classList.remove('hidden');
    
    // Update button state
    setButtonLoading(true);
    
    try {
        // Create FormData
        const formData = new FormData(form);
        
        // Submit form
        const response = await fetch('/convert', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            currentTaskId = result.task_id;
            startPolling();
        } else {
            throw new Error(result.error || 'Unknown error occurred');
        }
        
    } catch (error) {
        console.error('Error:', error);
        showError(error.message);
        setButtonLoading(false);
    }
}

function validateForm() {
    const apiKey = document.getElementById('api_key').value.trim();
    const audioFile = fileInput.files[0];
    const outputDir = document.getElementById('output_directory').value.trim();
    
    if (!apiKey) {
        showError('Please enter your Sarvam AI API key.');
        return false;
    }
    
    if (!audioFile) {
        showError('Please select an audio file.');
        return false;
    }
    
    if (!outputDir) {
        showError('Please specify an output directory.');
        return false;
    }
    
    // Check file size (100MB limit)
    const maxSize = 100 * 1024 * 1024; // 100MB
    if (audioFile.size > maxSize) {
        showError('File size exceeds 100MB limit. Please select a smaller file.');
        return false;
    }
    
    // Check file type
    const allowedTypes = ['audio/wav', 'audio/mpeg', 'audio/mp3', 'audio/flac', 'audio/aac', 'audio/m4a'];
    const fileExtension = audioFile.name.split('.').pop().toLowerCase();
    const allowedExtensions = ['wav', 'mp3', 'flac', 'aac', 'm4a'];
    
    if (!allowedExtensions.includes(fileExtension)) {
        showError('Invalid file format. Please select a WAV, MP3, FLAC, AAC, or M4A file.');
        return false;
    }
    
    return true;
}

function startPolling() {
    if (!currentTaskId) return;
    
    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/status/${currentTaskId}`);
            const status = await response.json();
            
            if (response.ok) {
                updateProgress(status);
                
                if (status.status === 'completed') {
                    stopPolling();
                    showSuccess(status);
                } else if (status.status === 'failed') {
                    stopPolling();
                    showError(status.error || 'Processing failed');
                }
            } else {
                console.error('Status check failed:', status.error);
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000); // Poll every 2 seconds
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
    currentTaskId = null;
}

function updateProgress(status) {
    const progressMap = {
        'processing': 20,
        'Splitting audio...': 30,
        'Processing audio chunks...': 60,
        'Merging audio chunks...': 90
    };
    
    let progressPercent = 10; // Default starting progress
    
    if (status.progress) {
        // Check for chunk processing pattern
        const chunkMatch = status.progress.match(/Processing chunk (\d+)\/(\d+)/);
        if (chunkMatch) {
            const current = parseInt(chunkMatch[1]);
            const total = parseInt(chunkMatch[2]);
            progressPercent = 30 + ((current / total) * 30); // 30% to 60%
        } else if (progressMap[status.progress]) {
            progressPercent = progressMap[status.progress];
        }
    }
    
    progressFill.style.width = `${progressPercent}%`;
    progressStatus.textContent = status.status === 'processing' ? 'Processing...' : status.status;
    progressDetails.textContent = status.progress || 'Processing audio translation...';
}

function showSuccess(status) {
    hideAllSections();
    successSection.classList.remove('hidden');
    
    if (status.output_file) {
        successDetails.innerHTML = `
            <strong>Output File:</strong> ${status.output_file}<br>
            <strong>Status:</strong> Translation completed successfully
        `;
    }
    
    setButtonLoading(false);
}

function showError(message) {
    hideAllSections();
    errorSection.classList.remove('hidden');
    errorMessage.textContent = message;
    setButtonLoading(false);
    stopPolling();
}

function hideAllSections() {
    progressSection.classList.add('hidden');
    successSection.classList.add('hidden');
    errorSection.classList.add('hidden');
}

function setButtonLoading(loading) {
    const icon = convertBtn.querySelector('i');
    const text = convertBtn.querySelector('span');
    
    if (loading) {
        convertBtn.disabled = true;
        convertBtn.classList.add('processing');
        icon.className = 'fas fa-sync-alt';
        text.textContent = 'Processing...';
    } else {
        convertBtn.disabled = false;
        convertBtn.classList.remove('processing');
        icon.className = 'fas fa-sync-alt';
        text.textContent = 'Convert Audio';
    }
}

function resetForm() {
    // Reset form
    form.reset();
    
    // Reset file display
    fileDisplay.classList.remove('file-selected');
    const icon = fileDisplay.querySelector('i');
    const text = fileDisplay.querySelector('span');
    icon.className = 'fas fa-cloud-upload-alt';
    text.textContent = 'Click to select audio file or drag and drop';
    
    // Hide all sections
    hideAllSections();
    
    // Reset button
    setButtonLoading(false);
    
    // Stop any polling
    stopPolling();
}

// Language options mapping for better display
const languageNames = {
    'en-IN': 'English (India)',
    'hi-IN': 'Hindi (India)',
    'kn-IN': 'Kannada (India)',
    'ta-IN': 'Tamil (India)',
    'te-IN': 'Telugu (India)',
    'ml-IN': 'Malayalam (India)',
    'bn-IN': 'Bengali (India)',
    'gu-IN': 'Gujarati (India)',
    'mr-IN': 'Marathi (India)',
    'pa-IN': 'Punjabi (India)'
};

// Add language change handlers for better UX
document.getElementById('source_language').addEventListener('change', function() {
    const targetSelect = document.getElementById('target_language');
    const sourceValue = this.value;
    
    // Ensure source and target are different
    if (targetSelect.value === sourceValue) {
        // Find a different language to set as target
        const options = Array.from(targetSelect.options);
        const differentOption = options.find(option => option.value !== sourceValue);
        if (differentOption) {
            targetSelect.value = differentOption.value;
        }
    }
});

document.getElementById('target_language').addEventListener('change', function() {
    const sourceSelect = document.getElementById('source_language');
    const targetValue = this.value;
    
    // Ensure source and target are different
    if (sourceSelect.value === targetValue) {
        // Find a different language to set as source
        const options = Array.from(sourceSelect.options);
        const differentOption = options.find(option => option.value !== targetValue);
        if (differentOption) {
            sourceSelect.value = differentOption.value;
        }
    }
});

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    console.log('Audio Translation Pipeline initialized');
    
    // Set default output directory with timestamp
    const now = new Date();
    const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, -5);
    document.getElementById('output_directory').value = `output_${timestamp}`;
});

// Handle page unload to clean up polling
window.addEventListener('beforeunload', function() {
    stopPolling();
});