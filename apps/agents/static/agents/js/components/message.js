class Message {
    constructor(content, isAgent = false, avatar = null) {
        this.content = content;
        this.isAgent = isAgent;
        this.avatar = avatar;
    }

    render(domId) {
        const messageElement = document.createElement('div');
        messageElement.id = `${domId}-container`;
        messageElement.className = `d-flex justify-content-${this.isAgent ? 'start' : 'end'} mb-4`;

        const html = `
            ${this.isAgent ? `
            <div class="avatar me-2">
                <img src="${this.avatar || '/static/assets/img/team-3.jpg'}" 
                     alt="AI" class="border-radius-lg shadow">
            </div>` : ''}
            <div class="message ${this.isAgent ? 'agent' : 'user'}" style="max-width: 75%;">
                <div class="message-content position-relative">
                    <div class="message-text">${this.content}</div>
                    <div class="message-actions opacity-0">
                        <button class="btn btn-link text-secondary p-1 copy-message" title="Copy message">
                            <i class="fas fa-copy"></i>
                        </button>
                        ${!this.isAgent ? `
                        <button class="btn btn-link text-secondary p-1 edit-message" title="Edit message">
                            <i class="fas fa-edit"></i>
                        </button>
                        ` : ''}
                    </div>
                </div>
            </div>
            ${!this.isAgent ? `
            <div class="avatar ms-2">
                <img src="/static/assets/img/team-2.jpg" alt="User" class="border-radius-lg shadow">
            </div>` : ''}
        `;

        messageElement.innerHTML = html;
        
        // Add hover event listeners
        const messageContent = messageElement.querySelector('.message-content');
        const messageActions = messageElement.querySelector('.message-actions');
        if (messageContent && messageActions) {
            messageContent.addEventListener('mouseenter', () => {
                messageActions.classList.remove('opacity-0');
            });
            messageContent.addEventListener('mouseleave', () => {
                messageActions.classList.add('opacity-0');
            });
        }
        
        // Add click handlers for buttons
        const copyButton = messageElement.querySelector('.copy-message');
        const editButton = messageElement.querySelector('.edit-message');
        
        if (copyButton) {
            copyButton.addEventListener('click', (e) => {
                e.stopPropagation();
                window.copyMessage(copyButton);
            });
        }
        
        if (editButton) {
            editButton.addEventListener('click', (e) => {
                e.stopPropagation();
                window.editMessage(editButton);
            });
        }
        
        return messageElement;
    }
}

export { Message }; 