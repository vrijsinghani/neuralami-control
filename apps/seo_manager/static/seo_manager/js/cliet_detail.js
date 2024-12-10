document.addEventListener('DOMContentLoaded', function() {
    {% for keyword in client.targeted_keywords.all %}
    (function() {
        const modalId = 'view-history-{{ keyword.id }}';
        const canvasId = 'keyword-chart-{{ keyword.id }}';
        const modal = document.getElementById(modalId);
        let currentChart = null;

        if (!modal) return;

        const history = [
            {% for entry in keyword.ranking_history.all %}
                {
                    date: '{{ entry.date|date:"M d, Y" }}',
                    position: {{ entry.average_position }},
                    impressions: {{ entry.impressions }},
                    clicks: {{ entry.clicks }},
                    ctr: {{ entry.ctr }}
                }{% if not forloop.last %},{% endif %}
            {% endfor %}
        ];

        function recreateCanvas(containerId) {
            const container = document.getElementById(containerId);
            if (!container) return null;
            
            // Remove existing canvas
            const oldCanvas = document.getElementById(canvasId);
            if (oldCanvas) {
                oldCanvas.remove();
            }
            
            // Create new canvas
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
            // Force cleanup of any existing charts
            destroyChart();
            
            // Recreate canvas
            const canvas = recreateCanvas('chart-container-{{ keyword.id }}');
            if (!canvas) {
                console.error(`Cannot create canvas for ${canvasId}`);
                return;
            }

            // Wait for next tick to ensure DOM is updated
            setTimeout(() => {
                currentChart = new Chart(canvas, {
                    type: 'line',
                    data: {
                        labels: history.map(entry => entry.date).reverse(),
                        datasets: [{
                            label: 'Position',
                            data: history.map(entry => entry.position).reverse(),
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

        modal.addEventListener('hidden.bs.modal', function() {
            destroyChart();
        });

        window.addEventListener('unload', destroyChart);
    })();
    {% endfor %}
});

document.addEventListener('DOMContentLoaded', function() {
  // Collect Rankings Button
  document.getElementById('collectRankingsBtn').addEventListener('click', function() {
    Swal.fire({
      title: 'Collecting Rankings Data',
      text: 'This may take a few minutes...',
      allowOutsideClick: false,
      didOpen: () => {
        Swal.showLoading()
      }
    });

    fetch('{% url "seo_manager:collect_rankings" client.id %}', {
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
  document.getElementById('generateReportBtn').addEventListener('click', function() {
    Swal.fire({
      title: 'Generating Report',
      text: 'Please wait...',
      allowOutsideClick: false,
      didOpen: () => {
        Swal.showLoading()
      }
    });

    fetch('{% url "seo_manager:generate_report" client.id %}', {
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
    })
    
  });

  // Backfill Rankings Button
  document.getElementById('backfillRankingsBtn').addEventListener('click', function() {
    Swal.fire({
      title: 'Backfill Historical Data',
      text: 'This will collect ranking data for the past 12 months. This may take several minutes. Continue?',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Yes, proceed',
      cancelButtonText: 'No, cancel'
    }).then((result) => {
      if (result.isConfirmed) {
        Swal.fire({
          title: 'Collecting Historical Data',
          text: 'This may take several minutes...',
          allowOutsideClick: false,
          didOpen: () => {
            Swal.showLoading()
          }
        });

        fetch('{% url "seo_manager:backfill_rankings" client.id %}', {
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
    });
  });
});

document.addEventListener('DOMContentLoaded', function() {
  // Initialize Quill editors
  var toolbarOptions = [
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
    var addProfileEditor = new Quill('#add-profile-editor', {
      theme: 'snow',
      modules: {
        toolbar: toolbarOptions
      }
    });

    // Handle form submission
    document.getElementById('addProfileForm').addEventListener('submit', function(e) {
      var content = addProfileEditor.root.innerHTML;
      document.getElementById('add-profile-content').value = content;
    });
  }

  // Edit Profile Editor
  if (document.getElementById('edit-profile-editor')) {
    var editProfileEditor = new Quill('#edit-profile-editor', {
      theme: 'snow',
      modules: {
        toolbar: toolbarOptions
      }
    });

    // Handle form submission
    document.getElementById('editProfileForm').addEventListener('submit', function(e) {
      var content = editProfileEditor.root.innerHTML;
      document.getElementById('edit-profile-content').value = content;
    });
  }
});

  document.addEventListener('DOMContentLoaded', function() {
    // Add handler for Magically Fill In button
    document.getElementById('magicallyFillBtn').addEventListener('click', function() {
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
  
      // Make the request to generate profile
      fetch('{% url "seo_manager:generate_magic_profile" client.id %}', {
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
          // Start polling for task status
          const pollInterval = setInterval(() => {
            const toolStatusUrl = "{% url 'agents:get_tool_status' 'TASK_ID' %}".replace('TASK_ID', data.task_id);
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
                // else task is still running, continue polling
              })
              .catch(error => {
                clearInterval(pollInterval);
                Swal.fire({
                  icon: 'error',
                  title: 'Error',
                  text: 'Failed to check task status'
                });
              });
          }, 2000); // Poll every 2 seconds
        } else {
          Swal.fire({
            icon: 'error',
            title: 'Error',
            text: data.error || 'Failed to start profile generation'
          });
        }
      })
      .catch(error => {
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
    });
  });

document.addEventListener('DOMContentLoaded', function() {
    // Initialize flatpickr for target date
    flatpickr("#target_date", {
        dateFormat: "Y-m-d",
        minDate: "today"
    });

    // Form submission handling
    const form = document.getElementById('addObjectiveForm');
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            fetch(this.action, {
                method: 'POST',
                body: new FormData(this),
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Success!',
                        text: 'Business objective added successfully'
                    }).then(() => {
                        window.location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: data.message || 'An error occurred'
                    });
                }
            });
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const deleteBtn = document.getElementById('deleteClientBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', function() {
            const clientId = this.dataset.clientId;
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
                    // Show loading state
                    Swal.fire({
                        title: 'Deleting...',
                        html: 'Please wait',
                        allowOutsideClick: false,
                        didOpen: () => {
                            Swal.showLoading()
                        }
                    });

                    // Make delete request
                    fetch(`{% url 'seo_manager:delete_client' client.id %}`, {
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
                                // Redirect to clients list
                                window.location.href = "{% url 'seo_manager:client_list' %}";
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
            });
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // View switching functionality
    const listView = document.getElementById('projects-list-view');
    const kanbanView = document.getElementById('projects-kanban-view');
    const listViewBtn = document.getElementById('list-view');
    const kanbanViewBtn = document.getElementById('kanban-view');

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

    // Initialize DataTables for better table functionality
    if (document.getElementById('projects-table')) {
        new simpleDatatables.DataTable("#projects-table", {
            searchable: true,
            fixedHeight: true,
            perPage: 10
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Activity Timeline Filtering
    const filterLinks = document.querySelectorAll('[data-filter]');
    const timelineBlocks = document.querySelectorAll('.timeline-block');
    
    filterLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Update active state
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

    // Load More Functionality
    const loadMoreBtn = document.getElementById('loadMoreActivities');
    if (loadMoreBtn) {
        let page = 1;
        loadMoreBtn.addEventListener('click', function() {
            page++;
            loadMoreBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Loading...';
            
            fetch(`{% url 'seo_manager:load_more_activities' client.id %}?page=${page}`)
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

    // Export Activity
    const exportBtn = document.getElementById('exportActivityBtn');
    if (exportBtn) {
        exportBtn.addEventListener('click', function() {
            const filter = document.querySelector('[data-filter].active').dataset.filter;
            window.location.href = `{% url 'seo_manager:export_activities' client.id %}?filter=${filter}`;
        });
    }
});

document.addEventListener('DOMContentLoaded', function() {
    // Initialize DataTable for snapshots
    if (document.getElementById('snapshots-table')) {
        new simpleDatatables.DataTable("#snapshots-table", {
            searchable: true,
            fixedHeight: true,
            perPage: 7
        });
    }

    // Create Snapshot Button Handler
    const createSnapshotBtn = document.getElementById('createSnapshotBtn');
    if (createSnapshotBtn) {
        createSnapshotBtn.addEventListener('click', function() {
            Swal.fire({
                title: 'Creating Snapshot',
                html: 'Scanning website meta tags...',
                timerProgressBar: true,
                didOpen: () => {
                    Swal.showLoading();
                }
            });

            fetch('{% url "seo_manager:create_meta_tags_snapshot" client.id %}', {
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
                        text: 'Meta tags snapshot created successfully'
                    }).then(() => {
                        window.location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: data.error || 'Failed to create snapshot'
                    });
                }
            });
        });
    }

    // View Snapshot Function
    window.viewSnapshot = function(filename) {
        const modal = new bootstrap.Modal(document.getElementById('viewMetaTagsModal'));
        
        fetch(`{% url 'file_manager' %}/meta-tags/${filename}`)
            .then(response => response.json())
            .then(data => {
                const report = document.getElementById('metaTagsReport');
                // Generate report HTML here
                report.innerHTML = generateReportHTML(data);
                modal.show();
            });
    };

    // Compare Changes Function
    window.compareWithPrevious = function(filename) {
        Swal.fire({
            title: 'Comparing Changes',
            html: 'Analyzing differences...',
            timerProgressBar: true,
            didOpen: () => {
                Swal.showLoading();
            }
        });

        // Add your comparison logic here
    };

    // Delete Snapshot Function
    window.deleteSnapshot = function(filename) {
        Swal.fire({
            title: 'Are you sure?',
            text: "This snapshot will be permanently deleted!",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Yes, delete it!'
        }).then((result) => {
            if (result.isConfirmed) {
                // Add your delete logic here
            }
        });
    };
});

function generateReportHTML(data) {
    // Add your report generation logic here
    return `
        <div class="report-container">
            <!-- Report content -->
        </div>
    `;
}

document.addEventListener('DOMContentLoaded', function() {
    // Business Objectives Filtering
    const objectiveFilterLinks = document.querySelectorAll('[data-objective-filter]');
    const objectiveCards = document.querySelectorAll('.objective-card');
    
    objectiveFilterLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Update active state
            objectiveFilterLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
            
            const filter = this.dataset.objectiveFilter;
            
            objectiveCards.forEach(card => {
                if (filter === 'all' || card.dataset.status === filter) {
                    card.style.display = 'block';
                    setTimeout(() => {
                        card.style.opacity = '1';
                        card.style.transform = 'translateY(0)';
                    }, 50);
                } else {
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(-10px)';
                    setTimeout(() => {
                        card.style.display = 'none';
                    }, 300);
                }
            });
        });
    });

    // Initialize Flatpickr for date inputs
    if (document.getElementById('target_date')) {
        flatpickr("#target_date", {
            dateFormat: "Y-m-d",
            minDate: "today",
            defaultDate: "today"
        });
    }

    // Form validation and submission
    const objectiveForm = document.getElementById('addObjectiveForm');
    if (objectiveForm) {
        objectiveForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            
            fetch(this.action, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Success!',
                        text: 'Business objective added successfully',
                        showConfirmButton: false,
                        timer: 1500
                    }).then(() => {
                        window.location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: data.message || 'Failed to add objective'
                    });
                }
            });
        });
    }

    // Status Update Functions
    window.updateObjectiveStatus = function(objectiveId, newStatus) {
        Swal.fire({
            title: 'Updating Status',
            text: 'Please wait...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });

        fetch(`{% url 'seo_manager:update_objective_status' client_id=client.id objective_index=0 %}`.replace('0', objectiveId), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({ status: newStatus })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Updated!',
                    text: 'Objective status has been updated.',
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
        });
    };

    // Delete Objective Function
    window.deleteObjective = function(objectiveId) {
        Swal.fire({
            title: 'Are you sure?',
            text: "This objective will be permanently deleted!",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#d33',
            cancelButtonColor: '#3085d6',
            confirmButtonText: 'Yes, delete it!'
        }).then((result) => {
            if (result.isConfirmed) {
                document.querySelector(`#deleteObjectiveForm${objectiveId}`).submit();
            }
        });
    };

    // Progress Animation
    const progressBars = document.querySelectorAll('.progress-bar');
    progressBars.forEach(bar => {
        const targetWidth = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.width = targetWidth;
        }, 300);
    });
});

// Add this function to handle objective status updates
function updateObjectiveStatus(clientId, objectiveIndex, newStatus) {
    fetch(`{% url 'seo_manager:update_objective_status' client_id=client.id objective_index=0 %}`.replace('0', objectiveIndex), {
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
}

// Add click event listeners to status toggle buttons
document.addEventListener('DOMContentLoaded', function() {
    const statusToggles = document.querySelectorAll('.objective-status-toggle');
    statusToggles.forEach(toggle => {
        toggle.addEventListener('click', function() {
            const clientId = this.dataset.clientId;
            const objectiveIndex = this.dataset.objectiveIndex;
            const newStatus = this.dataset.newStatus;
            updateObjectiveStatus(clientId, objectiveIndex, newStatus);
        });
    });
});