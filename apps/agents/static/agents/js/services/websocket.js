class ChatWebSocket {
    constructor(config, messageHandler) {
        this.config = config;
        this.messageHandler = messageHandler;
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000; // Start with 1 second
    }

    connect() {
        const wsUrl = `${this.config.urls.wsBase}?session=${this.config.sessionId}`;
        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.messageHandler.handleConnectionStatus('connected');
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
            this._handleReconnect();
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.messageHandler.handleConnectionStatus('error');
        };
    }

    send(message) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        } else {
            console.error('WebSocket is not connected');
            this.messageHandler.handleError('Connection lost. Please try again.');
        }
    }

    _handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
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
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }
}

export { ChatWebSocket }; 