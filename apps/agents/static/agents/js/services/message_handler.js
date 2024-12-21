class MessageHandler {
    constructor(messageList, toolOutputManager) {
        this.messageList = messageList;
        this.toolOutputManager = toolOutputManager;
        this.messagesContainer = document.getElementById('chat-messages');
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
                this.handleAgentMessage(message);
                break;
            case 'agent_finish':
                console.log('Agent finish:', message);
                this.handleAgentFinish(message);
                break;
            case 'tool_start':
                console.log('Tool start:', message);
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
                this.handleErrorMessage(message);
                break;
            default:
                console.warn('Unknown message type:', message.type);
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
        // Add message to the UI with its ID
        this.messageList.addMessage(message.message, false, null, message.id);
    }

    handleAgentMessage(message) {
        // Check if this is a tool-related message
        if (message.message.startsWith('Tool Start:')) {
            try {
                const toolMessage = message.message.replace('Tool Start:', '').trim();
                // Extract tool name and data
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
                
                // Check if the result contains tabular data
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
        } else {
            this.messageList.addMessage(message.message, true, null, message.id);
        }
    }

    handleAgentFinish(message) {
        // Check if the message contains analytics data
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
            // If not JSON or no analytics data, display as regular message
            this.messageList.addMessage(message.message, true, null, message.id);
        }
    }

    handleToolStart(message) {
        this.toolOutputManager.handleToolStart(message);
    }

    handleToolEnd(message) {
        // Tool end is handled by handleToolResult
    }

    handleToolResult(message) {
        let result;
        try {
            // Try to parse the result if it's a string
            const data = typeof message.result === 'string' ? JSON.parse(message.result) : message.result;
            result = { type: 'json', data };
        } catch (error) {
            // If parsing fails, treat as plain text
            result = { type: 'text', data: message.result };
        }
        this.toolOutputManager.handleToolResult(result);
    }

    handleErrorMessage(message) {
        // Display error message in UI if needed
        console.error('Server error:', message.message);
    }
}

export { MessageHandler }; 