import { ToolHandler } from './components/tool_outputs/base.js';

export function deleteConversation(sessionId, event) {
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

export class ChatManager {
    constructor(options) {
        // Get required elements from options
        this.elements = {
            input: document.getElementById('message-input'),
            sendButton: document.getElementById('send-message'),
            messages: document.getElementById('chat-messages'),
            status: document.getElementById('connection-status')
        };

        // Store current agent info
        this.currentAgent = {
            id: options.agentId,
            avatar: options.agentAvatar || '/static/agents/img/agent-avatar.png',
            name: options.agentName || 'Agent'
        };

        // Store user avatar
        this.userAvatar = options.userAvatar || '/static/agents/img/user-avatar.jpg';

        // Store other options
        this.currentModel = options.model;
        this.clientId = options.clientId;
        this.isLoading = false;
        this.isEditing = false;

        // Initialize components
        this.toolHandler = new ToolHandler(this);

        // Setup WebSocket
        this.setupWebSocket();
    }

    disableInput() {
        if (this.elements.input) {
            this.elements.input.disabled = true;
            this.isLoading = true;
        }
        if (this.elements.sendButton) {
            this.elements.sendButton.disabled = true;
        }
    }

    enableInput() {
        if (this.elements.input) {
            this.elements.input.disabled = false;
            this.isLoading = false;
            this.elements.input.value = '';
            this.elements.input.style.height = 'auto';
            if (typeof autosize === 'function') {
                autosize.update(this.elements.input);
            }
        }
        if (this.elements.sendButton) {
            this.elements.sendButton.disabled = false;
        }
    }

    async sendMessage(event) {
        try {
            // Get message from input
            const message = this.elements.input.value;
            if (!message || !message.trim() || this.isLoading) return;

            // Disable input while processing
            this.disableInput();

            // Display user message immediately
            this.appendMessage(message, false);

            // Send to server
            await this.socket.send(JSON.stringify({
                message: message,
                agent_id: this.currentAgent.id,
                model: this.currentModel,
                client_id: this.clientId,
                is_edit: this.isEditing
            }));

            // Reset edit state
            this.isEditing = false;

        } catch (error) {
            console.error('Error sending message:', error);
            this.showError('Failed to send message');
            this.enableInput();
        }
    }

    setupWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.socket = new WebSocket(
            `${wsProtocol}//${window.location.host}/ws/chat/?session=${this.elements.messages.dataset.sessionId}`
        );
        this.setupEventListeners();
    }

    setupEventListeners() {
        // WebSocket event listeners
        this.socket.onmessage = (event) => this.handleMessage(event.data);
        this.socket.onclose = () => {
            this.showError('Connection lost. Attempting to reconnect...');
            setTimeout(() => this.reconnect(), 2000);
        };
        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.showError('Connection error occurred');
        };

        // Input event listeners
        if (this.elements.input) {
            this.elements.input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    this.sendMessage();
                }
            });
        }

        if (this.elements.sendButton) {
            this.elements.sendButton.addEventListener('click', () => this.sendMessage());
        }
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
            
            if (!message) {
                console.warn('Empty message received');
                return;
            }

            switch (message.type) {
                case 'system_message':
                    console.log('System message:', message);
                    if (message.connection_status) {
                        this.updateStatus(message.connection_status);
                    }
                    break;

                case 'tool_start':
                    console.log('Tool start:', message);
                    const toolContainer = this.toolHandler.handleToolStart(message.message);
                    if (toolContainer) {
                        this.appendToChat(toolContainer);
                    }
                    break;

                case 'tool_end':
                    console.log('Tool end:', message);
                    const resultContainer = this.toolHandler.handleToolResult({
                        type: 'text',
                        data: message.message.output
                    });
                    if (resultContainer) {
                        this.appendToChat(resultContainer);
                    }
                    break;

                case 'agent_finish':
                    console.log('Agent finish:', message);
                    this.appendMessage(message.message, true, false);
                    break;

                default:
                    console.log('Unknown message type:', message.type);
            }
        } catch (error) {
            console.error('Error handling message:', error);
            this.showError('Failed to process message');
        }
    }

    handleToolStart(content) {
        if (!content) return;

        // Format tool name for display
        const prettyToolName = content.name.split('_')
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
                                    <pre class="json-output mt-2">${JSON.stringify(content.input, null, 2)}</pre>
                                </div>
                                ${content.log ? `
                                <div class="tool-log mt-3">
                                    <strong>Log:</strong>
                                    <div class="mt-2">${content.log}</div>
                                </div>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        
        // Initialize collapse with show: false
        const collapseElement = document.getElementById(messageId);
        if (collapseElement) {
            new bootstrap.Collapse(collapseElement, {
                toggle: false  // This ensures it starts collapsed
            });
        }

        this.scrollToBottom();
    }

    handleToolOutput(content) {
        if (!content) return;

        // Find the last tool message and append output
        const lastToolMessage = this.elements.messages.querySelector('.tool-message.start:last-child');
        if (lastToolMessage) {
            const collapseContent = lastToolMessage.querySelector('.collapse');
            const outputHtml = `
                <div class="tool-output mt-3">
                    <strong>Output:</strong>
                    <pre class="json-output mt-2">${JSON.stringify(content, null, 2)}</pre>
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

    handleEditMessage(messageId) {
        const messageElement = document.getElementById(`${messageId}-container`);
        if (!messageElement) return;

        const messageText = messageElement.querySelector('.message-text').textContent.trim();
        this.elements.input.value = messageText;
        this.elements.input.focus();
        this.isEditing = true;
        this.editingMessageId = messageId;

        // Remove the edited message and all messages after it
        let currentElement = messageElement;
        while (currentElement) {
            const nextElement = currentElement.nextElementSibling;
            currentElement.remove();
            currentElement = nextElement;
        }

        // Update autosize if available
        if (typeof autosize === 'function') {
            autosize.update(this.elements.input);
        }
    }

    appendMessage(content, isAgent = false, withActions = true) {
        const messageId = `msg-${Date.now()}`;
        const html = `
            <div id="${messageId}-container" class="d-flex justify-content-${isAgent ? 'start' : 'end'} mb-4">
                ${isAgent ? `
                <div class="avatar me-2">
                    <img src="${this.currentAgent.avatar}" alt="${this.currentAgent.name}" class="border-radius-lg shadow">
                </div>` : ''}
                <div class="message ${isAgent ? 'agent' : 'user'}" style="max-width: 75%;">
                    <div class="message-content position-relative">
                        <div class="message-text">${content}</div>
                        ${withActions ? `
                        <div class="message-actions opacity-0">
                            <button class="btn btn-link text-secondary p-1 copy-message">
                                <i class="fas fa-copy"></i>
                            </button>
                            ${!isAgent ? `
                            <button class="btn btn-link text-secondary p-1 edit-message">
                                <i class="fas fa-edit"></i>
                            </button>` : ''}
                        </div>` : ''}
                    </div>
                </div>
                ${!isAgent ? `
                <div class="avatar ms-2">
                    <img src="${this.userAvatar}" alt="User" class="border-radius-lg shadow">
                </div>` : ''}
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        if (withActions) {
            this.addMessageEventListeners(messageId);
        }
        this.scrollToBottom();
    }

    addMessageEventListeners(messageId) {
        const container = document.getElementById(`${messageId}-container`);
        if (!container) return;

        const messageContent = container.querySelector('.message-content');
        const messageActions = container.querySelector('.message-actions');
        const copyButton = container.querySelector('.copy-message');
        const editButton = container.querySelector('.edit-message');

        // Show/hide actions on hover
        if (messageContent && messageActions) {
            messageContent.addEventListener('mouseenter', () => {
                messageActions.classList.remove('opacity-0');
            });
            messageContent.addEventListener('mouseleave', () => {
                messageActions.classList.add('opacity-0');
            });
        }

        // Copy button functionality
        if (copyButton) {
            copyButton.addEventListener('click', () => {
                const messageText = container.querySelector('.message-text').textContent.trim();
                navigator.clipboard.writeText(messageText);
                this.showNotification('Message copied to clipboard!');
            });
        }

        // Edit button functionality
        if (editButton) {
            editButton.addEventListener('click', () => {
                this.handleEditMessage(messageId);
            });
        }
    }

    showError(message) {
        if (!message) return;

        const html = `
            <div class="d-flex justify-content-center mb-4">
                <div class="alert alert-danger d-flex align-items-center w-75" role="alert">
                    <div class="text-white me-3">
                        <i class="fas fa-exclamation-circle"></i>
                    </div>
                    <div class="text-white">
                        ${message}
                    </div>
                </div>
            </div>
        `;
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.elements.messages.scrollTop = this.elements.messages.scrollHeight;
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

    appendCollapsedMessage({ tool, content, type, rawData }) {
        const prettyToolName = tool.split('_')
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
                        <div class="collapse show" id="${messageId}">
                            <div class="tool-details mt-3">
                                ${type === 'table' ? `
                                    <div class="table-responsive">
                                        ${content}
                                    </div>
                                ` : `
                                    <div class="json-output">
                                        <pre style="white-space: pre-wrap; word-break: break-word;">${content}</pre>
                                    </div>
                                `}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        
        // Initialize collapse and start expanded for tables
        const collapseElement = document.getElementById(messageId);
        if (collapseElement) {
            new bootstrap.Collapse(collapseElement, {
                toggle: true
            });
            if (type === 'table') {
                bootstrap.Collapse.getInstance(collapseElement).show();
            }
        }

        this.scrollToBottom();
    }

    showLoadingIndicator() {
        // Remove any existing loading indicator
        this.removeLoadingIndicator();

        const html = `
            <div class="d-flex justify-content-start mb-4 streaming-message">
                <div class="avatar me-2">
                    <img src="${this.currentAgent.avatar}" alt="${this.currentAgent.name}" class="border-radius-lg shadow">
                </div>
                <div class="agent-message" style="max-width: 75%;">
                    <div class="message-content loading-content">
                        <div class="typing-indicator">
                            <div class="typing-dots">
                                <span></span>
                                <span></span>
                                <span></span>
                            </div>
                            <div class="typing-text ms-2">Thinking...</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        this.elements.messages.insertAdjacentHTML('beforeend', html);
        this.scrollToBottom();
        this.isLoading = true;
    }

    removeLoadingIndicator() {
        const loadingMessage = this.elements.messages.querySelector('.streaming-message');
        if (loadingMessage) {
            loadingMessage.remove();
        }
        this.isLoading = false;
    }

    // Add method to convert markdown tables to HTML
    markdownTableToHtml(markdownTable) {
        const rows = markdownTable.trim().split('\n');
        const headers = rows[0].split('|').filter(cell => cell.trim()).map(cell => cell.trim());
        
        let html = '<table class="table table-striped table-hover">\n<thead>\n<tr>';
        
        // Add headers
        headers.forEach(header => {
            html += `<th>${header}</th>`;
        });
        html += '</tr>\n</thead>\n<tbody>';
        
        // Add data rows (skip header and separator rows)
        rows.slice(2).forEach(row => {
            const cells = row.split('|').filter(cell => cell.trim()).map(cell => cell.trim());
            html += '\n<tr>';
            cells.forEach(cell => {
                html += `<td>${cell}</td>`;
            });
            html += '</tr>';
        });
        
        html += '\n</tbody>\n</table>';
        return html;
    }

    // Add method to format analytics summary data
    formatAnalyticsSummary(stats) {
        let html = '<div class="analytics-summary">';
        for (const [metric, values] of Object.entries(stats)) {
            html += `
                <div class="metric-group mb-3">
                    <h5 class="metric-title">${this.formatMetricName(metric)}</h5>
                    <table class="table table-sm">
                        <tbody>
                            ${Object.entries(values).map(([key, value]) => `
                                <tr>
                                    <td>${this.formatMetricName(key)}</td>
                                    <td>${typeof value === 'number' ? value.toFixed(2) : value}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }
        html += '</div>';
        return html;
    }

    formatMetricName(name) {
        return name
            .replace(/([A-Z])/g, ' $1')
            .replace(/^./, str => str.toUpperCase())
            .trim();
    }

    appendToChat(element) {
        if (element instanceof Element) {
            this.elements.messages.appendChild(element);
        } else if (typeof element === 'string') {
            this.elements.messages.insertAdjacentHTML('beforeend', element);
        }
        this.scrollToBottom();
    }

    handleNewChat() {
        // Check if we have the new chat URL in window.chatConfig
        if (window.chatConfig?.urls?.newChat) {
            window.location.href = window.chatConfig.urls.newChat;
        } else {
            // Fallback to a default path if config URL isn't available
            window.location.href = '/chat/new/';
        }
    }
}

// Initialize everything when the document is ready
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.chatManager = new ChatManager({
            sessionId: window.chatConfig.sessionId,
            currentConversation: window.chatConfig.currentConversation,
            defaultModel: window.chatConfig.defaultModel
        });

        // Make deleteConversation available globally
        window.deleteConversation = deleteConversation;

        console.log('Chat manager initialized baby!');
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