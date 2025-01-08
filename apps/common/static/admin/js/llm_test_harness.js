// LLM Test Harness JavaScript
jQuery(function($) {
    'use strict';
    
    console.log("Document ready");
    
    // Get configs from window
    const configs = window.llmConfigs;
    
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
    
    // Cache for model information
    let modelCache = {};
    
    function showError(message) {
        errorMessage.textContent = message;
        $(errorAlert).fadeIn(300);
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
            </div>
            <button type="button" class="btn btn-danger btn-sm mt-2 remove-message">
                <i class="fas fa-trash"></i> Remove
            </button>
        `;
        messagesContainer.appendChild(messageDiv);
        $(messageDiv).slideDown(300);  // Animate the new message
    });
    
    // Remove message button handler with animation
    $(messagesContainer).on('click', '.remove-message', function() {
        const messageDiv = $(this).closest('.message');
        messageDiv.slideUp(300, function() {
            messageDiv.remove();
        });
    });
    
    // Form submission handler
    $(form).on('submit', async function(e) {
        e.preventDefault();
        
        const provider = providerSelect.value;
        const model = modelSelect.value;
        const temperature = parseFloat(document.getElementById('temperature').value) || 0.7;
        const maxTokens = parseInt(document.getElementById('max_tokens').value) || 1000;
        const stream = document.getElementById('stream').checked;
        
        // Collect messages
        const messages = Array.from(messagesContainer.getElementsByClassName('message')).map(msg => ({
            role: msg.querySelector('[name="role"]').value,
            content: msg.querySelector('[name="content"]').value
        }));
        
        // Show loading with animation
        $(loading).fadeIn(300);
        $(completionContainer).fadeOut(300);
        completionText.textContent = '';
        metadataDiv.textContent = '';
        $(errorAlert).fadeOut(300);
        
        try {
            const requestData = {
                provider_type: provider,
                model,
                messages,
                temperature,
                max_tokens: maxTokens,
                stream
            };
            
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