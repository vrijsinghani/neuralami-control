// Get current timestamp for cache busting
const version = new Date().getTime();

// Create URLs with cache busting
const messageListUrl = new URL('/static/agents/js/components/message_list.js', window.location.href);
const webSocketUrl = new URL('/static/agents/js/services/websocket.js', window.location.href);
const messageHandlerUrl = new URL('/static/agents/js/services/message_handler.js', window.location.href);
const toolOutputUrl = new URL('/static/agents/js/components/tool_outputs/base.js', window.location.href);

// Add version parameter to each URL
messageListUrl.searchParams.set('v', version);
webSocketUrl.searchParams.set('v', version);
messageHandlerUrl.searchParams.set('v', version);
toolOutputUrl.searchParams.set('v', version);

// Initialize components asynchronously
async function initializeComponents() {
    // Import modules dynamically
    const [
        { MessageList },
        { ChatWebSocket },
        { MessageHandler },
        { ToolOutputManager }
    ] = await Promise.all([
        import(messageListUrl.toString()),
        import(webSocketUrl.toString()),
        import(messageHandlerUrl.toString()),
        import(toolOutputUrl.toString())
    ]);

    return { MessageList, ChatWebSocket, MessageHandler, ToolOutputManager };
}

class ChatApp {
    constructor(config) {
        this.config = config;
        this.participantType = 'unset'; // Track participant type
        this.crewInitialized = false; // Track if crew has been initialized
        
        // Initialize highlight.js
        hljs.configure({
            ignoreUnescapedHTML: true,
            languages: ['javascript', 'python', 'bash', 'json', 'html', 'css']
        });
        
        this.elements = {
            messages: document.getElementById('chat-messages'),
            input: document.getElementById('message-input'),
            sendButton: document.getElementById('send-message'),
            agentSelect: document.getElementById('agent-select'),
            modelSelect: document.getElementById('model-select'),
            clientSelect: document.getElementById('client-select'),
            crewSelect: document.getElementById('crew-select'),
            newChatBtn: document.getElementById('new-chat-btn'),
            shareBtn: document.getElementById('share-conversation')
        };
    }

    async initialize() {
        // Import and initialize components
        const { MessageList, ChatWebSocket, MessageHandler, ToolOutputManager } = await initializeComponents();
        
        // Initialize components
        this.messageList = new MessageList(this.elements.messages);
        this.toolOutputManager = new ToolOutputManager();
        
        // Create message handler first without websocket
        this.messageHandler = new MessageHandler(this.messageList, this.toolOutputManager);
        
        // Create websocket with message handler
        this.websocket = new ChatWebSocket(this.config, this.messageHandler);
        
        // Update message handler with websocket
        this.messageHandler.websocket = this.websocket;
        
        // Set message handler callback for system messages
        this.messageHandler.onSystemMessage = this.handleSystemMessage.bind(this);
        
        // Bind event handlers
        this._bindEvents();

        // Listen for edit-message custom event
        document.addEventListener('edit-message', (event) => {
            const messageContainer = document.getElementById(`${event.detail.domId}-container`);
            if (messageContainer) {
                this.editMessage(messageContainer.querySelector('.edit-message'));
            }
        });

        // Connect WebSocket
        this.websocket.connect();
        
        // Initialize autosize for textarea
        if (this.elements.input) {
            autosize(this.elements.input);
        }
        
        // Set initial agent avatar and initialize chatConfig
        if (!window.chatConfig.currentAgent) {
            const selectedOption = this.elements.agentSelect?.selectedOptions[0];

            window.chatConfig.currentAgent = {
                avatar: selectedOption ? selectedOption.dataset.avatar : '/static/assets/img/team-3.jpg',
                name: selectedOption ? selectedOption.dataset.name : 'AI Assistant'
            };
        }
        this._updateAgentAvatar();
        
        // Update MessageList with current agent
        this.messageList.updateCurrentAgent(window.chatConfig.currentAgent);

        // Expose functions globally
        window.editMessage = this.editMessage.bind(this);
        window.copyMessage = this.copyMessage.bind(this);
        window.deleteConversation = this.deleteConversation.bind(this);
    }

    handleSystemMessage(message) {
        console.log('Handling system message:', message);
        // Update participant type from system message
        if (message.participant_type) {
            this.participantType = message.participant_type;
            this._updateUIForParticipantType();
        }
    }

    _updateUIForParticipantType() {
        console.log('Updating UI for participant type:', this.participantType);
        const selectedOption = this.elements.agentSelect?.selectedOptions[0];
        const selectedType = selectedOption?.dataset.type;

        // Update UI based on participant type
        if (this.participantType === 'crew' || selectedType === 'crew') {
            if (this.elements.agentSelect) {
                this.elements.agentSelect.disabled = true;
                this.elements.modelSelect.disabled = true;
            }
            // Update agent name to show crew if available
            const crewOption = this.elements.crewSelect?.selectedOptions[0];
            if (crewOption && document.getElementById('agent-name')) {
                document.getElementById('agent-name').textContent = `Crew: ${crewOption.textContent}`;
            }
        } else if (this.participantType === 'agent' || selectedType === 'agent') {
            if (this.elements.crewSelect) {
                this.elements.crewSelect.disabled = true;
            }
        }
    }

    _handleAgentOrCrewSelection() {
        const selectedOption = this.elements.agentSelect?.selectedOptions[0];
        if (!selectedOption) return;

        const selectedType = selectedOption.dataset.type;
        const selectedId = selectedOption.value;

        if (selectedType === 'crew') {
            // Just update the UI and participant type, don't start crew yet
            this.participantType = 'crew';
            this.crewInitialized = false; // Reset initialization flag
        } else {
            // Update participant type for agent
            this.participantType = 'agent';
        }

        this._updateUIForParticipantType();
        this._updateAgentAvatar();
    }

    _sendMessage() {
        const message = this.elements.input.value.trim();
        if (!message) return;

        const selectedOption = this.elements.agentSelect?.selectedOptions[0];
        const selectedType = selectedOption?.dataset.type;

        // Send message based on participant type
        if (this.participantType === 'crew' || selectedType === 'crew') {
            // If this is the first message to the crew, initialize it
            if (!this.crewInitialized) {
                this.websocket.send({
                    type: 'start_crew',
                    crew_id: selectedOption.value,
                    client_id: this.elements.clientSelect.value
                });
                this.crewInitialized = true;
            }
            
            // Send the crew message
            this.websocket.send({
                message: message,
                type: 'crew_message',
                crew_id: selectedOption.value,
                client_id: this.elements.clientSelect.value
            });
        } else {
            // Regular agent message
            this.websocket.send({
                message: message,
                agent_id: selectedOption.value,
                model: this.elements.modelSelect.value,
                client_id: this.elements.clientSelect.value
            });
        }

        // Clear input
        this.elements.input.value = '';
        autosize.update(this.elements.input);
    }

    editMessage(button) {
        const messageContainer = button.closest('.d-flex');
        if (!messageContainer) {
            console.warn('Could not find message container');
            return;
        }

        const messageText = messageContainer.querySelector('.message-text')?.textContent.trim();
        if (!messageText) {
            console.warn('Could not find message text');
            return;
        }
        
        // Get the message ID
        const domId = messageContainer.id.replace('-container', '');
        const backendId = this.messageList.getMessageId(domId);
        
        if (!backendId) {
            console.warn('No backend message ID found for container:', domId);
            return;
        }
        
        try {
            console.log('Editing message:', { domId, backendId, messageText });
            
            // Set input value to message content
            this.elements.input.value = messageText;
            this.elements.input.focus();
            autosize.update(this.elements.input);
            
            // Delete messages from the message list
            this.messageList.deleteMessagesFromIndex(domId);
            
            // Notify backend to handle edit
            this.websocket.send({
                type: 'edit',
                message: messageText,
                message_id: backendId,
                session_id: this.config.sessionId
            });
            
        } catch (error) {
            console.error('Error editing message:', error);
            alert('Failed to edit message. Please try again.');
        }
    }

    copyMessage(button) {
        const messageText = button.closest('.message-content')?.querySelector('.message-text')?.textContent.trim();
        if (!messageText) {
            console.warn('Could not find message text');
            return;
        }
        
        navigator.clipboard.writeText(messageText).then(() => {
            // Show temporary success indicator
            const icon = button.querySelector('i');
            icon.classList.remove('fa-copy');
            icon.classList.add('fa-check');
            setTimeout(() => {
                icon.classList.remove('fa-check');
                icon.classList.add('fa-copy');
            }, 1000);
        }).catch(err => {
            console.error('Failed to copy text:', err);
        });
    }

    _bindEvents() {
        // Message sending
        if (this.elements.input && this.elements.sendButton) {
            this.elements.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this._sendMessage();
                }
            });
            
            this.elements.sendButton.addEventListener('click', () => {
                this._sendMessage();
            });
        }

        // Agent/Crew selection
        if (this.elements.agentSelect) {
            this.elements.agentSelect.addEventListener('change', () => {
                this._handleAgentOrCrewSelection();
            });
        }

        // New chat button
        if (this.elements.newChatBtn) {
            this.elements.newChatBtn.addEventListener('click', () => {
                window.location.href = this.elements.newChatBtn.dataset.url;
            });
        }

        // Share button
        if (this.elements.shareBtn) {
            this.elements.shareBtn.addEventListener('click', () => {
                this.exportToMarkdown();
            });
        }
    }

    _updateAgentAvatar() {
        const selectedOption = this.elements.agentSelect.selectedOptions[0];
        if (selectedOption) {
            const avatarPath = selectedOption.dataset.avatar || '/static/assets/img/team-3.jpg';
            const avatarUrl = avatarPath.startsWith('/') ? avatarPath : `/static/assets/img/${avatarPath}`;
            const name = selectedOption.dataset.name;
            
            const avatarImg = document.getElementById('agent-avatar').querySelector('img');
            if (avatarImg) {
                avatarImg.src = avatarUrl;
                avatarImg.alt = name;
            }
            
            const nameElement = document.getElementById('agent-name');
            if (nameElement) {
                nameElement.textContent = name;
            }
            
            // Update global config for Message component
            window.chatConfig.currentAgent = {
                avatar: avatarUrl,
                name: name
            };
            
            // Update MessageList with new agent info
            this.messageList.updateCurrentAgent(window.chatConfig.currentAgent);
        }
    }

    async deleteConversation(sessionId, event) {
        if (event) {
            event.preventDefault();
            event.stopPropagation();
        }

        if (!confirm('Are you sure you want to delete this conversation?')) {
            return;
        }

        try {
            const url = this.config.urls.deleteConversation.replace('{sessionId}', sessionId);
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.config.csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error('Failed to delete conversation');
            }

            // Redirect to new chat if we're deleting the current conversation
            if (sessionId === this.config.sessionId) {
                window.location.href = this.config.urls.newChat;
            } else {
                // Otherwise just remove the conversation from the list
                const conversationElement = event.target.closest('.position-relative');
                if (conversationElement) {
                    conversationElement.remove();
                }
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('Failed to delete conversation. Please try again.');
        }
    }

    scrollToBottom() {
        if (this.elements.messages) {
            const scrollHeight = this.elements.messages.scrollHeight;
            this.elements.messages.scrollTo({
                top: scrollHeight,
                behavior: 'smooth'
            });
        }
    }

    appendMessage(content, isAgent = false, withActions = true, messageId = null) {
        // Use MessageList's addMessage method
        const domId = this.messageList.addMessage(content, isAgent, 
            isAgent ? window.chatConfig.currentAgent?.avatar : null, 
            messageId
        );
        
        // Add event listeners for actions
        if (withActions) {
            this.addMessageEventListeners(domId);
        }
    }

    async deleteMessagesFromIndex(messageContainer) {
        // Get the actual message container if we're passed a child element
        const container = messageContainer.closest('.d-flex');
        if (!container) {
            console.warn('Could not find message container');
            return;
        }

        // Get the message ID from the container ID
        const domId = container.id.replace('-container', '');
        const backendId = this.messageList.getMessageId(domId);
        
        if (!backendId) {
            console.warn('No backend message ID found for container:', domId);
            return;
        }
        
        try {
            // Delete messages from the message list
            this.messageList.deleteMessagesFromIndex(domId);
            
            // Notify backend to handle edit
            const editData = {
                type: 'edit',
                message: this.elements.input.value.trim(),
                message_id: backendId,
                session_id: this.config.sessionId
            };
            this.websocket.send(editData);
            
        } catch (error) {
            console.error('Error editing messages:', error);
            alert('Failed to edit messages. Please try again.');
        }
    }

    addMessageEventListeners(domId) {
        const container = document.getElementById(`${domId}-container`);
        if (!container) return;

        const messageContent = container.querySelector('.message-content');
        const messageActions = container.querySelector('.message-actions');
        const copyButton = container.querySelector('.copy-message');
        const editButton = container.querySelector('.edit-message');

        // Copy button functionality
        if (copyButton) {
            copyButton.addEventListener('click', (e) => {
                e.stopPropagation();
                const messageText = container.querySelector('.message-text').textContent.trim();
                navigator.clipboard.writeText(messageText).then(() => {
                    // Show success feedback
                    const icon = copyButton.querySelector('i');
                    icon.classList.remove('fa-copy');
                    icon.classList.add('fa-check');
                    setTimeout(() => {
                        icon.classList.remove('fa-check');
                        icon.classList.add('fa-copy');
                    }, 1000);
                });
            });
        }

        // Edit button functionality
        if (editButton) {
            editButton.addEventListener('click', async (e) => {
                e.stopPropagation();
                const messageText = container.querySelector('.message-text').textContent.trim();
                
                // 1. Put the message text in the input field
                this.elements.input.value = messageText;
                this.elements.input.focus();
                autosize.update(this.elements.input);

                // 2. Delete this message and all subsequent messages
                await this.deleteMessagesFromIndex(container);
            });
        }
    }

    exportToMarkdown() {
        let markdown = '# Chat Conversation\n\n';
        const messages = this.elements.messages.querySelectorAll('.message');
        
        messages.forEach(message => {
            const isAgent = message.classList.contains('agent');
            const messageText = message.querySelector('.message-text').textContent.trim();
            const role = isAgent ? 'Assistant' : 'User';
            
            markdown += `**${role}**: ${messageText}\n\n`;
        });

        // Create a blob and trigger download
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat-export-${new Date().toISOString().slice(0,10)}.md`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    }
}

export { ChatApp }; 