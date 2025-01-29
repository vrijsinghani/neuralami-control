// Initialize tables and scrollbars
export function initializeTables() {
    // Initialize Perfect Scrollbar for tables with fixed height
    const tableElements = document.querySelectorAll('.table-responsive');
    if (tableElements.length > 0) {
        tableElements.forEach(element => {
            element.style.maxHeight = '800px';
            new PerfectScrollbar(element, {
                wheelSpeed: 1,
                wheelPropagation: true,
                minScrollbarLength: 20,
                suppressScrollX: true
            });
        });
    }

    // Initialize DataTable
    const issuesTable = document.getElementById('issues-table');
    let dataTableSearch;
    if (issuesTable) {
        dataTableSearch = new simpleDatatables.DataTable("#issues-table", {
            searchable: true,
            fixedHeight: false,
            perPage: 50,
            perPageSelect: [25, 50, 100, 200],
            columns: [
                { select: 0, sort: "desc" },
                { select: 1, sort: "asc" },
                { select: 2, sort: "asc" },
                { select: 3, sortable: false }
            ],
            labels: {
                placeholder: "Search issues...",
                perPage: "{select} issues per page",
                noRows: "No issues found",
                info: "Showing {start} to {end} of {rows} entries",
                noResults: "No results match your search query"
            },
            layout: {
                top: "{search}{select}",
                bottom: "<div class='d-flex justify-content-between align-items-center'>{info}{pager}</div>"
            },
            classes: {
                wrapper: "datatable-wrapper",
                input: "form-control form-control-sm",
                selector: "form-select form-select-sm",
                pager: "pagination mb-0"
            }
        });

        // Move search and select elements to our toolbar
        const searchElement = document.querySelector('.datatable-search');
        const selectElement = document.querySelector('.datatable-dropdown');
        const dtSearchInput = document.querySelector('.datatable-input');
        const dtSelector = document.querySelector('.datatable-selector');

        if (searchElement && dtSearchInput && dtSearchInput.parentElement) {
            searchElement.appendChild(dtSearchInput.parentElement);
        }
        if (selectElement && dtSelector && dtSelector.parentElement) {
            selectElement.appendChild(dtSelector.parentElement);
        }
    }

    return dataTableSearch;
} 