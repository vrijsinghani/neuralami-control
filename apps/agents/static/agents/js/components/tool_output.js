console.debug('🛠️ Loading ToolOutputHandler module...');

export class ToolOutputHandler {
    constructor(config) {
        this.toolContainers = new Map();
        this.agentAvatar = config?.agentAvatar || '/static/agents/img/agent-avatar.png';
        this.agentName = config?.agentName || 'Agent';
        console.log('ToolOutputHandler initialized:', config);
    }

    handleToolStart(data) {
        console.log('Tool start data:', data);
        if (!data) return null;

        const toolName = data.name;
        const toolInput = data.input;

        if (!toolName) {
            console.warn('No tool name provided');
            return null;
        }

        const containerId = `tool-${Date.now()}`;
        const prettyToolName = toolName.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');

        const container = document.createElement('div');
        container.id = containerId;
        container.className = 'd-flex justify-content-start mb-4';
        container.innerHTML = `
            <div class="avatar me-2">
                <img src="${this.agentAvatar}" 
                     alt="${this.agentName}" 
                     class="border-radius-lg shadow">
            </div>
            <div class="tool-message w-100" style="max-width: 75%;">
                <div class="message-content tool-usage">
                    <div class="tool-header d-flex align-items-center" 
                         data-bs-toggle="collapse" 
                         data-bs-target="#${containerId}-content"
                         role="button"
                         aria-expanded="false">
                        <i class="fas fa-cog me-2"></i>
                        <strong>${prettyToolName}</strong>
                        <i class="fas fa-chevron-down ms-auto"></i>
                    </div>
                    <div class="collapse" id="${containerId}-content">
                        <div class="tool-details mt-3">
                            <div class="tool-input">
                                <strong>Input:</strong>
                                <pre class="json-output mt-2">${this.formatToolInput(toolInput)}</pre>
                            </div>
                            <div class="tool-output mt-3 d-none">
                                <strong>Output:</strong>
                                <div class="output-content mt-2"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.toolContainers.set(containerId, container);
        
        // Initialize collapse after the container is added to the DOM
        setTimeout(() => {
            const collapseElement = container.querySelector('.collapse');
            if (collapseElement) {
                new bootstrap.Collapse(collapseElement, {
                    toggle: false // Start collapsed
                });
            }
        }, 0);

        return container;
    }

    handleToolResult(data) {
        console.debug('🛠️ handleToolResult called with data:', data);
        if (!data) return null;

        const lastContainerId = Array.from(this.toolContainers.keys()).pop();
        if (!lastContainerId) {
            console.warn('No tool container found for result');
            return null;
        }

        const container = this.toolContainers.get(lastContainerId);
        const outputDiv = container.querySelector('.tool-output');
        const outputContent = container.querySelector('.output-content');

        if (outputDiv && outputContent) {
            outputDiv.classList.remove('d-none');
            outputContent.innerHTML = this.formatToolOutput(data);
        }

        return container;
    }

    formatToolInput(input) {
        try {
            if (typeof input === 'string') {
                return input;
            }
            return JSON.stringify(input, null, 2);
        } catch (e) {
            console.error('Error formatting tool input:', e);
            return String(input);
        }
    }

    formatToolOutput(result) {
        console.log('Formatting tool output:', result);
        if (!result) return '';

        try {
            // If result is a string, check if it's a markdown table
            if (typeof result === 'string' || (result.type === 'text' && typeof result.data === 'string')) {
                const content = result.data || result;
                // Check if content is a markdown table (starts with | and has header separator)
                if (content.startsWith('|') && content.includes('|-')) {
                    return `<div class="table-responsive">${this.markdownTableToHtml(content)}</div>`;
                }
            }

            switch (result.type) {
                case 'text':
                    return `<div class="text-output">${result.data}</div>`;
                case 'json':
                    return `<pre class="json-output">${JSON.stringify(result.data, null, 2)}</pre>`;
                case 'error':
                    return `<div class="error-output">${result.message || 'Unknown error'}</div>`;
                default:
                    if (typeof result === 'string' && result.startsWith('{')) {
                        try {
                            const jsonData = JSON.parse(result);
                            return `<pre class="json-output">${JSON.stringify(jsonData, null, 2)}</pre>`;
                        } catch (e) {
                            return `<div class="text-output">${result}</div>`;
                        }
                    }
                    return `<pre>${JSON.stringify(result, null, 2)}</pre>`;
            }
        } catch (e) {
            console.error('Error formatting tool output:', e);
            return `<div class="error-output">Error formatting output: ${e.message}</div>`;
        }
    }

    markdownTableToHtml(markdownTable) {
        const rows = markdownTable.trim().split('\n');
        const headers = rows[0].split('|').filter(cell => cell.trim()).map(cell => cell.trim());
        
        let html = '<table class="table table-striped table-hover">\n<thead>\n<tr>';
        
        // Add headers
        headers.forEach(header => {
            html += `<th>${header}</th>`;
        });
        html += '</tr>\n</thead>\n<tbody>';
        
        // Add data rows (skip header and separator rows)
        rows.slice(2).forEach(row => {
            const cells = row.split('|').filter(cell => cell.trim()).map(cell => cell.trim());
            html += '\n<tr>';
            cells.forEach(cell => {
                html += `<td>${cell}</td>`;
            });
            html += '</tr>';
        });
        
        html += '\n</tbody>\n</table>';
        return html;
    }
} 