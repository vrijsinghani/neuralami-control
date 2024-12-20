class Message {
    constructor(content, isAgent = false, avatar = null, timestamp = null) {
        this.content = content;
        this.isAgent = isAgent;
        this.avatar = avatar || (isAgent ? window.chatConfig.currentAgent.avatar : '/static/agents/img/user-avatar.jpg');
        this.timestamp = timestamp || new Date().toISOString();
    }

    render() {
        const messageDiv = document.createElement('div');
        messageDiv.className = `d-flex ${this.isAgent ? 'justify-content-start' : 'justify-content-end'} mb-4`;
        
        const html = `
            ${this.isAgent ? `
            <div class="avatar me-2">
                <img src="${this.avatar}" alt="agent" class="border-radius-lg shadow">
            </div>` : ''}
            <div class="message ${this.isAgent ? 'agent' : 'user'}" style="max-width: 75%;">
                <div class="message-content">
                    ${marked.parse(this.content)}
                </div>
                <div class="message-timestamp text-xxs">
                    ${new Date(this.timestamp).toLocaleTimeString()}
                </div>
            </div>
            ${!this.isAgent ? `
            <div class="avatar ms-2">
                <img src="${this.avatar}" alt="user" class="border-radius-lg shadow">
            </div>` : ''}
        `;
        
        messageDiv.innerHTML = html;
        return messageDiv;
    }
}

export { Message }; 