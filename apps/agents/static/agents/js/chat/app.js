import { MessageList } from '/static/agents/js/components/message_list.js';
import { ChatWebSocket } from '/static/agents/js/services/websocket.js';
import { MessageHandler } from '/static/agents/js/services/message_handler.js';
import { ToolOutputManager } from '/static/agents/js/components/tool_outputs/base.js';

class ChatApp {
    constructor(config) {
        this.config = config;
        this.elements = {
            messages: document.getElementById('chat-messages'),
            input: document.getElementById('message-input'),
            sendButton: document.getElementById('send-message'),
            agentSelect: document.getElementById('agent-select'),
            modelSelect: document.getElementById('model-select'),
            clientSelect: document.getElementById('client-select'),
            newChatBtn: document.getElementById('new-chat-btn')
        };
        
        // Initialize components
        this.messageList = new MessageList(this.elements.messages);
        this.toolOutputManager = new ToolOutputManager();
        this.messageHandler = new MessageHandler(this.messageList, this.toolOutputManager);
        this.websocket = new ChatWebSocket(config, this.messageHandler);
        
        // Bind event handlers
        this._bindEvents();

        // Expose functions globally
        window.editMessage = this.editMessage.bind(this);
        window.copyMessage = this.copyMessage.bind(this);
        window.deleteConversation = this.deleteConversation.bind(this);
    }

    editMessage(button) {
        const messageContent = button.closest('.message').querySelector('.message-content');
        const originalText = messageContent.textContent.trim();
        
        // Set input value to message content
        this.elements.input.value = originalText;
        autosize.update(this.elements.input);
        
        // Focus input
        this.elements.input.focus();
    }

    copyMessage(button) {
        const messageContent = button.closest('.message').querySelector('.message-content');
        const text = messageContent.textContent.trim();
        
        navigator.clipboard.writeText(text).then(() => {
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

    initialize() {
        // Connect WebSocket
        this.websocket.connect();
        
        // Initialize autosize for textarea
        if (this.elements.input) {
            autosize(this.elements.input);
        }
        
        // Set initial agent avatar and initialize chatConfig
        if (!window.chatConfig.currentAgent) {
            const selectedOption = this.elements.agentSelect?.selectedOptions[0];
            console.log('Initial agent avatar setup:', {
                selectedOption,
                avatar: selectedOption?.dataset.avatar,
                name: selectedOption?.dataset.name,
                allOptions: Array.from(this.elements.agentSelect?.options || []).map(opt => ({
                    name: opt.dataset.name,
                    avatar: opt.dataset.avatar
                }))
            });
            window.chatConfig.currentAgent = {
                avatar: selectedOption ? selectedOption.dataset.avatar : '/static/assets/img/team-3.jpg',
                name: selectedOption ? selectedOption.dataset.name : 'AI Assistant'
            };
        }
        this._updateAgentAvatar();
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

        // Agent selection
        if (this.elements.agentSelect) {
            this.elements.agentSelect.addEventListener('change', () => {
                this._updateAgentAvatar();
            });
        }

        // New chat button
        if (this.elements.newChatBtn) {
            this.elements.newChatBtn.addEventListener('click', () => {
                window.location.href = this.elements.newChatBtn.dataset.url;
            });
        }
    }

    _sendMessage() {
        const message = this.elements.input.value.trim();
        if (!message) return;

        const agentId = this.elements.agentSelect.value;
        const modelName = this.elements.modelSelect.value;
        const clientId = this.elements.clientSelect.value;

        // Display user message immediately
        this.messageList.addMessage(message, false);

        // Send message to server
        this.websocket.send({
            message: message,
            agent_id: agentId,
            model: modelName,
            client_id: clientId
        });

        // Clear input
        this.elements.input.value = '';
        autosize.update(this.elements.input);
    }

    _updateAgentAvatar() {
        const selectedOption = this.elements.agentSelect.selectedOptions[0];
        if (selectedOption) {
            const avatarPath = selectedOption.dataset.avatar || '/static/assets/img/team-3.jpg';
            const avatarUrl = avatarPath.startsWith('/') ? avatarPath : `/static/assets/img/${avatarPath}`;
            const name = selectedOption.dataset.name;
            
            console.log('Updating agent avatar:', {
                avatarPath,
                avatarUrl,
                name,
                selectedOption,
                allDataset: {...selectedOption.dataset}
            });
            
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
}

export { ChatApp }; 