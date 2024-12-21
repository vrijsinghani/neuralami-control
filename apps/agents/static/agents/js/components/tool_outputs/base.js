class ToolOutputManager {
    constructor() {
        this.activeContainer = null;
        this.messagesContainer = document.getElementById('chat-messages');
    }

    handleToolStart(data) {
        try {
            // Try to parse if string, otherwise use as is
            const toolData = typeof data === 'string' ? JSON.parse(data) : data;
            
            // Create a new container for this tool output
            const container = document.createElement('div');
            container.className = 'tool-output mb-3';
            const containerId = `tool-${Date.now()}`;
            container.innerHTML = `
                <div class="tool-header d-flex align-items-center cursor-pointer collapsed" data-bs-toggle="collapse" data-bs-target="#${containerId}-content">
                    <i class="fas fa-chevron-down me-2 toggle-icon"></i>
                    <i class="fas fa-tools me-2"></i>
                    <span class="tool-name">${toolData.tool || 'Tool'}</span>
                </div>
                <div class="tool-content mt-2 collapse" id="${containerId}-content">
                    ${toolData.input ? `
                    <div class="tool-input text-muted mb-2">
                        <small>Input: ${toolData.input}</small>
                    </div>` : ''}
                    <div class="tool-result"></div>
                </div>
            `;
            
            // Add to messages container
            if (this.messagesContainer) {
                this.messagesContainer.appendChild(container);
                this.activeContainer = container;
                
                // Scroll to the new container
                container.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
        } catch (error) {
            console.error('Error handling tool start:', error);
            // Create a minimal container for error case
            const container = document.createElement('div');
            container.className = 'tool-output mb-3';
            container.innerHTML = `
                <div class="tool-header d-flex align-items-center">
                    <i class="fas fa-tools me-2"></i>
                    <span class="tool-name">Tool Execution</span>
                </div>
            `;
            
            if (this.messagesContainer) {
                this.messagesContainer.appendChild(container);
                this.activeContainer = container;
            }
        }
    }

    handleToolResult(result) {
        try {
            let container = this.activeContainer;
            
            // If no active container, create a standalone one
            if (!container) {
                console.warn('No active tool container found for result');
                return;
            }

            const resultContainer = container.querySelector('.tool-result');
            if (!resultContainer) return;

            // Handle different result types
            if (result.type === 'error') {
                resultContainer.innerHTML = `
                    <div class="tool-error mt-3">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        <span class="text-danger">${result.data}</span>
                    </div>
                `;
            } else if (result.type === 'table' && Array.isArray(result.data)) {
                resultContainer.innerHTML = this._createTable(result.data);
            } else if (result.type === 'json') {
                // Check for nested analytics_data in JSON result
                if (result.data.analytics_data && Array.isArray(result.data.analytics_data)) {
                    resultContainer.innerHTML = this._createTable(result.data.analytics_data);
                } else {
                    resultContainer.innerHTML = `
                        <pre class="json-output">${JSON.stringify(result.data, null, 2)}</pre>
                    `;
                }
            } else {
                resultContainer.textContent = typeof result === 'string' ? result : JSON.stringify(result);
            }

            // Don't clear active container - keep it for potential end message
        } catch (error) {
            console.error('Error handling tool result:', error);
        }
    }

    _createTable(data) {
        if (!Array.isArray(data) || data.length === 0) return '';

        const headers = Object.keys(data[0]);
        let html = `
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            ${headers.map(header => `<th>${header}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(row => `
                            <tr>
                                ${headers.map(header => `<td>${row[header]}</td>`).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        return html;
    }
}

export { ToolOutputManager }; 