// Check required dependencies
if (typeof bootstrap === 'undefined') {
    console.error('Bootstrap is required but not loaded');
}
if (typeof markdownit === 'undefined') {
    console.error('markdown-it is required but not loaded');
}
if (typeof jKanban === 'undefined') {
    console.error('jKanban is required but not loaded');
}

// Verify required variables from template
if (typeof crewId === 'undefined') {
    console.error('crewId is required but not defined');
}
if (typeof clientId === 'undefined') {
    console.warn('clientId is not defined'); // warning since it can be null
}

// Initialize markdown
const md = window.markdownit();

// WebSocket configuration and state
const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
let socket = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
let reconnectDelay = 1000;
let pingInterval = null;
let lastPongTime = Date.now();

// Task tracking
let lastUpdatedTaskId = null;

// DOM elements cache
const elements = {
    kanbanContainer: document.getElementById('kanban-tasks'),
    executionNumber: document.getElementById('execution-number'),
    cancelButton: document.getElementById('cancelExecutionBtn'),
    modalContent: document.getElementById('modalContent'),
    contentModal: document.getElementById('contentModal'),
    humanInputModal: document.getElementById('humanInputModal'),
    humanInputText: document.getElementById('humanInputText')
};

// Initialize CSRF token
function getCsrfToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!token) {
        console.error('CSRF token not found');
        return '';
    }
    return token.value;
}

// Rest of your code...
async function fetchActiveExecutions() {
    try {
        const response = await fetch(`/agents/crew/${crewId}/active-executions/`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        
        // Update cancel button based on active executions
        const hasActiveExecution = data.executions && data.executions.length > 0;
        const activeExecutionId = hasActiveExecution ? data.executions[0].execution_id : null;
        updateCancelButton(hasActiveExecution, activeExecutionId);
        
        // Clear boards first
        document.querySelectorAll('.kanban-drag').forEach(board => {
            board.innerHTML = '';
        });
        
        // Repopulate with active executions
        data.executions.forEach(execution => {
            updateKanbanBoard({
                execution_id: execution.execution_id,
                task_id: execution.task_id,
                name: execution.name,
                status: execution.status,
                stages: execution.stages
            });
        });
        
        return data;
    } catch (error) {
        console.error('Error fetching active executions:', error);
        return null;
    }
}

function connectWebSocket() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        console.log('WebSocket already connected');
        return;
    }
    
    // Close existing socket if it exists
    if (socket) {
        socket.close();
    }

    // Clear all kanban boards
    document.querySelectorAll('.kanban-drag').forEach(board => {
        board.innerHTML = '';
    });
    
    try {
        socket = new WebSocket(
            `${wsScheme}://${window.location.host}/ws/crew/${crewId}/kanban/`
        );
        
        socket.onopen = function(e) {
            console.log('WebSocket connection established');
            // Fetch active executions when connection is established
            fetchActiveExecutions();
        };

        socket.onmessage = function(e) {
            try {
                const data = JSON.parse(e.data);
                
                if (data.type === 'pong') {
                    lastPongTime = Date.now(); // Track last pong time
                    return;
                }
                
                if (data.type === 'error') {
                    console.error('Server error:', data.message);
                    return;
                }
                
                // Handle different message types
                switch (data.type) {
                    case 'execution_update':
                        updateKanbanBoard(data);
                        break;
                    case 'agent_step':
                        updateAgentProgress(data);
                        break;
                    case 'task_complete':
                        handleTaskComplete(data);
                        break;
                    case 'human_input_request':
                        handleHumanInputRequest(data);
                        break;
                    case 'execution_status_update':
                        handleWebSocketMessage(data);
                        break;
                    default:
                        console.log('Unknown message type:', data.type);
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        socket.onclose = function(e) {
            console.log('WebSocket connection closed', e.code, e.reason);
            stopPingInterval();
            
            // Don't reconnect if closed normally
            if (e.code === 1000 || e.code === 1001) {
                console.log('WebSocket closed normally');
                return;
            }
            
            // Attempt to reconnect if not at max attempts
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                console.log(`Attempting to reconnect (${reconnectAttempts}/${maxReconnectAttempts})...`);
                
                // Exponential backoff with jitter
                reconnectDelay = Math.min(reconnectDelay * 2, 30000);
                const jitter = Math.random() * 1000;
                setTimeout(connectWebSocket, reconnectDelay + jitter);
            } else {
                console.error('Max reconnection attempts reached');
            }
        };

        socket.onerror = function(e) {
            console.error('WebSocket error:', e);
            // Let onclose handle reconnection
        };
        
    } catch (error) {
        console.error('Error creating WebSocket:', error);
        // Attempt to reconnect on connection error
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(connectWebSocket, reconnectDelay);
        }
    }
}

// Ping interval to keep connection alive
function startPingInterval() {
    stopPingInterval(); // Clear any existing interval
    
    // Send ping every 15 seconds
    pingInterval = setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            // Check if we haven't received a pong in 45 seconds
            if (Date.now() - lastPongTime > 45000) {
                console.log('No pong received for 45 seconds, reconnecting...');
                socket.close();
                connectWebSocket();
                return;
            }
            
            socket.send(JSON.stringify({ type: 'ping' }));
        }
    }, 15000);
}

function stopPingInterval() {
    if (pingInterval) {
        clearInterval(pingInterval);
        pingInterval = null;
    }
}

// Initial connection
connectWebSocket();

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    stopPingInterval();
    if (socket) {
        socket.close();
    }
});

function showContentModal(stageId, content) {
    try {
        const modalContent = document.getElementById('modalContent');
        if (!modalContent) {
            console.error('Modal content element not found');
            return;
        }
        modalContent.innerHTML = md.render(content);
        const modal = new bootstrap.Modal(document.getElementById('contentModal'));
        modal.show();
    } catch (error) {
        console.error('Error showing modal:', error);
    }
}
function updateKanbanBoard(data) {
    console.log('Updating kanban board:', data);
    
    // Only proceed if we have an execution_id
    if (!data.execution_id) {
        console.log('No execution_id provided, skipping update');
        return;
    }
    
    // Update cancel button based on execution status
    if (data.execution_id && data.status) {
        const isActive = ['PENDING', 'RUNNING'].includes(data.status.toUpperCase());
        updateCancelButton(isActive, isActive ? data.execution_id : null);
    }
    
    // Update execution number in header
    const executionSpan = document.getElementById('execution-number');
    if (executionSpan) {
        executionSpan.textContent = ` - Execution #${data.execution_id}`;
    }

    // Get CrewAI task ID for kanban board placement
    let crewaiTaskId = data.crewai_task_id;
    
    // Handle system updates (like PENDING, RUNNING, COMPLETED) or null crewai_task_id
    if (!crewaiTaskId || (typeof crewaiTaskId === 'string' && crewaiTaskId.includes('-'))) {
        // If we have a last updated task ID, use that
        if (lastUpdatedTaskId) {
            crewaiTaskId = lastUpdatedTaskId;
        } else {
            // If no last updated task ID, use the first task board
            const firstTaskBoard = document.querySelector('.kanban-board');
            if (firstTaskBoard) {
                addUpdateToBoard(firstTaskBoard, data);
                return;
            } else {
                console.log('No task boards found for system update');
                return;
            }
        }
    } else if (typeof crewaiTaskId === 'number' || (typeof crewaiTaskId === 'string' && !crewaiTaskId.includes('-'))) {
        // This is a regular task update (number or non-hyphenated string)
        // Update the last updated task ID
        lastUpdatedTaskId = crewaiTaskId;
    }

    // Find the task board for this specific task
    const taskBoard = document.querySelector(`[data-task-id="${crewaiTaskId}"]`);
    if (!taskBoard) {
        console.log('Task board not found for CrewAI task ID:', crewaiTaskId);
        // Fallback to first task board if no specific board found
        const firstTaskBoard = document.querySelector('.kanban-board');
        if (firstTaskBoard) {
            addUpdateToBoard(firstTaskBoard, data);
        }
        return;
    }

    // Add the update to the board
    addUpdateToBoard(taskBoard, data);

    // Update all cards in this task board if status is COMPLETED
    const status = data.status?.toUpperCase();
    if (status === 'COMPLETED') {
        const cards = taskBoard.querySelectorAll('.kanban-item');
        cards.forEach(card => {
            const header = card.querySelector('.card-header');
            if (header) {
                header.className = 'card-header bg-gradient-success text-white p-2';
            }
        });
    }
}


function addUpdateToBoard(taskBoard, data) {
    const kanbanDrag = taskBoard.querySelector('.kanban-drag');
    if (!kanbanDrag) return;

    const stageId = `${data.stage?.stage_type || 'status'}-${Date.now()}`;
    const content = data.stage?.content || '';
    const truncatedContent = content.length > 200 ? content.substring(0, 200) + '...' : content;
    
    const stageHtml = `
        <div class="stage-item" data-execution-id="${data.execution_id}" data-stage-id="${stageId}">
            <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-2">
                    <span class="stage-status status-${(data.stage?.status || data.status)?.toLowerCase()}">
                        ${data.stage?.status || data.status}
                    </span>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <button class="btn btn-link btn-sm p-0 text-muted view-full-content" 
                            data-stage-id="${stageId}"
                            data-content="${encodeURIComponent(content)}"
                            data-metadata="${encodeURIComponent(JSON.stringify(data.stage?.metadata || {}))}"
                            data-status="${data.stage?.status || 'Unknown'}"
                            data-stage-type="${data.stage?.type || 'Unknown'}"
                            data-agent="${data.stage?.agent || 'Unknown'}">
                        <i class="fas fa-info-circle"></i>
                    </button>
                    ${data.stage?.artifacts ? `
                        <button class="btn btn-link btn-sm p-0 text-muted" 
                                onclick="downloadArtifacts('${data.execution_id}', '${stageId}')">
                            <i class="fas fa-download"></i>
                        </button>
                    ` : ''}
                    <span class="time-stamp">${new Date().toLocaleTimeString()}</span>
                </div>
            </div>
            
            <h6 class="stage-title">${data.stage?.title || 'Status Update'}</h6>
            
            <div class="stage-content">
                ${md.render(truncatedContent)}
                <button class="btn btn-sm bg-gradient-info text-white mt-2" 
                        data-stage-id="${stageId}"
                        data-content="${encodeURIComponent(content)}"
                        data-metadata="${encodeURIComponent(JSON.stringify(data.stage?.metadata || {}))}"
                        data-status="${data.stage?.status || 'Unknown'}"
                        data-stage-type="${data.stage?.type || 'Unknown'}"
                        data-agent="${data.stage?.agent || 'Unknown'}">
                    <i class="fas fa-eye me-1"></i>View Details
                </button>
            </div>
            
            ${data.stage?.agent ? `
                <div class="stage-agent">
                    <i class="fas fa-${data.stage.type === 'message' ? 'comment' : 'robot'}"></i>
                    ${data.stage.agent}
                </div>
            ` : ''}
        </div>`;

    kanbanDrag.insertAdjacentHTML('beforeend', stageHtml);
}


function updateAgentProgress(data) {
    console.log('Updating agent progress:', data);
    const execution = document.querySelector(`[data-execution-id="${data.execution_id}"]`);
    if (!execution) return;

    const stageContainer = execution.querySelector('.card-body');
    const agentSection = stageContainer.querySelector('.agent-progress') || 
        stageContainer.insertAdjacentHTML('beforeend', '<div class="agent-progress mt-3"></div>');

    const progressHtml = `
        <div class="alert alert-info mb-2">
            <strong>${data.agent || 'Agent'}</strong>: ${data.content}
        </div>
    `;
    
    if (agentSection.children.length > 5) {
        agentSection.removeChild(agentSection.firstChild);
    }
    agentSection.insertAdjacentHTML('beforeend', progressHtml);
}

function handleTaskComplete(data) {
    console.log('Task completed:', data);
    const execution = document.querySelector(`[data-execution-id="${data.execution_id}"]`);
    if (!execution) return;

    // Show completion message
    const stageContainer = execution.querySelector('.card-body');
    const completionHtml = `
        <div class="alert alert-success mb-0">
            <strong>Task Complete!</strong> ${data.message || ''}
        </div>
    `;
    stageContainer.insertAdjacentHTML('beforeend', completionHtml);
}

function handleHumanInputRequest(data) {
    console.log('Human input requested:', data);
    showInputModal(data.execution_id);
}

function getCsrfToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!token) {
        console.error('CSRF token not found');
        return '';
    }
    return token.value;
}

function showStartExecutionModal() {
    Swal.fire({
        title: 'Start Crew Execution',
        html: `
            <div class="text-start">
                <p>You are about to start a new crew execution.</p>
                ${!clientId ? '<p class="text-danger">Warning: No client selected. Please select a client first.</p>' : ''}
                <p>The crew will begin processing tasks in sequence.</p>
            </div>
        `,
        icon: 'info',
        showCancelButton: true,
        confirmButtonText: 'Start Execution',
        cancelButtonText: 'Cancel',
        customClass: {
            confirmButton: 'btn bg-gradient-success',
            cancelButton: 'btn bg-gradient-danger'
        },
        buttonsStyling: false
    }).then((result) => {
        if (result.isConfirmed) {
            startExecution();
        }
    });
}

function startExecution() {
    const csrfToken = getCsrfToken();
    
    if (!csrfToken) {
        Swal.fire({
            title: 'Error',
            text: 'CSRF token not found. Please refresh the page.',
            icon: 'error',
            customClass: {
                confirmButton: 'btn bg-gradient-primary'
            },
            buttonsStyling: false
        });
        return;
    }

    if (!clientId) {
        Swal.fire({
            title: 'Error',
            text: 'No client selected. Please select a client first.',
            icon: 'error',
            customClass: {
                confirmButton: 'btn bg-gradient-primary'
            },
            buttonsStyling: false
        });
        return;
    }

    // Clear all kanban boards
    const kanbanBoards = document.querySelectorAll('.kanban-board');
    kanbanBoards.forEach(board => {
        const kanbanDrag = board.querySelector('.kanban-drag');
        if (kanbanDrag) {
            kanbanDrag.innerHTML = '';
        }
    });

    // Reset execution number
    const executionSpan = document.getElementById('execution-number');
    if (executionSpan) {
        executionSpan.textContent = '';
    }

    fetch(`/agents/crew/${crewId}/start-execution/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            client_id: clientId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            Swal.fire({
                title: 'Success',
                text: 'Execution started successfully',
                icon: 'success',
                customClass: {
                    confirmButton: 'btn bg-gradient-success'
                },
                buttonsStyling: false
            });
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        Swal.fire({
            title: 'Error',
            text: 'Error starting execution: ' + error.message,
            icon: 'error',
            customClass: {
                confirmButton: 'btn bg-gradient-primary'
            },
            buttonsStyling: false
        });
    });
}

function showInputModal(executionId) {
    const modal = new bootstrap.Modal(document.getElementById('humanInputModal'));
    document.getElementById('humanInputModal').dataset.executionId = executionId;
    modal.show();
}

function submitHumanInput() {
    const executionId = document.getElementById('humanInputModal').dataset.executionId;
    const inputText = document.getElementById('humanInputText').value;
    const csrfToken = getCsrfToken();
    
    if (!csrfToken) {
        alert('Error: CSRF token not found. Please refresh the page.');
        return;
    }
    
    fetch(`/agents/crew/execution/${executionId}/input/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ input: inputText })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            bootstrap.Modal.getInstance(document.getElementById('humanInputModal')).hide();
            document.getElementById('humanInputText').value = '';
        } else {
            alert('Error submitting input');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error submitting input');
    });
}

// Update the event listener to handle both .view-full-content and the View Details button
document.addEventListener('click', function(e) {
    // Check if clicked element is either the info icon or the View Details button
    if (e.target.matches('.view-full-content') || e.target.closest('.btn-sm.bg-gradient-info')) {
        const targetElement = e.target.matches('.view-full-content') ? 
            e.target : 
            e.target.closest('.btn-sm.bg-gradient-info');
            
        const stageData = {
            stage: {
                stage_id: targetElement.dataset.stageId,
                content: decodeURIComponent(targetElement.dataset.content),
                metadata: JSON.parse(decodeURIComponent(targetElement.dataset.metadata || '{}')),
                status: targetElement.dataset.status || 'Unknown',
                type: targetElement.dataset.stageType || 'Unknown',
                agent: targetElement.dataset.agent || 'Unknown'
            }
        };
        
        showDetailsModal(stageData.stage.stage_id, stageData);
    }
});

// Update showDetailsModal to ensure modal elements exist
function showDetailsModal(stageId, data) {
    try {
        // Parse the data if it's a string
        const stageData = typeof data === 'string' ? JSON.parse(data) : data;
        
        // Get modal elements
        const modalStatus = document.getElementById('modalStatus');
        const modalStageType = document.getElementById('modalStageType');
        const modalAgent = document.getElementById('modalAgent');
        const modalContent = document.getElementById('modalContent');
        const detailsModal = document.getElementById('detailsModal');
        
        // Check if all required elements exist
        if (!modalStatus || !modalStageType || !modalAgent || !modalContent || !detailsModal) {
            console.error('Required modal elements not found');
            return;
        }
        
        // Set modal content
        modalStatus.textContent = stageData.stage?.status || stageData.status || 'Unknown';
        modalStageType.textContent = stageData.stage?.type || 'Unknown';
        modalAgent.textContent = stageData.stage?.agent || 'Unknown';
        modalContent.innerHTML = md.render(stageData.stage?.content || '');
        
        // Store the data for export
        detailsModal.dataset.exportData = JSON.stringify(stageData);
        
        // Show the modal
        const modal = new bootstrap.Modal(detailsModal);
        modal.show();
    } catch (error) {
        console.error('Error showing modal:', error);
    }
}

function exportDetails() {
    const modal = document.getElementById('detailsModal');
    const data = JSON.parse(modal.dataset.exportData || '{}');
    
    // Create export content
    const content = [
        `# Stage Details\n`,
        `## Basic Information`,
        `- Status: ${data.stage?.status || data.status || 'Unknown'}`,
        `- Stage Type: ${data.stage?.type || 'Unknown'}`,
        `- Agent: ${data.stage?.agent || 'Unknown'}\n`,
        `## Content`,
        `${data.stage?.content || ''}\n`
    ].join('\n');
    
    // Create and trigger download
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stage-details-${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// Function to show/hide cancel button based on execution status
function updateCancelButton(hasActiveExecution, executionId) {
    console.log('updateCancelButton:', { hasActiveExecution, executionId });  // Debug log
    const cancelBtn = document.getElementById('cancelExecutionBtn');
    if (!cancelBtn) {
        console.error('Cancel button not found');  // Debug log
        return;
    }
    cancelBtn.style.display = hasActiveExecution ? 'block' : 'none';
    if (hasActiveExecution) {
        cancelBtn.setAttribute('data-execution-id', executionId);
    } else {
        cancelBtn.removeAttribute('data-execution-id');
    }
}

// Add cancel execution functionality
async function cancelExecution(executionId) {
    try {
        const result = await Swal.fire({
            title: 'Cancel Execution',
            html: `
                <div class="text-start">
                    <p>Are you sure you want to cancel this execution?</p>
                    <p class="text-warning">This action cannot be undone.</p>
                </div>
            `,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Yes, Cancel Execution',
            cancelButtonText: 'No, Keep Running',
            customClass: {
                confirmButton: 'btn bg-gradient-danger me-3',
                cancelButton: 'btn bg-gradient-secondary ms-3',
                actions: 'my-3'
            },
            buttonsStyling: false
        });

        if (result.isConfirmed) {
            const response = await fetch(`/agents/execution/${executionId}/cancel/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'Content-Type': 'application/json',
                },
            });

            if (!response.ok) {
                throw new Error('Failed to cancel execution');
            }
            
            Swal.fire({
                title: 'Execution Cancelled',
                text: 'The execution has been cancelled successfully.',
                icon: 'success',
                customClass: {
                    confirmButton: 'btn bg-gradient-success'
                },
                buttonsStyling: false
            });
            
            updateCancelButton(false);
        }
    } catch (error) {
        console.error('Error cancelling execution:', error);
        Swal.fire({
            title: 'Error',
            text: 'Failed to cancel execution. Please try again.',
            icon: 'error',
            customClass: {
                confirmButton: 'btn bg-gradient-primary'
            },
            buttonsStyling: false
        });
    }
}

// Add click handler for cancel button
document.getElementById('cancelExecutionBtn').addEventListener('click', function() {
    const executionId = this.getAttribute('data-execution-id');
    if (executionId) {
            cancelExecution(executionId);
        }
    });

function handleWebSocketMessage(data) {
    if (data.type === 'execution_status_update' || data.type === 'execution_update') {
        // Update cancel button based on execution status
        const isActive = ['PENDING', 'RUNNING'].includes(data.status.toUpperCase());
        updateCancelButton(isActive, isActive ? data.execution_id : null);
    }
}
// Initial fetch of active executions and setup of cancel button
document.addEventListener('DOMContentLoaded', async function() {
    const data = await fetchActiveExecutions();
    const hasActiveExecution = data && data.executions && data.executions.length > 0;
    const activeExecutionId = hasActiveExecution ? data.executions[0].execution_id : null;
    updateCancelButton(hasActiveExecution, activeExecutionId);
});

