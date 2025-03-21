class ToolOutputManager {
    constructor() {
        this.activeContainer = null;
        this.messagesContainer = document.getElementById('chat-messages');
        this.charts = new Map(); // Store chart instances
        this.toolContainers = new Map(); // Map to store tool containers by tool run ID
        
        // The date-fns adapter is automatically registered via the bundle
    }

    handleToolStart(data) {
        try {
            // Try to parse if string, otherwise use as is
            const toolData = typeof data === 'string' ? JSON.parse(data) : data;
            const toolName = toolData.tool || 'Unknown Tool';
            
            // Create a unique ID for this tool run
            const toolRunId = toolData.run_id || `${toolName}-${Date.now()}`;
            
            // Create a new container for this tool output
            const container = document.createElement('div');
            container.className = 'd-flex justify-content-start mb-4';
            const containerId = `tool-${Date.now()}`;
            container.innerHTML = `
                <div class="avatar me-2">
                    <img src="${window.chatConfig.currentAgent.avatar}" 
                         alt="${window.chatConfig.currentAgent.name}" 
                         class="border-radius-lg shadow">
                </div>
                <div class="message agent" style="max-width: 90%;">
                    <div class="tool-output">
                        <div class="tool-header d-flex align-items-center justify-content-between">
                            <div class="d-flex align-items-center cursor-pointer collapsed" data-bs-toggle="collapse" data-bs-target="#${containerId}-content">
                                <i class="fas fa-chevron-down me-2 toggle-icon"></i>
                                <i class="fas fa-tools me-2"></i>
                                <span class="tool-name small">${toolName}</span>
                            </div>
                        </div>
                        <div class="tool-content mt-2 collapse" id="${containerId}-content">
                            ${toolData.input ? `
                            <div class="tool-input text-muted mb-2">
                                <small>Input: ${toolData.input}</small>
                            </div>` : ''}
                            <div class="tool-result"></div>
                        </div>
                    </div>
                </div>
            `;
            
            // Add to messages container
            if (this.messagesContainer) {
                this.messagesContainer.appendChild(container);
                this.activeContainer = container;
                
                // Store the container in our map using the tool run ID as key
                // This ensures multiple runs of the same tool don't overwrite each other
                this.toolContainers.set(toolRunId, {
                    container,
                    toolName
                });
                
                // Keep a reference for debugging
                console.debug(`Created tool container for ${toolName} with ID ${toolRunId}`);
                
                // Scroll to the new container
                container.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
        } catch (error) {
            console.error('Error handling tool start:', error);
            // Create a minimal container for error case
            const container = document.createElement('div');
            container.className = 'd-flex justify-content-start mb-4';
            container.innerHTML = `
                <div class="avatar me-2">
                    <img src="${window.chatConfig.currentAgent.avatar}" 
                         alt="${window.chatConfig.currentAgent.name}" 
                         class="border-radius-lg shadow">
                </div>
                <div class="message agent" style="max-width: 90%;">
                    <div class="tool-output">
                        <div class="tool-header d-flex align-items-center">
                            <i class="fas fa-tools me-2"></i>
                            <span class="tool-name small">Tool Execution</span>
                        </div>
                    </div>
                </div>
            `;
            
            if (this.messagesContainer) {
                this.messagesContainer.appendChild(container);
                this.activeContainer = container;
            }
        }
    }

    handleToolResult(result) {
        try {
            if (!result) {
                console.warn('Empty result passed to handleToolResult');
                return;
            }
            
            console.debug('ToolOutputManager.handleToolResult received:', result);
            
            // Try to find an appropriate container for this result
            let container = this.activeContainer;
            const toolName = result.toolName || (result.data && result.data.name);
            const toolRunId = result.toolRunId;
            
            // First try to find by run ID (most precise)
            if (toolRunId && this.toolContainers.has(toolRunId)) {
                container = this.toolContainers.get(toolRunId).container;
                console.debug(`Found container by run ID ${toolRunId}`);
            }
            // Then try by tool name (may not be unique if tool was run multiple times)
            else if (toolName) {
                // Look for the latest container with this tool name
                let latestContainer = null;
                let latestTimestamp = 0;
                
                for (const [id, data] of this.toolContainers.entries()) {
                    if (data.toolName === toolName) {
                        // Extract timestamp from the ID (assuming the format includes timestamp)
                        const timestampMatch = id.match(/.*-(\d+)$/);
                        if (timestampMatch) {
                            const timestamp = parseInt(timestampMatch[1], 10);
                            if (timestamp > latestTimestamp) {
                                latestTimestamp = timestamp;
                                latestContainer = data.container;
                            }
                        }
                    }
                }
                
                if (latestContainer) {
                    container = latestContainer;
                    console.debug(`Found latest container for tool ${toolName}`);
                }
            }
            
            if (!container) {
                console.warn('No active tool container found for result');
                return;
            }

            const resultContainer = container.querySelector('.tool-result');
            if (!resultContainer) {
                console.warn('No result container found within the tool container');
                return;
            }

            if (result.type === 'error') {
                resultContainer.innerHTML = `
                    <div class="tool-error mt-2">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        <span class="text-danger small">${result.data}</span>
                    </div>
                `;
            } else if (result.type === 'text') {
                // Check if the text looks like CSV data
                const text = result.data.trim();
                // More robust CSV detection - check for consistent number of columns
                const lines = text.split(/[\n\r]+/).filter(row => row.trim());
                const firstLineCommas = (lines[0] || '').split(',').length - 1;
                
                // Check if this looks like CSV data:
                // 1. Has commas
                // 2. No double line breaks (not markdown)
                // 3. At least 2 columns
                // 4. Consistent number of columns in first few rows
                const isLikelyCSV = text.includes(',') && 
                                  !text.includes('\n\n') && 
                                  firstLineCommas >= 1 &&
                                  lines.slice(0, Math.min(5, lines.length))
                                       .every(line => (line.split(',').length - 1) === firstLineCommas);

                if (isLikelyCSV) {
                    try {
                        // Split into rows and parse CSV
                        const headers = this._parseCSVRow(lines[0]);
                        
                        // Only proceed if we have valid headers
                        if (headers.length > 1) {
                            const data = lines.slice(1).map(row => {
                                const values = this._parseCSVRow(row);
                                return headers.reduce((obj, header, i) => {
                                    // Try to convert numeric values
                                    let value = values[i] || '';
                                    value = value.trim();
                                    
                                    // Convert to number if possible and not empty
                                    if (value !== '' && !isNaN(value) && !isNaN(parseFloat(value))) {
                                        value = parseFloat(value);
                                    }
                                    
                                    obj[header] = value;
                                    return obj;
                                }, {});
                            });

                            // If we successfully parsed it as CSV and have data
                            if (data.length > 0) {
                                console.debug('Successfully parsed CSV data:', {
                                    headers,
                                    rowCount: data.length,
                                    sampleRow: data[0]
                                });
                                this._handleVisualData(resultContainer, data);
                                return;
                            }
                        }
                    } catch (e) {
                        console.debug('CSV parsing failed, falling back to text display', e);
                    }
                }
                
                // If not CSV or parsing failed, display as text
                const parsedContent = marked.parse(result.data);
                resultContainer.innerHTML = `
                    <div class="tool-text mt-2">
                        <div class="tool-content-normalized">${parsedContent}</div>
                    </div>
                `;
            } else if (result.type === 'json' || (result.type === 'table' && Array.isArray(result.data))) {
                // Show appropriate visualization based on the data
                this._handleVisualData(resultContainer, result.data);
            } else {
                // Default to JSON display for unknown types
                resultContainer.innerHTML = `
                    <div class="tool-json mt-2">
                        <pre class="tool-content-normalized"><code>${JSON.stringify(result.data, null, 2)}</code></pre>
                    </div>
                `;
            }
            
            // Auto-expand the result
            const collapseEl = container.querySelector('.tool-content');
            if (collapseEl && collapseEl.classList.contains('collapse')) {
                new bootstrap.Collapse(collapseEl).show();
            }
            
            // Clear active container once we've rendered a result into it
            if (this.activeContainer === container) {
                this.activeContainer = null;
            }
            
        } catch (error) {
            console.error('Error handling tool result:', error);
        }
    }
    
    // Helper method to handle visualization for data
    _handleVisualData(resultContainer, data) {
        const timeSeriesData = this._findTimeSeriesData(data);
        
        if (timeSeriesData) {
            // Add visualization toggle buttons
            const toggleContainer = document.createElement('div');
            toggleContainer.className = 'mb-2 btn-group';
            toggleContainer.innerHTML = `
                <button class="btn btn-primary btn-sm active" data-view="chart">
                    <i class="fas fa-chart-line me-1"></i>Chart
                </button>
                <button class="btn btn-primary btn-sm" data-view="table">
                    <i class="fas fa-table me-1"></i>Table
                </button>
            `;
            
            // Add visualization container
            const vizContainer = document.createElement('div');
            vizContainer.className = 'visualization-container';
            vizContainer.style.width = '100%';            
            resultContainer.appendChild(toggleContainer);
            resultContainer.appendChild(vizContainer);
            
            // Add event listeners for toggle buttons
            toggleContainer.querySelectorAll('button').forEach(button => {
                button.addEventListener('click', (e) => {
                    const view = e.currentTarget.dataset.view;
                    this._updateVisualization(vizContainer, view, timeSeriesData, data);
                    
                    // Update active button
                    toggleContainer.querySelectorAll('button').forEach(b => 
                        b.classList.toggle('active', b === e.currentTarget));
                });
            });
            
            // Initialize with chart view
            this._updateVisualization(vizContainer, 'chart', timeSeriesData, data);
        } else {
            // Check if we have tabular data
            const tableData = this._findTableData(data);
            if (tableData && tableData.length > 0) {
                resultContainer.innerHTML += this._createTable(tableData);
                this._addCsvDownloadButton(resultContainer, tableData);
            } else {
                // Default to JSON display
                resultContainer.innerHTML += `
                    <div class="tool-json mt-2">
                        <pre class="small"><code>${JSON.stringify(data, null, 2)}</code></pre>
                    </div>
                `;
            }
        }
    }

    _updateVisualization(container, view, timeSeriesData, originalData) {
        // Clear previous visualization
        container.innerHTML = '';
        
        if (view === 'chart' && timeSeriesData) {
            // Set container to full width before creating chart
            container.style.width = '100%';
            container.style.minHeight = '400px';
            
            // Force layout recalculation before creating chart
            container.getBoundingClientRect();            // Create chart with filtered data
            this._createChart(container, timeSeriesData);
        } else if (view === 'table') {
            // Create table with original data
            container.innerHTML = this._createTable(originalData);
            
            // Initialize DataTable
            setTimeout(() => {
                try {
                    const tableId = container.querySelector('table').id;
                    new simpleDatatables.DataTable(`#${tableId}`, {
                        searchable: true,
                        fixedHeight: false,
                        perPage: 10
                    });
                } catch (error) {
                    console.warn('Failed to initialize DataTable:', error);
                }
            }, 100);
        }
    }

    _findTableData(data) {
        // If data is already an array of objects with at least one row, it's tabular
        if (Array.isArray(data) && data.length > 0 && typeof data[0] === 'object') {
            return data;
        }

        // Look for arrays in the object values
        if (typeof data === 'object') {
            for (const key in data) {
                const value = data[key];
                if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object') {
                    return value;
                }
            }
        }

        return null;
    }

    _createTable(data) {
        if (!Array.isArray(data) || !data.length) return '';

        const tableId = `table-${Date.now()}`;
        const headers = Object.keys(data[0]);
        const rows = data.map(row => headers.map(header => {
            const value = row[header];
            // Format dates and numbers
            if (value instanceof Date || (typeof value === 'string' && !isNaN(Date.parse(value)))) {
                return new Date(value).toISOString().split('T')[0];
            }
            if (typeof value === 'number') {
                return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
            }
            return value;
        }));

        const tableHtml = `
            <div class="table-responsive">
                <table id="${tableId}" class="table table-sm">
                    <thead>
                        <tr>
                            ${headers.map(header => `<th>${this._formatFieldName(header)}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map(row => `
                            <tr>
                                ${row.map(cell => `<td>${cell}</td>`).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        // Initialize DataTable after a short delay to ensure the table is in the DOM
        setTimeout(() => {
            try {
                const tableElement = document.getElementById(tableId);
                if (tableElement) {
                    new simpleDatatables.DataTable(`#${tableId}`, {
                        searchable: true,
                        fixedHeight: false,
                        perPage: 10,
                        perPageSelect: [10, 25, 50, 100]
                    });
                } else {
                    console.warn(`Table element ${tableId} not found in DOM`);
                }
            } catch (error) {
                console.warn(`Failed to initialize DataTable for ${tableId}:`, error);
            }
        }, 100);

        return tableHtml;
    }

    _addCsvDownloadButton(container, data) {
        if (!data || !data.length) return;

        // Get or create tool-actions container
        let toolActions = container.querySelector('.tool-actions');
        if (!toolActions) {
            toolActions = document.createElement('div');
            toolActions.className = 'tool-actions d-flex align-items-center mt-2';
            container.appendChild(toolActions);
        }

        const headers = Object.keys(data[0]);
        const csvContent = [
            headers.join(','),
            ...data.map(row => headers.map(header => {
                let value = row[header];
                // Format dates and numbers
                if (value instanceof Date || (typeof value === 'string' && !isNaN(Date.parse(value)))) {
                    value = new Date(value).toISOString().split('T')[0];
                } else if (typeof value === 'number') {
                    value = value.toFixed(2);
                }
                // Handle values that need quotes (contains commas, quotes, or newlines)
                if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n'))) {
                    value = `"${value.replace(/"/g, '""')}"`;
                }
                return value;
            }).join(','))
        ].join('\n');

        // Create download button
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        
        const downloadButton = document.createElement('a');
        downloadButton.href = url;
        downloadButton.download = 'table_data.csv';
        downloadButton.className = 'btn btn-link text-primary p-0 ms-2';
        downloadButton.innerHTML = '<i class="fas fa-download"></i>';
        downloadButton.title = 'Download as CSV';
        
        // Clean up the URL on click
        downloadButton.addEventListener('click', () => {
            setTimeout(() => URL.revokeObjectURL(url), 100);
        });

        // Create copy button
        const copyButton = document.createElement('button');
        copyButton.className = 'btn btn-link text-primary p-0 ms-2';
        copyButton.innerHTML = '<i class="fas fa-copy"></i>';
        copyButton.title = 'Copy CSV to clipboard';
        
        copyButton.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(csvContent);
                // Show success feedback
                const originalIcon = copyButton.innerHTML;
                copyButton.innerHTML = '<i class="fas fa-check text-success"></i>';
                setTimeout(() => {
                    copyButton.innerHTML = originalIcon;
                }, 1000);
            } catch (err) {
                console.error('Failed to copy:', err);
                // Show error feedback
                const originalIcon = copyButton.innerHTML;
                copyButton.innerHTML = '<i class="fas fa-times text-danger"></i>';
                setTimeout(() => {
                    copyButton.innerHTML = originalIcon;
                }, 1000);
            }
        });

        // Add buttons to container
        toolActions.appendChild(copyButton);
        toolActions.appendChild(downloadButton);
    }

    _findTimeSeriesData(data) {
        // Check if data is an array of objects with date/time and numeric fields
        if (!Array.isArray(data) || !data.length) return null;

        // Look for date/time fields (prefer 'date' or 'timestamp' if they exist)
        const dateFields = Object.keys(data[0]).filter(key => {
            const value = data[0][key];
            return typeof value === 'string' && !isNaN(Date.parse(value));
        });

        if (dateFields.length === 0) return null;

        // Prefer fields named 'date' or 'timestamp', otherwise take the first date field
        const dateField = dateFields.find(field => 
            field.toLowerCase() === 'date' || 
            field.toLowerCase() === 'timestamp'
        ) || dateFields[0];

        // Find numeric fields, excluding those that end with common suffixes for derived values
        const excludeSuffixes = ['_change', '_previous', '_percent', '_ratio', '_delta'];
        const numericFields = Object.keys(data[0]).filter(key => {
            if (key === dateField) return false;
            const value = data[0][key];
            // Check if it's a number and doesn't end with excluded suffixes
            return typeof value === 'number' && 
                   !excludeSuffixes.some(suffix => key.toLowerCase().endsWith(suffix.toLowerCase()));
        });

        if (numericFields.length === 0) return null;

        // Find potential categorical fields (string fields with a reasonable number of unique values)
        const maxCategories = 10; // Maximum number of unique categories to consider
        const categoricalFields = Object.keys(data[0]).filter(key => {
            if (key === dateField || numericFields.includes(key)) return false;
            const values = new Set(data.map(item => item[key]));
            return typeof data[0][key] === 'string' && values.size > 1 && values.size <= maxCategories;
        });

        // If we found categorical fields, use the first one for grouping
        const categoryField = categoricalFields.length > 0 ? categoricalFields[0] : null;

        // Group data by date and category (if exists)
        const groupedData = new Map();
        
        data.forEach(item => {
            const date = new Date(item[dateField]);
            const dateKey = date.toISOString().split('T')[0]; // Group by day
            const categoryKey = categoryField ? item[categoryField] : 'default';
            const groupKey = `${dateKey}|${categoryKey}`;
            
            if (!groupedData.has(groupKey)) {
                groupedData.set(groupKey, {
                    counts: {},
                    sums: {},
                    date,
                    category: categoryKey
                });
            }
            
            const group = groupedData.get(groupKey);
            numericFields.forEach(field => {
                if (typeof item[field] === 'number' && !isNaN(item[field])) {
                    group.sums[field] = (group.sums[field] || 0) + item[field];
                    group.counts[field] = (group.counts[field] || 0) + 1;
                }
            });
        });

        // Convert grouped data back to array format with averages
        const aggregatedData = Array.from(groupedData.values()).map(group => {
            const result = {
                [dateField]: group.date
            };
            if (categoryField) {
                result[categoryField] = group.category;
            }
            numericFields.forEach(field => {
                if (group.counts[field]) {
                    result[field] = group.sums[field] / group.counts[field];
                }
            });
            return result;
        });

        // Sort by date
        aggregatedData.sort((a, b) => a[dateField] - b[dateField]);

        return {
            dateField,
            numericFields,
            categoryField,
            data: aggregatedData
        };
    }

    _createChart(container, timeSeriesData) {
        const { dateField, numericFields, categoryField, data } = timeSeriesData;
        const chartId = `chart-${Date.now()}`;
        const canvas = document.createElement('canvas');
        canvas.id = chartId;

        // Ensure full width by setting style before appending to container
        canvas.style.width = '100%';
        canvas.style.height = '400px';        
        
        container.appendChild(canvas);

        const ctx = canvas.getContext('2d');
        
        // Create datasets based on numeric fields and categories
        let datasets = [];
        if (categoryField) {
            // Get unique categories
            const categories = [...new Set(data.map(item => item[categoryField]))];
            
            // For each numeric field and category combination
            numericFields.forEach(field => {
                categories.forEach(category => {
                    const categoryData = data.filter(item => item[categoryField] === category);
                    datasets.push({
                        label: `${this._formatFieldName(field)} - ${category}`,
                        data: categoryData.map(item => ({ x: new Date(item[dateField]), y: item[field] })),
                        borderColor: this._getRandomColor(),
                        tension: 0.4,
                        fill: false,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        pointHitRadius: 10
                    });
                });
            });
        } else {
            // Original behavior for no categories
            datasets = numericFields.map(field => ({
                label: this._formatFieldName(field),
                data: data.map(item => ({ x: new Date(item[dateField]), y: item[field] })),
                borderColor: this._getRandomColor(),
                tension: 0.4,
                fill: false,
                pointRadius: 3,
                pointHoverRadius: 5,
                pointHitRadius: 10
            }));
        }

        // Determine the time unit based on the data
        const dates = data.map(item => new Date(item[dateField]));
        const timeUnit = this._determineTimeUnit(dates);
        
        // Calculate min and max dates for the scale
        const minDate = new Date(Math.min(...dates));
        const maxDate = new Date(Math.max(...dates));
        
        // Calculate a reasonable number of ticks based on the date range
        const range = maxDate - minDate;
        const numberOfTicks = Math.min(10, data.length);
        
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: timeUnit,
                            displayFormats: {
                                hour: 'MMM d, HH:mm',
                                day: 'MMM d',
                                week: 'MMM d',
                                month: 'MMM yyyy'
                            },
                            tooltipFormat: timeUnit === 'hour' ? 'MMM d, HH:mm' :
                                         timeUnit === 'day' ? 'MMM d, yyyy' :
                                         timeUnit === 'week' ? 'MMM d, yyyy' :
                                         'MMM yyyy'
                        },
                        min: minDate,
                        max: maxDate,
                        ticks: {
                            source: 'auto',
                            autoSkip: true,
                            maxTicksLimit: numberOfTicks
                        },
                        title: {
                            display: true,
                            text: 'Time'
                        }
                    },
                    y: {
                        beginAtZero: false,
                        title: {
                            display: true,
                            text: 'Value'
                        },
                        ticks: {
                            autoSkip: true,
                            maxTicksLimit: 8
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Time Series Data'
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                return `${label}: ${value.toLocaleString(undefined, {maximumFractionDigits: 2})}`;
                            }
                        }
                    },
                    legend: {
                        position: 'top',
                        align: 'center'
                    }
                },
                elements: {
                    point: {
                        radius: 3,
                        hitRadius: 10,
                        hoverRadius: 5
                    },
                    line: {
                        tension: 0.4
                    }
                }
            }
        });

        // Set fixed dimensions for chart container
        const containerWidth = container.clientWidth || container.offsetWidth || 600;
        canvas.style.height = '400px';
        canvas.style.width = containerWidth + 'px';
        
        this.charts.set(chartId, chart);
        
        // Add resize handler to ensure chart adapts to container width changes
        const resizeObserver = new ResizeObserver(() => {
            try {
                // Update canvas width to match container width
                const newWidth = container.clientWidth || container.offsetWidth;
                if (newWidth > 0) {
                    canvas.style.width = newWidth + 'px';
                    chart.resize();
                }
            } catch (e) {
                console.warn('Error resizing chart:', e);
            }
        });
        resizeObserver.observe(container);

        return chartId;
    }

    _formatFieldName(field) {
        // Convert camelCase or snake_case to Title Case
        return field
            .replace(/([A-Z])/g, ' $1') // Split camelCase
            .replace(/_/g, ' ')         // Replace underscores with spaces
            .replace(/\w\S*/g, txt => txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase()); // Title case
    }

    _determineTimeUnit(dates) {
        if (dates.length < 2) return 'day'; // Default to day if not enough data points
        
        // Sort dates to ensure correct interval calculation
        dates.sort((a, b) => a - b);
        
        // Calculate all intervals between consecutive dates
        const intervals = [];
        for (let i = 1; i < dates.length; i++) {
            intervals.push(dates[i] - dates[i-1]);
        }
        
        // Get median interval in milliseconds
        intervals.sort((a, b) => a - b);
        const medianInterval = intervals[Math.floor(intervals.length / 2)];
        
        // Convert to hours for easier comparison
        const hours = medianInterval / (1000 * 60 * 60);
        
        // Determine appropriate unit based on median interval
        // For hourly data (intervals between 30 mins and 4 hours)
        if (hours <= 4) return 'hour';
        
        // For daily data (intervals between 4 hours and 5 days)
        if (hours <= 24 * 5) return 'day';
        
        // For weekly data (intervals between 5 days and 15 days)
        if (hours <= 24 * 15) return 'week';
        
        // For monthly data (intervals greater than 15 days)
        return 'month';
    }

    _getRandomColor() {
        const colors = [
            '#3498db', '#2ecc71', '#e74c3c', '#f1c40f', '#9b59b6',
            '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b'
        ];
        return colors[Math.floor(Math.random() * colors.length)];
    }

    _convertTimeSeriesDataToTable(timeSeriesData) {
        const { dateField, numericFields, data } = timeSeriesData;
        
        // Convert the time series data to a tabular format
        return data.map(item => {
            const row = {
                [dateField]: new Date(item[dateField]).toISOString()
            };
            numericFields.forEach(field => {
                row[field] = item[field];
            });
            return row;
        });
    }

    // Helper method to properly parse CSV rows (handling quoted values)
    _parseCSVRow(row) {
        const values = [];
        let currentValue = '';
        let insideQuotes = false;
        
        for (let i = 0; i < row.length; i++) {
            const char = row[i];
            
            if (char === '"') {
                if (insideQuotes && row[i + 1] === '"') {
                    // Handle escaped quotes
                    currentValue += '"';
                    i++;
                } else {
                    // Toggle quote state
                    insideQuotes = !insideQuotes;
                }
            } else if (char === ',' && !insideQuotes) {
                // End of value
                values.push(currentValue.trim());
                currentValue = '';
            } else {
                currentValue += char;
            }
        }
        
        // Add the last value
        values.push(currentValue.trim());
        return values;
    }
}

export { ToolOutputManager }; 