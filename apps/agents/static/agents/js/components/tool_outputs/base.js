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
                <div class="tool-header d-flex align-items-center cursor-pointer" data-bs-toggle="collapse" data-bs-target="#${containerId}-content">
                <i class="fas fa-chevron-right me-2 toggle-icon"></i>
                <i class="fas fa-tools me-2"></i>
                    <span class="tool-name">${toolData.tool || 'Tool'}</span>
                </div>
                <div class="tool-content mt-2 collapse show" id="${containerId}-content">
                    ${toolData.input ? `
                    <div class="tool-input text-muted mb-2">
                        <small>Input: ${toolData.input}</small>
                    </div>` : ''}
                    <div class="tool-result"></div>
                </div>
            `;
            
            // Add click handler for chevron rotation
            const header = container.querySelector('.tool-header');
            header.addEventListener('click', () => {
                const icon = header.querySelector('.toggle-icon');
                icon.style.transform = icon.style.transform === 'rotate(90deg)' ? '' : 'rotate(90deg)';
            });
            
            // Add to messages container
            if (this.messagesContainer) {
                this.messagesContainer.appendChild(container);
                this.activeContainer = container;
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
                container = document.createElement('div');
                container.className = 'tool-output mb-3';
                const containerId = `tool-result-${Date.now()}`;
                container.innerHTML = `
                    <div class="tool-header d-flex align-items-center cursor-pointer" data-bs-toggle="collapse" data-bs-target="#${containerId}-content">
                        <i class="fas fa-chevron-right me-2 toggle-icon"></i>
                        <i class="fas fa-tools me-2"></i>
                        <span class="tool-name">Tool Result</span>
                    </div>
                    <div class="tool-content mt-2 collapse show" id="${containerId}-content">
                        <div class="tool-result"></div>
                    </div>
                `;

                // Add click handler for chevron rotation
                const header = container.querySelector('.tool-header');
                header.addEventListener('click', () => {
                    const icon = header.querySelector('.toggle-icon');
                    icon.style.transform = icon.style.transform === 'rotate(90deg)' ? '' : 'rotate(90deg)';
                });
                
                if (this.messagesContainer) {
                    this.messagesContainer.appendChild(container);
                }
            }

            const resultContainer = container.querySelector('.tool-result');
            if (!resultContainer) return;

            // Handle different result types
            if (result.type === 'table' && Array.isArray(result.data)) {
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

            // Clear active container after handling result
            this.activeContainer = null;
        } catch (error) {
            console.error('Error handling tool result:', error);
        }
    }

    _createTable(data) {
        if (!Array.isArray(data) || !data.length) return '';
        
        const headers = Object.keys(data[0]);
        return `
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            ${headers.map(header => `<th scope="col">${header}</th>`).join('')}
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
    }
}

export { ToolOutputManager }; 