import { renderJson } from './json-renderer.js';
import { extractJsonFromResponse } from './utils.js';

// Handle plan generation
export function initializePlanGeneration() {
    document.querySelectorAll('.generate-plan').forEach(button => {
        button.addEventListener('click', async function(e) {
            const currentButton = this;
            const url = this.dataset.url;
            const auditId = this.dataset.auditId;
            
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
                const response = await fetch('/seo-audit/api/remediation-plan/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.csrfToken
                    },
                    body: JSON.stringify({
                        audit_id: auditId,
                        url: url
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
        });
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
                    
                    // Show plan content modal
                    const analysisData = extractJsonFromResponse(selectedPlan.content.analysis[0]);
                    const recommendationsData = extractJsonFromResponse(selectedPlan.content.recommendations[0]);
                    const validationStepsData = extractJsonFromResponse(selectedPlan.content.validation_steps[0]);
                    
                    console.log('Parsed data:', { analysisData, recommendationsData, validationStepsData });
                    
                    Swal.fire({
                        title: 'Remediation Plan',
                        html: `
                            <div class="text-start">
                                <div class="mb-4">
                                    <h6 class="mb-3 border-bottom pb-2">Analysis</h6>
                                    ${analysisData.critical_issues?.length ? renderJson(analysisData.critical_issues) : '<p>No critical issues found.</p>'}
                                    ${analysisData.high_priority?.length ? renderJson(analysisData.high_priority) : '<p>No high priority issues found.</p>'}
                                    ${analysisData.medium_priority?.length ? renderJson(analysisData.medium_priority) : '<p>No medium priority issues found.</p>'}
                                    ${analysisData.low_priority?.length ? renderJson(analysisData.low_priority) : '<p>No low priority issues found.</p>'}
                                    <div class="mt-3">
                                        <strong>Summary:</strong>
                                        <p>${analysisData.summary || 'No summary available.'}</p>
                                    </div>
                                    <div class="mt-3">
                                        <strong>Impact Analysis:</strong>
                                        <p>${analysisData.impact_analysis || 'No impact analysis available.'}</p>
                                    </div>
                                </div>
                                
                                <div class="mb-4">
                                    <h6 class="mb-3 border-bottom pb-2">Recommendations</h6>
                                    ${recommendationsData.recommendations?.length ? renderJson(recommendationsData.recommendations) : '<p>No recommendations available.</p>'}
                                </div>
                                
                                <div>
                                    <h6 class="mb-3 border-bottom pb-2">Validation Steps</h6>
                                    ${validationStepsData.validation_steps?.length ? renderJson(validationStepsData.validation_steps) : '<p>No validation steps available.</p>'}
                                </div>
                            </div>
                        `,
                        width: '800px',
                        showCloseButton: true,
                        showConfirmButton: false,
                        customClass: {
                            htmlContainer: 'remediation-plan-modal'
                        }
                    });
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