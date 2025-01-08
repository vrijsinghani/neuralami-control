import { escapeHtml } from './utils.js';

// Generic JSON to HTML renderer
export function renderJson(data, level = 0) {
    if (data === null || data === undefined) {
        return '<span class="text-muted">null</span>';
    }

    // Handle different data types
    if (Array.isArray(data)) {
        if (data.length === 0) return '<span class="text-muted">[]</span>';
        
        // Special handling for arrays of objects
        if (typeof data[0] === 'object' && data[0] !== null) {
            return data.map(item => {
                // Check if this is a validation step object
                if (item.recommendation_id || item.validation_steps) {
                    return `
                        <div class="mb-3 p-3 border rounded">
                            <div class="mb-2">
                                <strong>For: </strong>
                                <span class="text-primary">${item.recommendation_id || 'Unknown'}</span>
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
                if (item.issue || item.solution) {
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
                return `
                    <div class="mb-2">
                        ${renderJson(item, level + 2)}
                    </div>
                `;
            }).join('');
        }
        
        // Regular arrays
        return `
            <ul class="list-unstyled ps-3 mb-0">
                ${data.map(item => `
                    <li class="mb-1">• ${typeof item === 'string' ? escapeHtml(item) : renderJson(item, level + 2)}</li>
                `).join('')}
            </ul>
        `;
    }

    if (typeof data === 'object') {
        const entries = Object.entries(data)
            .filter(([key]) => !['model', 'usage', 'provider'].includes(key));
        
        if (entries.length === 0) return '<span class="text-muted">{}</span>';
        
        return entries.map(([key, value]) => {
            // Skip rendering the key if it's a nested object we handle specially
            if ((key === 'recommendations' || key === 'validation_steps') && Array.isArray(value)) {
                return renderJson(value, level);
            }
            
            // Format key for display
            const formattedKey = key.split('_')
                .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                .join(' ');
            
            return `
                <div class="mb-2">
                    <strong>${formattedKey}:</strong>
                    ${typeof value === 'string' ? `<span>${escapeHtml(value)}</span>` : renderJson(value, level + 2)}
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