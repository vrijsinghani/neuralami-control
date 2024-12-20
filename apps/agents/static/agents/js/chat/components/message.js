class Message {
    constructor(content, isAgent = false, avatar = null, timestamp = null) {
        this.content = content;
        this.isAgent = isAgent;
        
        // Handle avatar path - ensure it always has the full static path
        const defaultAvatar = isAgent ? 'team-3.jpg' : 'user-avatar.jpg';
        const avatarFilename = avatar || (isAgent ? 
            (window.chatConfig?.currentAgent?.avatar || defaultAvatar) : 
            defaultAvatar);
            
        // Ensure avatar has the full static path
        this.avatar = avatarFilename.startsWith('/static/') ? 
            avatarFilename : 
            `/static/assets/img/${avatarFilename}`;
            
        this.timestamp = timestamp || new Date().toISOString();
    }

    render() {
        const messageDiv = document.createElement('div');
        messageDiv.className = `d-flex ${this.isAgent ? 'justify-content-start' : 'justify-content-end'} mb-4`;
        
        const html = `
            ${this.isAgent ? `
            <div class="avatar me-2">
                <img src="${this.avatar}" alt="${this.isAgent ? 'agent' : 'user'}" class="border-radius-lg shadow" onerror="this.src='/static/assets/img/team-3.jpg'">
            </div>` : ''}
            <div class="message ${this.isAgent ? 'agent' : 'user'}" style="max-width: 75%;">
                <div class="message-content">
                    ${marked.parse(this.content)}
                </div>
                <div class="d-flex justify-content-between align-items-center">
                    <div class="message-timestamp text-xxs">
                        ${new Date(this.timestamp).toLocaleTimeString()}
                    </div>
                    ${!this.isAgent ? `
                    <div class="message-actions">
                        <button class="btn btn-link text-secondary p-0 me-2" onclick="editMessage(this)" title="Edit message">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-link text-secondary p-0" onclick="copyMessage(this)" title="Copy message">
                            <i class="fas fa-copy"></i>
                        </button>
                    </div>` : ''}
                </div>
            </div>
            ${!this.isAgent ? `
            <div class="avatar ms-2">
                <img src="${this.avatar}" alt="user" class="border-radius-lg shadow" onerror="this.src='/static/assets/img/user-avatar.jpg'">
            </div>` : ''}
        `;
        
        messageDiv.innerHTML = html;
        return messageDiv;
    }
}

export { Message }; 