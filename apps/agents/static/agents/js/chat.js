// Chat WebSocket connection
let socket = null;
let currentAgentId = null;
let currentClientId = null;
let currentParticipantType = 'agent';  // 'agent' or 'crew'

// Initialize chat
$(document).ready(function() {
    // Initialize autosize for message input
    autosize($('#message-input'));

    // Connect WebSocket
    connectWebSocket();

    // Handle agent/crew selection
    $('#agent-select').change(function() {
        const selectedOption = $(this).find(':selected');
        const type = selectedOption.data('type');
        const id = selectedOption.val();
        
        if (type === 'crew') {
            currentParticipantType = 'crew';
            // Send crew execution request
            socket.send(JSON.stringify({
                type: 'start_crew',
                crew_id: id,
                message: 'Starting crew execution...'
            }));
            
            // Disable model selection for crews
            $('#model-select').prop('disabled', true);
        } else {
            currentParticipantType = 'agent';
            currentAgentId = id;
            
            // Enable model selection for agents
            $('#model-select').prop('disabled', false);
        }
    });

    // Handle client selection
    $('#client-select').change(function() {
        currentClientId = $(this).val();
    });

    // Handle message sending
    $('#send-message').click(sendMessage);
    $('#message-input').keypress(function(e) {
        if (e.which == 13 && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
});

// Connect WebSocket
function connectWebSocket() {
    const sessionId = $('#chat-messages').data('session-id');
    const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${wsScheme}://${window.location.host}/ws/chat/${sessionId}/`;
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = function(e) {
        console.log('WebSocket connected');
        $('#connection-status .connection-dot').removeClass('disconnected').addClass('connected');
    };
    
    socket.onclose = function(e) {
        console.log('WebSocket disconnected');
        $('#connection-status .connection-dot').removeClass('connected').addClass('disconnected');
        // Try to reconnect after 1 second
        setTimeout(connectWebSocket, 1000);
    };
    
    socket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        handleMessage(data);
    };
}

// Send message
function sendMessage() {
    const messageInput = $('#message-input');
    const message = messageInput.val().trim();
    
    if (!message) return;
    
    // Get current model
    const model = $('#model-select').val();
    
    // Send message based on participant type
    if (currentParticipantType === 'agent') {
        socket.send(JSON.stringify({
            type: 'message',
            message: message,
            agent_id: currentAgentId,
            client_id: currentClientId,
            model: model
        }));
    } else {
        socket.send(JSON.stringify({
            type: 'message',
            message: message
        }));
    }
    
    // Clear input
    messageInput.val('');
    autosize.update(messageInput);
}

// Handle incoming messages
function handleMessage(data) {
    const messagesDiv = $('#chat-messages');
    const messageHtml = formatMessage(data);
    
    if (messageHtml) {
        messagesDiv.append(messageHtml);
        messagesDiv.scrollTop(messagesDiv[0].scrollHeight);
        
        // Initialize syntax highlighting for code blocks
        messagesDiv.find('pre code').each(function(i, block) {
            hljs.highlightBlock(block);
        });
    }
}

// Format message for display
function formatMessage(data) {
    const timestamp = new Date(data.timestamp).toLocaleTimeString();
    let html = '';
    
    switch (data.type) {
        case 'user_message':
            html = `
                <div class="chat-message user-message" data-id="${data.id}">
                    <div class="message-content">
                        <div class="message-text">${marked(data.message)}</div>
                        <div class="message-time">${timestamp}</div>
                    </div>
                </div>`;
            break;
            
        case 'agent_message':
        case 'crew_message':
            html = `
                <div class="chat-message ${data.type}" data-id="${data.id}">
                    <div class="message-content">
                        <div class="message-text">${marked(data.message)}</div>
                        <div class="message-time">${timestamp}</div>
                    </div>
                </div>`;
            break;
            
        case 'system_message':
            html = `
                <div class="chat-message system-message">
                    <div class="message-content">
                        <div class="message-text">${data.message}</div>
                        <div class="message-time">${timestamp}</div>
                    </div>
                </div>`;
            break;
            
        case 'error':
            html = `
                <div class="chat-message error-message">
                    <div class="message-content">
                        <div class="message-text">${data.message}</div>
                        <div class="message-time">${timestamp}</div>
                    </div>
                </div>`;
            break;
    }
    
    return html;
}
