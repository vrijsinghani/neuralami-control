// LLM Test Harness JavaScript
jQuery(function($) {
    'use strict';
    
    // Get configs from window
    const configs = window.llmConfigs;
    
    // Cache for model information
    let modelCache = {};
    let dropzoneCounter = 0;
    
    const form = document.getElementById('test-form');
    const providerSelect = document.getElementById('provider');
    const modelSelect = document.getElementById('model');
    const modelInfo = document.getElementById('model-info');
    const addMessageBtn = document.getElementById('add-message');
    const messagesContainer = document.getElementById('messages');
    const completionContainer = document.getElementById('completion');
    const completionText = document.querySelector('.completion-text');
    const metadataDiv = document.querySelector('.metadata');
    const loading = document.querySelector('.loading');
    const errorAlert = document.getElementById('error-alert');
    const errorMessage = document.getElementById('error-message');
    const enableVision = document.getElementById('enable_vision');
    
    function showError(message) {
        errorMessage.textContent = message;
        $(errorAlert).fadeIn(300);
    }
    
    // Initialize Dropzone for a message
    function initDropzone(container) {
        const dropzoneEl = container.querySelector('.dropzone');
        if (!dropzoneEl) return null;
        
        // Generate unique ID if not already set
        if (!dropzoneEl.id) {
            dropzoneEl.id = `message-dropzone-${++dropzoneCounter}`;
        }
        
        try {
            const dropzone = new Dropzone(`#${dropzoneEl.id}`, {
                url: "/file-upload",
                addRemoveLinks: true,
                acceptedFiles: 'image/jpeg,image/png',
                autoProcessQueue: false,
                uploadMultiple: true,
                parallelUploads: 5,
                maxFilesize: 5,
                dictDefaultMessage: `
                    <i class="fas fa-cloud-upload-alt me-2"></i>
                    Drop images here or click to upload (JPEG, PNG only)
                `,
                init: function() {
                    this.on("addedfile", function(file) {
                        console.log("Processing file:", file.name, "type:", file.type);
                        
                        // Check both MIME type and file extension
                        const needsConversion = file.type !== 'image/jpeg' && file.type !== 'image/png' ||
                                             file.name.toLowerCase().endsWith('.jfif');
                        
                        if (needsConversion) {
                            console.log("Converting file to JPEG:", file.name);
                            const img = new Image();
                            img.onload = () => {
                                const canvas = document.createElement('canvas');
                                canvas.width = img.width;
                                canvas.height = img.height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0);
                                
                                // Convert to JPEG data URL and create new blob
                                canvas.toBlob((blob) => {
                                    // Create a new File object with JPEG type
                                    const convertedFile = new File([blob], file.name.replace(/\.[^/.]+$/, '.jpg'), {
                                        type: 'image/jpeg',
                                        lastModified: new Date().getTime()
                                    });
                                    
                                    // Replace the file in dropzone
                                    const index = this.files.indexOf(file);
                                    if (index !== -1) {
                                        this.files[index] = convertedFile;
                                    }
                                    
                                    // Store the data URL
                                    convertedFile.dataURL = canvas.toDataURL('image/jpeg', 0.9);
                                    console.log("Converted image to JPEG:", convertedFile.name);
                                }, 'image/jpeg', 0.9);
                            };
                            img.onerror = (error) => {
                                console.error("Error loading image for conversion:", error);
                                showError(`Failed to convert image ${file.name}`);
                            };
                            img.src = URL.createObjectURL(file);
                        } else {
                            console.log("Using file as-is:", file.name);
                            const reader = new FileReader();
                            reader.onload = (e) => {
                                file.dataURL = e.target.result;
                                console.log("Created dataURL for:", file.name);
                            };
                            reader.readAsDataURL(file);
                        }
                    });
                    
                    this.on("thumbnail", function(file, dataUrl) {
                        console.log("Generated thumbnail for:", file.name);
                        if (!file.dataURL) {
                            file.dataURL = dataUrl;
                        }
                    });
                    
                    this.on("error", function(file, message) {
                        console.error("Dropzone error:", message);
                        showError(message);
                        this.removeFile(file);
                    });
                }
            });
            
            return dropzone;
        } catch (error) {
            console.error('Error initializing dropzone:', error);
            return null;
        }
    }
    
    // Initialize existing dropzones after a short delay
    setTimeout(() => {
        document.querySelectorAll('.message').forEach(initDropzone);
    }, 100);
    
    // Add message button handler with animation
    $(addMessageBtn).on('click', function() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message';
        messageDiv.style.display = 'none';  // Hide initially for animation
        messageDiv.innerHTML = `
            <div class="message-role">
                <select class="form-control" name="role">
                    <option value="system">System</option>
                    <option value="user" selected>User</option>
                    <option value="assistant">Assistant</option>
                </select>
            </div>
            <div class="message-content">
                <textarea class="form-control" name="content" rows="4" required></textarea>
                <div class="image-upload mt-2" style="display: ${enableVision.checked ? 'block' : 'none'}">
                    <div action="/file-upload" class="form-control dropzone" id="message-dropzone-${dropzoneCounter + 1}"></div>
                </div>
            </div>
            <button type="button" class="btn btn-danger btn-sm mt-2 remove-message">
                <i class="fas fa-trash"></i> Remove
            </button>
        `;
        
        messagesContainer.appendChild(messageDiv);
        
        // Initialize dropzone and show message
        initDropzone(messageDiv);
        $(messageDiv).slideDown(300);
    });
    
    // Handle vision checkbox change
    $(enableVision).on('change', function() {
        const imageUploads = document.querySelectorAll('.image-upload');
        if (this.checked) {
            imageUploads.forEach(upload => $(upload).slideDown(300));
        } else {
            imageUploads.forEach(upload => $(upload).slideUp(300));
        }
    });
    
    // Remove message button handler with animation
    $(messagesContainer).on('click', '.remove-message', function() {
        const messageDiv = $(this).closest('.message');
        const dropzoneEl = messageDiv.find('.dropzone')[0];
        
        // Cleanup dropzone instance
        if (dropzoneEl) {
            const dropzone = Dropzone.forElement(dropzoneEl);
            if (dropzone) {
                dropzone.destroy();
            }
        }
        
        messageDiv.slideUp(300, function() {
            messageDiv.remove();
        });
    });

    // Modify the form submission to include images
    async function getMessageData() {
        const messages = [];
        const messageElements = messagesContainer.querySelectorAll('.message');
        
        for (const messageEl of messageElements) {
            const role = messageEl.querySelector('select[name="role"]').value;
            const content = messageEl.querySelector('textarea[name="content"]').value;
            const dropzoneEl = messageEl.querySelector('.dropzone');
            const dropzone = dropzoneEl ? Dropzone.forElement(dropzoneEl) : null;
            
            if (enableVision.checked && dropzone && dropzone.files.length > 0) {
                const parts = [];
                
                // Get the first image file
                const file = dropzone.files[0];
                
                try {
                    // Get the image data
                    const imageData = await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => {
                            const base64Data = reader.result.split(',')[1];
                            resolve(base64Data);
                        };
                        reader.onerror = reject;
                        reader.readAsDataURL(file);
                    });
                    
                    // Add image first
                    parts.push({
                        mime_type: file.type,
                        data: imageData
                    });
                    
                    // Add prompt after image
                    if (content.trim()) {
                        parts.push(content.trim());
                    } else {
                        parts.push("Describe the image");
                    }
                    
                    messages.push({
                        role: role,
                        content: parts
                    });
                    
                    console.log(`Processed image: ${file.name}, type: ${file.type}, data length: ${imageData.length}`);
                } catch (error) {
                    console.error('Error processing image:', error);
                    showError(`Failed to process image ${file.name}: ${error.message}`);
                }
            } else {
                messages.push({
                    role: role,
                    content: content
                });
            }
        }
        
        // Debug log to verify message structure
        const debugMessages = JSON.parse(JSON.stringify(messages));
        debugMessages.forEach(msg => {
            if (Array.isArray(msg.content)) {
                msg.content.forEach(part => {
                    if (part.data) {
                        part.data = part.data.substring(0, 50) + '...';
                    }
                });
            }
        });
        console.log('Sending messages:', debugMessages);
        
        return messages;
    }
    
    // Load models when provider changes
    $(providerSelect).on('change', async function() {
        const provider = this.value;
        modelSelect.innerHTML = '<option value="">Loading models...</option>';
        modelInfo.innerHTML = '';
        
        if (!provider) {
            modelSelect.innerHTML = '<option value="">Select Provider First</option>';
            return;
        }
        
        try {
            // Show loading state
            $(modelSelect).addClass('loading').prop('disabled', true);
            
            // Try to get models from cache first
            if (!modelCache[provider]) {
                const response = await fetch(window.llmModelsUrl + '?provider=' + provider);
                if (!response.ok) throw new Error('Failed to load models');
                const data = await response.json();
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                if (!data || Object.keys(data).length === 0) {
                    throw new Error('No models available for this provider');
                }
                
                modelCache[provider] = data;
            }
            
            const models = modelCache[provider];
            modelSelect.innerHTML = '<option value="">Select Model</option>';
            
            Object.entries(models).forEach(([modelId, modelData]) => {
                const option = document.createElement('option');
                option.value = modelId;
                option.textContent = modelId;
                option.dataset.info = JSON.stringify(modelData);
                modelSelect.appendChild(option);
            });
            
            // Set default model if specified in config
            const activeConfig = configs.find(c => c.provider_type === provider && c.is_active);
            if (activeConfig && activeConfig.default_model) {
                modelSelect.value = activeConfig.default_model;
                updateModelInfo();
            }
        } catch (error) {
            console.error('Error loading models:', error);
            showError('Failed to load models. Please try again.');
            modelSelect.innerHTML = '<option value="">Failed to load models</option>';
        } finally {
            $(modelSelect).removeClass('loading').prop('disabled', false);
        }
    });
    
    // Update model info when model changes with animation
    $(modelSelect).on('change', function() {
        $(modelInfo).fadeOut(200, function() {
            updateModelInfo();
            $(modelInfo).fadeIn(200);
        });
    });
    
    function updateModelInfo() {
        const selectedOption = modelSelect.selectedOptions[0];
        if (selectedOption && selectedOption.dataset.info) {
            const modelData = JSON.parse(selectedOption.dataset.info);
            modelInfo.innerHTML = `
                <div class="mt-2">
                    <strong>Description:</strong> ${modelData.description || 'N/A'}<br>
                    <strong>Context Window:</strong> ${modelData.context_window || modelData.input_tokens || 'N/A'} tokens<br>
                    <strong>Features:</strong> 
                    ${modelData.supports_vision ? '<span class="badge bg-info me-1">🖼️ Vision</span>' : ''}
                    ${modelData.supports_json ? '<span class="badge bg-success me-1">📋 JSON</span>' : ''}
                    ${modelData.supports_functions ? '<span class="badge bg-warning me-1">⚙️ Functions</span>' : ''}
                </div>
            `;
            
            // Update max tokens based on model limits
            const maxTokensInput = document.getElementById('max_tokens');
            if (modelData.output_tokens) {
                maxTokensInput.max = modelData.output_tokens;
                maxTokensInput.value = Math.min(maxTokensInput.value, modelData.output_tokens);
            }
        } else {
            modelInfo.innerHTML = '';
        }
    }
    
    // Form submission handler
    $(form).on('submit', async function(e) {
        e.preventDefault();
        
        const provider = providerSelect.value;
        const model = modelSelect.value;
        const temperature = parseFloat(document.getElementById('temperature').value) || 0.7;
        const maxTokens = parseInt(document.getElementById('max_tokens').value) || 1000;
        const stream = document.getElementById('stream').checked;
        
        // Show loading with animation
        $(loading).fadeIn(300);
        $(completionContainer).fadeOut(300);
        completionText.textContent = '';
        metadataDiv.textContent = '';
        $(errorAlert).fadeOut(300);
        
        try {
            const messages = await getMessageData();
            
            // Transform to Gemini vision API format
            const requestData = {
                provider_type: provider,
                model,
                messages: messages,  // Send all messages instead of just first message content
                temperature,
                max_tokens: maxTokens,
                stream
            };
            
            // Log request data for debugging
            const debugRequestData = JSON.parse(JSON.stringify(requestData));
            if (debugRequestData.messages) {
                debugRequestData.messages.forEach(msg => {
                    if (Array.isArray(msg.content)) {
                        msg.content.forEach(part => {
                            if (part.data) {
                                part.data = part.data.substring(0, 50) + '...';
                            }
                        });
                    }
                });
            }
            console.log('Sending request:', debugRequestData);
            
            if (stream) {
                // Handle streaming response
                const response = await fetch(window.llmCompletionUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.csrfToken
                    },
                    body: JSON.stringify(requestData)
                });
                
                if (!response.ok) {
                    throw new Error('Failed to get streaming response');
                }
                
                $(completionContainer).fadeIn(300);
                const reader = response.body.getReader();
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    
                    const text = new TextDecoder().decode(value);
                    completionText.textContent += text;
                    // Auto-scroll to bottom of completion
                    completionText.scrollTop = completionText.scrollHeight;
                }
            } else {
                // Handle regular response
                const response = await fetch(window.llmCompletionUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.csrfToken
                    },
                    body: JSON.stringify(requestData)
                });
                
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to get completion');
                }
                
                $(completionContainer).fadeIn(300);
                completionText.textContent = data.completion;
                
                if (data.metadata) {
                    console.log('Response metadata:', data.metadata);
                    const usage = data.metadata.usage || {};
                    const promptTokens = usage.prompt_tokens || usage.input_tokens || data.metadata.prompt_tokens || data.metadata.input_tokens || 'N/A';
                    const completionTokens = usage.completion_tokens || usage.output_tokens || data.metadata.completion_tokens || data.metadata.output_tokens || 'N/A';
                    const totalTokens = usage.total_tokens || data.metadata.total_tokens || (promptTokens !== 'N/A' && completionTokens !== 'N/A' ? promptTokens + completionTokens : 'N/A');

                    metadataDiv.innerHTML = `
                        <div class="metadata-content">
                            <h5 class="mb-3">Usage Statistics</h5>
                            <div class="row">
                                <div class="col-md-4">
                                    <div class="card bg-light">
                                        <div class="card-body">
                                            <h6 class="card-title">Prompt Tokens</h6>
                                            <p class="card-text">${promptTokens}</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="card bg-light">
                                        <div class="card-body">
                                            <h6 class="card-title">Completion Tokens</h6>
                                            <p class="card-text">${completionTokens}</p>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="card bg-light">
                                        <div class="card-body">
                                            <h6 class="card-title">Total Tokens</h6>
                                            <p class="card-text">${totalTokens}</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                }
            }
        } catch (error) {
            console.error('Error:', error);
            showError(error.message || 'An error occurred');
        } finally {
            $(loading).fadeOut(300);
        }
    });
}); 