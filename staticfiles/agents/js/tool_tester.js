/**
 * Tool tester client handling
 * Handles client selection and attribute population for tool testing
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize client dropdown if tool schema requires client-related fields
    initClientDropdown();
    
    // Set up form submission handling for client attributes
    const toolForm = document.getElementById('tool-test-form');
    const clientAttributesInput = document.getElementById('client-attributes');
    
    if (toolForm && clientAttributesInput) {
        toolForm.addEventListener('submit', function(e) {
            // Check if client attributes are needed but not provided
            if (hasClientRelatedProperties() && 
                (!clientAttributesInput.value || clientAttributesInput.value === '{}')) {
                
                const clientSelect = document.getElementById('client-select');
                if (clientSelect && clientSelect.value === '') {
                    e.preventDefault();
                    alert('Please select a client to populate required attributes.');
                    return false;
                }
            }
        });
    }
});

/**
 * Initialize the client dropdown
 * Fetches clients and sets up the dropdown
 */
function initClientDropdown() {
    // Wait for tool schema to be loaded
    const checkSchema = setInterval(() => {
        if (window.toolSchema) {
            clearInterval(checkSchema);
            
            // Check if the tool requires client-related fields
            if (hasClientRelatedProperties()) {
                // Show client selection container
                const clientSelectionContainer = document.getElementById('client-selection-container');
                if (clientSelectionContainer) {
                    clientSelectionContainer.style.display = 'block';
                }
                
                // Fetch clients for the dropdown
                fetchClients();
                
                // Set up client selection handling
                const clientSelect = document.getElementById('client-select');
                if (clientSelect) {
                    clientSelect.addEventListener('change', handleClientSelection);
                }
            }
        }
    }, 100);
}

/**
 * Check if the tool schema contains client-related properties
 * This includes properties like client_id, analytics_property_id, etc.
 */
function hasClientRelatedProperties() {
    if (!window.toolSchema || !window.toolSchema.properties) {
        return false;
    }
    
    const properties = window.toolSchema.properties;
    
    // List of known client-related property names
    const clientRelatedProps = [
        'client_id', 
        'analytics_property_id', 
        'analytics_credentials',
        'search_console_property_url',
        'search_console_credentials',
        'website_url',
        'client_name'
    ];
    
    // Check if any of the client-related properties are in the schema
    return clientRelatedProps.some(prop => prop in properties);
}

/**
 * Fetch clients from the server
 */
function fetchClients() {
    fetch('/agents/tools/clients/')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(clients => {
            populateClientDropdown(clients);
        })
        .catch(error => {
            console.error('Error fetching clients:', error);
            const clientSelect = document.getElementById('client-select');
            if (clientSelect) {
                clientSelect.innerHTML = '<option value="">Failed to load clients</option>';
            }
        });
}

/**
 * Populate the client dropdown with fetched clients
 */
function populateClientDropdown(clients) {
    const clientSelect = document.getElementById('client-select');
    if (!clientSelect) return;
    
    clientSelect.innerHTML = '<option value="">-- Select a client --</option>';
    
    clients.forEach(client => {
        const option = document.createElement('option');
        option.value = client.id;
        option.textContent = client.name;
        if (client.website_url) {
            option.textContent += ` (${client.website_url})`;
        }
        clientSelect.appendChild(option);
    });
}

/**
 * Handle client selection
 * Fetches client attributes and populates form fields
 */
function handleClientSelection() {
    const clientSelect = document.getElementById('client-select');
    const clientId = clientSelect.value;
    const loadingIndicator = document.getElementById('loading-indicator');
    
    if (!clientId) {
        // Clear client attributes if no client is selected
        document.getElementById('client-attributes').value = '';
        return;
    }
    
    // Show loading indicator
    if (loadingIndicator) {
        loadingIndicator.style.display = 'block';
    }
    
    // Fetch client attributes
    fetch(`/agents/tools/client-attributes/${clientId}/`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(attributes => {
            // Store client attributes in hidden input
            document.getElementById('client-attributes').value = JSON.stringify(attributes);
            
            // Auto-fill form fields with client attributes
            autoFillClientFields(attributes);
            
            // Hide loading indicator
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error fetching client attributes:', error);
            
            // Hide loading indicator
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            
            // Show error message
            alert('Failed to load client attributes. Please try again.');
        });
}

/**
 * Auto-fill form fields with client attributes
 */
function autoFillClientFields(attributes) {
    if (!window.toolSchema || !window.toolSchema.properties) return;
    
    const properties = window.toolSchema.properties;
    
    // Map of schema properties to client attribute keys
    const propertyMappings = {
        'client_id': 'client_id',
        'client_name': 'client_name',
        'website_url': 'website_url',
        'analytics_property_id': 'analytics_property_id',
        'analytics_credentials': 'analytics_credentials',
        'search_console_property_url': 'search_console_property_url',
        'search_console_credentials': 'search_console_credentials',
        'targeted_keywords': 'targeted_keywords'
    };
    
    // For each property in the schema, check if we have a matching attribute
    Object.keys(properties).forEach(propName => {
        if (propName in propertyMappings) {
            const attrName = propertyMappings[propName];
            const input = document.getElementById(propName);
            
            if (input && attributes[attrName] !== undefined) {
                const value = attributes[attrName];
                
                if (properties[propName].type === 'object' && typeof value === 'object') {
                    // For object types (like credentials), stringify the value
                    input.value = JSON.stringify(value, null, 2);
                } else {
                    // For other types, just set the value
                    input.value = value;
                }
                
                // Add highlighting effect to show auto-filled fields
                input.classList.add('autofilled');
                setTimeout(() => {
                    input.classList.remove('autofilled');
                }, 2000);
            }
        }
    });
} 