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
        this.messageQueue = [];
        this.connecting = false;
        
        // Cloudflare optimized settings
        this.pingInterval = 25000; // 25 seconds
        this.pongTimeout = 10000;  // 10 seconds to wait for pong
    }

    connect() {
        if (this.connecting) {
            console.log('WebSocket already connecting or reconnecting in progress');
            return;
        }

        if (this.socket?.readyState === WebSocket.OPEN) {
            console.log('WebSocket already connected');
            return;
        }

        this.connecting = true;

        if (this.socket) {
            this.socket.close();
        }

        const wsScheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${wsScheme}${window.location.host}${this.config.endpoint}`;

        try {
            console.log('Establishing WebSocket connection...');
            this.socket = new WebSocket(wsUrl);
            this.setupEventHandlers();
        } catch (error) {
            console.error('Error creating WebSocket:', error);
            this.connecting = false;
            this.handleReconnect();
        }
    }

    setupEventHandlers() {
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.connecting = false;
            this.reconnectAttempts = 0;
            this.emit('connectionStatus', 'connected');
            this.startPingInterval();
            
            // Process any queued messages
            while (this.messageQueue.length > 0) {
                const data = this.messageQueue.shift();
                this.send(data);
            }
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
            console.log(`WebSocket closed: ${event.code} - ${event.reason}`);
            this.isConnected = false;
            this.connecting = false;
            this.stopPingInterval();
            this.emit('connectionStatus', 'disconnected');
            
            if (event.code !== 1000 && event.code !== 1001) {
                this.handleReconnect();
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.connecting = false;
            this.emit('connectionStatus', 'error');
        };
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            const jitter = Math.random() * 1000;
            const totalDelay = delay + jitter;
            
            console.log(`Attempting to reconnect in ${totalDelay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            
            setTimeout(() => {
                console.log('Reconnecting...');
                this.connect();
            }, totalDelay);
        } else {
            console.error('Max reconnection attempts reached');
            this.emit('error', 'Max reconnection attempts reached');
        }
    }

    send(data) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            console.log('WebSocket not connected, queueing message:', data);
            this.messageQueue.push(data);
            if (!this.isConnected && !this.connecting) {
                this.connect();
            }
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
        this.pingIntervalId = setInterval(() => {
            if (this.socket?.readyState === WebSocket.OPEN) {
                // Check if we haven't received a pong in too long
                if (Date.now() - this.lastPongTime > this.pingInterval + this.pongTimeout) {
                    console.log('Pong timeout - reconnecting WebSocket');
                    this.socket.close();
                    this.connect();
                    return;
                }
                this.send({ type: 'ping' });
            }
        }, this.pingInterval);
    }

    stopPingInterval() {
        if (this.pingIntervalId) {
            clearInterval(this.pingIntervalId);
            this.pingIntervalId = null;
        }
    }
} 