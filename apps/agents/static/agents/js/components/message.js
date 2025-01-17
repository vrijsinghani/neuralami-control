class Message {
    constructor(content, isAgent = false, options = null) {
        // Handle case where content is a JSON object with message field
        if (typeof content === 'object' && content !== null && content.message) {
            this.content = content.message;
            this.rawContent = content;
        } else {
            this.content = content;
            this.rawContent = null;
        }
        this.isAgent = isAgent;
        this.options = options;
        this.avatar = (options && options.avatar) || 
                     (isAgent ? window.chatConfig.currentAgent.avatar : '/static/assets/img/user-avatar.jfif');
    }

    getMessageClass() {
        if (!this.isAgent) return 'user';
        if (!this.options?.type?.startsWith('crew_')) return 'agent';
        return `agent crew-message ${this.options.type}`;
    }

    _detectAndFormatTableData(content) {
        try {
            // Try to parse the content as JSON
            let data = content;
            if (typeof content === 'string') {
                // Check if content is wrapped in markdown code block
                const codeBlockMatch = content.match(/```(?:json)?\n([\s\S]*?)\n```/);
                if (codeBlockMatch) {
                    // Clean up the JSON content - handle ellipsis
                    let jsonContent = codeBlockMatch[1];
                    
                    // Extract entries before ellipsis and the last entry
                    const startContent = jsonContent.match(/{[\s\S]*?"analytics_data":\s*\[([\s\S]*?)\s*\.\.\./);
                    const endContent = jsonContent.match(/\.\.\.\s*([\s\S]*?\]\s*})/);
                    
                    if (startContent && endContent) {
                        // Combine the entries into valid JSON
                        const beforeEllipsis = startContent[0].replace(/,\s*\.\.\./, '');
                        const afterEllipsis = endContent[1];
                        jsonContent = beforeEllipsis + ',' + afterEllipsis;
                        try {
                            data = JSON.parse(jsonContent);
                        } catch (e) {
                            console.error('Error parsing reconstructed JSON:', e);
                            return null;
                        }
                    } else {
                        // Try parsing without the ellipsis
                        try {
                            jsonContent = jsonContent.replace(/,\s*\.\.\.\s*,/, ',');
                            data = JSON.parse(jsonContent);
                        } catch (e) {
                            console.error('Error parsing JSON after removing ellipsis:', e);
                            return null;
                        }
                    }
                }
            }

            // Look for common patterns in the data structure
            if (typeof data === 'object' && data !== null) {
                // Check for common response patterns and nested data
                for (const key of ['data', 'results', 'analytics_data', 'records', 'rows', 'items', 'response']) {
                    if (data[key] && Array.isArray(data[key]) && data[key].length > 0) {
                        const tableHtml = this._createTable(data[key]);
                        if (tableHtml) {
                            // If there's text before or after the code block, preserve it
                            let parts = [];
                            if (this.rawContent && this.rawContent.message) {
                                parts = this.rawContent.message.split(/```json\n[\s\S]*?\n```/);
                            } else {
                                parts = this.content.split(/```(?:json)?\n[\s\S]*?\n```/);
                            }
                            const prefix = parts[0] ? marked.parse(parts[0].trim()) : '';
                            const suffix = parts[1] ? marked.parse(parts[1].trim()) : '';
                            return prefix + tableHtml + suffix;
                        }
                    }
                }

                // If no list found in known keys, check all values
                for (const value of Object.values(data)) {
                    if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
                        return this._createTable(value);
                    }
                }
            }
        } catch (error) {
            console.error('Error detecting table data:', error);
        }
        return null;
    }

    _createTable(data) {
        if (!Array.isArray(data) || !data.length) return null;

        const tableId = `table-${Date.now()}`;
        const headers = Object.keys(data[0]);
        const rows = data.map(row => headers.map(header => {
            const value = row[header];
            // Format dates and numbers
            if (value instanceof Date || (typeof value === 'string' && !isNaN(Date.parse(value)))) {
                return new Date(value).toISOString().split('T')[0];
            }
            if (typeof value === 'number') {
                return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
            }
            return value;
        }));

        return `
            <div class="table-responsive">
                <table id="${tableId}" class="table table-sm">
                    <thead>
                        <tr>
                            ${headers.map(header => `<th>${this._formatFieldName(header)}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => `
                            <tr>
                                ${row.map(cell => `<td>${cell}</td>`).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    _formatFieldName(field) {
        // Convert camelCase or snake_case to Title Case
        return field
            .replace(/([A-Z])/g, ' $1') // Split camelCase
            .replace(/_/g, ' ')         // Replace underscores with spaces
            .replace(/\w\S*/g, txt => txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase()); // Title case
    }

    render(domId) {
        const messageElement = document.createElement('div');
        messageElement.id = `${domId}-container`;
        messageElement.className = `d-flex ${this.isAgent ? 'justify-content-start' : 'justify-content-end'} mb-4`;

        // Format content for display
        let formattedContent = this.content;
        if (this.isAgent) {
            try {
                // First try to detect and format table data
                const tableHtml = this._detectAndFormatTableData(this.content);
                if (tableHtml) {
                    formattedContent = tableHtml;
                } else {
                    formattedContent = marked.parse(this.content);
                }
            } catch (error) {
                console.error('Error parsing content:', error);
                formattedContent = this.content;
            }
        }

        messageElement.innerHTML = `
            ${this.isAgent ? `<div class="avatar me-2">
                <img src="${this.avatar}" 
                     alt="${window.chatConfig.currentAgent.name}" 
                     class="border-radius-lg shadow">
            </div>` : ''}
            <div class="message ${this.getMessageClass()}" style="max-width: 75%;">
                ${this.options?.metadata?.agent ? `
                <div class="message-header">
                    <small class="text-muted">${this.options.metadata.agent}</small>
                </div>` : ''}
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

        // Initialize DataTable for any tables in the message
        const table = messageElement.querySelector('table');
        if (table) {
            setTimeout(() => {
                try {
                    new simpleDatatables.DataTable(table, {
                        searchable: true,
                        fixedHeight: false,
                        perPage: 10
                    });
                } catch (error) {
                    console.warn(`Failed to initialize DataTable:`, error);
                }
            }, 100);
        }

        return messageElement;
    }
}

export { Message }; 