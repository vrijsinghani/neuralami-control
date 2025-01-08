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

// Helper function to clean JSON string
function cleanJsonString(str) {
    if (typeof str !== 'string') return str;
    
    // Remove control characters
    str = str.replace(/[\u0000-\u001F\u007F-\u009F]/g, '');
    
    // Fix escaped newlines
    str = str.replace(/\\n/g, ' ');
    
    // Fix double quotes inside strings
    str = str.replace(/(?<!\\)\\"/g, '"');
    
    return str;
}

// Helper function to extract JSON from LLM response
export function extractJsonFromResponse(text) {
    try {
        // If already an object, return it
        if (typeof text === 'object' && text !== null && !Array.isArray(text)) {
            return text;
        }

        // If it's a string containing JSON
        if (typeof text === 'string') {
            // Clean the JSON string
            const cleanedText = cleanJsonString(text);
            
            try {
                // Try parsing as raw JSON first
                return JSON.parse(cleanedText);
            } catch (e) {
                console.log('Failed to parse cleaned JSON directly:', e);
                
                // Try to extract JSON from markdown code blocks
                const jsonMatch = cleanedText.match(/```json\n?([\s\S]*?)\n?```/);
                if (jsonMatch && jsonMatch[1]) {
                    const jsonStr = cleanJsonString(jsonMatch[1]);
                    try {
                        return JSON.parse(jsonStr);
                    } catch (e) {
                        console.log('Failed to parse JSON from code block:', e);
                    }
                }
                
                // Try to extract specific sections
                const sections = ['critical_issues', 'high_priority', 'medium_priority', 'low_priority', 'summary', 'impact_analysis', 'recommendations', 'validation_steps'];
                const extractedData = {};
                
                for (const section of sections) {
                    const sectionMatch = cleanedText.match(new RegExp(`"${section}"\\s*:\\s*(\\[[^\\]]*\\]|{[^}]*}|"[^"]*")`));
                    if (sectionMatch && sectionMatch[1]) {
                        try {
                            extractedData[section] = JSON.parse(cleanJsonString(sectionMatch[1]));
                        } catch (e) {
                            console.log(`Failed to parse ${section} section:`, e);
                        }
                    }
                }
                
                if (Object.keys(extractedData).length > 0) {
                    return extractedData;
                }
            }
        }

        // If it's an array, process the first element
        if (Array.isArray(text) && text[0]) {
            return extractJsonFromResponse(text[0]);
        }

        throw new Error('Could not extract valid JSON from response');
    } catch (e) {
        console.error('JSON extraction failed:', e);
        // Return a default structure instead of null
        return {
            critical_issues: [],
            high_priority: [],
            medium_priority: [],
            low_priority: [],
            summary: 'Error parsing plan data',
            impact_analysis: 'Error parsing plan data',
            recommendations: [],
            validation_steps: []
        };
    }
} 