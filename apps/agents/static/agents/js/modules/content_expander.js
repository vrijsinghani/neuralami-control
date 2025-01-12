// Content expander module for handling expandable card content
export class ContentExpander {
    constructor() {
        this.sidePanel = null;
        this.activeCard = null;
        this.setupSidePanel();
    }

    setupSidePanel() {
        // Create side panel if it doesn't exist
        if (!document.getElementById('content-side-panel')) {
            const panel = document.createElement('div');
            panel.id = 'content-side-panel';
            panel.className = 'position-fixed end-0 top-0 h-100 bg-white shadow-lg';
            panel.style.width = '0';
            panel.style.transition = 'width 0.3s ease-in-out';
            panel.style.zIndex = '1040';
            panel.innerHTML = `
                <div class="d-flex flex-column h-100">
                    <div class="p-3 border-bottom d-flex justify-content-between align-items-center">
                        <h6 class="mb-0 content-title"></h6>
                        <div>
                            <button class="btn btn-link text-dark p-0 me-3" id="export-content">
                                <i class="fas fa-download"></i>
                            </button>
                            <button class="btn btn-link text-dark p-0" id="close-panel">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="p-3 flex-grow-1 overflow-auto content-body"></div>
                </div>
            `;
            document.body.appendChild(panel);
            this.sidePanel = panel;
            
            // Add event listeners
            document.getElementById('close-panel').addEventListener('click', () => this.closeSidePanel());
            document.getElementById('export-content').addEventListener('click', () => this.exportContent());
        }
    }

    expandContent(cardElement, title, content, metadata = {}) {
        console.log('expandContent called', { title, content, metadata });
        this.activeCard = cardElement;
        this.activeContent = { title, content, metadata };
        
        // Highlight active card
        if (this.activeCard) {
            this.activeCard.classList.add('border-primary');
        }
        
        // Update panel content
        const titleEl = this.sidePanel.querySelector('.content-title');
        const bodyEl = this.sidePanel.querySelector('.content-body');
        
        titleEl.textContent = title;
        // Use the global markdown-it instance
        if (!window.md) {
            console.error('markdown-it not initialized');
            return;
        }
        
        // Check if content appears to be markdown
        // const isMarkdown = /^#|\[.*\]\(.*\)|\*{1,2}|`{1,3}/.test(content);

        const renderedContent = window.md.render(content);

        console.log('Rendered content:', renderedContent);  // Fixed syntax error here
    
        bodyEl.innerHTML = `
            <div class="card border-0">
                <div class="card-body">
                    <div class="markdown-content mb-3">${renderedContent}</div>
                    ${this.renderMetadata(metadata)}
                </div>
            </div>
        `;
            
        // Show panel
        this.sidePanel.style.width = '500px';
    }

    renderMetadata(metadata) {
        if (!Object.keys(metadata).length) return '';
        
        return `
            <div class="border-top pt-3 mt-3">
                ${Object.entries(metadata).map(([key, value]) => `
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <small class="text-muted">${key}:</small>
                        <span class="text-sm">${value}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    closeSidePanel() {
        // Remove highlight from active card
        if (this.activeCard) {
            this.activeCard.classList.remove('border-primary');
            this.activeCard = null;
        }
        
        // Hide panel
        this.sidePanel.style.width = '0';
    }

    exportContent() {
        if (!this.activeContent) return;
        
        const { title, content, metadata } = this.activeContent;
        const exportData = {
            title,
            content,
            metadata,
            exportedAt: new Date().toISOString()
        };
        
        // Create blob and download
        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title.toLowerCase().replace(/\s+/g, '-')}-${new Date().getTime()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// Add CSS styles
const style = document.createElement('style');
style.textContent = `
    #content-side-panel {
        border-left: 1px solid #dee2e6;
    }
    .markdown-content {
        white-space: pre-wrap;
        word-break: break-word;
    }
    .markdown-content {
        max-width: 800px;
        margin: 0 auto;
    }
    .markdown-content > * {
        margin: 1rem 0;
    }
    .markdown-content pre {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 4px;
        overflow-x: auto;
    }
    .content-body {
        scrollbar-width: thin;
    }
    .content-body::-webkit-scrollbar {
        width: 6px;
    }
    .content-body::-webkit-scrollbar-thumb {
        background-color: #adb5bd;
        border-radius: 3px;
    }
`;
document.head.appendChild(style);
