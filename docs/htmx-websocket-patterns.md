# HTMX WebSocket Patterns

This guide outlines best practices for implementing real-time updates with HTMX WebSockets in our Django application.

## Basic Setup

### 1. Include the WebSocket Extension

```html
<!-- Include HTMX WebSocket extension -->
<script src="https://unpkg.com/htmx.org/dist/ext/ws.js"></script>
```

### 2. Set Up the Container

**Simple approach (inline):**
```html
<div class="container-fluid py-4"
     hx-ext="ws"
     ws-connect="/ws/your-endpoint/{{ id }}/">
  <!-- Content that will receive updates -->
</div>
```

**Dynamic approach (JavaScript):**
```javascript
// Configure the connection programmatically
const container = document.getElementById('yourContainer');
container.setAttribute('ws-connect', `/ws/your-endpoint/${taskId}/`);
htmx.process(container);
```

## Message Handling Patterns

### 1. Out-of-Band Swaps (Simple Updates)

```html
<!-- Target element with out-of-band swap -->
<span id="status-badge" hx-swap-oob="true">{{ status }}</span>
```

### 2. Progress Tracking (Advanced)

```html
<!-- Progress bar that updates based on WebSocket messages -->
<div class="progress mb-3">
  <div class="progress-bar bg-gradient-primary" 
       role="progressbar" 
       style="width: 0%" 
       id="research-progress" 
       hx-swap-oob="true"></div>
</div>
```

### 3. JSON Message Processing (Most Flexible)

```javascript
// Listen for WebSocket messages and process JSON data
document.body.addEventListener('htmx:wsAfterMessage', function(event) {
  console.log("Raw WebSocket message:", event.detail.message);
  try {
    const data = JSON.parse(event.detail.message);
    
    // Update UI based on message type
    if (data.progress) {
      updateProgressUI(data.progress);
    } else if (data.status === 'complete') {
      handleCompletion(data);
    } else if (data.status === 'failed') {
      handleError(data);
    }
  } catch (e) {
    console.error("Error processing WebSocket message:", e);
  }
});
```

## Debugging WebSockets

```javascript
// Add these listeners to debug WebSocket connections
document.body.addEventListener('htmx:wsOpen', function(evt) {
  console.log('WebSocket opened:', evt.detail);
});

document.body.addEventListener('htmx:wsClose', function(evt) {
  console.log('WebSocket closed:', evt.detail);
});

document.body.addEventListener('htmx:wsError', function(evt) {
  console.error('WebSocket error:', evt.detail);
});
```

## UI Patterns

### 1. Loading Overlay

```html
<div id="progressOverlay" class="progress-overlay d-none" hx-ext="ws">
  <div class="progress-content">
    <h5 id="progressAction">Processing...</h5>
    <div class="progress">
      <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated" 
           role="progressbar" style="width: 0%"></div>
    </div>
    <p id="progressMessage" class="text-sm mt-2">Starting operation</p>
    
    <!-- Stats display -->
    <div class="progress-stats">
      <!-- Add your stats here -->
    </div>
  </div>
</div>
```

### 2. Timeline Updates

```html
<div class="timeline timeline-one-side">
  <!-- Existing steps rendered server-side -->
  {% for step in steps %}
    {% include "partials/_step.html" with step=step %}
  {% endfor %}
  
  <!-- Processing indicator -->
  <div id="processing-indicator" class="{% if not in_progress %}d-none{% endif %}">
    <span class="timeline-step bg-info">
      <i class="fas fa-circle-notch fa-spin"></i>
    </span>
    <div class="timeline-content">
      <h6>Processing Next Step</h6>
    </div>
  </div>
</div>
```

## Best Practices

1. **Event Delegation**: Listen at the document level for `htmx:wsAfterMessage` to capture all messages

2. **Proper Error Handling**:
   - Parse JSON safely with try/catch
   - Provide user feedback for connection issues
   - Log connection events for debugging

3. **Initialization**:
   - Set up listeners after the DOM is loaded
   - Verify WebSocket support before attempting connection
   - Include fallback for failed connections

4. **UI Updates**:
   - Update UI elements incrementally as data arrives
   - Provide visual feedback during long-running operations
   - Use CSS transitions for smooth progress updates

5. **Connection Management**:
   - Connect only when needed
   - Disconnect when appropriate (page navigation, task completion)
   - Handle reconnection attempts gracefully

## Django Consumer Implementation

For reference, your Django consumer should follow this pattern:

```python
class YourConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f"task_{self.task_id}"
        
        # Join the group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()
        
        # Start background task to check status
        asyncio.create_task(self.check_status_periodically())
        
    async def disconnect(self, close_code):
        # Leave the group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        
    # Handle messages from WebSocket
    async def receive(self, text_data):
        # Process incoming messages if needed
        
    # Send progress updates to WebSocket
    async def progress_update(self, event):
        # Send the progress data to the WebSocket
        await self.send(text_data=json.dumps({
            'progress': event['progress']
        }))
        
    # Send status updates to WebSocket
    async def status_update(self, event):
        # Send the status update to the WebSocket
        await self.send(text_data=json.dumps({
            'status': event['status'],
            'result': event.get('result'),
            'message': event.get('message')
        }))
``` 