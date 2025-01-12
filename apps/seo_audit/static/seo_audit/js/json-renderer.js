import { escapeHtml } from './utils.js';

// Generic JSON to HTML renderer
export function renderJson(data, level = 0, parentKey = '') {
    if (data === null || data === undefined) {
        return '';
    }

    // Handle different data types
    if (Array.isArray(data)) {
        if (data.length === 0) return '';  // Don't show empty arrays
        
        // Special handling for arrays of objects
        if (typeof data[0] === 'object' && data[0] !== null) {
            return data.map(item => {
                // Check if this is a validation step object
                if (item.recommendation_id && item.validation_steps) {
                    return `
                        <div class="mb-3 p-3 border rounded">
                            <div class="mb-2">
                                <strong>For: </strong>
                                <span class="text-primary">${escapeHtml(item.recommendation_id)}</span>
                            </div>
                            ${item.validation_steps ? `
                                <div class="mb-2">
                                    <strong>Steps:</strong>
                                    <ul class="mb-2 list-unstyled ps-3">
                                        ${item.validation_steps.map(step => 
                                            `<li class="mb-1">• ${escapeHtml(step)}</li>`
                                        ).join('')}
                                    </ul>
                                </div>
                            ` : ''}
                            ${item.success_criteria ? `
                                <div class="mb-2">
                                    <strong>Success Criteria:</strong>
                                    <div class="ps-3">${escapeHtml(item.success_criteria)}</div>
                                </div>
                            ` : ''}
                            ${item.tools_needed ? `
                                <div>
                                    <strong>Tools Needed:</strong>
                                    <div class="d-flex flex-wrap gap-1 ps-3">
                                        ${item.tools_needed.map(tool => 
                                            `<span class="badge bg-secondary">${escapeHtml(tool)}</span>`
                                        ).join(' ')}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    `;
                }
                
                // Check if this is a recommendation object
                if (item.issue || item.solution || item.implementation_steps) {
                    return `
                        <div class="mb-3 p-3 border rounded">
                            <div class="mb-2">
                                <h6 class="mb-2">${escapeHtml(item.issue || '')}</h6>
                                <p class="mb-3">${escapeHtml(item.solution || '')}</p>
                            </div>
                            ${item.implementation_steps ? `
                                <div class="mb-2">
                                    <strong>Implementation Steps:</strong>
                                    <ul class="mb-2 list-unstyled ps-3">
                                        ${item.implementation_steps.map(step => 
                                            `<li class="mb-1">• ${escapeHtml(step)}</li>`
                                        ).join('')}
                                    </ul>
                                </div>
                            ` : ''}
                            <div class="d-flex justify-content-between">
                                ${item.priority ? `
                                    <span class="badge bg-${
                                        (item.priority + '').toLowerCase() === 'high' ? 'danger' : 
                                        (item.priority + '').toLowerCase() === 'medium' ? 'warning' : 'info'
                                    }">${escapeHtml(item.priority)}</span>
                                ` : ''}
                                ${item.estimated_effort ? `
                                    <small class="text-muted">Effort: ${escapeHtml(item.estimated_effort)}</small>
                                ` : ''}
                            </div>
                        </div>
                    `;
                }
                
                // Default object rendering
                if (Object.keys(item).length === 0) return '';  // Don't render empty objects
                return `
                    <div class="mb-2">
                        ${renderJson(item, level + 2, parentKey)}
                    </div>
                `;
            }).join('');
        }
        
        // Regular arrays
        return `
            <ul class="list-unstyled ps-3 mb-0">
                ${data.map(item => `
                    <li class="mb-1">• ${typeof item === 'string' ? escapeHtml(item) : renderJson(item, level + 2, parentKey)}</li>
                `).join('')}
            </ul>
        `;
    }

    if (typeof data === 'object') {
        const entries = Object.entries(data)
            .filter(([key]) => !['model', 'usage', 'provider'].includes(key))
            .filter(([_, value]) => {
                // Filter out empty objects and arrays
                if (value === null || value === undefined) return false;
                if (Array.isArray(value) && value.length === 0) return false;
                if (typeof value === 'object' && Object.keys(value).length === 0) return false;
                return true;
            });
        
        if (entries.length === 0) return '';  // Don't show empty objects
        
        return entries.map(([key, value]) => {
            // Format key for display
            const formattedKey = key.split('_')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                .join(' ');
            
            // Special handling for recommendations and validation steps sections
            if ((key === 'recommendations' || key === 'validation_steps') && Array.isArray(value)) {
                // Only render if there's actual content
                const content = renderJson(value, level, key);  // Pass the current key
                if (!content) return '';
                
                // Only show header if it's not already in the content
                const showHeader = !parentKey || parentKey !== key;
                return `
                    <div class="mb-4">
                        ${showHeader ? `<h5 class="mb-3">${formattedKey}</h5>` : ''}
                        ${content}
                    </div>
                `;
            }
            
            // Skip rendering if the value is empty
            if (typeof value === 'object' && Object.keys(value).length === 0) return '';
            
            return `
                <div class="mb-2">
                    <strong>${formattedKey}:</strong>
                    ${typeof value === 'string' ? `<span>${escapeHtml(value)}</span>` : renderJson(value, level + 2, key)}
                </div>
            `;
        }).join('');
    }

    // Handle primitive values
    if (typeof data === 'string') {
        return `<span>${escapeHtml(data)}</span>`;
    }
    
    if (typeof data === 'number' || typeof data === 'boolean') {
        return `<span class="text-info">${data}</span>`;
    }

    return `<span class="text-muted">${escapeHtml(String(data))}</span>`;
}