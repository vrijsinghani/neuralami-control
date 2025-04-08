/**
 * Minimal JavaScript functions for the crawl.html template
 * These functions are kept to a minimum to maximize HTMX usage
 */

// Function to update UI when crawl is cancelled
function updateUIForCancelledCrawl() {
    // Hide the progress spinner
    const spinner = document.getElementById('progress-spinner');
    if (spinner) spinner.style.display = 'none';

    // Update the status title
    const statusTitle = document.getElementById('crawling-status-title');
    if (statusTitle) statusTitle.textContent = 'Crawl Cancelled';

    // Hide the cancel button
    const cancelButton = document.getElementById('cancel-crawl-btn');
    if (cancelButton) cancelButton.style.display = 'none';

    // Show a notification
    if (typeof Swal !== 'undefined') {
        Swal.fire({
            title: 'Crawl Cancelled',
            text: 'The crawl has been cancelled successfully.',
            icon: 'warning',
            confirmButtonText: 'OK'
        });
    }
}

// Function to toggle advanced options
function toggleAdvancedOptions() {
    const advancedOptions = document.getElementById('advanced-options');
    const button = document.getElementById('toggle-advanced-options');

    if (advancedOptions && button) {
        // Toggle the d-none class
        advancedOptions.classList.toggle('d-none');

        // Update button text
        if (advancedOptions.classList.contains('d-none')) {
            button.innerHTML = '<i class="fas fa-cog me-1"></i> Show Advanced Options';
        } else {
            button.innerHTML = '<i class="fas fa-times me-1"></i> Hide Advanced Options';
        }
    }
}

// No longer needed - we'll rely on HTMX OOB swaps and template logic

// Function to attach to an existing crawl
function attachToCrawl(taskId, url) {
    if (!taskId) return;

    // Show progress section
    document.getElementById('crawling-progress-section').style.display = 'block';

    // Update the crawling status title
    const statusTitle = document.getElementById('crawling-status-title');
    if (statusTitle) statusTitle.textContent = `Crawling in Progress: ${url}`;

    // Reset stats cards
    const pagesVisitedElement = document.getElementById('pages-visited-count');
    const linksFoundElement = document.getElementById('links-found-count');
    const currentUrlElement = document.getElementById('current-page-url');

    if (pagesVisitedElement) pagesVisitedElement.textContent = '0';
    if (linksFoundElement) linksFoundElement.textContent = '0';
    if (currentUrlElement) currentUrlElement.textContent = 'Connecting...';

    // Set up WebSocket connection
    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsPath = `${wsScheme}://${window.location.host}/ws/crawl/${taskId}/`;

    // Set the WebSocket connection attribute
    const container = document.getElementById('crawl-container');
    container.setAttribute('ws-connect', wsPath);
    container.setAttribute('data-task-id', taskId);

    // Process the container to connect WebSocket
    htmx.process(container);

    // Show notification
    Swal.fire({
        title: 'Connected',
        text: 'Connected to crawl',
        icon: 'info',
        toast: true,
        position: 'top-end',
        showConfirmButton: false,
        timer: 3000,
        timerProgressBar: true
    });
}

// Function to cancel a crawl task
function cancelCrawl() {
    // Get the task ID from the crawl container
    const taskId = document.getElementById('crawl-container').getAttribute('data-task-id');

    if (!taskId) {
        console.error('No task ID found');
        return;
    }

    console.log('Stop button clicked, task ID: ' + taskId);

    // Get the CSRF token
    const csrfToken = document.querySelector('input[name=csrfmiddlewaretoken]').value;

    // Send the cancel request
    fetch('/crawl_website/cancel_crawl/' + taskId + '/', {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken}
    })
    .then(response => {
        if (response.ok) {
            console.log('Crawl cancelled successfully');
            updateUIForCancelledCrawl();

            // Close the WebSocket connection
            const container = document.getElementById('crawl-container');
            if (container) {
                htmx.trigger(container, 'htmx:wsClose');
                // Remove the ws-connect attribute to prevent automatic reconnection
                container.removeAttribute('ws-connect');
            }
        } else {
            console.error('Failed to cancel crawl:', response.status);
        }
    })
    .catch(error => {
        console.error('Error cancelling crawl:', error);
    });
}

// Initialize tooltips when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    tooltipTriggerList.forEach(function (tooltipTriggerEl) {
        new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Add WebSocket event listeners for debugging
    htmx.on('htmx:wsOpen', function(evt) {
        console.log('WebSocket connected:', evt);
    });

    htmx.on('htmx:wsClose', function(evt) {
        console.log('WebSocket closed:', evt);
    });

    htmx.on('htmx:wsError', function(evt) {
        console.error('WebSocket error:', evt);
    });
});

// Function to update UI when crawl is cancelled
function updateUIForCancelledCrawl() {
    // Hide the progress spinner
    const spinner = document.getElementById('progress-spinner');
    if (spinner) spinner.style.display = 'none';

    // Update the status title
    const statusTitle = document.getElementById('crawling-status-title');
    if (statusTitle) statusTitle.textContent = 'Crawl Cancelled';

    // Hide the cancel button
    const cancelButton = document.getElementById('cancel-crawl-btn');
    if (cancelButton) cancelButton.style.display = 'none';
}

// Handle crawl completion event - only for notifications
htmx.on('htmx:wsMessage', function(evt) {
    try {
        // Try to parse as JSON
        const data = JSON.parse(evt.detail.message);

        // Only handle event messages for notifications
        if (data && data.type === 'event') {
            // Show appropriate notification based on event type
            if (data.event_name === 'crawl_complete') {
                console.log('Crawl completed:', data);

                // Show notification
                Swal.fire({
                    title: 'Crawl Complete',
                    text: data.message || 'Crawl completed successfully',
                    icon: 'success',
                    confirmButtonText: 'OK'
                });
            } else if (data.event_name === 'crawl_error') {
                console.log('Crawl error:', data);

                // Show notification
                Swal.fire({
                    title: 'Crawl Failed',
                    text: data.message || 'An error occurred during the crawl',
                    icon: 'error',
                    confirmButtonText: 'OK'
                });
            } else if (data.event_name === 'crawl_cancelled') {
                console.log('Crawl cancelled:', data);

                // Update UI for cancelled crawl
                updateUIForCancelledCrawl();

                // Show notification
                Swal.fire({
                    title: 'Crawl Cancelled',
                    text: data.message || 'Crawl was cancelled',
                    icon: 'warning',
                    confirmButtonText: 'OK'
                });
            }
        }
    } catch (e) {
        // Not JSON, let HTMX handle it
        // HTMX will process HTML fragments with OOB swaps
    }
});

// Listen for HTMX after-swap event to check for cancelled status
htmx.on('htmx:afterSwap', function(evt) {
    // Check if the swapped content contains a cancelled message
    if (evt.detail.target && evt.detail.target.id === 'crawl-status-progress') {
        if (evt.detail.target.innerHTML.includes('Crawl Cancelled')) {
            updateUIForCancelledCrawl();
        }
    }
});