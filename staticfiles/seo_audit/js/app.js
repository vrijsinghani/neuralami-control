import { initializeTables } from '/static/seo_audit/js/table-init.js';
import { initializePlanGeneration, initializePlanViewing } from '/static/seo_audit/js/plan-handlers.js';
import { initializeCharts } from '/static/seo_audit/js/chart-init.js';

class AuditApp {
    constructor(config) {
        this.config = config;
    }

    initialize() {
        document.addEventListener('DOMContentLoaded', () => {
            // Initialize tables
            const dataTableSearch = initializeTables();

            // Initialize plan generation and viewing
            initializePlanGeneration();
            initializePlanViewing();

            // Initialize charts if data is available
            if (this.config.severityData && this.config.issueTypeData) {
                initializeCharts(this.config.severityData, this.config.issueTypeData);
            }
        });
    }
}

export { AuditApp }; 