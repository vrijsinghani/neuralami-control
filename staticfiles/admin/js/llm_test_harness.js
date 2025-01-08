// LLM Test Harness JavaScript
(function($) {
    'use strict';
    
    $(document).ready(function() {
        console.log("Document ready");
        console.log("jQuery version:", $.fn.jquery);
        
        // Parse configs from JSON script tag
        const configs = JSON.parse(document.getElementById('config-data').textContent);
        console.log("Configs:", configs);
        
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
        
        console.log("Provider select element:", providerSelect);
        console.log("Available providers:", Array.from(providerSelect.options).map(opt => ({value: opt.value, text: opt.text})));
        
        // Cache for model information
        let modelCache = {};
        
        function showError(message) {
            console.error("Error:", message);
            errorMessage.textContent = message;
            errorAlert.style.display = 'block';
        }
        
        // Load models when provider changes
        $(providerSelect).on('change', async function() {
            console.log("Provider changed to:", this.value);
            const provider = this.value;
            modelSelect.innerHTML = '<option value="">Loading models...</option>';
            modelInfo.innerHTML = '';
            
            if (!provider) {
                modelSelect.innerHTML = '<option value="">Select Provider First</option>';
                return;
            }
            
            try {
                console.log("Fetching models for provider:", provider);
                // Try to get models from cache first
                if (!modelCache[provider]) {
                    const response = await fetch(window.llmModelsUrl + '?provider=' + provider);
                    console.log("API Response:", response);
                    if (!response.ok) throw new Error('Failed to load models');
                    modelCache[provider] = await response.json();
                    console.log("Received models:", modelCache[provider]);
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
                console.log("Available configs:", configs);
                const activeConfig = configs.find(c => c.provider_type === provider && c.is_active);
                if (activeConfig && activeConfig.default_model) {
                    console.log("Setting default model:", activeConfig.default_model);
                    modelSelect.value = activeConfig.default_model;
                    updateModelInfo();
                }
            } catch (error) {
                console.error('Error loading models:', error);
                showError('Failed to load models. Please try again.');
                modelSelect.innerHTML = '<option value="">Failed to load models</option>';
            }
        });
        
        // Update model info when model changes
        $(modelSelect).on('change', updateModelInfo);
        
        function updateModelInfo() {
            const selectedOption = modelSelect.selectedOptions[0];
            if (selectedOption && selectedOption.dataset.info) {
                const modelData = JSON.parse(selectedOption.dataset.info);
                modelInfo.innerHTML = `
                    <div class="mt-2">
                        <strong>Description:</strong> ${modelData.description || 'N/A'}<br>
                        <strong>Context Window:</strong> ${modelData.context_window || modelData.input_tokens || 'N/A'} tokens<br>
                        <strong>Features:</strong> 
                        ${modelData.supports_vision ? '🖼️ Vision ' : ''}
                        ${modelData.supports_json ? '📋 JSON ' : ''}
                        ${modelData.supports_functions ? '⚙️ Functions ' : ''}
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
        
        // Add message button handler
        $(addMessageBtn).on('click', function() {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message mt-3';
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
                <button type="button" class="btn btn-danger btn-sm mt-2 remove-message">Remove</button>
            `;
            messagesContainer.appendChild(messageDiv);
        });
        
        // Remove message button handler
        $(messagesContainer).on('click', '.remove-message', function() {
            $(this).closest('.message').remove();
        });
        
        // Form submission handler
        $(form).on('submit', async function(e) {
            e.preventDefault();
            
            const provider = providerSelect.value;
            const model = modelSelect.value;
            const temperature = parseFloat(document.getElementById('temperature').value);
            const maxTokens = parseInt(document.getElementById('max_tokens').value);
            const stream = document.getElementById('stream').checked;
            
            // Collect messages
            const messages = Array.from(messagesContainer.getElementsByClassName('message')).map(msg => ({
                role: msg.querySelector('[name="role"]').value,
                content: msg.querySelector('[name="content"]').value
            }));
            
            // Show loading
            loading.style.display = 'block';
            completionContainer.style.display = 'none';
            completionText.textContent = '';
            metadataDiv.textContent = '';
            errorAlert.style.display = 'none';
            
            try {
                if (stream) {
                    // Handle streaming response
                    const response = await fetch(window.llmCompletionUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.csrfToken
                        },
                        body: JSON.stringify({
                            provider_type: provider,
                            model,
                            messages,
                            temperature,
                            max_tokens,
                            stream: true
                        })
                    });
                    
                    if (!response.ok) {
                        throw new Error('Failed to get streaming response');
                    }
                    
                    completionContainer.style.display = 'block';
                    const reader = response.body.getReader();
                    
                    while (true) {
                        const {done, value} = await reader.read();
                        if (done) break;
                        
                        const text = new TextDecoder().decode(value);
                        completionText.textContent += text;
                    }
                } else {
                    // Handle regular response
                    const response = await fetch(window.llmCompletionUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.csrfToken
                        },
                        body: JSON.stringify({
                            provider_type: provider,
                            model,
                            messages,
                            temperature,
                            max_tokens,
                            stream: false
                        })
                    });
                    
                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Failed to get completion');
                    }
                    
                    completionContainer.style.display = 'block';
                    completionText.textContent = data.completion;
                    
                    if (data.metadata) {
                        metadataDiv.innerHTML = `
                            <strong>Usage:</strong><br>
                            Prompt Tokens: ${data.metadata.usage?.prompt_tokens || 'N/A'}<br>
                            Completion Tokens: ${data.metadata.usage?.completion_tokens || 'N/A'}<br>
                            Total Tokens: ${data.metadata.usage?.total_tokens || 'N/A'}
                        `;
                    }
                }
            } catch (error) {
                console.error('Error:', error);
                showError(error.message || 'An error occurred');
            } finally {
                loading.style.display = 'none';
            }
        });
        
        // Trigger initial model load if provider is pre-selected
        if (providerSelect.value) {
            console.log("Triggering initial model load for:", providerSelect.value);
            $(providerSelect).trigger('change');
        }
    });
})(django.jQuery); 