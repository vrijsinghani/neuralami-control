class ImageOptimizationWebSocket {
    constructor(optimizationId) {
        this.optimizationId = optimizationId;
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.handlers = new Map();
        this.lastPongTime = Date.now();
    }

    connect() {
        if (this.socket?.readyState === WebSocket.OPEN) {
            console.log('WebSocket already connected');
            return;
        }

        if (this.socket) {
            this.socket.close();
        }

        const wsScheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${wsScheme}${window.location.host}/ws/image-optimizer/${this.optimizationId}/`;

        try {
            this.socket = new WebSocket(wsUrl);
            this.setupEventHandlers();
            this.startPingInterval();
        } catch (error) {
            console.error('Error creating WebSocket:', error);
            this.handleReconnect();
        }
    }

    setupEventHandlers() {
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.emit('connectionStatus', 'connected');
        };

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'pong') {
                    this.lastPongTime = Date.now();
                    return;
                }
                this.handleMessage(data);
            } catch (error) {
                console.error('Error processing message:', error);
            }
        };

        this.socket.onclose = (event) => {
            this.isConnected = false;
            this.stopPingInterval();
            this.emit('connectionStatus', 'disconnected');
            
            if (event.code !== 1000 && event.code !== 1001) {
                this.handleReconnect();
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.emit('connectionStatus', 'error');
        };
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            const jitter = Math.random() * 1000;
            setTimeout(() => this.connect(), delay + jitter);
        } else {
            this.emit('error', { message: 'Max reconnection attempts reached' });
        }
    }

    handleMessage(data) {
        switch (data.type) {
            case 'optimization_update':
                this.emit('optimizationUpdate', data);
                break;
            case 'job_update':
                this.emit('jobUpdate', data);
                break;
            case 'error':
                this.emit('error', data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    send(data) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            console.warn('WebSocket not connected, message not sent:', data);
        }
    }

    on(event, handler) {
        if (!this.handlers.has(event)) {
            this.handlers.set(event, new Set());
        }
        this.handlers.get(event).add(handler);
    }

    emit(event, data) {
        const handlers = this.handlers.get(event);
        if (handlers) {
            handlers.forEach(handler => handler(data));
        }
    }

    disconnect() {
        this.stopPingInterval();
        if (this.socket) {
            this.socket.close();
        }
    }

    startPingInterval() {
        this.stopPingInterval();
        this.pingInterval = setInterval(() => {
            if (this.socket?.readyState === WebSocket.OPEN) {
                if (Date.now() - this.lastPongTime > 45000) {
                    this.socket.close();
                    this.connect();
                    return;
                }
                this.send({ type: 'ping' });
            }
        }, 15000);
    }

    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}

export { ImageOptimizationWebSocket }; 