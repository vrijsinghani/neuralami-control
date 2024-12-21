class MessageHandler {
    constructor(messageList, toolOutputManager) {
        this.messageList = messageList;
        this.toolOutputManager = toolOutputManager;
        this.statusElement = document.getElementById('connection-status');
    }

    handleMessage(data) {
        console.log('Received message:', data);
        
        if (!data) {
            console.warn('Empty message received');
            return;
        }

        switch (data.type) {
            case 'system_message':
                console.log('System message:', data);
                if (data.connection_status) {
                    this.handleConnectionStatus(data.connection_status);
                }
                break;

            case 'user_message':
                console.log('User message:', data);
                this.messageList.addMessage(data.message, false);
                break;

            case 'agent_message':
                console.log('Agent message:', data);
                // Check if this is a tool-related message
                if (data.message.startsWith('Tool Start:')) {
                    // Handle tool start
                    const toolMessage = data.message.replace('Tool Start:', '').trim();
                    if (this.toolOutputManager) {
                        const toolContainer = this.toolOutputManager.handleToolStart(toolMessage);
                        if (toolContainer) {
                            this.messageList.container.appendChild(toolContainer);
                        }
                    }
                } else if (data.message.startsWith('tool_start:')) {
                    // Handle tool start JSON format
                    const toolMessage = data.message.replace('tool_start:', '').trim();
                    if (this.toolOutputManager) {
                        const toolContainer = this.toolOutputManager.handleToolStart(toolMessage);
                        if (toolContainer) {
                            this.messageList.container.appendChild(toolContainer);
                        }
                    }
                } else if (data.message.startsWith('tool_end:')) {
                    // Handle tool end
                    const toolMessage = data.message.replace('tool_end:', '').trim();
                    if (this.toolOutputManager) {
                        try {
                            const messageData = JSON.parse(toolMessage);
                            const outputData = typeof messageData.output === 'string' ? JSON.parse(messageData.output) : messageData.output;
                            const resultData = {
                                type: 'json',
                                data: outputData
                            };
                            const resultContainer = this.toolOutputManager.handleToolResult(resultData);
                            if (resultContainer) {
                                this.messageList.container.appendChild(resultContainer);
                            }
                        } catch (error) {
                            console.error('Error parsing tool end message:', error);
                        }
                    }
                } else if (data.message.startsWith('Tool Result:')) {
                    // Handle tool result
                    const toolMessage = data.message.replace('Tool Result:', '').trim();
                    if (this.toolOutputManager) {
                        try {
                            const resultData = {
                                type: 'json',
                                data: JSON.parse(toolMessage)
                            };
                            const resultContainer = this.toolOutputManager.handleToolResult(resultData);
                            if (resultContainer) {
                                this.messageList.container.appendChild(resultContainer);
                            }
                        } catch (error) {
                            console.error('Error parsing tool result message:', error);
                        }
                    }
                } else {
                    // Regular agent message
                    this.messageList.addMessage(data.message, true);
                }
                break;

            case 'agent_finish':
                console.log('Agent finish:', data);
                this.messageList.addMessage(data.message, true);
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }

    handleConnectionStatus(status) {
        if (!this.statusElement) return;
        
        const dot = this.statusElement.querySelector('.connection-dot');
        if (!dot) return;

        // Remove all existing status classes
        dot.classList.remove('connected', 'disconnected', 'error');
        
        switch (status) {
            case 'connected':
                dot.classList.add('connected');
                break;
            case 'disconnected':
                dot.classList.add('disconnected');
                break;
            case 'error':
                dot.classList.add('error');
                break;
        }
    }

    handleError(error) {
        console.error('Error:', error);
        // Add error message to chat
        this.messageList.addMessage(
            `Error: ${error}`,
            true,
            null,
            new Date().toISOString()
        );
    }
}

export { MessageHandler }; 