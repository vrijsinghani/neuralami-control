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

            case 'tool_start':
                console.log('Tool start:', data);
                if (this.toolOutputManager) {
                    const toolContainer = this.toolOutputManager.handleToolStart(data.message);
                    if (toolContainer) {
                        this.messageList.container.appendChild(toolContainer);
                    }
                }
                break;

            case 'tool_end':
                console.log('Tool end - raw data:', data);
                if (this.toolOutputManager) {
                    console.log('Tool end - message before parse:', data.message);
                    const messageData = typeof data.message === 'string' ? JSON.parse(data.message) : data.message;
                    console.log('Tool end - messageData after parse:', messageData);
                    
                    console.log('Tool end - output before parse:', messageData.output);
                    const outputData = typeof messageData.output === 'string' ? JSON.parse(messageData.output) : messageData.output;
                    console.log('Tool end - outputData after parse:', outputData);
                    
                    const resultData = {
                        type: 'json',
                        data: outputData
                    };
                    console.log('Tool end - sending to handleToolResult:', resultData);
                    
                    const resultContainer = this.toolOutputManager.handleToolResult(resultData);
                    if (resultContainer) {
                        this.messageList.container.appendChild(resultContainer);
                    }
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