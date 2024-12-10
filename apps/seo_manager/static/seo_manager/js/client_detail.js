document.addEventListener('DOMContentLoaded', function() {
    const { clientId, urls, keywords } = window.clientData;

    // Initialize keyword charts
    keywords.forEach(keyword => {
        initializeKeywordChart(keyword);
    });

    // Collect Rankings Button
    document.getElementById('collectRankingsBtn')?.addEventListener('click', function() {
        Swal.fire({
            title: 'Collecting Rankings Data',
            text: 'This may take a few minutes...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading()
            }
        });

        fetch(urls.collectRankings, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    text: data.message
                }).then(() => {
                    window.location.reload();
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.error
                });
            }
        });
    });

    // Generate Report Button
    document.getElementById('generateReportBtn')?.addEventListener('click', function() {
        Swal.fire({
            title: 'Generating Report',
            text: 'Please wait...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading()
            }
        });

        fetch(urls.generateReport, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('reportContent').innerHTML = data.report_html;
                var reportModal = new bootstrap.Modal(document.getElementById('reportModal'));
                Swal.close();
                reportModal.show();
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.error
                });
            }
        });
    });

    // Backfill Rankings Button
    document.getElementById('backfillRankingsBtn')?.addEventListener('click', function() {
        Swal.fire({
            title: 'Backfill Historical Data',
            text: 'This will collect ranking data for the past 12 months. This may take several minutes. Continue?',
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Yes, proceed',
            cancelButtonText: 'No, cancel'
        }).then((result) => {
            if (result.isConfirmed) {
                handleBackfillRankings();
            }
        });
    });

    // Magically Fill In Button
    document.getElementById('magicallyFillBtn')?.addEventListener('click', handleMagicFill);

    // Initialize Quill editors
    initializeQuillEditors();

    // Delete Client Button
    document.getElementById('deleteClientBtn')?.addEventListener('click', handleDeleteClient);

    // View switching functionality
    initializeViewSwitching();

    // Activity Timeline Filtering
    initializeActivityFiltering();

    // Initialize DataTables
    initializeDataTables();

    // Initialize Search Console import functionality
    initializeSearchConsoleImport();

    // Initialize Create Snapshot button
    initializeCreateSnapshot();
});

// Helper Functions

function initializeKeywordChart(keyword) {
    const modalId = `view-history-${keyword.id}`;
    const canvasId = `keyword-chart-${keyword.id}`;
    const modal = document.getElementById(modalId);
    let currentChart = null;

    if (!modal) return;

    function recreateCanvas(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return null;
        
        const oldCanvas = document.getElementById(canvasId);
        if (oldCanvas) {
            oldCanvas.remove();
        }
        
        const newCanvas = document.createElement('canvas');
        newCanvas.id = canvasId;
        container.appendChild(newCanvas);
        return newCanvas;
    }

    function destroyChart() {
        if (currentChart) {
            currentChart.destroy();
            currentChart = null;
        }
        Chart.helpers.each(Chart.instances, function(instance) {
            if (instance.canvas.id === canvasId) {
                instance.destroy();
            }
        });
    }

    modal.addEventListener('show.bs.modal', function() {
        destroyChart();
        
        const canvas = recreateCanvas(`chart-container-${keyword.id}`);
        if (!canvas) return;

        setTimeout(() => {
            currentChart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: keyword.history.map(entry => entry.date).reverse(),
                    datasets: [{
                        label: 'Position',
                        data: keyword.history.map(entry => entry.position).reverse(),
                        borderColor: '#5e72e4',
                        backgroundColor: 'rgba(94, 114, 228, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            reverse: true,
                            beginAtZero: false
                        }
                    }
                }
            });
        }, 0);
    });

    modal.addEventListener('hidden.bs.modal', destroyChart);
    window.addEventListener('unload', destroyChart);
}

function handleBackfillRankings() {
    const { urls } = window.clientData;

    Swal.fire({
        title: 'Collecting Historical Data',
        text: 'This may take several minutes...',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading()
        }
    });

    fetch(urls.backfillRankings, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Success!',
                text: data.message
            }).then(() => {
                window.location.reload();
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: data.error
            });
        }
    })
    .catch(error => {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'An error occurred while collecting historical data.'
        });
    });
}

function handleMagicFill() {
    const { urls } = window.clientData;
    
    const swalInstance = Swal.fire({
        title: 'Generating Client Profile',
        html: 'This may take a few minutes...',
        timerProgressBar: true,
        allowOutsideClick: false,
        showCancelButton: true,
        cancelButtonText: 'Cancel',
        didOpen: () => {
            Swal.showLoading();
        }
    });

    const controller = new AbortController();
    const signal = controller.signal;

    fetch(urls.generateMagicProfile, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        signal: signal
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            pollTaskStatus(data.task_id);
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: data.error || 'Failed to start profile generation'
            });
        }
    })
    .catch(error => {
        if (error.name === 'AbortError') return;
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'Failed to generate profile'
        });
    });

    swalInstance.then((result) => {
        if (result.dismiss === Swal.DismissReason.cancel) {
            controller.abort();
            Swal.fire({
                icon: 'info',
                title: 'Cancelled',
                text: 'Profile generation was cancelled'
            });
        }
    });
}

function pollTaskStatus(taskId) {
    const { urls } = window.clientData;
    const toolStatusUrl = urls.getToolStatus.replace('TASK_ID', taskId);
    
    const pollInterval = setInterval(() => {
        fetch(toolStatusUrl)
            .then(response => response.json())
            .then(statusData => {
                if (statusData.status === 'SUCCESS') {
                    clearInterval(pollInterval);
                    Swal.fire({
                        icon: 'success',
                        title: 'Success!',
                        text: 'Profile generated successfully'
                    }).then(() => {
                        window.location.reload();
                    });
                } else if (statusData.status === 'FAILURE') {
                    clearInterval(pollInterval);
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: statusData.error || 'Failed to generate profile'
                    });
                }
            })
            .catch(error => {
                clearInterval(pollInterval);
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: 'Failed to check task status'
                });
            });
    }, 2000);
}

function initializeQuillEditors() {
    const toolbarOptions = [
        ['bold', 'italic', 'underline', 'strike'],
        ['blockquote', 'code-block'],
        [{ 'header': 1 }, { 'header': 2 }],
        [{ 'list': 'ordered'}, { 'list': 'bullet' }],
        [{ 'script': 'sub'}, { 'script': 'super' }],
        [{ 'indent': '-1'}, { 'indent': '+1' }],
        ['link'],
        ['clean']
    ];

    // Add Profile Editor
    if (document.getElementById('add-profile-editor')) {
        const addProfileEditor = new Quill('#add-profile-editor', {
            theme: 'snow',
            modules: { toolbar: toolbarOptions }
        });

        document.getElementById('addProfileForm')?.addEventListener('submit', function(e) {
            document.getElementById('add-profile-content').value = addProfileEditor.root.innerHTML;
        });
    }

    // Edit Profile Editor
    if (document.getElementById('edit-profile-editor')) {
        const editProfileEditor = new Quill('#edit-profile-editor', {
            theme: 'snow',
            modules: { toolbar: toolbarOptions }
        });

        document.getElementById('editProfileForm')?.addEventListener('submit', function(e) {
            document.getElementById('edit-profile-content').value = editProfileEditor.root.innerHTML;
        });
    }
}

function handleDeleteClient() {
    const { urls } = window.clientData;
    const clientName = this.dataset.clientName;

    Swal.fire({
        title: 'Are you sure?',
        html: `You are about to delete client: <strong>${clientName}</strong><br>This action cannot be undone!`,
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#d33',
        cancelButtonColor: '#3085d6',
        confirmButtonText: 'Yes, delete it!',
        cancelButtonText: 'Cancel'
    }).then((result) => {
        if (result.isConfirmed) {
            deleteClientRequest();
        }
    });
}

function deleteClientRequest() {
    const { urls } = window.clientData;

    Swal.fire({
        title: 'Deleting...',
        html: 'Please wait',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading()
        }
    });

    fetch(urls.deleteClient, {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Deleted!',
                text: 'Client has been deleted successfully.',
                showConfirmButton: false,
                timer: 1500
            }).then(() => {
                window.location.href = urls.clientList;
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: data.error || 'An error occurred while deleting the client.'
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'An error occurred while deleting the client.'
        });
    });
}

function initializeViewSwitching() {
    const listView = document.getElementById('projects-list-view');
    const kanbanView = document.getElementById('projects-kanban-view');
    const listViewBtn = document.getElementById('list-view');
    const kanbanViewBtn = document.getElementById('kanban-view');

    if (!listView || !kanbanView || !listViewBtn || !kanbanViewBtn) return;

    listViewBtn.addEventListener('change', function() {
        if (this.checked) {
            listView.style.display = 'block';
            kanbanView.style.display = 'none';
        }
    });

    kanbanViewBtn.addEventListener('change', function() {
        if (this.checked) {
            listView.style.display = 'none';
            kanbanView.style.display = 'block';
        }
    });
}

function initializeActivityFiltering() {
    const filterLinks = document.querySelectorAll('[data-filter]');
    const timelineBlocks = document.querySelectorAll('.timeline-block');
    
    filterLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            filterLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
            
            const filter = this.dataset.filter;
            
            timelineBlocks.forEach(block => {
                if (filter === 'all' || block.dataset.category === filter) {
                    block.style.display = 'flex';
                    block.style.opacity = '1';
                } else {
                    block.style.display = 'none';
                    block.style.opacity = '0';
                }
            });
        });
    });

    initializeLoadMore();
    initializeExport();
}

function initializeLoadMore() {
    const loadMoreBtn = document.getElementById('loadMoreActivities');
    if (!loadMoreBtn) return;

    let page = 1;
    loadMoreBtn.addEventListener('click', function() {
        const { urls } = window.clientData;
        page++;
        loadMoreBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Loading...';
        
        fetch(`${urls.loadMoreActivities}?page=${page}`)
            .then(response => response.json())
            .then(data => {
                if (data.activities) {
                    const timeline = document.querySelector('.timeline');
                    timeline.insertAdjacentHTML('beforeend', data.activities);
                    
                    if (!data.has_more) {
                        loadMoreBtn.style.display = 'none';
                    }
                }
                loadMoreBtn.innerHTML = '<i class="fas fa-sync me-1"></i>Load More';
            });
    });
}

function initializeExport() {
    const exportBtn = document.getElementById('exportActivityBtn');
    if (!exportBtn) return;

    exportBtn.addEventListener('click', function() {
        const { urls } = window.clientData;
        const filter = document.querySelector('[data-filter].active').dataset.filter;
        window.location.href = `${urls.exportActivities}?filter=${filter}`;
    });
}

function initializeDataTables() {
    if (document.getElementById('projects-table')) {
        new simpleDatatables.DataTable("#projects-table", {
            searchable: true,
            fixedHeight: true,
            perPage: 10
        });
    }

    if (document.getElementById('snapshots-table')) {
        new simpleDatatables.DataTable("#snapshots-table", {
            searchable: true,
            fixedHeight: true,
            perPage: 7
        });
    }
}

// Export functions that need to be globally available
window.updateObjectiveStatus = function(clientId, objectiveIndex, newStatus) {
    fetch(`/seo/clients/${clientId}/objectives/${objectiveIndex}/status/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify({
            status: newStatus
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: 'Success!',
                text: data.message,
                showConfirmButton: false,
                timer: 1500
            }).then(() => {
                window.location.reload();
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: data.error || 'Failed to update status'
            });
        }
    })
    .catch(error => {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'An error occurred while updating the status'
        });
    });
};

function initializeSearchConsoleImport() {
    const selectAllCheckbox = document.getElementById('select-all-keywords');
    const importButton = document.getElementById('import-selected-keywords');
    
    if (!selectAllCheckbox || !importButton) return;

    // Handle "Select All" checkbox
    selectAllCheckbox.addEventListener('change', function() {
        const checkboxes = document.querySelectorAll('.keyword-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.checked = this.checked;
        });
    });

    // Handle Import button click
    importButton.addEventListener('click', function() {
        const selectedKeywords = [];
        const checkboxes = document.querySelectorAll('.keyword-checkbox:checked');
        
        checkboxes.forEach(checkbox => {
            selectedKeywords.push({
                keyword: checkbox.value,
                position: parseFloat(checkbox.dataset.position),
                clicks: parseInt(checkbox.dataset.clicks),
                impressions: parseInt(checkbox.dataset.impressions),
                ctr: parseFloat(checkbox.dataset.ctr)
            });
        });

        if (selectedKeywords.length === 0) {
            Swal.fire({
                icon: 'warning',
                title: 'No Keywords Selected',
                text: 'Please select at least one keyword to import.'
            });
            return;
        }

        // Show loading state
        Swal.fire({
            title: 'Importing Keywords',
            text: 'Please wait...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });

        // Send import request
        fetch(`/seo/clients/${window.clientData.clientId}/keywords/import-from-search-console/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify(selectedKeywords)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    text: data.message
                }).then(() => {
                    window.location.reload();
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.error || 'Failed to import keywords'
                });
            }
        })
        .catch(error => {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: 'An error occurred while importing keywords'
            });
        });
    });
}

function initializeCreateSnapshot() {
    const createSnapshotBtn = document.getElementById('createSnapshotBtn');
    if (!createSnapshotBtn) return;

    createSnapshotBtn.addEventListener('click', function() {
        const { clientId } = window.clientData;

        Swal.fire({
            title: 'Creating Meta Tags Snapshot',
            text: 'This may take a few moments...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading()
            }
        });

        fetch(`/seo/clients/${clientId}/meta-tags/snapshot/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Success!',
                    text: data.message,
                    showConfirmButton: true
                }).then(() => {
                    window.location.reload();
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.message || 'Failed to create meta tags snapshot'
                });
            }
        })
        .catch(error => {
            console.error('Error:', error);
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: 'An error occurred while creating the snapshot.'
            });
        });
    });
}