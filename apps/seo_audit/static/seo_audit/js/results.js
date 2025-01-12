import { initializeTables } from './table-init.js?v=' + new Date().getTime();
import { initializePlanGeneration, initializePlanViewing, initializePlanDeletion } from './plan-handlers.js?v=' + new Date().getTime();
import { initializeCharts } from './chart-init.js?v=' + new Date().getTime();

// Ensure jQuery is properly initialized
if (typeof jQuery === 'undefined') {
    console.error('jQuery is not loaded');
} else {
    window.$ = window.jQuery = jQuery;
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tables
    const dataTableSearch = initializeTables();

    // Initialize plan generation, viewing and deletion
    initializePlanGeneration();
    initializePlanViewing();
    initializePlanDeletion();

    // Initialize charts if data is available
    const severityData = window.severityData;
    const issueTypeData = window.issueTypeData;
    if (severityData && issueTypeData) {
        initializeCharts(severityData, issueTypeData);
    }
});