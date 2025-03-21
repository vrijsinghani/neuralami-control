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
        this.processedMessageIds = new Set(); // Track message IDs that have been processed
        this.toolRunMessages = new Map(); // Map of message IDs to tool run IDs
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
                // Only remove loading indicator if crew execution is completed
                if (message.status && (message.status === 'DONE' || message.status === 'COMPLETED')) {
                    this.removeLoadingIndicator();
                }
                this.handleCrewMessage(message);
                break;
            case 'execution_update':
                this.handleExecutionUpdate(message);
                break;
            case 'agent_finish':
                console.log('Agent finish:', message);
                this.handleAgentFinish(message);
                break;
            case 'tool_start':
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
        // Skip if we've already processed this message
        if (message.id && this.processedMessageIds.has(message.id)) {
            console.log('Skipping already processed user message:', message.id);
            return;
        }
        
        // Track this message as processed if it has an ID
        if (message.id) {
            this.processedMessageIds.add(message.id);
        }
        
        // Add the message to the UI
        this.messageList.addMessage(message.message, false, null, message.id);
        
        // Only show loading indicator for fresh messages
        // (not historical ones loaded from the server)
        const isHistoricalMessage = message.timestamp && 
            new Date(message.timestamp).getTime() < Date.now() - 5000; // 5 seconds threshold
            
        if (!isHistoricalMessage) {
            // IMPORTANT: We remove the human input context handling from here
            // It's now handled directly in ChatApp._sendMessage
            
            this.showLoadingIndicator();
        }
    }

    handleAgentMessage(message) {
        // Skip if we've already processed this message
        if (message.id && this.processedMessageIds.has(message.id)) {
            console.log('Skipping already processed agent message:', message.id);
            return;
        }
        
        // Track this message as processed if it has an ID
        if (message.id) {
            this.processedMessageIds.add(message.id);
        }

        const messageContent = message.content || message.message;
        
        // Skip empty messages
        if (!messageContent || messageContent.trim() === '') {
            console.warn('Skipping empty agent message');
            return;
        }
        
        // Handle special message content
        if (messageContent === 'I\'m thinking...') {
            return; // Skip "thinking" messages
        }
        
        // Handle tool-related messages
        if (messageContent.startsWith('Tool Start:')) {
            // Extract tool info and create a tool container
            const toolMatch = messageContent.match(/Tool Start:\s*(.+?)($|\n)/);
            if (toolMatch) {
                const toolName = toolMatch[1].trim();
                console.debug(`Extracted tool name: "${toolName}" from message: "${messageContent}"`);
                
                // Generate a unique run ID if we don't have one from the backend
                // Use the message ID if available, or generate a timestamp-based one
                const toolRunId = `${toolName}-${message.id || Date.now()}`;
                
                this.handleToolStart({
                    tool: toolName,
                    input: '',  // No input available in this format
                    run_id: toolRunId
                });
                
                // Store this tool run ID for future reference
                if (message.id) {
                    this.toolRunMessages.set(message.id, toolRunId);
                }
            }
            return;
        }
        
        if (messageContent === 'Tool Result') {
            // For tool result messages, use the handleToolResult method
            this.handleToolResult(message);
            return;
        }
        
        // For regular agent messages, add to the message list as a simple string
        this.messageList.addMessage(messageContent, true, null, message.id);
        
        this.scrollToBottom();
    }

    handleAgentFinish(message) {
        this.removeLoadingIndicator();
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
        console.debug('handleToolStart received:', message);
        
        const toolData = {
            tool: message.tool || message.content?.tool || message.message?.tool,
            input: message.input || message.content?.input || message.message?.input,
            run_id: message.run_id || message.content?.run_id || message.message?.run_id
        };
        
        console.debug('Passing to ToolOutputManager:', toolData);
        this.toolOutputManager.handleToolStart(toolData);
    }

    handleToolEnd(message) {
        // Handle tool end if needed
    }

    handleToolResult(message) {
        let result;
        console.debug('Processing tool result:', message);
        
        // Try to determine the associated tool run ID
        let toolRunId = null;
        if (message.additional_kwargs && message.additional_kwargs.tool_call && 
            message.additional_kwargs.tool_call.run_id) {
            // If the backend provides a run ID, use it
            toolRunId = message.additional_kwargs.tool_call.run_id;
        } else if (message.id && this.toolRunMessages) {
            // Look for a previously recorded tool run message that might be related
            // This is a heuristic - the result likely follows the tool start message
            const possibleStartIds = [...this.toolRunMessages.keys()].sort();
            for (const startId of possibleStartIds) {
                if (startId < message.id) {
                    // This start came before our result, might be related
                    toolRunId = this.toolRunMessages.get(startId);
                }
            }
        }
        
        try {
            // First check for tool data in additional_kwargs
            if (message.additional_kwargs && message.additional_kwargs.tool_call) {
                console.debug('Found tool_call in additional_kwargs:', message.additional_kwargs.tool_call);
                const toolData = message.additional_kwargs.tool_call;
                const toolOutput = toolData.output;
                const toolName = toolData.name;
                
                if (toolOutput.error) {
                    result = { type: 'error', data: toolOutput.error, toolName, toolRunId };
                } else if (toolOutput.analytics_data && Array.isArray(toolOutput.analytics_data)) {
                    result = { type: 'table', data: toolOutput.analytics_data, toolName, toolRunId };
                } else if (toolOutput.text) {
                    // Special case for search results which often have a text field
                    result = { type: 'text', data: toolOutput.text, toolName, toolRunId };
                } else {
                    result = { type: 'json', data: toolOutput, toolName, toolRunId };
                }
            } else {
                // Legacy format - handle both content and message formats
                const data = message.content || message.message;
                console.debug('No tool_call in additional_kwargs, parsing message content:', data);
                
                // Don't attempt to parse if it's just the string "Tool Result"
                if (data === "Tool Result") {
                    console.error('Tool result message without data, skipping display');
                    return;
                }
                
                const parsedData = typeof data === 'string' ? JSON.parse(data) : data;
                
                if (parsedData.error) {
                    result = { type: 'error', data: parsedData.error, toolRunId };
                } else if (parsedData.analytics_data && Array.isArray(parsedData.analytics_data)) {
                    result = { type: 'table', data: parsedData.analytics_data, toolRunId };
                } else {
                    result = { type: 'json', data: parsedData, toolRunId };
                }
            }
        } catch (error) {
            console.error('Error parsing tool result:', error);
            result = { type: 'text', data: message.content || message.message, toolRunId };
        }
        
        console.debug('Passing result to ToolOutputManager:', result);
        this.toolOutputManager.handleToolResult(result);
    }

    handleErrorMessage(message) {
        console.error('Server error:', message.message);
    }

    handleCrewMessage(message) {
        // Skip if we've already processed this message
        if (message.id && this.processedMessageIds.has(message.id)) {
            console.log('Skipping already processed crew message:', message.id);
            return;
        }
        
        // Track this message as processed if it has an ID
        if (message.id) {
            this.processedMessageIds.add(message.id);
        }

        // Handle crew-specific messages
        if (message.message && typeof message.message === 'string') {
            // Handle tool messages
            if (message.message.startsWith('Using tool:') || message.message.startsWith('Tool Start:')) {
                // Don't add the tool start message directly to chat
                const toolMessage = message.message;
                const toolMatch = toolMessage.match(/^(?:Tool Start:|Using Tool:)\s*(.+?)($|\n)/);
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
            console.log('Human input request received, storing context:', message.context);
            // Store the context so when user replies, we'll send it back with the response
            this.lastHumanInputContext = message.context;
            
            // Remove loading indicator to show we're waiting for user input
            this.removeLoadingIndicator();
            
            // Add a visual indicator to show that we're expecting input
            const inputIndicator = document.querySelector('#message-input');
            if (inputIndicator) {
                inputIndicator.setAttribute('placeholder', 'Type your response...');
                inputIndicator.focus();
            }
        }

        // Only add non-tool messages to UI
        if (message.message && 
            !message.message.startsWith('Using tool:') && 
            !message.message.startsWith('Tool Start:') && 
            !message.message.startsWith('Tool Result:') && 
            !message.message.startsWith('Tool result:') && 
            !message.message.startsWith('Tool Error:')) {
            this.messageList.addMessage(
                message.message, 
                true,
                null,
                message.id
            );
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
            this.messageList.addMessage(
                message.message, 
                true,
                null,
                message.id
            );
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