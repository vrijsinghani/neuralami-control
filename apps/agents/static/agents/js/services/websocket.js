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
        if (this.socket?.readyState === WebSocket.CONNECTING) {
            console.log('WebSocket already connecting, skipping connect attempt');
            return;
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
            
            // Don't attempt to reconnect if this was a normal closure
            if (event.code === 1000 || event.code === 1001) {
                console.log('WebSocket closed normally, not attempting reconnect');
                return;
            }
            
            this._handleReconnect();
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.messageHandler.handleConnectionStatus('error');
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
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            console.log(`Attempting to reconnect in ${delay}ms...`);
            
            setTimeout(() => {
                console.log('Reconnecting...');
                this.connect();
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
            this.messageHandler.handleError('Connection lost. Please refresh the page.');
            this.isReconnecting = false;
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close(1000, 'Normal closure');  // Use 1000 for normal closure
        }
    }
}

export { ChatWebSocket }; 