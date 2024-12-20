import { Message } from './message.js';

class MessageList {
    constructor(container) {
        this.container = container;
        this.messages = [];
        this._setupContainer();
    }

    _setupContainer() {
        // Ensure container has proper styling
        this.container.style.height = '70vh';
        this.container.style.overflowY = 'auto';
    }

    addMessage(content, isAgent = false, avatar = null, timestamp = null) {
        const message = new Message(content, isAgent, avatar, timestamp);
        this.messages.push(message);
        this._appendMessageToDOM(message);
        this._scrollToBottom();
    }

    _appendMessageToDOM(message) {
        const messageElement = message.render();
        this.container.appendChild(messageElement);
        
        // Handle code blocks if any
        const codeBlocks = messageElement.querySelectorAll('pre code');
        if (codeBlocks.length > 0) {
            codeBlocks.forEach(block => {
                hljs.highlightElement(block);
            });
        }
    }

    _scrollToBottom() {
        this.container.scrollTop = this.container.scrollHeight;
    }

    clear() {
        this.messages = [];
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
                msg.timestamp
            );
        });
    }
}

export { MessageList }; 