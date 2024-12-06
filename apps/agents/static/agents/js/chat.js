class ChatManager {
    constructor(config) {
        // Initialize with provided configuration
        this.socket = config.socket;
        this.sessionId = config.sessionId;
        this.currentConversation = config.currentConversation;
        this.selectedAgentId = null;
        this.isProcessing = false;
        this.isReconnecting = false;
        
        // Store element references from config
        this.elements = {
            agentSelect: config.agentSelect,
            modelSelect: config.modelSelect,
            clientSelect: config.clientSelect,
            messageInput: config.messageInput,
            sendButton: config.sendButton,
            chatMessages: config.messagesContainer,
            connectionStatus: config.connectionStatus,
            agentAvatar: config.agentAvatar?.querySelector('img') || config.agentAvatar,
            agentName: config.agentName,
            selectedModel: config.selectedModel,
            newChatBtn: document.getElementById('new-chat-btn')
        };
        
        // Initialize
        this.initialize();
    }

    initialize() {
        if (!this.validateElements()) {
            console.error('Failed to initialize: missing required elements');
            return;
        }
        
        // Set initial agent selection
        if (this.elements.agentSelect.options.length > 0) {
            this.selectedAgentId = this.elements.agentSelect.value;
            this.updateAgentInfo(this.elements.agentSelect.selectedOptions[0]);
        }

        // Initialize autosize for textarea
        this.initializeAutosize();
        
        // Bind events
        this.bindEvents();
        
        // Set up WebSocket handlers
        this.setupWebSocket();
    }

    updateAgentInfo(selectedOption) {
        if (!selectedOption) return;

        // Update agent avatar if available
        if (this.elements.agentAvatar && selectedOption.dataset.avatar) {
            this.elements.agentAvatar.src = selectedOption.dataset.avatar;
        }
        
        // Update agent name if available
        if (this.elements.agentName && selectedOption.dataset.name) {
            this.elements.agentName.textContent = selectedOption.dataset.name;
        }
    }

    handleAgentSelection() {
        const selectedOption = this.elements.agentSelect.selectedOptions[0];
        if (!selectedOption) return;

        this.selectedAgentId = this.elements.agentSelect.value;
        this.updateAgentInfo(selectedOption);
    }

    validateElements() {
        const requiredElements = [
            'agentSelect', 'modelSelect', 'clientSelect', 
            'messageInput', 'sendButton', 'chatMessages'
        ];

        const missingElements = requiredElements.filter(
            elementName => !this.elements[elementName]
        );

        if (missingElements.length > 0) {
            console.error('Missing required elements:', missingElements);
            return false;
        }
        return true;
    }

    setupWebSocket() {
        if (!this.socket) {
            console.error('No WebSocket provided');
            return;
        }

        this.socket.onopen = () => this.handleSocketOpen();
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.processMessageData(data);
            } catch (error) {
                console.error('Failed to process message:', error);
                this.handleError('Failed to process message');
            }
        };
        this.socket.onclose = (event) => this.handleSocketClose(event);
        this.socket.onerror = (error) => this.handleSocketError(error);
    }

    initializeAutosize() {
        if (typeof autosize === 'function') {
            autosize(this.elements.messageInput);
        } else {
            console.warn('Autosize plugin not loaded. Textarea will not auto-resize.');
            // Set a default height for the textarea
            this.elements.messageInput.style.minHeight = '50px';
            this.elements.messageInput.style.maxHeight = '200px';
        }
    }

    bindEvents() {
        // Agent selection
        this.elements.agentSelect?.addEventListener('change', () => this.handleAgentSelection());

        // Message sending
        this.elements.sendButton?.addEventListener('click', () => this.sendMessage());
        this.elements.messageInput?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Connection management
        document.addEventListener('visibilitychange', () => this.handleVisibilityChange());
        window.addEventListener('beforeunload', () => this.closeWebSocket());

        // Add event listener for Ctrl+Enter
        this.elements.messageInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault(); // Prevent default newline
                this.sendMessage();
            }
        });
    }

    appendMessage(message, isAgent = false) {
        if (!this.elements.chatMessages) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `d-flex ${isAgent ? 'justify-content-start' : 'justify-content-end'} mb-4`;
        
        const contentWrapper = document.createElement('div');
        contentWrapper.className = isAgent ? 'agent-message' : 'user-message';
        contentWrapper.style.maxWidth = '75%';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (isAgent) {
            // For agent messages, handle HTML and markdown
            if (message.includes('<table') || message.includes('<div')) {
                contentDiv.innerHTML = message;

                // Add Bootstrap classes to table if not already present
                const table = contentDiv.querySelector('table');
                if (table) {
                    table.classList.add('table', 'table-striped', 'table-hover', 'table-sm');
                    
                    // Add Bootstrap classes to thead and tbody
                    const thead = table.querySelector('thead');
                    if (thead) {
                        thead.classList.add('table-dark');
                    }
                }
            } else if (message.startsWith('{') || message.startsWith('[')) {
                // Try to parse and format JSON
                try {
                    const parsed = JSON.parse(message);
                    contentDiv.innerHTML = `<pre class="json-output">${JSON.stringify(parsed, null, 2)}</pre>`;
                } catch (e) {
                    // If JSON parsing fails, treat as markdown
                    contentDiv.innerHTML = marked.parse(message);
                }
            } else {
                // Regular markdown content
                contentDiv.innerHTML = marked.parse(message);
            }
            
            // Add agent info
            if (this.elements.agentAvatar && this.elements.agentName) {
                const agentInfo = document.createElement('div');
                agentInfo.className = 'd-flex align-items-center mb-2';
                
                const avatar = document.createElement('img');
                avatar.src = this.elements.agentAvatar.src;
                avatar.className = 'avatar-img rounded-circle me-2';
                avatar.style.width = '24px';
                avatar.style.height = '24px';
                
                const name = document.createElement('span');
                name.className = 'text-dark font-weight-bold text-sm';
                name.textContent = this.elements.agentName.textContent;
                
                agentInfo.appendChild(avatar);
                agentInfo.appendChild(name);
                contentDiv.insertBefore(agentInfo, contentDiv.firstChild);
            }
        } else {
            // User messages are always plain text
            contentDiv.textContent = message;
        }
        
        contentWrapper.appendChild(contentDiv);
        messageDiv.appendChild(contentWrapper);
        this.elements.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    showTypingIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'chat-message agent typing-indicator';
        indicator.innerHTML = `
            <div class="message-content">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        this.elements.chatMessages.appendChild(indicator);
        this.scrollToBottom();
        return indicator;
    }

    scrollToBottom() {
        if (this.elements.chatMessages) {
            this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
        }
    }

    processMessageData(data) {
        if (data.error) {
            console.error('Error:', data.message);
            this.handleError(data.message);
            return;
        }

        if (data.type === 'keep_alive_response') return;

        // Remove typing indicator if exists
        if (this._currentTypingIndicator) {
            this._currentTypingIndicator.remove();
            this._currentTypingIndicator = null;
        }

        // Process message based on type
        if (data.type === 'user_message') {
            if (data.message) {
                this.appendMessage(data.message, false);
            }
        } else if (data.type === 'agent_message') {
            let message = data.message || '';
            
            // Check if this is a tool usage message
            if (message && (message.includes('AgentAction(tool=') || message.includes('AgentStep(action='))) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'agent-message';
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content tool-usage';
                
                // Create header with icon
                const header = document.createElement('div');
                header.className = 'd-flex align-items-center';
                
                const icon = document.createElement('i');
                icon.className = 'fas fa-cog me-2';
                header.appendChild(icon);
                
                const title = document.createElement('span');
                title.className = 'tool-title';
                
                // Extract tool name
                const toolMatch = message.match(/tool='([^']+)'/);
                if (toolMatch) {
                    const toolName = toolMatch[1].replace(/_/g, ' ');
                    title.textContent = `Using: ${toolName}`;
                } else {
                    title.textContent = 'Processing Data';
                }
                header.appendChild(title);
                
                // Add collapse toggle
                const toggle = document.createElement('button');
                toggle.className = 'btn btn-link btn-sm ms-auto';
                toggle.innerHTML = '<i class="fas fa-chevron-down"></i>';
                header.appendChild(toggle);
                
                // Create collapsible content
                const content = document.createElement('div');
                content.className = 'collapse mt-2';
                
                // Format the message for better readability
                const formattedMessage = message
                    .replace(/AgentAction/g, '\nAgentAction')
                    .replace(/AgentStep/g, '\nAgentStep')
                    .replace(/HumanMessage/g, '\nHumanMessage')
                    .replace(/AIMessage/g, '\nAIMessage')
                    .replace(/observation=/g, '\nobservation=');
                
                content.innerHTML = `<pre class="json-output">${formattedMessage}</pre>`;
                
                // Add click handler for toggle
                toggle.addEventListener('click', () => {
                    const isCollapsed = !content.classList.contains('show');
                    content.classList.toggle('show');
                    toggle.innerHTML = isCollapsed ? 
                        '<i class="fas fa-chevron-up"></i>' : 
                        '<i class="fas fa-chevron-down"></i>';
                });
                
                contentDiv.appendChild(header);
                contentDiv.appendChild(content);
                messageDiv.appendChild(contentDiv);
                this.elements.chatMessages.appendChild(messageDiv);
                this.scrollToBottom();
                return;
            }
            
            // Handle regular messages
            if (message) {
                if (message.includes('<table') || message.includes('<div')) {
                    this.appendMessage(message, true);
                } else if (message.includes('|') && message.includes('\n')) {
                    // Convert markdown table to HTML
                    const lines = message.trim().split('\n');
                    let html = '<table class="table table-striped table-hover table-sm"><thead><tr>';
                    
                    // Process headers
                    const headers = lines[0].split('|').map(h => h.trim()).filter(h => h);
                    headers.forEach(header => {
                        html += `<th>${header}</th>`;
                    });
                    html += '</tr></thead><tbody>';
                    
                    // Skip header and separator lines
                    for (let i = 2; i < lines.length; i++) {
                        const cells = lines[i].split('|').map(c => c.trim()).filter(c => c);
                        if (cells.length) {
                            html += '<tr>';
                            cells.forEach(cell => {
                                html += `<td>${cell}</td>`;
                            });
                            html += '</tr>';
                        }
                    }
                    html += '</tbody></table>';
                    this.appendMessage(html, true);
                } else {
                    this.appendMessage(message, true);
                }
            }
        } else if (data.type === 'system_message') {
            this.handleSystemMessage(data);
        } else if (data.type === 'error') {
            this.handleError(data.message || 'An unknown error occurred');
        }

        this.isProcessing = false;
        if (this.elements.sendButton) {
            this.elements.sendButton.disabled = false;
        }
    }

    handleError(message) {
        console.error('Error:', message);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.textContent = message;
        this.elements.chatMessages.appendChild(errorDiv);
        this.scrollToBottom();
    }

    handleSystemMessage(data) {
        if (data.connection_status === 'connected') {
            if (this.elements.connectionStatus) {
                const dot = this.elements.connectionStatus.querySelector('.connection-dot');
                if (dot) {
                    dot.className = 'connection-dot connected';
                }
            }
        }
    }

    startNewChat() {
        Swal.fire({
            title: 'Start New Chat?',
            text: 'This will clear the current conversation.',
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'Yes, start new',
            cancelButtonText: 'Cancel'
        }).then((result) => {
            if (result.isConfirmed) {
                this.elements.chatMessages.innerHTML = '';
                this.elements.messageInput.value = '';
                
                // Safely update autosize
                if (typeof autosize === 'function') {
                    autosize.update(this.elements.messageInput);
                }
                
                Swal.fire({
                    icon: 'success',
                    title: 'New Chat Started',
                    toast: true,
                    position: 'bottom-end',
                    showConfirmButton: false,
                    timer: 3000,
                    timerProgressBar: true
                });
            }
        });
    }

    async reconnectWebSocket() {
        if (this.isReconnecting) return;
        
        this.isReconnecting = true;
        this.updateConnectionStatus('Reconnecting...', 'warning');
        
        try {
            await this.closeWebSocket();
            await new Promise(resolve => setTimeout(resolve, 1000));
            this.initializeWebSocket();
        } finally {
            this.isReconnecting = false;
        }
    }

    updateConnectionStatus(message, status = 'success') {
        const dot = this.elements.connectionStatus.querySelector('.connection-dot');
        
        // Remove all status classes
        dot.classList.remove('connected', 'connecting');
        
        // Add appropriate class based on status
        switch(status) {
            case 'success':
                dot.classList.add('connected');
                break;
            case 'warning':
                dot.classList.add('connecting');
                break;
            case 'error':
                // Default red state (no class needed)
                break;
        }
        
        this.elements.connectionStatus.setAttribute('title', message);
        
        // Initialize or update tooltip
        if (!this.elements.connectionStatus._tooltip) {
            this.elements.connectionStatus._tooltip = new bootstrap.Tooltip(this.elements.connectionStatus);
        } else {
            this.elements.connectionStatus._tooltip.dispose();
            this.elements.connectionStatus._tooltip = new bootstrap.Tooltip(this.elements.connectionStatus);
        }
    }

    handleSocketOpen() {
        this.updateConnectionStatus('Connected', 'success');
        if (this.elements.sendButton) {
            this.elements.sendButton.disabled = false;
        }
        this.setupKeepAlive();
    }

    handleSocketClose(event) {
        this.updateConnectionStatus('Disconnected', 'error');
        this.elements.sendButton.disabled = true;
        
        if (!this.isReconnecting) {
            setTimeout(() => this.reconnectWebSocket(), 5000);
        }
    }

    handleSocketError(error) {
        console.error('WebSocket error:', error);
        this.updateConnectionStatus('Connection Error', 'error');
    }

    handleVisibilityChange() {
        if (document.visibilityState === 'visible') {
            if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
                this.reconnectWebSocket();
            }
        }
    }

    setupKeepAlive() {
        this.keepAliveInterval = setInterval(() => {
            if (this.socket?.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({
                    type: 'keep_alive',
                    timestamp: Date.now()
                }));
            }
        }, 25000);
    }

    async closeWebSocket() {
        if (this.keepAliveInterval) {
            clearInterval(this.keepAliveInterval);
        }
        
        if (this.socket) {
            this.socket.onclose = null; // Prevent reconnection attempt
            this.socket.close();
            this.socket = null;
        }
    }

    async sendMessage() {
        const message = this.elements.messageInput.value.trim();
        const agentId = this.elements.agentSelect.value;
        const modelName = this.elements.modelSelect.value;
        const clientId = this.elements.clientSelect.value || null;  // Use null if empty

        if (!message || !agentId) {
            this.handleError('Please enter a message and select an agent');
            return;
        }

        if (this.isProcessing) {
            return;
        }

        this.isProcessing = true;
        if (this.elements.sendButton) {
            this.elements.sendButton.disabled = true;
        }

        try {
            await this.socket.send(JSON.stringify({
                type: 'user_message',
                message: message,
                agent_id: agentId,
                model: modelName,
                client_id: clientId || undefined  // Only send if not null
            }));

            // Clear input after successful send
            this.elements.messageInput.value = '';
            this.elements.messageInput.style.height = 'auto';

        } catch (error) {
            console.error('Error sending message:', error);
            this.handleError('Failed to send message');
            this.isProcessing = false;
            if (this.elements.sendButton) {
                this.elements.sendButton.disabled = false;
            }
        }
    }
} 