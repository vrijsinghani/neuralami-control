class MessageHandler {
    constructor(messageList, toolOutputManager) {
        this.messageList = messageList;
        this.toolOutputManager = toolOutputManager;
        this.websocket = null;  // Will be set after construction
        this.messagesContainer = document.getElementById('chat-messages');
        this.currentToolContainer = null;
        this.loadingIndicator = null;
        this.onSystemMessage = null; // Callback for system messages
        this.lastHumanInputContext = null; // Store context for human input
    }

    handleMessage(message) {
        console.log('Received message:', message);

        switch (message.type) {
            case 'system_message':
                this.handleSystemMessage(message);
                break;
            case 'user_message':
                this.handleUserMessage(message);
                break;
            case 'agent_message':
                this.removeLoadingIndicator();
                this.handleAgentMessage(message);
                break;
            case 'crew_message':
                this.removeLoadingIndicator();
                this.handleCrewMessage(message);
                break;
            case 'execution_update':
                this.handleExecutionUpdate(message);
                break;
            case 'agent_finish':
                console.log('Agent finish:', message);
                this.removeLoadingIndicator();
                this.handleAgentFinish(message);
                break;
            case 'tool_start':
                this.removeLoadingIndicator();
                this.handleToolStart(message);
                break;
            case 'tool_end':
                this.handleToolEnd(message);
                break;
            case 'tool_result':
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
        // Call the system message callback if set
        if (this.onSystemMessage) {
            this.onSystemMessage(message);
        }

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
        // Only add to UI if this is the first time we're seeing this message
        if (message.id) {
            this.messageList.addMessage(message.message, false, null, message.id);
            
            // If we have stored human input context, send the response
            if (this.lastHumanInputContext && this.websocket) {
                this.websocket.send({
                    type: 'user_message',
                    message: message.message,
                    context: this.lastHumanInputContext
                });
                this.lastHumanInputContext = null;
            }
        }
        
        this.showLoadingIndicator();
    }

    handleAgentMessage(message) {
        // Handle structured tool messages
        if (message.content && message.content.tool) {
            this.toolOutputManager.handleToolStart({
                tool: message.content.tool,
                input: message.content.input
            });
            return;
        }

        // Handle legacy text-based tool messages
        if (typeof message.message === 'string') {
            if (message.message.startsWith('Tool Start:') || message.message.startsWith('Using Tool:')) {
                try {
                    const toolMessage = message.message;
                    const toolMatch = toolMessage.match(/^(?:Tool Start:|Using Tool:)\s*(.*?)\s*-/);
                    const toolName = toolMatch ? toolMatch[1].trim() : 'Tool';
                    
                    this.toolOutputManager.handleToolStart({
                        tool: toolName,
                        input: toolMessage
                    });
                } catch (error) {
                    console.error('Error parsing tool start message:', error);
                    this.messageList.addMessage(message.message, true, null, message.id);
                }
            } else if (message.message.startsWith('Tool Result:') || message.message.startsWith('Tool result:')) {
                try {
                    const jsonStr = message.message.replace(/^(Tool Result:|Tool result:)/, '').trim();
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
        } else {
            // Handle structured message
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
        const toolData = {
            tool: message.content?.tool || message.message?.tool,
            input: message.content?.input || message.message?.input
        };
        this.toolOutputManager.handleToolStart(toolData);
    }

    handleToolEnd(message) {
        // Handle tool end if needed
    }

    handleToolResult(message) {
        let result;
        try {
            // Handle both content and message formats
            const data = message.content || message.message;
            const parsedData = typeof data === 'string' ? JSON.parse(data) : data;
            
            if (parsedData.error) {
                result = { type: 'error', data: parsedData.error };
            } else if (parsedData.analytics_data && Array.isArray(parsedData.analytics_data)) {
                result = { type: 'table', data: parsedData.analytics_data };
            } else {
                result = { type: 'json', data: parsedData };
            }
        } catch (error) {
            console.error('Error parsing tool result:', error);
            result = { type: 'text', data: message.content || message.message };
        }
        this.toolOutputManager.handleToolResult(result);
    }

    handleErrorMessage(message) {
        console.error('Server error:', message.message);
    }

    handleCrewMessage(message) {
        // Handle crew-specific messages
        if (message.message && typeof message.message === 'string') {
            // Handle tool messages
            if (message.message.startsWith('Using tool:') || message.message.startsWith('Tool Start:')) {
                // Don't add the tool start message directly to chat
                const toolMessage = message.message;
                const toolMatch = toolMessage.match(/^(?:Tool Start:|Using Tool:)\s*(.*?)(?:\nInput:|$)/);
                const toolName = toolMatch ? toolMatch[1].trim() : 'Tool';
                const inputMatch = toolMessage.match(/Input:(.*?)(?:\n|$)/s);
                const input = inputMatch ? inputMatch[1].trim() : '';
                
                this.toolOutputManager.handleToolStart({
                    tool: toolName,
                    input: input
                });
                return;
            } else if (message.message.startsWith('Tool Result:') || message.message.startsWith('Tool result:')) {
                // Don't add the tool result message directly to chat
                const resultContent = message.message.replace(/^(Tool Result:|Tool result:)/, '').trim();
                
                // Try to parse as JSON first
                try {
                    const jsonData = JSON.parse(resultContent);
                    if (jsonData.analytics_data && Array.isArray(jsonData.analytics_data)) {
                        this.toolOutputManager.handleToolResult({ 
                            type: 'table', 
                            data: jsonData.analytics_data 
                        });
                    } else {
                        this.toolOutputManager.handleToolResult({ 
                            type: 'json', 
                            data: jsonData 
                        });
                    }
                } catch (jsonError) {
                    // If not JSON, handle as text result
                    this.toolOutputManager.handleToolResult({ 
                        type: 'text', 
                        data: resultContent 
                    });
                }
                return;
            } else if (message.message.startsWith('Tool Error:')) {
                // Don't add the tool error message directly to chat
                const errorMessage = message.message.replace('Tool Error:', '').trim();
                this.toolOutputManager.handleToolResult({
                    type: 'error',
                    data: errorMessage
                });
                return;
            }
        }

        // If this is a human input request, store the context
        if (message.context?.is_human_input) {
            this.lastHumanInputContext = message.context;
            this.removeLoadingIndicator();
        }

        // Only add non-tool messages to UI
        if (!message.message?.startsWith('Using tool:') && 
            !message.message?.startsWith('Tool Start:') && 
            !message.message?.startsWith('Tool Result:') && 
            !message.message?.startsWith('Tool result:') && 
            !message.message?.startsWith('Tool Error:')) {
            this.messageList.addMessage(message, true);
            this.scrollToBottom();
        }
    }

    handleExecutionUpdate(message) {
        // Handle execution status updates
        if (message.status === 'RUNNING') {
            this.showLoadingIndicator();
        } else if (message.status === 'COMPLETED' || message.status === 'FAILED') {
            this.removeLoadingIndicator();
        }
        
        // Only add non-tool messages to UI
        if (message.message && 
            !message.message.startsWith('Using tool:') && 
            !message.message.startsWith('Tool Start:') && 
            !message.message.startsWith('Tool Result:') && 
            !message.message.startsWith('Tool result:') && 
            !message.message.startsWith('Tool Error:')) {
            this.messageList.addMessage({
                type: 'crew_message',
                message: message.message
            }, true, null, null);
            this.scrollToBottom();
        }
    }

    _sendMessage(message) {
        if (!this.websocket) {
            console.error('No websocket available for sending message');
            return;
        }

        // If we have human input context, send as human input response
        if (this.lastHumanInputContext) {
            this.websocket.send({
                type: 'user_message',
                message: message,
                context: this.lastHumanInputContext
            });
            this.lastHumanInputContext = null;
        } else {
            // Send as regular message
            this.websocket.send(message);
        }
    }
}

export { MessageHandler }; 