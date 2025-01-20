class Message {
    constructor(content, isAgent = false, avatar = null) {
        // Handle case where content is a JSON object with message field
        if (typeof content === 'object' && content !== null && content.message) {
            this.content = content.message;
            this.rawContent = content;
            this.isCrewMessage = content.type === 'crew_message';
            this.isAgent = isAgent || this.isCrewMessage; // Treat crew messages like agent messages
        } else {
            this.content = content;
            this.rawContent = null;
            this.isCrewMessage = false;
            this.isAgent = isAgent;
        }
        this.avatar = avatar || (this.isAgent ? window.chatConfig.currentAgent.avatar : '/static/assets/img/user-avatar.jfif');
    }

    _detectAndFormatTableData(content) {
        try {
            // First check if content starts with markdown headers or common markdown elements
            if (typeof content === 'string' && 
                (content.trim().startsWith('#') || 
                 content.trim().startsWith('*') || 
                 content.trim().startsWith('-'))) {
                return null; // Let the markdown parser handle it
            }

            // Try to parse the content as JSON
            let data = content;
            if (typeof content === 'string') {
                // Check if content is wrapped in markdown code block
                const codeBlockMatch = content.match(/```(?:json)?\n([\s\S]*?)\n```/);
                if (codeBlockMatch) {
                    try {
                        // Clean up the JSON content
                        let jsonContent = codeBlockMatch[1].trim();
                        data = JSON.parse(jsonContent);
                    } catch (e) {
                        console.debug('Content is not valid JSON, will be handled as markdown');
                        return null;
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
        if (this.isAgent || this.isCrewMessage) {
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
            ${this.isAgent || this.isCrewMessage ? `<div class="avatar me-2">
                <img src="${this.avatar}" 
                     alt="${this.isCrewMessage ? 'Crew' : window.chatConfig.currentAgent.name}" 
                     class="border-radius-lg shadow">
            </div>` : ''}
            <div class="message ${this.isAgent || this.isCrewMessage ? 'agent' : 'user'}" style="max-width: 75%;">
                <div class="message-content">
                    <div class="message-actions">
                        <button class="btn btn-link copy-message" title="Copy to clipboard">
                            <i class="fas fa-copy"></i>
                        </button>
                        ${!this.isAgent && !this.isCrewMessage ? `
                        <button class="btn btn-link edit-message" title="Edit message">
                            <i class="fas fa-edit"></i>
                        </button>` : ''}
                    </div>
                    <div class="message-text">
                        ${formattedContent}
                    </div>
                </div>
            </div>
            ${!this.isAgent && !this.isCrewMessage ? `<div class="avatar ms-2">
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