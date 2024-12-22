class Message {
    constructor(content, isAgent = false, avatar = null) {
        this.content = content;
        this.isAgent = isAgent;
        this.avatar = avatar || (isAgent ? window.chatConfig.currentAgent.avatar : '/static/assets/img/user-avatar.jfif');
    }

    render(domId) {
        const messageElement = document.createElement('div');
        messageElement.id = `${domId}-container`;
        messageElement.className = `d-flex ${this.isAgent ? 'justify-content-start' : 'justify-content-end'} mb-4`;

        // Format content for display
        let formattedContent = this.content;
        if (this.isAgent) {
            try {
                formattedContent = marked.parse(this.content);
            } catch (error) {
                console.error('Error parsing markdown:', error);
                formattedContent = this.content;
            }
        }

        messageElement.innerHTML = `
            ${this.isAgent ? `<div class="avatar me-2">
                <img src="${this.avatar}" 
                     alt="${window.chatConfig.currentAgent.name}" 
                     class="border-radius-lg shadow">
            </div>` : ''}
            <div class="message ${this.isAgent ? 'agent' : 'user'}" style="max-width: 75%;">
                <div class="message-content">
                    <div class="message-actions">
                        <button class="btn btn-link copy-message" title="Copy to clipboard">
                            <i class="fas fa-copy"></i>
                        </button>
                        ${!this.isAgent ? `
                        <button class="btn btn-link edit-message" title="Edit message">
                            <i class="fas fa-edit"></i>
                        </button>` : ''}
                    </div>
                    <div class="message-text">
                        ${formattedContent}
                    </div>
                </div>
            </div>
            ${!this.isAgent ? `<div class="avatar ms-2">
                <img src="${this.avatar}" alt="User" class="border-radius-lg shadow">
            </div>` : ''}
        `;

        // Add event listeners for message actions
        const copyButton = messageElement.querySelector('.copy-message');
        if (copyButton) {
            copyButton.addEventListener('click', () => {
                const textToCopy = messageElement.querySelector('.message-text').textContent;
                navigator.clipboard.writeText(textToCopy).then(() => {
                    copyButton.innerHTML = '<i class="fas fa-check"></i>';
                    setTimeout(() => {
                        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                    }, 1000);
                }).catch(err => {
                    console.error('Failed to copy text:', err);
                    copyButton.innerHTML = '<i class="fas fa-times"></i>';
                    setTimeout(() => {
                        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
                    }, 1000);
                });
            });
        }

        // Add event listener for edit button
        const editButton = messageElement.querySelector('.edit-message');
        if (editButton) {
            editButton.addEventListener('click', () => {
                const event = new CustomEvent('edit-message', { detail: { domId } });
                document.dispatchEvent(event);
            });
        }

        return messageElement;
    }
}

export { Message }; 