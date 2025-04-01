document.addEventListener('DOMContentLoaded', function() {
    initializeCreateSnapshot();
    initializeUrlInput();
    initializeDataTables();
});

function initializeCreateSnapshot() {
    const createSnapshotBtn = document.getElementById('createSnapshotBtn');
    if (!createSnapshotBtn) return;

    createSnapshotBtn.addEventListener('click', function() {
        const clientId = this.dataset.clientId;

        Swal.fire({
            title: 'Creating Meta Tags Snapshot',
            text: 'This will start a background process to extract meta tags.',
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'Start Extraction',
            cancelButtonText: 'Cancel',
            confirmButtonColor: '#3085d6',
            cancelButtonColor: '#d33'
        }).then((result) => {
            if (result.isConfirmed) {
                Swal.fire({
                    title: 'Starting Extraction',
                    text: 'Initializing the meta tags extraction process...',
                    allowOutsideClick: false,
                    didOpen: () => {
                        Swal.showLoading();
                    }
                });

                fetch(`/seo/clients/${clientId}/meta-tags/snapshot/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        Swal.close();
                        if (data.redirect_url) {
                            window.location.href = data.redirect_url;
                        } else if (data.task_id) {
                            // Connect to WebSocket if we have a task_id
                            connectWebSocket(data.task_id);
                        }
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
            }
        });
    });
}

function initializeUrlInput() {
    // Button click handler to show the URL input modal
    const createFromUrlBtn = document.getElementById('createFromUrlBtn');
    if (!createFromUrlBtn) return;

    createFromUrlBtn.addEventListener('click', function() {
        const urlInputModal = new bootstrap.Modal(document.getElementById('urlInputModal'));
        urlInputModal.show();
    });

    // URL submission handler
    const confirmUrlBtn = document.getElementById('confirmUrlBtn');
    if (!confirmUrlBtn) return;

    confirmUrlBtn.addEventListener('click', function() {
        const url = document.getElementById('urlInput').value.trim();
        
        if (!url) {
            Swal.fire({
                icon: 'warning',
                title: 'URL Required',
                text: 'Please enter a valid URL'
            });
            return;
        }

        // Hide the modal
        bootstrap.Modal.getInstance(document.getElementById('urlInputModal')).hide();

        // Show loading state
        Swal.fire({
            title: 'Starting Extraction',
            text: 'Initializing the meta tags extraction process...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });

        // Submit the URL
        fetch('/seo/meta-tags/snapshot-url/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: url })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.close();
                if (data.task_id) {
                    // Connect to WebSocket to track progress
                    connectWebSocket(data.task_id);
                }
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.message || 'Failed to start meta tags extraction'
                });
            }
        })
        .catch(error => {
            console.error('Error:', error);
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: 'An error occurred while starting the extraction.'
            });
        });
    });
}

function initializeDataTables() {
    if (document.getElementById('snapshots-table')) {
        new simpleDatatables.DataTable("#snapshots-table", {
            searchable: true,
            fixedHeight: true,
            perPage: 7
        });
    }
}
