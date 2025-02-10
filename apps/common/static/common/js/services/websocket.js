// Base WebSocket service for handling common WebSocket functionality
export class BaseWebSocketService {
    constructor(config) {
        this.config = config;
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
        const wsUrl = `${wsScheme}${window.location.host}${this.config.endpoint}`;

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
            this.emit('error', 'Max reconnection attempts reached');
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

    handleMessage(data) {
        console.log('Received message:', data);
        if (data.type === 'research_update') {
            if (this.handlers.has(data.type)) {
                this.handlers.get(data.type).forEach(handler => handler(data.data));
            }
        } else if (data.type && this.handlers.has(data.type)) {
            this.handlers.get(data.type).forEach(handler => handler(data));
        }
    }
} 