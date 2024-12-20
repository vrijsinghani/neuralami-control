export class ToolOutputManager {
    constructor() {
        this.activeTools = new Map();
    }

    handleToolStart(data) {
        const { name, input, timestamp } = data;
        
        const toolContainer = document.createElement('div');
        toolContainer.className = 'd-flex justify-content-start mb-4';
        toolContainer.innerHTML = `
            <div class="tool-output" style="max-width: 75%;">
                <div class="tool-header">
                    <strong>Tool:</strong> ${name}
                </div>
                <div class="tool-content">
                    <pre><code>${JSON.stringify(input, null, 2)}</code></pre>
                </div>
                <div class="tool-timestamp text-xxs">
                    ${new Date(timestamp).toLocaleTimeString()}
                </div>
            </div>
        `;
        
        // Store reference to active tool
        this.activeTools.set(name, toolContainer);
        
        return toolContainer;
    }

    handleToolResult(result) {
        const resultContainer = document.createElement('div');
        resultContainer.className = 'd-flex justify-content-start mb-4';
        
        let content = result.data;
        if (typeof content === 'object') {
            content = JSON.stringify(content, null, 2);
        }
        
        resultContainer.innerHTML = `
            <div class="tool-output" style="max-width: 75%;">
                <div class="tool-content">
                    <pre><code>${content}</code></pre>
                </div>
            </div>
        `;
        
        // Highlight code if present
        const codeBlock = resultContainer.querySelector('pre code');
        if (codeBlock) {
            hljs.highlightElement(codeBlock);
        }
        
        return resultContainer;
    }
} 