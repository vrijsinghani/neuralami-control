import { renderJson } from './json-renderer.js';
import { extractJsonFromResponse } from './utils.js';

// Handle plan generation
export function initializePlanGeneration() {
    document.querySelectorAll('.generate-plan').forEach(button => {
        button.addEventListener('click', async function(e) {
            const currentButton = this;
            const url = this.dataset.url;
            const auditId = this.dataset.auditId;
            
            // Show provider selection modal
            const modal = new bootstrap.Modal(document.getElementById('providerModal'));
            modal.show();
            
            // Handle provider selection
            document.getElementById('confirmProvider').onclick = async function() {
                const provider = document.getElementById('llmProvider').value;
                const model = document.getElementById('llmModel').value;
                
                if (!provider || !model) {
                    Swal.fire({
                        title: 'Error',
                        text: 'Please select both provider and model',
                        icon: 'error'
                    });
                    return;
                }
                
                modal.hide();
                
                // Show loading state
                Swal.fire({
                    title: 'Generating Plan',
                    text: 'Please wait while we generate your remediation plan...',
                    allowOutsideClick: false,
                    didOpen: () => {
                        Swal.showLoading();
                    }
                });
                
                try {
                    const response = await fetch('/seo-audit/api/remediation-plan/generate/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': window.csrfToken
                        },
                        body: JSON.stringify({
                            audit_id: auditId,
                            url: url,
                            provider: provider,
                            model: model
                        })
                    });
                    
                    const data = await response.json();
                    console.log('Plan generation response:', data); // Debug log
                    
                    if (!response.ok) {
                        throw new Error(data.error || data.message || 'Server returned ' + response.status + ' ' + response.statusText);
                    }
                    
                    if (!data.success) {
                        throw new Error(data.error || 'Failed to generate plan');
                    }
                    
                    // Close loading state
                    Swal.close();
                    
                    // Show success message
                    Swal.fire({
                        title: 'Success!',
                        text: 'Remediation plan generated successfully',
                        icon: 'success'
                    });
                    
                    // Show/update view plan button
                    const viewBtn = currentButton.parentElement.querySelector('.view-plan');
                    viewBtn.style.display = 'inline-block';
                    viewBtn.dataset.planId = data.plan_id;
                    viewBtn.dataset.plans = JSON.stringify(data.all_plans);
                    
                } catch (error) {
                    console.error('Error:', error);
                    Swal.fire({
                        title: 'Error',
                        text: 'Failed to generate remediation plan: ' + error.message,
                        icon: 'error'
                    });
                }
            };
        });
    });
    
    // Handle provider change to populate models
    document.getElementById('llmProvider').addEventListener('change', async function() {
        const modelSelect = document.getElementById('llmModel');
        const provider = this.value;
        
        if (!provider) {
            modelSelect.innerHTML = '<option value="">Select Provider First</option>';
            modelSelect.disabled = true;
            return;
        }
        
        try {
            // Show loading state
            modelSelect.disabled = true;
            modelSelect.innerHTML = '<option value="">Loading models...</option>';
            
            // Get models for selected provider using URL from template
            const response = await fetch(`${window.llmModelsUrl}?provider=${provider.toLowerCase()}`);
            if (!response.ok) throw new Error('Failed to fetch models');
            
            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Populate model select
            modelSelect.innerHTML = '<option value="">Select Model</option>';
            Object.entries(data).forEach(([modelId, modelData]) => {
                const option = document.createElement('option');
                option.value = modelId;
                option.textContent = modelId;
                modelSelect.appendChild(option);
            });
            
            modelSelect.disabled = false;
            
        } catch (error) {
            console.error('Error loading models:', error);
            modelSelect.innerHTML = '<option value="">Error loading models</option>';
            modelSelect.disabled = true;
            
            Swal.fire({
                title: 'Error',
                text: 'Failed to load models: ' + error.message,
                icon: 'error'
            });
        }
    });
}

// Handle plan viewing
export function initializePlanViewing() {
    document.querySelectorAll('.view-plan').forEach(button => {
        button.addEventListener('click', async function(e) {
            try {
                const response = await fetch(`/seo-audit/api/remediation-plan/${this.dataset.planId}/`);
                if (!response.ok) throw new Error('Failed to fetch plan');
                const data = await response.json();
                
                if (!data.success) {
                    throw new Error(data.error || 'Failed to load plan');
                }

                // Sort plans by creation date, newest first
                const plans = data.all_plans;
                plans.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
                console.log('Sorted plans:', plans);

                // Create plan selection dropdown HTML
                const planOptionsHtml = plans.map((plan, index) => `
                    <div class="mb-3">
                        <input type="radio" class="btn-check" name="plan-version" id="plan-${plan.id}" 
                               value="${plan.id}" ${index === 0 ? 'checked' : ''}>
                        <label class="btn btn-outline-primary w-100 text-start" for="plan-${plan.id}">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <strong>${plan.provider} - ${plan.model}</strong>
                                </div>
                                <small class="text-muted">
                                    ${new Date(plan.created_at).toLocaleString()}
                                </small>
                            </div>
                        </label>
                    </div>
                `).join('');

                // Show plan selection modal
                const result = await Swal.fire({
                    title: 'Select Plan Version',
                    html: `
                        <div class="plan-versions">
                            ${planOptionsHtml}
                        </div>
                    `,
                    showCancelButton: true,
                    confirmButtonText: 'View Selected Plan',
                    cancelButtonText: 'Cancel',
                    width: '600px',
                    preConfirm: () => {
                        const selectedPlanId = document.querySelector('input[name="plan-version"]:checked')?.value;
                        return plans.find(p => p.id.toString() === selectedPlanId);
                    }
                });

                if (result.isConfirmed && result.value) {
                    const selectedPlan = result.value;
                    console.log('Selected plan:', selectedPlan);
                    
                    // Parse content sections
                    const parsedSections = {};
                    if (selectedPlan.content) {
                        // Handle both object and array formats
                        const content = Array.isArray(selectedPlan.content) ? selectedPlan.content : [selectedPlan.content];
                        
                        // First try to parse each section directly
                        for (const item of content) {
                            if (typeof item === 'object' && !Array.isArray(item)) {
                                for (const [key, value] of Object.entries(item)) {
                                    // Skip empty values
                                    if (!value) continue;
                                    
                                    const parsed = extractJsonFromResponse(value);
                                    if (parsed) {
                                        parsedSections[key] = parsed;
                                    }
                                }
                            } else if (typeof item === 'string') {
                                // Try to parse string items directly
                                const parsed = extractJsonFromResponse(item);
                                if (parsed && typeof parsed === 'object') {
                                    Object.entries(parsed).forEach(([key, value]) => {
                                        if (value !== null && value !== undefined) {
                                            parsedSections[key] = value;
                                        }
                                    });
                                }
                            }
                        }
                    }

                    console.log('Final parsed sections:', parsedSections);

                    // Only show modal if we have parsed content
                    if (Object.keys(parsedSections).length > 0) {
                        // Render each section that has data
                        Swal.fire({
                            title: 'Remediation Plan',
                            html: `
                                <div class="text-start">
                                    ${Object.entries(parsedSections)
                                        .filter(([_, value]) => value !== null && (
                                            (Array.isArray(value) && value.length > 0) ||
                                            (typeof value === 'object' && Object.keys(value).length > 0) ||
                                            value.toString().trim() !== ''
                                        ))
                                        .map(([key, value]) => {
                                            const sectionTitle = key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
                                            return `
                                                <div class="mb-4">
                                                    <h6 class="mb-3 border-bottom pb-2">${sectionTitle}</h6>
                                                    ${renderJson(value)}
                                                </div>
                                            `;
                                        }).join('')}
                                </div>
                            `,
                            width: '800px',
                            showCloseButton: true,
                            showConfirmButton: false,
                            customClass: {
                                htmlContainer: 'remediation-plan-modal'
                            }
                        });
                    } else {
                        console.log('No valid sections found');
                        Swal.fire({
                            title: 'Error',
                            text: 'No valid content found in the plan',
                            icon: 'warning'
                        });
                    }
                }
            } catch (error) {
                console.error('Error loading plan:', error);
                Swal.fire({
                    title: 'Error',
                    text: 'Failed to load remediation plan: ' + error.message,
                    icon: 'error'
                });
            }
        });
    });
} 