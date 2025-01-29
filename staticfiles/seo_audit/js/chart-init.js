// Initialize charts with data
export function initializeCharts(severityData, issueTypeData) {
    // Severity Chart
    const severityCtx = document.getElementById('severityChart');
    if (severityCtx) {
        new Chart(severityCtx, {
            type: 'doughnut',
            data: {
                labels: severityData.labels,
                datasets: [{
                    data: severityData.values,
                    backgroundColor: [
                        '#f44335',  // Critical - Red
                        '#fb8c00',  // High - Orange
                        '#29b6f6',  // Medium - Light Blue
                        '#66bb6a'   // Low - Green
                    ],
                    borderWidth: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }

    // Issue Type Chart
    const issueTypeCtx = document.getElementById('issueTypeChart');
    if (issueTypeCtx) {
        new Chart(issueTypeCtx, {
            type: 'bar',
            data: {
                labels: issueTypeData.labels,
                datasets: [{
                    label: 'Number of Issues',
                    data: issueTypeData.values,
                    backgroundColor: '#3b82f6',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }
} 