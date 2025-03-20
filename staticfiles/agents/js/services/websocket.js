class ChatWebSocket {
    constructor(config, messageHandler) {
        this.config = config;
        this.messageHandler = messageHandler;
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
        this.isReconnecting = false;
        this.lastMessageQueue = [];  // Queue to store messages during reconnection
    }

    connect() {
        // If already connecting or reconnecting is in progress, don't try to connect again
        if (this.socket?.readyState === WebSocket.CONNECTING || this.isReconnecting) {
            console.log('WebSocket already connecting or reconnecting in progress, skipping connect attempt');
            return;
        }

        // Close any existing socket cleanly before creating a new one
        if (this.socket) {
            try {
                // Only try to close if not already closed
                if (this.socket.readyState !== WebSocket.CLOSED && this.socket.readyState !== WebSocket.CLOSING) {
                    console.log('Closing existing socket before reconnect');
                    this.socket.onclose = null; // Prevent the close handler from firing
                    this.socket.close(1000, 'Clean closure before reconnect');
                }
            } catch (e) {
                console.warn('Error closing existing socket:', e);
            }
        }

        const wsUrl = `${this.config.urls.wsBase}?session=${this.config.sessionId}`;
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.isReconnecting = false;
            this.messageHandler.handleConnectionStatus('connected');
            
            // Send any queued messages
            while (this.lastMessageQueue.length > 0) {
                const message = this.lastMessageQueue.shift();
                this.send(message);
            }
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.messageHandler.handleMessage(data);
            } catch (error) {
                console.error('Error handling message:', error);
            }
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket closed:', event);
            this.messageHandler.handleConnectionStatus('disconnected');
            
            // Don't attempt to reconnect if this was a normal closure or we're already reconnecting
            if (event.code === 1000 || event.code === 1001 || this.isReconnecting) {
                console.log('WebSocket closed normally or already reconnecting, not attempting reconnect');
                return;
            }
            
            // Start reconnection process
            this._handleReconnect();
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.messageHandler.handleConnectionStatus('error');
            // Don't attempt reconnect here - let the onclose handler do it
        };
    }

    send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            console.log('Sending WebSocket message:', data);
            this.socket.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket is not open, queueing message:', data);
            // Queue the message if we're reconnecting
            if (this.isReconnecting) {
                this.lastMessageQueue.push(data);
            }
        }
    }

    _handleReconnect() {
        if (this.isReconnecting) {
            console.log('Already attempting to reconnect, skipping');
            return;
        }

        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.isReconnecting = true;
            this.reconnectAttempts++;
            
            // Use a more moderate reconnection delay with a maximum cap
            const delay = Math.min(this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1), 5000);
            console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            
            setTimeout(() => {
                if (this.isReconnecting) {  // Double-check we're still in reconnecting state
                    console.log('Reconnecting...');
                    this.connect();
                }
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
            this.messageHandler.handleConnectionStatus('disconnected');
            this.messageHandler.handleError('Connection lost. Please refresh the page.');
            this.isReconnecting = false;
        }
    }

    disconnect() {
        this.isReconnecting = false; // Stop any reconnection in progress
        if (this.socket) {
            try {
                this.socket.close(1000, 'Normal closure');  // Use 1000 for normal closure
            } catch (e) {
                console.warn('Error closing socket during disconnect:', e);
            }
        }
    }
}

export { ChatWebSocket }; 