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

// Initialize markdown-it globally
window.md = window.markdownit();

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
let lastUpdatedTaskIndex = null;  // Track last used task index

// DOM elements cache
const elements = {
    kanbanContainer: document.getElementById('kanban-tasks'),
    executionNumber: document.getElementById('execution-number'),
    cancelButton: document.getElementById('cancelExecutionBtn')
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

// Import ContentExpander module
import { ContentExpander } from './modules/content_expander.js';
console.log('ContentExpander imported');
// Initialize content expander
const contentExpander = new ContentExpander();
console.log('ContentExpander initialized', contentExpander);
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
            const data = JSON.parse(e.data);
            
            if (!data.type) {
                console.error("Message missing type:", data);
                return;
            }
            
            handleWebSocketMessage(data);
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


function updateKanbanBoard(data) {
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

    // Use task_index for board placement, fallback to last used index
    const taskIndex = data.task_index !== undefined ? data.task_index : lastUpdatedTaskIndex;
    console.log('Updating board with task index:', taskIndex, '(from data:', data.task_index, ', last:', lastUpdatedTaskIndex, ')');
    
    // Get all kanban boards in order
    const taskBoards = document.querySelectorAll('.kanban-board');
    let targetBoard;
    
    if (taskIndex !== null && taskIndex !== undefined && taskIndex < taskBoards.length) {
        targetBoard = taskBoards[taskIndex];
        lastUpdatedTaskIndex = taskIndex;  // Update the last used index
        console.log('Found target board for index:', taskIndex);
    } else {
        // Fallback to first board if no valid index available
        targetBoard = taskBoards[0];
        console.log('Using first board as fallback, no valid task index');
    }

    if (targetBoard) {
        addUpdateToBoard(targetBoard, data);
    } else {
        console.log('No board found for update');
    }
}

function handleHumanInputSubmit(button) {
    const stageItem = button.closest('.stage-item');
    const executionId = stageItem.getAttribute('data-execution-id');
    console.log("Submitting human input for execution:", executionId);
    
    if (!executionId) {
        console.error("No execution ID found for human input submission");
        alert('Error: Could not determine execution ID');
        return;
    }

    const textarea = button.parentElement.querySelector('textarea');
    const input = textarea.value.trim();
    
    if (!input) {
        alert('Please enter a response before submitting.');
        return;
    }
    
    // Disable the button and textarea while submitting
    button.disabled = true;
    textarea.disabled = true;
    
    console.log(`Sending human input to /agents/crew/execution/${executionId}/input/`);
    
    fetch(`/agents/crew/execution/${executionId}/input/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            input: input
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Network response was not ok: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("Successfully submitted human input:", data);
        // Clear and disable the input after successful submission
        textarea.value = '';
    })
    .catch(error => {
        console.error('Error submitting human input:', error);
        alert('Failed to submit input. Please try again.');
        // Re-enable the button and textarea on error
        button.disabled = false;
        textarea.disabled = false;
    });
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
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

function handleWebSocketMessage(data) {
    console.log('Received WebSocket message:', data);
    
    try {
        if (data.type === 'execution_update') {
            // For all updates, use task_index if provided, otherwise keep current
            const taskIndex = data.task_index !== undefined ? data.task_index : lastUpdatedTaskIndex;
            if (data.task_index !== undefined) {
                lastUpdatedTaskIndex = data.task_index;
            }
            console.log('Using task index:', taskIndex, '(from data:', data.task_index, ', last:', lastUpdatedTaskIndex, ')');
            
            updateKanbanBoard({
                ...data,
                task_index: taskIndex
            });
        } else {
            console.warn('Unknown message type:', data.type);
        }
    } catch (error) {
        console.error('Error processing WebSocket message:', error);
    }
}

// Initial fetch of active executions and setup of cancel button
document.addEventListener('DOMContentLoaded', async function() {
    const data = await fetchActiveExecutions();
    const hasActiveExecution = data && data.executions && data.executions.length > 0;
    const activeExecutionId = hasActiveExecution ? data.executions[0].execution_id : null;
    updateCancelButton(hasActiveExecution, activeExecutionId);
});







function getCurrentTime() {
    return new Date().toLocaleTimeString();
}

function getStatusBadgeClass(status) {
    switch (status?.toLowerCase()) {
        case 'running':
            return 'info';
        case 'completed':
            return 'success';
        case 'failed':
            return 'danger';
        case 'waiting_for_human_input':
            return 'warning';
        case 'pending':
        default:
            return 'secondary';
    }
}

// Function to show/hide cancel button based on execution status
function updateCancelButton(hasActiveExecution, executionId) {
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

function addUpdateToBoard(taskBoard, data) {
    
    const kanbanDrag = taskBoard.querySelector('.kanban-drag');
    if (!kanbanDrag) return;
    
    const stageId = `stage-${data.execution_id}-${Date.now()}`;
    const stage = data.stage || {};
    
    // Special handling for human input request - only when it's an actual input request, not just a status update
    if (stage.stage_type === 'human_input_request' && data.status === 'WAITING_FOR_HUMAN_INPUT') {
        const cardHtml = `
            <div class="card mb-2 border-0 shadow-none">
                <div class="card-body p-3">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <span class="badge bg-gradient-${getStatusBadgeClass(stage.status)} text-xs">${stage.status || 'unknown'}</span>
                        <button class="btn btn-link text-dark p-0 expand-content" data-stage-id="${stageId}">
                            <i class="fas fa-expand-alt"></i>
                        </button>
                    </div>
                    <h6 class="text-sm mb-2">${stage.title || 'Human Input Required'}</h6>
                    <div class="content-preview text-sm mb-3">
                        ${stage.content || ''}
                    </div>
                    <div class="human-input-container">
                        <div class="form-group">
                            <textarea class="form-control" rows="3" placeholder="Enter your response here..."></textarea>
                            <button class="btn btn-primary btn-sm mt-2" onclick="handleHumanInputSubmit(this)">Submit</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Create card element
        const card = document.createElement('div');
        card.id = stageId;
        card.className = 'kanban-item stage-item';
        card.setAttribute('data-execution-id', data.execution_id);
        card.setAttribute('data-stage-id', stageId);
        card.innerHTML = cardHtml;
        console.log('Adding click listener to expand button')
        // Add click handler for expand button
        card.querySelector('.expand-content').addEventListener('click', (e) => {
            console.log('Expand button clicked');
            e.stopPropagation();
            contentExpander.expandContent(
                card,
                stage.title || 'Human Input Required',
                stage.content || '',
                {
                    Status: stage.status || 'unknown',
                    Agent: stage.agent || 'System',
                    'Stage Type': stage.stage_type || 'unknown',
                    Timestamp: getCurrentTime()
                }
            );
        });
        
        kanbanDrag.appendChild(card);
        return;
    }
    const contentPreview = stage.content ? window.md.render(stage.content) : '';
    
    const cardHtml = `
        <div class="card mb-2 border-0 shadow-none">
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="badge bg-gradient-${getStatusBadgeClass(stage.status)} text-xs">${stage.status || 'unknown'}</span>
                    <button class="btn btn-link text-dark p-0 expand-content" data-stage-id="${stageId}">
                        <i class="fas fa-expand-alt"></i>
                    </button>
                </div>
                <h6 class="text-sm mb-2">${stage.title || 'Untitled'}</h6>
                <div class="content-preview text-sm" style="max-height: 4.5em; overflow: hidden; position: relative;">
                    <div class="content-text markdown-content">${contentPreview}</div>
                    <div class="content-fade" style="position: absolute; bottom: 0; left: 0; right: 0; height: 20px; background: linear-gradient(transparent, white);"></div>
                </div>
            </div>
        </div>
    `;

    // Create card element
    const card = document.createElement('div');
    card.id = stageId;
    card.className = 'kanban-item';
    card.innerHTML = cardHtml;
    
    // Add click handler for expand button
    card.querySelector('.expand-content').addEventListener('click', (e) => {
        e.stopPropagation();
        contentExpander.expandContent(
            card,
            stage.title || 'Untitled',
            stage.content || '',
            {
                Status: stage.status || 'unknown',
                Agent: stage.agent || 'System',
                'Stage Type': stage.stage_type || 'unknown',
                Timestamp: getCurrentTime()
            }
        );
    });
    
    kanbanDrag.appendChild(card);
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

// Export functions that need to be globally accessible
window.showStartExecutionModal = showStartExecutionModal;
window.handleHumanInputSubmit = handleHumanInputSubmit;
