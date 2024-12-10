document.addEventListener('DOMContentLoaded', function() {
    // Initialize Flatpickr for the target date input
    flatpickr("#target_date", {
        dateFormat: "Y-m-d",
        minDate: "today",
        allowInput: true,
        altInput: true,
        altFormat: "F j, Y",
    });
    
    // Initialize Flatpickr for edit modal
    flatpickr("#edit_target_date", {
        dateFormat: "Y-m-d",
        minDate: "today",
        allowInput: true,
        altInput: true,
        altFormat: "F j, Y",
    });

    // Handle edit objective modal
    document.querySelectorAll('.edit-objective').forEach(function(element) {
        element.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Get data from the clicked element
            const data = e.target.closest('a').dataset;
            
            // Update form action URL
            const form = document.getElementById('editObjectiveForm');
            form.action = form.action.replace('/0/', `/${data.objectiveIndex}/`);
            
            // Populate form fields
            document.getElementById('edit_goal').value = data.goal;
            document.getElementById('edit_metric').value = data.metric;
            document.getElementById('edit_target_date')._flatpickr.setDate(data.targetDate);
            document.getElementById('edit_status').checked = data.status === 'true';
            document.getElementById('edit_objective_index').value = data.objectiveIndex;
        });
    });

    // Handle objective status toggles
    document.querySelectorAll('.objective-status-toggle').forEach(function(element) {
        element.addEventListener('click', function(e) {
            e.preventDefault();
            
            const clientId = this.dataset.clientId;
            const objectiveIndex = this.dataset.objectiveIndex;
            const newStatus = this.dataset.newStatus;
            
            // Send AJAX request to update status
            fetch(`/seo/clients/${clientId}/objectives/${objectiveIndex}/update-status/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    status: newStatus
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message
                    Swal.fire({
                        icon: 'success',
                        title: 'Status Updated',
                        text: 'The objective status has been updated successfully.',
                        showConfirmButton: false,
                        timer: 1500
                    }).then(() => {
                        // Reload the page to show updated status
                        window.location.reload();
                    });
                } else {
                    // Show error message
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: data.error || 'An error occurred while updating the status.',
                    });
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: 'An error occurred while updating the status.',
                });
            });
        });
    });

    // Helper function to get CSRF token
    function getCookie(name) {
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
}); 