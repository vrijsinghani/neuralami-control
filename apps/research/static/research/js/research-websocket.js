// Research-specific WebSocket service
export class ResearchWebSocketService {
    constructor(researchId) {
        this.researchId = researchId;
        this.socket = null;
        this.isConnected = false;
        
        // Get DOM elements
        this.progressContainer = document.getElementById('progress-container');
        this.urlsList = document.querySelector('#sourcesList .sources-list');
        this.learningsList = document.querySelector('.learnings-list');
        this.reportContainer = document.querySelector('.card.d-none');  // Select the hidden report card
        this.statusBadge = document.getElementById('status-badge');
        this.cancelButton = document.getElementById('cancel-research');
        
        // Initialize markdown-it
        this.md = window.markdownit({
            html: true,
            linkify: true,
            typographer: true,
            highlight: function (str, lang) {
                if (lang && window.hljs && window.hljs.getLanguage(lang)) {
                    try {
                        return window.hljs.highlight(str, { language: lang }).value;
                    } catch (__) {}
                }
                return '';
            }
        });
        
        // Initialize badge animation if research is pending or in progress
        if (this.statusBadge) {
            const status = this.statusBadge.textContent.trim();
            if (status === 'In Progress' || status === 'Pending') {
                this.statusBadge.classList.remove('bg-success', 'bg-danger', 'bg-warning');
                this.statusBadge.classList.add('bg-info', 'badge-animated');
                this.statusBadge.textContent = 'In Progress';
            }
        }
        
        this.connect();
    }

    connect() {
        const wsScheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${wsScheme}${window.location.host}/ws/research/${this.researchId}/`;
        
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.setupCancelButton();
        };
        
        this.socket.onclose = () => {
            console.log('WebSocket disconnected');
            this.isConnected = false;
            // Try to reconnect after 5 seconds
            setTimeout(() => this.connect(), 5000);
        };
        
        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'research_update') {
                    this.handleResearchUpdate(data.data);
                }
            } catch (error) {
                console.error('Error processing message:', error);
            }
        };
    }

    setupCancelButton() {
        if (this.cancelButton) {
            this.cancelButton.addEventListener('click', () => {
                if (confirm('Are you sure you want to cancel this research task?')) {
                    fetch(`/research/${this.researchId}/cancel/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': this.getCsrfToken(),
                        },
                    })
                    .then(response => {
                        if (response.ok) {
                            this.updateProgress('Research task cancelled by user.');
                            this.cancelButton.remove();
                            if (this.statusBadge) {
                                this.statusBadge.textContent = 'Cancelled';
                                this.statusBadge.className = 'badge bg-warning';
                            }
                        } else {
                            console.error('Failed to cancel research task');
                        }
                    })
                    .catch(error => {
                        console.error('Error cancelling research task:', error);
                    });
                }
            });
        }
    }

    getCsrfToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    handleResearchUpdate(data) {
        switch (data.update_type) {
            case 'generating_queries':
                this.updateProgress(data.message);
                if (this.statusBadge) {
                    this.statusBadge.textContent = 'In Progress';
                    this.statusBadge.classList.remove('bg-success', 'bg-danger', 'bg-warning');
                    this.statusBadge.classList.add('bg-info', 'badge-animated');
                }
                break;
                
            case 'queries_generated':
                this.updateProgress('Search queries generated: ' + data.queries.join(', '));
                break;
                
            case 'urls_found':
                this.updateUrls(data.urls);
                break;
                
            case 'processing_content':
                this.updateProgress(data.message);
                break;
                
            case 'learnings_extracted':
                this.updateLearnings(data.learnings);
                break;
                
            case 'completed':
                this.handleCompletion(data);
                break;
                
            case 'error':
                this.handleError(data.error);
                break;
                
            case 'cancelled':
                this.handleCancellation();
                break;
        }
    }

    updateProgress(message) {
        if (this.progressContainer) {
            const div = document.createElement('div');
            div.className = 'progress-update text-xs';
            div.textContent = message;
            this.progressContainer.appendChild(div);
            div.scrollIntoView({ behavior: 'smooth' });
        } else {
            console.error('Progress container not found for message:', message);
        }
    }

    updateUrls(urls) {
        if (this.urlsList && Array.isArray(urls)) {
            urls.forEach(url => {
                const sourceItem = document.createElement('div');
                sourceItem.className = 'source-item';
                sourceItem.innerHTML = `
                    <a href="${url}" target="_blank" rel="noopener noreferrer" class="text-xxs">
                        <i class="fas fa-link me-1"></i>
                        ${url.length > 50 ? url.substring(0, 47) + '...' : url}
                    </a>
                `;
                this.urlsList.appendChild(sourceItem);
            });
        } else {
            console.error('URLs list container not found or invalid URLs:', urls);
        }
    }

    updateLearnings(learnings) {
        if (this.learningsList && Array.isArray(learnings)) {
            learnings.forEach((learning, index) => {
                // Skip if learning is null or undefined
                if (!learning) return;
                
                // Extract text based on learning type
                let learningText;
                let categoryText = '';
                
                if (typeof learning === 'object') {
                    if (learning.detail) {
                        learningText = learning.detail;
                        if (learning.category) {
                            categoryText = `<strong class="d-block mb-1">${learning.category}</strong>`;
                        }
                    } else if (learning.fact) {
                        learningText = learning.fact;
                    } else {
                        learningText = JSON.stringify(learning);
                    }
                } else {
                    learningText = learning;
                }
                
                const learningBlock = document.createElement('div');
                learningBlock.className = 'learning-block';
                const uniqueId = `learning-${Date.now()}-${index}`;
                learningBlock.innerHTML = `
                    <div class="header d-flex align-items-center" style="cursor: pointer;" data-bs-toggle="collapse" data-bs-target="#${uniqueId}">
                        <i class="fas fa-lightbulb text-info me-2"></i>
                        <h6 class="mb-0 text-sm">${learningText.length > 75 ? learningText.substring(0, 75) + '...' : learningText}</h6>
                        <i class="fas fa-chevron-down ms-auto"></i>
                    </div>
                    <div class="collapse" id="${uniqueId}">
                        <div class="learning-content text-xs">
                            ${categoryText}
                            ${learningText}
                        </div>
                    </div>
                `;
                this.learningsList.appendChild(learningBlock);
            });
        } else {
            console.error('Learnings list container not found or invalid learnings:', learnings);
        }
    }

    handleCompletion(data) {
        if (data.status === 'completed') {
            if (this.reportContainer) {
                // Get the markdown content div
                let markdownContent = this.reportContainer.querySelector('.markdown-content');
                if (!markdownContent) {
                    markdownContent = document.createElement('div');
                    markdownContent.className = 'markdown-content';
                    this.reportContainer.querySelector('.card-body').appendChild(markdownContent);
                }

                // Render and set the report content
                const htmlContent = this.md.render(data.report || '');
                markdownContent.innerHTML = htmlContent;
                
                // Show the report container
                this.reportContainer.classList.remove('d-none');
                
                // Apply syntax highlighting if available
                if (window.hljs) {
                    this.reportContainer.querySelectorAll('pre code').forEach((block) => {
                        window.hljs.highlightBlock(block);
                    });
                }
            }

            if (this.statusBadge) {
                this.statusBadge.textContent = 'Completed';
                this.statusBadge.classList.remove('bg-info', 'bg-danger', 'bg-warning', 'badge-animated');
                this.statusBadge.classList.add('bg-success');
            }
        } else if (data.status === 'failed') {
            this.handleError(data.error);
        }
    }

    handleError(error) {
        if (this.progressContainer) {
            const div = document.createElement('div');
            div.className = 'progress-update';
            div.style.borderLeft = '3px solid #dc3545';  // Red border for errors
            div.textContent = `Error: ${error}`;
            this.progressContainer.appendChild(div);
            div.scrollIntoView({ behavior: 'smooth' });
        }
        
        if (this.statusBadge) {
            this.statusBadge.textContent = 'Failed';
            this.statusBadge.classList.remove('bg-info', 'bg-success', 'bg-warning', 'badge-animated');
            this.statusBadge.classList.add('bg-danger');
        }
    }

    handleCancellation() {
        this.updateProgress('Research task has been cancelled.');
        if (this.cancelButton) {
            this.cancelButton.remove();
        }
        if (this.statusBadge) {
            this.statusBadge.textContent = 'Cancelled';
            this.statusBadge.classList.remove('bg-info', 'bg-success', 'bg-danger', 'badge-animated');
            this.statusBadge.classList.add('bg-warning');
        }
    }
} 