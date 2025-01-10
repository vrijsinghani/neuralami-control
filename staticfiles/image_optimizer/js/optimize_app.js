import { ImageOptimizationWebSocket } from './services/websocket.js';

class OptimizeApp {
    constructor() {
        this.sockets = {};
        this.setupUI();
        this.setupEventListeners();
    }

    setupUI() {
        this.elements = {
            previewGrid: document.getElementById('previewGrid'),
            previewContainer: document.getElementById('previewContainer'),
            prevButton: document.getElementById('prevImage'),
            nextButton: document.getElementById('nextImage'),
            paginationText: document.getElementById('paginationText'),
            optimizeBtn: document.getElementById('optimizeBtn'),
            qualitySlider: document.getElementById('qualitySlider'),
            maxWidth: document.getElementById('maxWidth'),
            maxHeight: document.getElementById('maxHeight')
        };
        this.currentPreviewIndex = 0;
    }

    setupEventListeners() {
        this.elements.prevButton.addEventListener('click', () => this.navigatePreview('prev'));
        this.elements.nextButton.addEventListener('click', () => this.navigatePreview('next'));
    }

    connectWebSocket(optimizationId) {
        if (this.sockets[optimizationId]) {
            console.log('WebSocket already exists for:', optimizationId);
            return;
        }

        const socket = new ImageOptimizationWebSocket(optimizationId);

        socket.on('connectionStatus', (status) => {
            console.log('WebSocket status:', status);
            this.updateConnectionUI(status, optimizationId);
        });

        socket.on('optimizationUpdate', (data) => {
            this.handleOptimizationUpdate(data);
        });

        socket.on('jobUpdate', (data) => {
            this.handleJobUpdate(data);
        });

        socket.on('error', (error) => {
            console.error('WebSocket error:', error);
            Swal.fire({
                icon: 'error',
                title: 'Connection Error',
                text: error.message,
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000
            });
        });

        socket.connect();
        this.sockets[optimizationId] = socket;
    }

    updateConnectionUI(status, optimizationId) {
        const previewItem = document.querySelector(`[data-optimization-id="${optimizationId}"]`);
        if (!previewItem) return;

        const statusElement = previewItem.querySelector('.status');
        switch (status) {
            case 'connected':
                statusElement.textContent = 'Connected';
                break;
            case 'disconnected':
                statusElement.textContent = 'Disconnected';
                break;
            case 'connecting':
                statusElement.textContent = 'Connecting...';
                break;
            case 'error':
                statusElement.textContent = 'Connection Error';
                break;
        }
    }

    handleOptimizationUpdate(data) {
        if (!data.optimization_id) return;

        const previewItem = document.querySelector(`[data-optimization-id="${data.optimization_id}"]`);
        if (!previewItem) return;

        const optimizedPreview = previewItem.querySelector('.optimized-preview');
        const optimizedSize = previewItem.querySelector('.optimized-size');
        const status = previewItem.querySelector('.status');

        if (data.status === 'completed') {
            optimizedPreview.src = data.download_url;
            optimizedPreview.style.opacity = '1';
            optimizedSize.textContent = `${this.formatBytes(data.optimized_size)} (${data.reduction}% smaller)`;
            status.textContent = 'Completed';
            status.classList.remove('pending');
            status.classList.add('completed');

            this.addOptimizationToTable(data);
            this.closeSocket(data.optimization_id);
        } else if (data.status === 'failed') {
            status.textContent = 'Failed';
            status.classList.remove('pending');
            status.classList.add('failed');
            optimizedSize.textContent = 'Error: ' + data.message;

            Swal.fire({
                icon: 'error',
                title: 'Optimization Failed',
                text: data.message,
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000
            });
        }
    }

    handleJobUpdate(data) {
        if (!data.job_id || data.processed_files === undefined) return;

        const progress = (data.processed_files / data.total_files) * 100;
        Swal.update({
            html: `
                <div class="text-center">
                    <p class="mb-2">Processing image ${data.processed_files} of ${data.total_files}</p>
                    <div class="progress">
                        <div class="progress-bar bg-gradient-primary" role="progressbar" style="width: ${progress}%" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100"></div>
                    </div>
                </div>
            `
        });

        if (data.status === 'completed' && data.processed_files === data.total_files) {
            Swal.fire({
                icon: 'success',
                title: 'All Images Optimized!',
                html: `
                    <p>Successfully processed ${data.processed_files} images</p>
                    <p class="text-sm">Total reduction: ${data.total_reduction}%</p>
                `
            });
        }
    }

    navigatePreview(direction) {
        const previews = document.querySelectorAll('.preview-grid');
        if (direction === 'prev' && this.currentPreviewIndex > 0) {
            this.currentPreviewIndex--;
        } else if (direction === 'next' && this.currentPreviewIndex < previews.length - 1) {
            this.currentPreviewIndex++;
        }
        this.updatePreviewNavigation();
    }

    updatePreviewNavigation() {
        const previews = document.querySelectorAll('.preview-grid');
        this.elements.prevButton.disabled = this.currentPreviewIndex === 0;
        this.elements.nextButton.disabled = this.currentPreviewIndex === previews.length - 1;
        this.elements.paginationText.textContent = `Image ${this.currentPreviewIndex + 1} of ${previews.length}`;
        
        previews.forEach((preview, index) => {
            preview.classList.toggle('active', index === this.currentPreviewIndex);
        });
    }

    closeSocket(optimizationId) {
        if (this.sockets[optimizationId]) {
            this.sockets[optimizationId].disconnect();
            delete this.sockets[optimizationId];
        }
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    addOptimizationToTable(optimization) {
        const newRow = [
            optimization.file_name,
            this.formatBytes(optimization.original_size),
            this.formatBytes(optimization.optimized_size),
            `${optimization.reduction}%`,
            'Completed',
            `<a href="${optimization.download_url}" class="btn btn-link text-secondary mb-0" download>
                <i class="fa fa-download text-xs"></i> Download
            </a>`
        ];
        window.dataTable.insert({data: [newRow]});
    }
}

export { OptimizeApp }; 