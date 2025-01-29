document.addEventListener('DOMContentLoaded', function() {
    // Ensure urls are available
    if (!window.urls) {
        console.error('URLs not defined');
        return;
    }

    // Initialize DataTable
    new simpleDatatables.DataTable("#rankings-table", {
        perPage: 25,
        sort: { date: "desc" },
        searchable: true,
        fixedHeight: true,
        labels: {
            placeholder: "Search records..."
        }
    });

    // Initialize button handlers
    const collectRankingsBtn = document.getElementById('collectRankingsBtn');
    const generateReportBtn = document.getElementById('generateReportBtn');
    const backfillRankingsBtn = document.getElementById('backfillRankingsBtn');
    
    if (collectRankingsBtn) {
        collectRankingsBtn.addEventListener('click', function() {
        Swal.fire({
            title: 'Collecting Rankings Data',
            text: 'This may take a few minutes...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading()
            }
        });

        fetch(window.urls.collectRankings, {
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
    }

    if (generateReportBtn) {
        generateReportBtn.addEventListener('click', function() {
        Swal.fire({
            title: 'Generating Report',
            text: 'Please wait...',
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading()
            }
        });

        fetch(window.urls.generateReport, {
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
    }

    if (backfillRankingsBtn) {
        backfillRankingsBtn.addEventListener('click', function() {
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
    }

    // Initialize column visibility handlers
    const checkboxes = document.querySelectorAll('#dropdownDefaultCheckbox input[type="checkbox"]');
    checkboxes.forEach(function(checkbox) {
        checkbox.addEventListener('change', function() {
            const targetColumnId = this.getAttribute('data-target');
            const targetColumn = document.getElementById('th_' + targetColumnId);
            const targetDataCells = document.querySelectorAll('.td_' + targetColumnId);
            
            if (this.checked) {
                targetColumn.style.display = 'none';
                targetDataCells.forEach(cell => cell.style.display = 'none');
            } else {
                targetColumn.style.display = '';
                targetDataCells.forEach(cell => cell.style.display = '');
            }
        });
    });
});

function handleBackfillRankings() {
    Swal.fire({
        title: 'Collecting Historical Data',
        text: 'This may take several minutes...',
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading()
        }
    });

    fetch(window.urls.backfillRankings, {
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

function getPageItems(selectObject) {
    var value = selectObject.value;
    window.location.href = updateQueryStringParameter(window.location.href, 'items', value);
}

function updateQueryStringParameter(uri, key, value) {
    var re = new RegExp("([?&])" + key + "=.*?(&|$)", "i");
    var separator = uri.indexOf('?') !== -1 ? "&" : "?";
    if (uri.match(re)) {
        return uri.replace(re, '$1' + key + "=" + value + '$2');
    }
    else {
        return uri + separator + key + "=" + value;
    }
} 