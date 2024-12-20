class ToolOutputManager {
    constructor() {
        this.activeTools = new Map();
    }

    handleToolStart(message) {
        try {
            const toolData = typeof message === 'string' ? JSON.parse(message) : message;
            console.log('Tool start data:', toolData);

            // Parse input if it's a string
            let parsedInput;
            try {
                parsedInput = typeof toolData.input === 'string' ? 
                    JSON.parse(toolData.input.replace(/'/g, '"')) : 
                    toolData.input;
            } catch (e) {
                parsedInput = toolData.input;
            }

            // Create container for tool output
            const container = document.createElement('div');
            container.className = 'tool-output mb-3';
            container.id = `tool-${Date.now()}`; // Add unique ID
            
            // Create header with collapse functionality
            const header = document.createElement('div');
            header.className = 'd-flex align-items-center mb-2 cursor-pointer';
            header.setAttribute('data-bs-toggle', 'collapse');
            header.setAttribute('data-bs-target', `#${container.id}-content`);
            header.setAttribute('aria-expanded', 'false');
            header.innerHTML = `
                <i class="fas fa-chevron-right me-2 toggle-icon"></i>
                <i class="fas fa-tools me-2"></i>
                <span class="tool-name">${toolData.name}</span>
            `;
            
            // Create collapsible content area
            const content = document.createElement('div');
            content.className = 'tool-content p-3 border rounded collapse';
            content.id = `${container.id}-content`;
            content.innerHTML = `
                <div class="tool-status mb-3">
                    <div class="spinner-border spinner-border-sm text-primary" role="status">
                        <span class="visually-hidden">Running...</span>
                    </div>
                    <span class="ms-2">Running tool...</span>
                </div>
                <div class="tool-input mb-3">
                    <strong>Input:</strong>
                    <pre><code class="json">${JSON.stringify(parsedInput, null, 2)}</code></pre>
                </div>
                <div class="tool-result mt-3" style="display: none;"></div>
            `;
            
            // Add click handler for chevron rotation
            header.addEventListener('click', () => {
                const icon = header.querySelector('.toggle-icon');
                icon.style.transform = icon.style.transform === 'rotate(90deg)' ? '' : 'rotate(90deg)';
            });
            
            // Assemble container
            container.appendChild(header);
            container.appendChild(content);
            
            // Store reference to container
            this.activeTools.set(toolData.name, container);
            
            return container;
        } catch (error) {
            console.error('Error handling tool start:', error);
            return null;
        }
    }

    formatTableData(data) {
        if (!Array.isArray(data) || data.length === 0) return null;
        
        // Get headers from first row
        const headers = Object.keys(data[0]);
        
        // Create table HTML
        const tableHtml = `
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
        
        return tableHtml;
    }

    handleToolEnd(message) {
        try {
            // Parse the outer message if it's a string
            const messageData = typeof message.message === 'string' ? JSON.parse(message.message) : message.message;
            console.log('Parsed message data:', messageData);
            
            // Parse the output field which is another level of stringified JSON
            let output;
            try {
                output = typeof messageData.output === 'string' ? JSON.parse(messageData.output) : messageData.output;
                console.log('Parsed output:', output);
            } catch (e) {
                console.error('Error parsing output:', e);
                output = messageData.output;
            }

            // Find the tool's container - use the last active tool if name not available
            const container = this.activeTools.values().next().value;
            if (!container) {
                console.warn('No active tool found');
                return null;
            }

            // Update the tool's status and output
            const content = container.querySelector('.tool-content');
            if (content) {
                // Update status - remove loading indicator
                const statusDiv = content.querySelector('.tool-status');
                if (statusDiv) {
                    statusDiv.innerHTML = `
                        <i class="fas fa-check-circle text-success me-2"></i>
                        <span>Tool completed</span>
                    `;
                }

                // Update result
                const resultDiv = content.querySelector('.tool-result');
                if (resultDiv && output) {
                    resultDiv.style.display = 'block';
                    
                    try {
                        // Handle nested analytics_data if present
                        if (output.analytics_data) {
                            const tableHtml = this.formatTableData(output.analytics_data);
                            if (tableHtml) {
                                resultDiv.innerHTML = `
                                    <strong>Analytics Data:</strong>
                                    ${tableHtml}
                                `;
                                return;
                            }
                        }
                        
                        // If not analytics data, display as formatted JSON
                        resultDiv.innerHTML = `
                            <strong>Output:</strong>
                            <pre><code class="json">${JSON.stringify(output, null, 2)}</code></pre>
                        `;
                    } catch (e) {
                        console.error('Error formatting output:', e);
                        // If parsing fails, display as plain text
                        resultDiv.innerHTML = `
                            <strong>Output:</strong>
                            <pre><code>${output}</code></pre>
                        `;
                    }
                } else {
                    console.warn('No output or result div found');
                }
            }

            // Remove from active tools
            this.activeTools.clear();  // Clear all active tools
            
            return null;
        } catch (error) {
            console.error('Error handling tool end:', error);
            return null;
        }
    }

    handleToolResult(result) {
        try {
            console.log('handleToolResult - received:', result);
            
            // Find the active tool's container
            const activeContainer = this.activeTools.values().next().value;
            console.log('handleToolResult - active container:', activeContainer);
            
            if (activeContainer) {
                // Add result to the existing tool container
                const resultDiv = activeContainer.querySelector('.tool-result');
                console.log('handleToolResult - result div:', resultDiv);
                
                if (resultDiv) {
                    resultDiv.style.display = 'block';
                    
                    let content;
                    console.log('handleToolResult - processing result:', {
                        result_exists: !!result,
                        data_exists: result && result.data !== undefined,
                        type: result?.type,
                        data: result?.data
                    });
                    
                    if (result && result.data !== undefined) {
                        if (Array.isArray(result.data)) {
                            console.log('handleToolResult - handling array data');
                            content = this.formatTableData(result.data) || 
                                     `<pre class="mb-0"><code>${JSON.stringify(result.data, null, 2)}</code></pre>`;
                        } else {
                            console.log('handleToolResult - handling by type:', result.type);
                            switch (result.type) {
                                case 'text':
                                    content = `<pre class="mb-0"><code>${result.data}</code></pre>`;
                                    break;
                                case 'json':
                                    // Check for analytics_data
                                    if (result.data.analytics_data) {
                                        console.log('handleToolResult - found analytics_data:', result.data.analytics_data);
                                        const tableHtml = this.formatTableData(result.data.analytics_data);
                                        if (tableHtml) {
                                            content = `
                                                <strong>Analytics Data:</strong>
                                                ${tableHtml}
                                            `;
                                            break;
                                        }
                                    }
                                    content = `<pre class="mb-0"><code class="json">${JSON.stringify(result.data, null, 2)}</code></pre>`;
                                    break;
                                case 'error':
                                    content = `<div class="alert alert-danger mb-0">${result.data}</div>`;
                                    break;
                                default:
                                    content = `<div class="mb-0">${result.data}</div>`;
                            }
                        }
                    } else {
                        console.log('handleToolResult - no data available');
                        content = '<div class="alert alert-warning mb-0">No data available</div>';
                    }
                    
                    console.log('handleToolResult - final content:', content);
                    resultDiv.innerHTML = `
                        <strong>Result:</strong>
                        ${content}
                    `;
                }
                return null;
            }
            
            // If no active tool container, create a standalone result container
            console.log('handleToolResult - creating standalone container');
            const container = document.createElement('div');
            container.className = 'tool-result mb-3';
            container.id = `tool-result-${Date.now()}`;
            
            let content;
            if (result && result.data !== undefined) {
                if (Array.isArray(result.data)) {
                    content = this.formatTableData(result.data) || 
                             `<pre class="mb-0"><code>${JSON.stringify(result.data, null, 2)}</code></pre>`;
                } else {
                    switch (result.type) {
                        case 'text':
                            content = `<pre class="mb-0"><code>${result.data}</code></pre>`;
                            break;
                        case 'json':
                            content = `<pre class="mb-0"><code class="json">${JSON.stringify(result.data, null, 2)}</code></pre>`;
                            break;
                        case 'error':
                            content = `<div class="alert alert-danger mb-0">${result.data}</div>`;
                            break;
                        default:
                            content = `<div class="mb-0">${result.data}</div>`;
                    }
                }
            } else {
                content = '<div class="alert alert-warning mb-0">No data available</div>';
            }
            
            container.innerHTML = `
                <div class="d-flex align-items-center mb-2 cursor-pointer" data-bs-toggle="collapse" data-bs-target="#${container.id}-content" aria-expanded="false">
                    <i class="fas fa-chevron-right me-2 toggle-icon"></i>
                    <span>Tool Result</span>
                </div>
                <div class="collapse" id="${container.id}-content">
                    <div class="tool-content p-3 border rounded">
                        ${content}
                    </div>
                </div>
            `;
            
            // Add click handler for chevron rotation
            const header = container.querySelector('[data-bs-toggle="collapse"]');
            header.addEventListener('click', () => {
                const icon = header.querySelector('.toggle-icon');
                icon.style.transform = icon.style.transform === 'rotate(90deg)' ? '' : 'rotate(90deg)';
            });
            
            return container;
        } catch (error) {
            console.error('Error handling tool result:', error);
            return null;
        }
    }
}

export { ToolOutputManager }; 