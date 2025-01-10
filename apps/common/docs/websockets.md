# WebSocket Infrastructure Guide

This guide explains how to use the common WebSocket infrastructure for creating new real-time features in your application.

## Overview

Our WebSocket infrastructure provides a standardized way to handle real-time communication between client and server. It includes:

- Base WebSocket service (client-side)
- Base WebSocket consumer (server-side)
- Automatic reconnection
- Connection status management
- Error handling
- Ping/pong heartbeat mechanism

## Quick Start

### 1. Backend Setup

Create a new consumer for your feature by extending the base consumer:

```python
# your_app/consumers.py
from apps.common.websockets.base_consumer import BaseWebSocketConsumer

class YourFeatureConsumer(BaseWebSocketConsumer):
    async def connect(self):
        # Get ID from URL route
        self.feature_id = self.scope['url_route']['kwargs']['feature_id']
        # Set unique group name for this feature instance
        self.group_name = f"feature_{self.feature_id}"
        await super().connect()

    async def handle_message(self, data):
        """Handle incoming messages"""
        message_type = data.get('type')
        if message_type == 'your_action':
            # Handle your specific action
            await self.handle_your_action(data)

    async def handle_your_action(self, data):
        # Process the action
        result = await self.process_action(data)
        # Send response back to client
        await self.send_json({
            'type': 'action_result',
            'data': result
        })
```

Add URL routing for your consumer:

```python
# your_app/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(
        r'ws/your-feature/(?P<feature_id>\w+)/$',
        consumers.YourFeatureConsumer.as_asgi()
    ),
]
```

### 2. Frontend Setup

Create a specialized service for your feature:

```javascript
// your_app/static/your_app/js/services/feature_websocket.js
// IMPORTANT: Note the import path pattern for the base WebSocket service
import { BaseWebSocketService } from '/static/js/services/websocket.js';

class FeatureWebSocketService extends BaseWebSocketService {
    constructor(featureId) {
        super({
            endpoint: `/ws/your-feature/${featureId}/`
        });
        this.featureId = featureId;
    }

    // Add feature-specific methods
    async performAction(data) {
        this.send({
            type: 'your_action',
            data: data
        });
    }

    handleMessage(data) {
        switch (data.type) {
            case 'action_result':
                this.emit('actionComplete', data);
                break;
            case 'status_update':
                this.emit('statusUpdate', data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
}
```

Use the service in your application:

```javascript
// your_app/static/your_app/js/feature_app.js
// IMPORTANT: Use the correct path for your app's static files
import { FeatureWebSocketService } from './services/feature_websocket.js';

class FeatureApp {
    constructor(featureId) {
        this.websocket = new FeatureWebSocketService(featureId);
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Handle connection status
        this.websocket.on('connectionStatus', (status) => {
            this.updateConnectionUI(status);
        });

        // Handle action results
        this.websocket.on('actionComplete', (data) => {
            this.handleActionResult(data);
        });

        // Handle status updates
        this.websocket.on('statusUpdate', (data) => {
            this.updateStatus(data);
        });
    }

    initialize() {
        this.websocket.connect();
    }
}
```

## Static File Organization

### Import Paths
When importing the base WebSocket service or other common utilities, use the following path pattern:
```javascript
// CORRECT
import { BaseWebSocketService } from '/static/js/services/websocket.js';

// INCORRECT - Will result in 404
import { BaseWebSocketService } from '/static/apps/common/js/services/websocket.js';
import { BaseWebSocketService } from '/static/common/js/services/websocket.js';
```

### Static File Structure
```
static/
├── js/
│   └── services/
│       └── websocket.js  # Base WebSocket service
└── your_app/
    └── js/
        └── services/
            └── feature_websocket.js  # Your feature-specific service
```

### Django Static Files
Note that Django's static file collection works as follows:
1. Files in `apps/common/static/` are collected to `static/`
2. Files in `your_app/static/your_app/` are collected to `static/your_app/`
3. Always use the collected path (after `static/`) in your imports

For example:
- Source: `apps/common/static/js/services/websocket.js`
- Collected: `static/js/services/websocket.js`
- Import path: `/static/js/services/websocket.js`

## Key Features

### Connection Status

The base service provides connection status updates through events:

- connected
- disconnected
- connecting
- error

```javascript
websocket.on('connectionStatus', (status) => {
    switch (status) {
        case 'connected':
            showConnectedUI();
            break;
        case 'disconnected':
            showDisconnectedUI();
            break;
        // etc.
    }
});
```

### Error Handling

Errors are automatically emitted as events:

```javascript
websocket.on('error', (error) => {
    console.error('WebSocket error:', error);
    // Show error to user
    Swal.fire({
        title: 'Error',
        text: error.message,
        icon: 'error'
    });
});
```

### Automatic Reconnection

The service automatically handles reconnection with exponential backoff:

- Attempts to reconnect up to 5 times
- Increases delay between attempts
- Adds random jitter to prevent thundering herd

### Group Messages (Backend)

Send messages to all clients in a group:

```python
async def broadcast_update(self, data):
    await self.channel_layer.group_send(
        self.group_name,
        {
            'type': 'broadcast_message',
            'data': data
        }
    )

async def broadcast_message(self, event):
    """Handle messages from group_send"""
    await self.send_json(event['data'])
```

## Common Issues and Solutions

### Import Path Issues
- **Problem**: 404 errors when importing the base WebSocket service
- **Solution**: Use the correct static path pattern: `/static/js/services/websocket.js`
- **Explanation**: Django's static file serving requires the `apps` directory in the path

### Connection Issues
- Check WebSocket URL format
- Verify routing configuration
- Check for firewall/proxy issues
- Ensure ASGI application is properly configured

### Message Handling
- Verify message format
- Check for proper JSON serialization
- Validate message types
- Use consistent type names across frontend and backend

### Group Broadcasting
- Verify group names
- Check channel layer configuration
- Test group message handlers
- Monitor group sizes

## Security Considerations

### Authentication
- Implement proper authentication
- Validate user permissions
- Secure sensitive data

### Input Validation
- Validate all incoming messages
- Sanitize data before processing
- Implement rate limiting

### Group Access
- Validate group membership
- Control access to group messages
- Monitor group sizes

## Testing

### Connection Testing
```javascript
// Test WebSocket connection
describe('WebSocket Connection', () => {
    it('should connect successfully', async () => {
        const socket = new FeatureWebSocketService('test-id');
        await socket.connect();
        expect(socket.isConnected).toBe(true);
    });
});
```

### Message Testing
```javascript
// Test message handling
describe('Message Handling', () => {
    it('should handle action results', () => {
        const socket = new FeatureWebSocketService('test-id');
        socket.on('actionComplete', (data) => {
            expect(data.type).toBe('action_result');
        });
    });
});