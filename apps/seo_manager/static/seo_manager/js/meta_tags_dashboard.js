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

function viewSnapshot(filename) {
    fetch(`/file-manager/file/${encodeURIComponent(filename)}`)
        .then(response => response.json())
        .then(data => {
            // Format and display the data in the modal
            const formattedHtml = formatMetaTagsReport(data);
            document.getElementById('metaTagsReport').innerHTML = formattedHtml;
            
            // Show the modal
            const modal = new bootstrap.Modal(document.getElementById('viewMetaTagsModal'));
            modal.show();
        })
        .catch(error => {
            console.error('Error:', error);
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: 'Failed to load snapshot data'
            });
        });
}

function compareWithPrevious(filename) {
    // Get the list of all snapshots
    const snapshotRows = document.querySelectorAll('#snapshots-table tbody tr');
    let currentIndex = -1;
    let snapshots = [];
    
    snapshotRows.forEach((row, index) => {
        const rowFilename = row.querySelector('.text-sm').textContent;
        snapshots.push(rowFilename);
        if (rowFilename === filename) {
            currentIndex = index;
        }
    });

    // If this is the first snapshot, we can't compare
    if (currentIndex === snapshots.length - 1) {
        Swal.fire({
            icon: 'info',
            title: 'No Previous Snapshot',
            text: 'This is the oldest snapshot, no comparison available.'
        });
        return;
    }

    const previousFilename = snapshots[currentIndex + 1];

    // Fetch both snapshots and compare
    Promise.all([
        fetch(`/file-manager/meta-tags/${filename}`).then(r => r.json()),
        fetch(`/file-manager/meta-tags/${previousFilename}`).then(r => r.json())
    ])
    .then(([current, previous]) => {
        const comparisonHtml = generateComparisonReport(current, previous);
        document.getElementById('metaTagsReport').innerHTML = comparisonHtml;
        
        const modal = new bootstrap.Modal(document.getElementById('viewMetaTagsModal'));
        modal.show();
    })
    .catch(error => {
        console.error('Error:', error);
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'Failed to load comparison data'
        });
    });
}

function formatMetaTagsReport(data) {
    // Format the meta tags data into HTML
    let html = '<div class="table-responsive">';
    html += '<table class="table table-hover">';
    html += '<thead><tr><th>Page URL</th><th>Meta Tags</th><th>Issues</th></tr></thead>';
    html += '<tbody>';
    
    data.pages.forEach(page => {
        html += `<tr>
            <td><a href="${page.url}" target="_blank">${page.url}</a></td>
            <td>
                <ul class="list-unstyled mb-0">
                    ${page.meta_tags.map(tag => `
                        <li class="mb-1">
                            <code>${tag.name || tag.property}: ${tag.content}</code>
                        </li>
                    `).join('')}
                </ul>
            </td>
            <td>
                ${page.meta_tags.some(tag => tag.issues) 
                    ? '<span class="badge bg-warning">Issues Found</span>' 
                    : '<span class="badge bg-success">OK</span>'}
            </td>
        </tr>`;
    });
    
    html += '</tbody></table></div>';
    return html;
}

function generateComparisonReport(current, previous) {
    // Generate a comparison report between two snapshots
    let html = '<div class="comparison-report">';
    html += '<h5>Changes Since Last Snapshot</h5>';
    
    // Compare and show differences
    const changes = compareSnapshots(current, previous);
    
    if (changes.length === 0) {
        html += '<p class="text-muted">No changes detected</p>';
    } else {
        html += '<div class="table-responsive">';
        html += '<table class="table">';
        html += '<thead><tr><th>Page</th><th>Change Type</th><th>Details</th></tr></thead>';
        html += '<tbody>';
        
        changes.forEach(change => {
            html += `<tr>
                <td>${change.page}</td>
                <td><span class="badge bg-${change.type === 'added' ? 'success' : change.type === 'removed' ? 'danger' : 'warning'}">${change.type}</span></td>
                <td>${change.details}</td>
            </tr>`;
        });
        
        html += '</tbody></table></div>';
    }
    
    html += '</div>';
    return html;
}

function compareSnapshots(current, previous) {
    const changes = [];
    
    // Compare pages and their meta tags
    current.pages.forEach(currentPage => {
        const previousPage = previous.pages.find(p => p.url === currentPage.url);
        
        if (!previousPage) {
            changes.push({
                page: currentPage.url,
                type: 'added',
                details: 'New page added'
            });
            return;
        }
        
        // Compare meta tags
        currentPage.meta_tags.forEach(currentTag => {
            const previousTag = previousPage.meta_tags.find(t => 
                (t.name === currentTag.name && t.property === currentTag.property)
            );
            
            if (!previousTag) {
                changes.push({
                    page: currentPage.url,
                    type: 'added',
                    details: `Added tag: ${currentTag.name || currentTag.property}`
                });
            } else if (previousTag.content !== currentTag.content) {
                changes.push({
                    page: currentPage.url,
                    type: 'modified',
                    details: `Changed ${currentTag.name || currentTag.property} from "${previousTag.content}" to "${currentTag.content}"`
                });
            }
        });
    });
    
    // Check for removed pages
    previous.pages.forEach(previousPage => {
        if (!current.pages.find(p => p.url === previousPage.url)) {
            changes.push({
                page: previousPage.url,
                type: 'removed',
                details: 'Page removed'
            });
        }
    });
    
    return changes;
} 