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
                <div class="tool-header d-flex align-items-center justify-content-between">
                    <div class="d-flex align-items-center cursor-pointer collapsed" data-bs-toggle="collapse" data-bs-target="#${containerId}-content">
                        <i class="fas fa-chevron-down me-2 toggle-icon"></i>
                        <i class="fas fa-tools me-2"></i>
                        <span class="tool-name">${toolData.tool || 'Tool'}</span>
                    </div>
                    <div class="tool-actions">
                        <!-- CSV download button will be added here if table data is found -->
                    </div>
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
                this._addCsvDownloadButton(container, result.data);
            } else if (result.type === 'json') {
                // Find any array of objects in the JSON that could be a table
                const tableData = this._findTableData(result.data);
                if (tableData) {
                    resultContainer.innerHTML = this._createTable(tableData);
                    this._addCsvDownloadButton(container, tableData);
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

    _findTableData(data) {
        // If data is an array of objects, it's already tabular
        if (Array.isArray(data) && data.length > 0 && typeof data[0] === 'object') {
            return data;
        }

        // Look for arrays in the object values
        for (const key in data) {
            const value = data[key];
            if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
                return value;
            }
        }

        return null;
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

    _addCsvDownloadButton(container, data) {
        const toolActions = container.querySelector('.tool-actions');
        if (!toolActions || !data || !data.length) return;

        const headers = Object.keys(data[0]);
        const csvContent = [
            headers.join(','),
            ...data.map(row => headers.map(header => {
                let value = row[header];
                // Handle values that need quotes (contains commas, quotes, or newlines)
                if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n'))) {
                    value = `"${value.replace(/"/g, '""')}"`;
                }
                return value;
            }).join(','))
        ].join('\n');

        // Create download button
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        
        const downloadButton = document.createElement('a');
        downloadButton.href = url;
        downloadButton.download = 'table_data.csv';
        downloadButton.className = 'btn btn-link btn text-primary p-0 ms-2';
        downloadButton.innerHTML = '<i class="fas fa-download"></i>';
        downloadButton.title = 'Download as CSV';
        
        // Clean up the URL on click
        downloadButton.addEventListener('click', () => {
            setTimeout(() => URL.revokeObjectURL(url), 100);
        });

        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'btn btn-link btn text-primary p-0 ms-2';
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.title = 'Copy CSV to clipboard';
        
        copyButton.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(csvContent);
                // Show success feedback
                const originalIcon = copyButton.innerHTML;
                copyButton.innerHTML = '<i class="fas fa-check text-success"></i>';
                setTimeout(() => {
                    copyButton.innerHTML = originalIcon;
                }, 1000);
            } catch (err) {
                console.error('Failed to copy:', err);
                // Show error feedback
                const originalIcon = copyButton.innerHTML;
                copyButton.innerHTML = '<i class="fas fa-times text-danger"></i>';
                setTimeout(() => {
                    copyButton.innerHTML = originalIcon;
                }, 1000);
            }
        });

        toolActions.appendChild(copyButton);
        toolActions.appendChild(downloadButton);
    }
}

export { ToolOutputManager }; 