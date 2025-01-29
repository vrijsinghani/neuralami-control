// Helper function to safely escape HTML and preserve backticks
export function escapeHtml(str) {
    if (typeof str !== 'string') return str;
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;')
        .replace(/`(.*?)`/g, '<code>$1</code>');
}

// Helper function to decode HTML entities
function decodeHtmlEntities(str) {
    if (typeof str !== 'string') return str;
    const textarea = document.createElement('textarea');
    textarea.innerHTML = str;
    return textarea.value;
}

// Helper function to clean JSON string
function cleanJsonString(str) {
    if (typeof str !== 'string') return str;
    
    // First pass: Extract JSON from markdown if present
    let cleaned = str;
    const codeBlockMatch = str.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
    if (codeBlockMatch) {
        cleaned = codeBlockMatch[1].trim();
    }
    
    // Second pass: Clean up the string
    cleaned = cleaned
        // Remove control characters
        .replace(/[\u0000-\u001F\u007F-\u009F]/g, '')
        // Normalize newlines and whitespace
        .replace(/\r?\n/g, ' ')
        .replace(/\s+/g, ' ')
        // Handle HTML tags by preserving them
        .replace(/(<[^>]*>)/g, match => match.replace(/"/g, '&quot;'))
        .trim();

    // Third pass: Decode HTML entities in the cleaned string
    cleaned = decodeHtmlEntities(cleaned);
    
    return cleaned;
}

// Helper function to find the most complete JSON structure
function findMostCompleteJson(matches) {
    let bestMatch = null;
    let maxScore = -1;

    for (const match of matches) {
        try {
            const cleanedMatch = cleanJsonString(match);
            const parsed = JSON.parse(cleanedMatch);
            
            // Score the completeness of the JSON
            const score = calculateJsonScore(parsed);
            if (score > maxScore) {
                maxScore = score;
                bestMatch = parsed;
            }
        } catch (e) {
            console.log('Failed to parse match:', e);
            continue;
        }
    }

    return bestMatch;
}

// Helper function to score JSON completeness
function calculateJsonScore(obj) {
    if (!obj) return 0;
    let score = 0;

    if (Array.isArray(obj)) {
        score += obj.length;
        for (const item of obj) {
            score += calculateJsonScore(item);
        }
    } else if (typeof obj === 'object') {
        const keys = Object.keys(obj);
        score += keys.length;
        for (const key of keys) {
            if (key !== 'metadata' && key !== 'model' && key !== 'usage') {
                score += calculateJsonScore(obj[key]) * 2; // Give more weight to actual content
            }
        }
    }

    return score;
}

// Helper function to extract JSON from any format
export function extractJsonFromResponse(input) {
    try {
        // Handle null/undefined
        if (!input) return null;

        // If already a parsed object/array, return as is
        if (typeof input === 'object') {
            // If array, try each element
            if (Array.isArray(input)) {
                let bestResult = null;
                let maxScore = -1;

                for (const item of input) {
                    const result = extractJsonFromResponse(item);
                    if (result) {
                        const score = calculateJsonScore(result);
                        if (score > maxScore) {
                            maxScore = score;
                            bestResult = result;
                        }
                    }
                }
                return bestResult;
            }
            // If object and not null, filter out metadata
            if (input !== null) {
                const {metadata, model, usage, ...content} = input;
                return Object.keys(content).length > 0 ? content : input;
            }
        }

        // If string, try to parse as JSON
        if (typeof input === 'string') {
            // Clean the string
            const cleaned = cleanJsonString(input);
            
            try {
                // Try direct parse first
                const parsed = JSON.parse(cleaned);
                const {metadata, model, usage, ...content} = parsed;
                return Object.keys(content).length > 0 ? content : parsed;
            } catch (e) {
                // Try to find and parse JSON-like structures
                const matches = cleaned.match(/(\{[\s\S]*?\}|\[[\s\S]*?\])/g) || [];
                
                if (matches.length > 0) {
                    // Find the most complete JSON structure
                    const bestMatch = findMostCompleteJson(matches);
                    if (bestMatch) {
                        const {metadata, model, usage, ...content} = bestMatch;
                        return Object.keys(content).length > 0 ? content : bestMatch;
                    }
                }
            }
        }

        return null;
    } catch (error) {
        console.error('JSON extraction failed:', error);
        return null;
    }
} 