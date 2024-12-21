class MessageHandler {
    constructor(messageList, toolOutputManager) {
        this.messageList = messageList;
        this.toolOutputManager = toolOutputManager;
        this.messagesContainer = document.getElementById('chat-messages');
        this.currentToolContainer = null;
        this.loadingIndicator = null;
    }

    handleMessage(message) {
        console.log('Received message:', message);

        switch (message.type) {
            case 'system_message':
                console.log('System message:', message);
                this.handleSystemMessage(message);
                break;
            case 'user_message':
                console.log('User message:', message);
                this.handleUserMessage(message);
                break;
            case 'agent_message':
                console.log('Agent message:', message);
                this.removeLoadingIndicator();
                this.handleAgentMessage(message);
                break;
            case 'agent_finish':
                console.log('Agent finish:', message);
                this.removeLoadingIndicator();
                this.handleAgentFinish(message);
                break;
            case 'tool_start':
                console.log('Tool start:', message);
                this.removeLoadingIndicator();
                this.handleToolStart(message);
                break;
            case 'tool_end':
                console.log('Tool end:', message);
                this.handleToolEnd(message);
                break;
            case 'tool_result':
                console.log('Tool result:', message);
                this.handleToolResult(message);
                break;
            case 'error':
                console.log('Error message:', message);
                this.removeLoadingIndicator();
                this.handleErrorMessage(message);
                break;
            default:
                console.warn('Unknown message type:', message.type);
        }
    }

    showLoadingIndicator() {
        // Remove any existing loading indicator first
        this.removeLoadingIndicator();

        // Create the loading indicator
        const loadingContainer = document.createElement('div');
        loadingContainer.className = 'd-flex justify-content-start mb-4 streaming-message';
        loadingContainer.innerHTML = `
            <div class="avatar me-2">
                <img src="${this.messageList.currentAgent.avatar}" 
                     alt="${this.messageList.currentAgent.name}" 
                     class="border-radius-lg shadow">
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
        `;

        this.loadingIndicator = loadingContainer;
        this.messagesContainer.appendChild(loadingContainer);
        this.scrollToBottom();
    }

    removeLoadingIndicator() {
        if (this.loadingIndicator) {
            this.loadingIndicator.remove();
            this.loadingIndicator = null;
        }
    }

    scrollToBottom() {
        if (this.messagesContainer) {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }
    }

    handleSystemMessage(message) {
        if (message.connection_status) {
            this.handleConnectionStatus(message.connection_status);
        }
    }

    handleConnectionStatus(status) {
        const dot = document.querySelector('.connection-dot');
        if (dot) {
            dot.className = 'connection-dot ' + status;
        }
    }

    handleUserMessage(message) {
        this.messageList.addMessage(message.message, false, null, message.id);
        // Show loading indicator after user message
        this.showLoadingIndicator();
    }

    handleAgentMessage(message) {
        if (message.message.startsWith('Tool Start:')) {
            try {
                const toolMessage = message.message.replace('Tool Start:', '').trim();
                const [toolName, ...dataParts] = toolMessage.split(' - ');
                const toolData = {
                    tool: toolName.trim(),
                    input: dataParts.join(' - ').trim()
                };
                this.toolOutputManager.handleToolStart(toolData);
            } catch (error) {
                console.error('Error parsing tool start message:', error);
                this.messageList.addMessage(message.message, true, null, message.id);
            }
        } else if (message.message.startsWith('Tool Result:')) {
            try {
                const jsonStr = message.message.replace('Tool Result:', '').trim();
                const data = JSON.parse(jsonStr);
                
                if (data.analytics_data && Array.isArray(data.analytics_data)) {
                    this.toolOutputManager.handleToolResult({ 
                        type: 'table', 
                        data: data.analytics_data 
                    });
                } else {
                    this.toolOutputManager.handleToolResult({ 
                        type: 'json', 
                        data 
                    });
                }
            } catch (error) {
                console.error('Error parsing tool result message:', error);
                this.messageList.addMessage(message.message, true, null, message.id);
            }
        } else if (message.message.startsWith('Tool Error:')) {
            const errorMessage = message.message.replace('Tool Error:', '').trim();
            this.toolOutputManager.handleToolResult({
                type: 'error',
                data: errorMessage
            });
        } else {
            this.messageList.addMessage(message.message, true, null, message.id);
        }
    }

    handleAgentFinish(message) {
        try {
            const data = typeof message.message === 'string' ? JSON.parse(message.message) : message.message;
            if (data.analytics_data && Array.isArray(data.analytics_data)) {
                this.toolOutputManager.handleToolResult({
                    type: 'table',
                    data: data.analytics_data
                });
            } else {
                this.messageList.addMessage(message.message, true, null, message.id);
            }
        } catch (error) {
            this.messageList.addMessage(message.message, true, null, message.id);
        }
    }

    handleToolStart(message) {
        this.toolOutputManager.handleToolStart(message);
    }

    handleToolEnd(message) {
    }

    handleToolResult(message) {
        let result;
        try {
            const data = typeof message.result === 'string' ? JSON.parse(message.result) : message.result;
            result = { type: 'json', data };
        } catch (error) {
            result = { type: 'text', data: message.result };
        }
        this.toolOutputManager.handleToolResult(result);
    }

    handleErrorMessage(message) {
        console.error('Server error:', message.message);
    }
}

export { MessageHandler }; 