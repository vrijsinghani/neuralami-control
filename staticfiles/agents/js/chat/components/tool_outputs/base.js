export class ToolHandler {
    constructor(chatManager) {
        this.chatManager = chatManager;
        this.activeTools = new Map();
    }

    handleToolStart(content) {
        if (!content) return;

        // Format tool name for display
        const prettyToolName = content.name.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');

        const messageId = `tool-${Date.now()}`;
        const html = `
            <div class="d-flex justify-content-start mb-4">
                <div class="avatar me-2">
                    <img src="${this.chatManager.currentAgent.avatar}" alt="${this.chatManager.currentAgent.name}" class="border-radius-lg shadow">
                </div>
                <div class="tool-message start w-100" style="max-width: 75%;">
                    <div class="message-content tool-usage">
                        <div class="tool-header d-flex align-items-center collapsed" 
                             data-bs-toggle="collapse" 
                             data-bs-target="#${messageId}" 
                             aria-expanded="false" 
                             aria-controls="${messageId}"
                             role="button">
                            <i class="fas fa-cog me-2"></i>
                            <strong>${prettyToolName}</strong>
                            <i class="fas fa-chevron-down ms-auto"></i>
                        </div>
                        <div class="collapse" id="${messageId}">
                            <div class="tool-details mt-3">
                                <div class="tool-input">
                                    <strong>Input:</strong>
                                    <pre class="json-output mt-2">${JSON.stringify(content.input, null, 2)}</pre>
                                </div>
                                ${content.log ? `
                                <div class="tool-log mt-3">
                                    <strong>Log:</strong>
                                    <div class="mt-2">${content.log}</div>
                                </div>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        const container = document.createElement('div');
        container.innerHTML = html;
        this.activeTools.set(messageId, container);
        
        return container;
    }

    handleToolResult(result) {
        if (!result) return;

        const messageId = `tool-result-${Date.now()}`;
        let resultContent = '';

        switch (result.type) {
            case 'text':
                resultContent = `<div class="tool-result">${result.data}</div>`;
                break;
            case 'json':
                resultContent = `<pre class="json-output">${JSON.stringify(result.data, null, 2)}</pre>`;
                break;
            case 'table':
                resultContent = this.formatTableResult(result.data);
                break;
            case 'error':
                resultContent = `<div class="error-output">${result.data}</div>`;
                break;
            default:
                resultContent = `<div class="tool-result">${result.data}</div>`;
        }

        const html = `
            <div class="d-flex justify-content-start mb-4">
                <div class="avatar me-2">
                    <img src="${this.chatManager.currentAgent.avatar}" alt="${this.chatManager.currentAgent.name}" class="border-radius-lg shadow">
                </div>
                <div class="tool-message result w-100" style="max-width: 75%;">
                    <div class="message-content tool-usage">
                        <div class="tool-result-content">
                            ${resultContent}
                        </div>
                    </div>
                </div>
            </div>
        `;

        const container = document.createElement('div');
        container.innerHTML = html;
        return container;
    }

    formatTableResult(data) {
        if (!Array.isArray(data) || !data.length) return '';

        const headers = Object.keys(data[0]);
        const rows = data.map(row => headers.map(header => row[header]));

        return `
            <div class="table-responsive">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            ${headers.map(header => `<th>${header}</th>`).join('')}
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
} 