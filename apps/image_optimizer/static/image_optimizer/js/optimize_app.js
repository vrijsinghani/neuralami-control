import { ImageOptimizationWebSocket } from './services/websocket.js';

class OptimizeApp {
    constructor() {
        this.sockets = {};
        this.completedOptimizations = new Set();
        this.isCompleted = false;
        this.setupUI();
        this.setupDropzone();
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
        this.totalFiles = 0;
        this.currentJobId = null;
    }

    setupDropzone() {
        console.log('Setting up Dropzone...');
        const form = document.getElementById('imageDropzone');
        const uploadUrl = form.getAttribute('action');
        console.log('Upload URL:', uploadUrl);
        
        this.dropzone = new Dropzone("#imageDropzone", {
            url: uploadUrl,
            paramName: "file",
            maxFilesize: 50,
            acceptedFiles: "image/*",
            addRemoveLinks: true,
            createImageThumbnails: true,
            autoProcessQueue: false,
            parallelUploads: 4,
            uploadMultiple: false,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            init: function() {
                // Store dropzone instance for later use
                const dropzone = this;
                
                // Handle the queue completion
                this.on("queuecomplete", function() {
                    console.log("All files have been uploaded.");
                });
                
                // Handle when a file is added to the queue
                this.on("addedfile", function(file) {
                    console.log("File added to queue:", file.name);
                });
                
                // Handle when the upload starts
                this.on("sending", function(file, xhr, formData) {
                    console.log("Starting upload for:", file.name);
                });
            }
        });

        this.dropzone.on("addedfile", (file) => {
            console.log('File added:', file.name);
            if (this.totalFiles === 0) {
                this.elements.previewContainer.classList.remove('d-none');
            }
            
            const previewId = `preview-${file.upload.uuid}`;
            const previewHtml = `
                <div id="${previewId}" class="preview-grid ${this.totalFiles === 0 ? 'active' : ''}">
                    <div class="preview-item">
                        <h6>${file.name}</h6>
                        <div class="image-comparison">
                            <div class="image-box">
                                <h6>Original</h6>
                                <img src="${URL.createObjectURL(file)}" alt="Original ${file.name}">
                                <p>${this.formatBytes(file.size)}</p>
                            </div>
                            <div class="image-box">
                                <h6>Optimized</h6>
                                <img src="${window.PLACEHOLDER_IMAGE_URL}" 
                                     alt="Optimized ${file.name}" 
                                     class="optimized-preview"
                                     style="opacity: 0.2;">
                                <p class="optimized-size">Pending</p>
                            </div>
                        </div>
                        <div class="status pending">Pending Optimization</div>
                    </div>
                </div>
            `;
            this.elements.previewGrid.insertAdjacentHTML('beforeend', previewHtml);
            this.totalFiles++;
            this.updatePreviewNavigation();
        });

        this.dropzone.on("sending", (file, xhr, formData) => {
            console.log('Sending file:', file.name);
            const quality = Math.round(this.elements.qualitySlider.noUiSlider.get());
            const maxWidth = this.elements.maxWidth.value || '';
            const maxHeight = this.elements.maxHeight.value || '';
            
            formData.append("quality", quality);
            formData.append("max_width", maxWidth);
            formData.append("max_height", maxHeight);
            if (this.currentJobId) {
                formData.append("job_id", this.currentJobId);
            }
            
            console.log('Form data:', {
                quality: quality,
                max_width: maxWidth,
                max_height: maxHeight,
                job_id: this.currentJobId
            });
            
            const previewItem = document.getElementById(`preview-${file.upload.uuid}`);
            previewItem.querySelector('.status').textContent = 'Processing...';
        });

        this.dropzone.on("success", (file, response) => {
            console.log('Upload success:', file.name, response);
            if (response.success) {
                if (!this.currentJobId && response.job_id) {
                    this.currentJobId = response.job_id;
                }

                const previewItem = document.getElementById(`preview-${file.upload.uuid}`);
                previewItem.setAttribute('data-optimization-id', response.optimization_id);
                this.connectWebSocket(response.optimization_id);
            }
        });

        this.dropzone.on("error", (file, errorMessage, xhr) => {
            console.error('Upload error:', {
                file: file.name,
                error: errorMessage,
                xhr: xhr ? xhr.status : 'No XHR'
            });
            
            const previewItem = document.getElementById(`preview-${file.upload.uuid}`);
            const status = previewItem.querySelector('.status');
            status.textContent = 'Failed';
            status.classList.remove('pending');
            status.classList.add('failed');
            
            const optimizedSize = previewItem.querySelector('.optimized-size');
            optimizedSize.textContent = 'Error';
            
            let message = errorMessage;
            if (typeof errorMessage === 'object' && errorMessage.message) {
                message = errorMessage.message;
            }
            
            Swal.fire({
                icon: 'error',
                title: 'Optimization Failed',
                text: message,
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 3000
            });
        });

        this.dropzone.on("queuecomplete", () => {
            console.log('Queue complete');
        });
    }

    setupEventListeners() {
        this.elements.prevButton.addEventListener('click', () => this.navigatePreview('prev'));
        this.elements.nextButton.addEventListener('click', () => this.navigatePreview('next'));
        
        // Add optimize button handler
        this.elements.optimizeBtn.addEventListener('click', () => {
            console.log('Optimize button clicked');  // Debug log
            const queuedFiles = this.dropzone.getQueuedFiles();
            console.log('Queued files:', queuedFiles.length);
            
            if (queuedFiles.length > 0) {
                this.totalFiles = queuedFiles.length;
                this.currentJobId = null;
                
                Swal.fire({
                    title: 'Optimizing Images',
                    html: `
                        <div class="text-center">
                            <p class="mb-2">Processing image 1 of ${this.totalFiles}</p>
                            <div class="progress">
                                <div class="progress-bar bg-gradient-primary" role="progressbar" style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                            </div>
                        </div>
                    `,
                    allowOutsideClick: false,
                    showConfirmButton: false
                });
                
                console.log('Processing queue...');
                this.dropzone.processQueue();
            } else {
                Swal.fire({
                    icon: 'warning',
                    title: 'No Files',
                    text: 'Please add some files to optimize first.'
                });
            }
        });
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
        const previewItem = document.querySelector(`[data-optimization-id="${data.optimization_id}"]`);
        if (!previewItem) return;

        const statusElement = previewItem.querySelector('.status');
        const optimizedPreview = previewItem.querySelector('.optimized-preview');
        const optimizedSize = previewItem.querySelector('.optimized-size');

        switch (data.status) {
            case 'processing':
                statusElement.textContent = 'Processing...';
                statusElement.className = 'status pending';
                break;
            case 'completed':
                statusElement.textContent = 'Optimization Complete';
                statusElement.className = 'status completed';
                
                // Force image reload by adding timestamp
                const imageUrl = new URL(data.download_url, window.location.origin);
                imageUrl.searchParams.set('t', Date.now());
                
                // Create a new image object to ensure it loads
                const img = new Image();
                img.onload = () => {
                    optimizedPreview.src = img.src;
                    optimizedPreview.style.opacity = '1';
                };
                img.src = imageUrl.toString();
                
                optimizedSize.textContent = this.formatBytes(data.optimized_size);
                
                // Add to DataTable with proper data
                this.addOptimizationToTable({
                    file_name: data.file_name,
                    original_size: data.original_size,
                    optimized_size: data.optimized_size,
                    reduction: data.reduction,
                    download_url: data.download_url
                });

                // Track completed optimizations
                this.completedOptimizations.add(data.optimization_id);
                
                break;
            case 'failed':
                statusElement.textContent = 'Optimization Failed';
                statusElement.className = 'status failed';
                optimizedSize.textContent = 'Failed';
                
                // Also track failed ones as completed
                this.completedOptimizations.add(data.optimization_id);
                
                Swal.fire({
                    icon: 'error',
                    title: 'Optimization Failed',
                    text: data.error || 'An error occurred during optimization',
                    toast: true,
                    position: 'top-end',
                    showConfirmButton: false,
                    timer: 3000
                });
                break;
        }

        // Check if all optimizations are complete
        if (this.completedOptimizations.size === this.totalFiles) {
            this.handleAllOptimizationsComplete();
        }
    }

    handleJobUpdate(data) {
        if (!this.currentJobId || data.job_id !== this.currentJobId) return;

        const progress = (data.completed_count / this.totalFiles) * 100;
        const swalContent = document.querySelector('.swal2-html-container');
        
        if (swalContent) {
            swalContent.innerHTML = `
                <div class="text-center">
                    <p class="mb-2">Processing image ${data.completed_count} of ${this.totalFiles}</p>
                    <div class="progress">
                        <div class="progress-bar bg-gradient-primary" role="progressbar" 
                             style="width: ${progress}%" 
                             aria-valuenow="${progress}" 
                             aria-valuemin="0" 
                             aria-valuemax="100">
                        </div>
                    </div>
                </div>
            `;
        }

        // If job is complete and we've received all optimization updates
        if (data.status === 'completed' && data.completed_count === this.totalFiles) {
            // Check if we've received all individual optimization updates
            if (this.completedOptimizations.size === this.totalFiles) {
                this.handleAllOptimizationsComplete();
            } else {
                // Set a timeout to force completion if we don't receive all updates
                setTimeout(() => {
                    if (!this.isCompleted) {
                        this.handleAllOptimizationsComplete();
                    }
                }, 2000); // Wait 2 seconds for any remaining updates
            }
        }
    }

    handleAllOptimizationsComplete() {
        if (this.isCompleted) return; // Prevent multiple completions
        this.isCompleted = true;

        // Clean up WebSocket connections
        Object.values(this.sockets).forEach(socket => socket.disconnect());
        this.sockets = {};
        this.currentJobId = null;
        this.completedOptimizations.clear();

        Swal.fire({
            icon: 'success',
            title: 'Optimization Complete',
            text: `Successfully processed ${this.totalFiles} images`,
            timer: 3000,
            showConfirmButton: false
        });
    }

    navigatePreview(direction) {
        const previews = document.querySelectorAll('.preview-grid');
        previews[this.currentPreviewIndex].classList.remove('active');
        
        if (direction === 'next') {
            this.currentPreviewIndex = (this.currentPreviewIndex + 1) % this.totalFiles;
        } else {
            this.currentPreviewIndex = (this.currentPreviewIndex - 1 + this.totalFiles) % this.totalFiles;
        }
        
        previews[this.currentPreviewIndex].classList.add('active');
        this.updatePreviewNavigation();
    }

    updatePreviewNavigation() {
        this.elements.prevButton.disabled = this.totalFiles <= 1;
        this.elements.nextButton.disabled = this.totalFiles <= 1;
        this.elements.paginationText.textContent = `Image ${this.currentPreviewIndex + 1} of ${this.totalFiles}`;
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
        // Create a new row with proper formatting
        const newRow = [
            `<span class="text-sm">${optimization.file_name}</span>`,
            `<span class="text-sm">${this.formatBytes(optimization.original_size)}</span>`,
            `<span class="text-sm">${this.formatBytes(optimization.optimized_size)}</span>`,
            `<span class="text-sm">${optimization.reduction}%</span>`,
            `<span class="badge badge-sm bg-gradient-success">Completed</span>`,
            `<a href="${optimization.download_url}" class="btn btn-link text-secondary mb-0" download>
                <i class="fa fa-download text-xs"></i> Download
            </a>`
        ];
        
        // Insert at the beginning of the table
        this.dataTable.insert({data: [newRow], index: 0});
        
        // Force refresh to ensure proper rendering
        this.dataTable.refresh();
    }
}

export { OptimizeApp }; 