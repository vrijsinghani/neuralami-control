import { Message } from '/static/agents/js/components/message.js';

class MessageList {
    constructor(container) {
        this.container = container;
        this.messages = [];
        this.messageIds = new Map();  // Track message IDs
        
        // Get agent info from window.chatConfig
        this.currentAgent = {
            avatar: '/static/assets/img/agent-avatar-female-3.jfif',
            name: 'Agent'
        };
        
        this._setupContainer();
    }

    // Add method to update current agent
    updateCurrentAgent(agent) {
        if (agent?.avatar && agent?.name) {
            this.currentAgent = {
                avatar: agent.avatar,
                name: agent.name
            };
        }
    }

    _setupContainer() {
        // Ensure container has proper styling
        this.container.style.overflowY = 'auto';
    }

    addMessage(content, isAgent = false, avatar = null, messageId = null) {
        // Check if this is a crew message
        const isCrewMessage = typeof content === 'object' && content?.type === 'crew_message';
        
        const message = new Message(content, isAgent || isCrewMessage, avatar);
        this.messages.push(message);
        const domId = this._appendMessageToDOM(message);
        
        // Track message ID if provided
        if (messageId) {
            this.messageIds.set(domId, messageId);
        }
        
        this._scrollToBottom();
        return domId;
    }

    _appendMessageToDOM(message) {
        const domId = `msg-${Date.now()}`;
        const messageElement = message.render(domId);
        this.container.appendChild(messageElement);
        
        // Handle code blocks if any
        const codeBlocks = messageElement.querySelectorAll('pre code');
        if (codeBlocks.length > 0) {
            codeBlocks.forEach(block => {
                hljs.highlightElement(block);
            });
        }
        
        return domId;
    }

    _scrollToBottom() {
        this.container.scrollTop = this.container.scrollHeight;
    }

    clear() {
        this.messages = [];
        this.messageIds.clear();
        this.container.innerHTML = '';
    }

    // Method to handle historical messages
    loadHistory(messages) {
        this.clear();
        messages.forEach(msg => {
            this.addMessage(
                msg.content,
                msg.is_agent,
                msg.avatar,
                msg.id
            );
        });
    }

    deleteMessagesFromIndex(domId) {
        const container = document.getElementById(`${domId}-container`);
        if (!container) {
            console.warn('Could not find message container');
            return;
        }

        // Get the message ID
        const messageId = this.messageIds.get(domId);
        if (!messageId) {
            console.warn('No backend message ID found for container:', domId);
            return;
        }

        // Find all messages after this one (including this one)
        let currentElement = container;
        const messagesToDelete = [];
        
        while (currentElement) {
            if (currentElement.id && currentElement.id.includes('msg-')) {
                const currentDomId = currentElement.id.replace('-container', '');
                messagesToDelete.push({
                    element: currentElement,
                    domId: currentDomId,
                    backendId: this.messageIds.get(currentDomId)
                });
            }
            currentElement = currentElement.nextElementSibling;
        }

        // Remove messages and clear their IDs
        messagesToDelete.forEach(({ element, domId }) => {
            this.messageIds.delete(domId);
            element.remove();
        });
    }

    getMessageId(domId) {
        const messageId = this.messageIds.get(domId);
        return messageId;
    }
}

export { MessageList }; 