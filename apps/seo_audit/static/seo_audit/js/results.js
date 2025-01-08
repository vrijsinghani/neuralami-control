import { initializeTables } from './table-init.js';
import { initializePlanGeneration, initializePlanViewing } from './plan-handlers.js';
import { initializeCharts } from './chart-init.js';

// Ensure jQuery is properly initialized
if (typeof jQuery === 'undefined') {
    console.error('jQuery is not loaded');
} else {
    window.$ = window.jQuery = jQuery;
}

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tables
    const dataTableSearch = initializeTables();

    // Initialize plan generation and viewing
    initializePlanGeneration();
    initializePlanViewing();

    // Initialize charts if data is available
    const severityData = window.severityData;
    const issueTypeData = window.issueTypeData;
    if (severityData && issueTypeData) {
        initializeCharts(severityData, issueTypeData);
    }
}); 