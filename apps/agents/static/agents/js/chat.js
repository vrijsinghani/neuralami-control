function deleteConversation(sessionId, event) {
    event.preventDefault();
    event.stopPropagation();
    
    if (confirm('Are you sure you want to delete this conversation?')) {
        fetch(window.chatConfig.urls.deleteConversation.replace('{sessionId}', sessionId), {
            method: 'POST',
            headers: {
                'X-CSRFToken': window.chatConfig.csrfToken,
            }
        })
        .then(response => {
            if (response.ok) {
                if (window.location.href.includes(sessionId)) {
                    window.location.href = window.chatConfig.urls.newChat;
                } else {
                    event.target.closest('.position-relative').remove();
                }
            } else {
                throw new Error('Failed to delete conversation');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to delete conversation');
        });
    }
}

window.deleteConversation = deleteConversation;

class ChatManager {
    constructor(options) {
        // Get required elements from options
        this.elements = {
            input: document.getElementById('message-input'),
            sendBtn: document.getElementById('send-message'),
            messages: document.getElementById('chat-messages'),
            status: document.getElementById('connection-status'),
            agentSelect: document.getElementById('agent-select'),
            modelSelect: document.getElementById('model-select'),
            clientSelect: document.getElementById('client-select'),
            newChatBtn: document.getElementById('new-chat-btn')
        };

        // Store session info
        this.sessionId = this.elements.messages?.dataset.sessionId;
        if (!this.sessionId) {
            throw new Error('Chat messages container or session ID not found');
        }

        // Store current agent info
        this.currentAgent = {
            avatar: document.querySelector('#agent-avatar img')?.src || '/static/agents/img/agent-avatar.png',
            name: document.querySelector('#agent-name')?.textContent || 'Agent'
        };

        // Store user avatar
        this.userAvatar = document.querySelector('#user-avatar img')?.src || '/static/agents/img/user-avatar.jpg';

        // Initialize autosize for textarea
        if (typeof autosize === 'function') {
            autosize(this.elements.input);
        }

        // Setup WebSocket
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(
            `${wsProtocol}//${window.location.host}/ws/chat/?session=${this.sessionId}`
        );

        this.setupEventListeners();
    }

    setupEventListeners() {
        // WebSocket events
        this.socket.onopen = () => this.updateStatus('connected');
        this.socket.onclose = () => {
            this.updateStatus('disconnected');
            setTimeout(() => this.reconnect(), 5000);
        };
        this.socket.onmessage = (event) => this.handleMessage(event.data);

        // Send message events
        this.elements.sendBtn?.addEventListener('click', () => this.sendMessage());
        this.elements.input?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Update agent info on selection
        this.elements.agentSelect?.addEventListener('change', () => {
            const option = this.elements.agentSelect.selectedOptions[0];
            if (option) {
                // Update stored agent info
                this.currentAgent = {
                    avatar: option.dataset.avatar || '/static/assets/img/team-3.jpg',
                    name: option.dataset.name || 'Agent'
                };

                // Update UI elements
                const avatar = document.querySelector('#agent-avatar img');
                const name = document.getElementById('agent-name');
                if (avatar) avatar.src = this.currentAgent.avatar;
                if (name) name.textContent = this.currentAgent.name;
            }
        });
    }

    updateStatus(status) {
        const dot = this.elements.status?.querySelector('.connection-dot');
        if (dot) {
            dot.classList.toggle('connected', status === 'connected');
        }
    }

    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            console.log('Received message:', message);
            
            switch (message.type) {
                case 'agent_message':
                    // Collapse messages with specific content
                    if (message.message && message.message.includes('AgentStep')) {
                        console.log('AgentStep');
                        this.appendCollapsedMessage(message.message);
                        return;
                    }
                    // Ignore messages with specific content
                    if (message.message && message.message.includes('AgentAction')) {
                        console.log('agent_message');
                        return; // Ignore this message
                    }

                    // Only handle non-tool messages
                    if (message.message && typeof message.message === 'string') {
                        console.log('non-tool message');
                        this.appendMessage(message.message, true);
                    }
                    break;

                case 'user_message':
                    console.log('user_message');
                    this.appendMessage(message.message, false);
                    break;

                case 'error':
                    this.showError(message.message || 'An error occurred');
                    break;

                case 'system_message':
                    if (message.connection_status) {
                        console.log('system_message');
                        this.updateStatus(message.connection_status);
                    }
                    break;
            }
        } catch (error) {
            console.error('Failed to parse message:', error);
        }
    }

    appendCollapsedMessage(content) {
        // Extract tool name from the content
        const toolNameMatch = content.match(/tool='([^']+)'/);
        const toolName = toolNameMatch ? toolNameMatch[1] : 'Unknown Tool';
        
        // Extract observation from AgentStep
        const observationMatch = content.match(/observation='([^']+)'/);
        const observation = observationMatch ? observationMatch[1] : content;
        
        // Format tool name for display
        const prettyToolName = toolName.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');

        const messageId = `msg-${Date.now()}`;
        const html = `
            <div class="d-flex justify-content-start mb-4">
                <div class="avatar me-2">
                    <img src="${this.currentAgent.avatar}" alt="${this.currentAgent.name}" class="border-radius-lg shadow">
                </div>
                <div class="tool-message start w-100" style="max-width: 75%;">
                    <div class="message-content tool-usage">
                        <div class="tool-header d-flex align-items-center" 
                             data-bs-toggle="collapse" 
                             data-bs-target="#${messageId}" 
                             aria-expanded="false" 
                             aria-controls="${messageId}"
                             role="button">
                            <i class="fas fa-cog me-2"></i>
                            <strong>${prettyToolName}</strong>
                            <i class="fas fa-chevron-down ms-auto"></i>
                        </div>
                        <div class="collapse" id="${messageId}">
                            <div class="tool-details mt-3">
                                <div class="json-output">
                                    <pre style="white-space: pre-wrap; word-break: break-word;">${observation}</pre>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        
        // Initialize collapse and ensure it starts collapsed
        const collapseElement = document.getElementById(messageId);
        if (collapseElement) {
            const bsCollapse = new bootstrap.Collapse(collapseElement, {
                toggle: false // Ensure it starts collapsed
            });
        }
    
        this.scrollToBottom();
    }

    handleToolMessage(message) {
        console.log('Handling tool message:', message);
        switch (message.message_type) {
            case 'tool_start':
                this.handleToolStart(message.message);
                break;
            case 'tool_output':
                this.handleToolOutput(message.message);
                break;
            case 'tool_error':
                this.handleToolError(message.message);
                break;
            default:
                console.log('Unknown tool message type:', message.message_type);
        }
    }

    handleToolStart(content) {
        console.log('Starting tool with content:', content);
        if (!content) return;

        let toolName = content.name;
        let toolInput = content.input;
        let toolOutput = content.output;

        // Format tool name for display
        const prettyToolName = toolName.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');

        const messageId = `tool-${Date.now()}`;
        const html = `
            <div class="d-flex justify-content-start mb-4">
                <div class="avatar me-2">
                    <img src="${this.currentAgent.avatar}" alt="${this.currentAgent.name}" class="border-radius-lg shadow">
                </div>
                <div class="tool-message start w-100" style="max-width: 75%;">
                    <div class="message-content tool-usage">
                        <div class="tool-header d-flex align-items-center collapsed" 
                             data-bs-toggle="collapse" 
                             data-bs-target="#${messageId}" 
                             aria-expanded="false" 
                             aria-controls="${messageId}"
                             role="button">
                            <i class="fas fa-cog me-2"></i>
                            <strong>${prettyToolName}</strong>
                            <i class="fas fa-chevron-down ms-auto"></i>
                        </div>
                        <div class="collapse" id="${messageId}">
                            <div class="tool-details mt-3">
                                <div class="tool-input">
                                    <strong>Input:</strong>
                                    <pre class="json-output mt-2">${JSON.stringify(toolInput, null, 2)}</pre>
                                </div>
                                ${toolOutput ? `
                                <div class="tool-output mt-3">
                                    <strong>Output:</strong>
                                    <div class="mt-2">${toolOutput}</div>
                                </div>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        
        // Initialize collapse
        const collapseElement = document.getElementById(messageId);
        if (collapseElement) {
            new bootstrap.Collapse(collapseElement);
        }

        this.scrollToBottom();
    }

    handleToolOutput(content) {
        if (!content) return;

        let formattedContent;
        if (typeof content === 'object') {
            formattedContent = JSON.stringify(content, null, 2);
        } else {
            formattedContent = content;
        }

        // Find the last tool message and append output
        const lastToolMessage = this.elements.messages.querySelector('.tool-message.start:last-child');
        if (lastToolMessage) {
            const collapseContent = lastToolMessage.querySelector('.collapse');
            const outputHtml = `
                <div class="tool-output mt-3">
                    <strong>Output:</strong>
                    <pre class="json-output mt-2">${formattedContent}</pre>
                </div>
            `;
            collapseContent.insertAdjacentHTML('beforeend', outputHtml);
        }
        
        this.scrollToBottom();
    }

    handleToolError(content) {
        if (!content) return;

        const messageId = `msg-${Date.now()}`;
        const html = `
            <div class="d-flex justify-content-start mb-4" id="${messageId}-container">
                <div class="avatar me-3">
                    <img src="${this.currentAgent.avatar}" alt="${this.currentAgent.name}" 
                         class="border-radius-lg shadow-sm" width="48" height="48">
                </div>
                <div class="tool-message error" style="max-width: 75%;">
                    <div class="message-content position-relative">
                        <div class="message-actions position-absolute top-0 end-0 m-2 opacity-0">
                            <button class="btn btn-link btn-sm p-0 copy-message" title="Copy to clipboard">
                                <i class="fas fa-copy"></i>
                            </button>
                        </div>
                        <div class="message-text">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            ${typeof content === 'object' ? content.message : content}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.addMessageEventListeners(messageId);
        this.scrollToBottom();
    }

    addMessageEventListeners(messageId) {
        const messageContainer = document.getElementById(`${messageId}-container`);
        if (!messageContainer) return;

        // Show/hide actions on hover
        messageContainer.addEventListener('mouseenter', () => {
            messageContainer.querySelector('.message-actions')?.classList.remove('opacity-0');
        });
        messageContainer.addEventListener('mouseleave', () => {
            messageContainer.querySelector('.message-actions')?.classList.add('opacity-0');
        });

        // Copy button
        const copyBtn = messageContainer.querySelector('.copy-message');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => {
                const textToCopy = messageContainer.querySelector('.message-text').textContent.trim();
                navigator.clipboard.writeText(textToCopy).then(() => {
                    // Show temporary success feedback
                    const icon = copyBtn.querySelector('i');
                    icon.classList.remove('fa-copy');
                    icon.classList.add('fa-check');
                    setTimeout(() => {
                        icon.classList.remove('fa-check');
                        icon.classList.add('fa-copy');
                    }, 1500);
                });
            });
        }

        // Edit button
        const editBtn = messageContainer.querySelector('.edit-message');
        if (editBtn) {
            editBtn.addEventListener('click', () => {
                const messageText = messageContainer.querySelector('.message-text').textContent.trim();
                this.elements.input.value = messageText;
                this.elements.input.focus();
                
                // Set edit state
                this.isEditing = true;
                
                // Remove the edited message and all messages after it
                let currentElement = messageContainer;
                while (currentElement) {
                    const temp = currentElement.nextElementSibling;
                    currentElement.remove();
                    currentElement = temp;
                }
                
                if (typeof autosize === 'function') {
                    autosize.update(this.elements.input);
                }
            });
        }
    }

    appendMessage(content, isAgent) {
        if (!content && content !== '') return;

        // Remove streaming message container if it exists
        const streamingMessage = this.elements.messages.querySelector('.streaming-message');
        if (streamingMessage) {
            streamingMessage.remove();
        }

        let formattedContent;
        if (isAgent && typeof content === 'string') {
            try {
                formattedContent = marked.parse(content);
            } catch (error) {
                console.warn('Failed to parse markdown:', error);
                formattedContent = content;
            }
        } else {
            formattedContent = content;
        }

        const messageId = `msg-${Date.now()}`;
        const html = `
            <div class="d-flex ${isAgent ? 'justify-content-start' : 'justify-content-end'} mb-4" id="${messageId}-container">
                ${isAgent ? `<div class="avatar me-2">
                    <img src="${this.currentAgent.avatar}" alt="${this.currentAgent.name}" class="border-radius-lg shadow">
                </div>` : ''}
                <div class="${isAgent ? 'agent-message' : 'user-message'}" style="max-width: 75%;">
                    <div class="message-content">
                        <div class="message-actions position-absolute top-0 end-0 m-2 opacity-0">
                            <button class="btn btn-link btn-sm p-0 me-2 copy-message" title="Copy to clipboard">
                                <i class="fas fa-copy"></i>
                            </button>
                            ${isAgent ? '' : `
                            <button class="btn btn-link btn-sm p-0 edit-message" title="Edit message">
                                <i class="fas fa-edit"></i>
                            </button>`}
                        </div>
                        <div class="message-text">
                            ${formattedContent}
                        </div>
                    </div>
                </div>
                ${!isAgent ? `<div class="avatar ms-2">
                    <img src="${this.userAvatar}" alt="user" class="border-radius-lg shadow">
                </div>` : ''}
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.addMessageEventListeners(messageId);
        this.scrollToBottom();
    }

    showError(message) {
        if (!message) return;

        const html = `
            <div class="alert alert-danger">
                ${message}
            </div>
        `;
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
    }

    sendMessage() {
        const message = this.elements.input.value.trim();
        if (!message) return;

        try {
            // Send the new message
            this.socket.send(JSON.stringify({
                type: 'user_message',
                message: message,
                is_edit: this.isEditing || false,
                agent_id: this.elements.agentSelect.value,
                model: this.elements.modelSelect.value,
                client_id: this.elements.clientSelect.value || undefined
            }));

            // Reset edit state
            this.isEditing = false;

            // Clear input
            this.elements.input.value = '';
            this.elements.input.style.height = 'auto';
            if (typeof autosize === 'function') {
                autosize.update(this.elements.input);
            }
        } catch (error) {
            console.error('Failed to send message:', error);
            this.showError('Failed to send message');
        }
    }

    reconnect() {
        if (this.socket?.readyState === WebSocket.CLOSED) {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            this.socket = new WebSocket(
                `${wsProtocol}//${window.location.host}/ws/chat/?session=${this.elements.messages.dataset.sessionId}`
            );
            this.setupEventListeners();
        }
    }
}

// Initialize everything when the document is ready
document.addEventListener('DOMContentLoaded', () => {
    try {
        // Create WebSocket connection
        const wsUrl = `${window.chatConfig.urls.wsBase}?session=${window.chatConfig.sessionId}`;
        const socket = new WebSocket(wsUrl);
        
        // Initialize chat manager
        window.chatManager = new ChatManager({
            socket,
            sessionId: window.chatConfig.sessionId,
            currentConversation: window.chatConfig.currentConversation,
            defaultModel: window.chatConfig.defaultModel
        });

        // Handle new chat button
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.addEventListener('click', (event) => {
                event.preventDefault();
                window.location.href = window.chatConfig.urls.newChat;
            });
        }

        console.log('Chat manager initialized');
    } catch (error) {
        console.error('Failed to initialize chat:', error);
        const messages = document.getElementById('chat-messages');
        if (messages) {
            messages.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Error:</strong> Failed to initialize chat: ${error.message}
                </div>
            `;
        }
    }
}); 