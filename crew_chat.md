# Crew Chat Implementation Plan

## Objective
Extend the existing chat system to support conversations with CrewAI crews while maintaining backward compatibility with the current agent-based chat and kanban-based crew execution systems. This enhancement will allow users to interact with crews through the chat interface, where chat messages become crew inputs and chat history provides context for crew execution.

## Architecture

### Core Components
1. **CrewChatContext**
   - Managed through Django models (Conversation and CrewChatSession)
   - Maintains chat history and task outputs using Django's ORM
   - Provides contextual information to crew tasks through JSONField

2. **CrewChatService**
   - Extends existing ChatService
   - Handles crew initialization and execution in chat context
   - Manages message routing between chat interface and crew execution

3. **Enhanced Callbacks**
   - CrewChatStepCallback: Handles step-level events
   - CrewChatTaskCallback: Manages task-level events
   - WebSocketCallbackHandler: Routes messages to chat interface

4. **Input Handling**
   - Chat-based human input interface
   - Integration with existing crew execution flow
   - Preservation of chat context during input requests

### Integration Points
```
[Chat Interface] <-> [CrewChatService] <-> [CrewChatContext]
         ^                   ^                    ^
         |                   |                    |
         v                   v                    v
[WebSocket Layer] <-> [Crew Execution] <-> [Task Context]
```

## Step by Step Implementation

### Phase 1: Database and Models
1. Update existing models
   ```python
   # apps/agents/models.py
   class Conversation(models.Model):
       # Existing fields...
       
       # New fields for crew support
       participant_type = models.CharField(
           max_length=50, 
           choices=[
               ('agent', 'Agent Chat'),
               ('crew', 'Crew Chat')
           ],
           default='agent'
       )
       crew_execution = models.OneToOneField(
           'CrewExecution',
           on_delete=models.SET_NULL,
           null=True,
           blank=True,
           related_name='chat_conversation'
       )

       async def get_recent_messages(self, limit=10):
           """Get recent messages for this conversation"""
           return await self.chatmessage_set.filter(
               is_deleted=False
           ).order_by('-timestamp')[:limit]

       async def get_task_outputs(self, limit=5):
           """Get recent task outputs from crew execution"""
           if self.crew_execution and self.crew_execution.crew_output:
               return self.crew_execution.crew_output.to_dict()
           return None

   class CrewExecution(models.Model):
       # Existing fields...
       
       # New field for chat support
       chat_enabled = models.BooleanField(default=False)

   class CrewChatSession(models.Model):
       conversation = models.OneToOneField(
           'Conversation',
           on_delete=models.CASCADE,
           related_name='crew_chat_session'
       )
       crew_execution = models.OneToOneField(
           'CrewExecution',
           on_delete=models.CASCADE,
           related_name='chat_session'
       )
       last_activity = models.DateTimeField(auto_now=True)
       status = models.CharField(
           max_length=50,
           choices=[
               ('active', 'Active'),
               ('paused', 'Paused'),
               ('completed', 'Completed'),
               ('cleaned', 'Cleaned')
           ]
       )
       context_data = models.JSONField(default=dict)

       async def get_full_context(self):
           """Get full context including messages, task outputs, and context data"""
           messages = await self.conversation.get_recent_messages()
           task_outputs = await self.conversation.get_task_outputs()
           return {
               'messages': messages,
               'task_outputs': task_outputs,
               'context_data': self.context_data
           }

       def update_context(self, key, value):
           """Update a specific context value"""
           if self.context_data is None:
               self.context_data = {}
           self.context_data[key] = value
           self.save(update_fields=['context_data', 'last_activity'])
   ```

2. Generate and apply migrations
   ```bash
   python manage.py makemigrations agents
   python manage.py migrate
   ```

### Phase 2: Service Layer Implementation

Instead of creating separate WebSocket handlers and resource managers, we'll extend the existing chat infrastructure:

1. Created `CrewChatService` in `apps/agents/websockets/services/crew_chat_service.py`:
   - Handles crew chat initialization
   - Processes incoming messages
   - Manages crew message sending
   - Integrates with crew execution for human input

2. Extended `ChatConsumer` in `apps/agents/websockets/chat_consumer.py`:
   - Added crew chat support while maintaining existing agent chat functionality
   - Uses `participant_type` to differentiate between agent and crew chats
   - Initializes `CrewChatService` for crew conversations
   - Preserves all existing functionality (message history, editing, etc.)

3. Reuses existing WebSocket routing in `core/routing.py`:
   - Uses existing `/ws/chat/<session>` endpoint for both agent and crew chats
   - Differentiates handling based on conversation's `participant_type`

This approach:
- Maintains backward compatibility with existing agent chats
- Follows DRY principles by reusing existing infrastructure
- Keeps changes focused and minimal
- Preserves existing message history and editing capabilities

### Phase 3: Integration with Crew Execution

The crew execution system already handles tool management and human input through:
1. `human_input_handler` for managing user interactions
2. `StepCallback` and `TaskCallback` for message passing
3. Kanban channel for real-time updates

Our chat implementation integrates with this by:
1. Using the existing WebSocket consumer to handle both agent and crew chats
2. Updating the execution's `human_input_response` when crew chat messages are received
3. Leveraging the existing crew execution status management

This approach:
- Maintains simplicity by using existing infrastructure
- Ensures consistent handling of human input across the system
- Preserves the existing crew execution workflow

### Phase 4: Monitoring and Logging
1. Set up structured logging
   ```python
   # apps/agents/chat/monitoring/logging.py
   class CrewChatLogger:
       def __init__(self, session_id):
           self.session_id = session_id
           self.logger = logging.getLogger('crew_chat')
           
       def log_event(self, event_type, **kwargs):
           self.logger.info({
               "event_type": event_type,
               "session_id": self.session_id,
               "timestamp": timezone.now().isoformat(),
               **kwargs
           })
   ```

2. Implement metrics collection
   ```python
   # apps/agents/chat/monitoring/metrics.py
   class CrewChatMetrics:
       def __init__(self):
           self.metrics = {
               "response_times": [],
               "memory_usage": [],
               "tool_usage": defaultdict(int)
           }
           
       async def record_metric(self, metric_type, value):
           self.metrics[metric_type].append({
               "value": value,
               "timestamp": timezone.now()
           })
           
       async def cleanup_old_metrics(self, hours=24):
           threshold = timezone.now() - timedelta(hours=hours)
           for metric_list in self.metrics.values():
               metric_list = [
                   m for m in metric_list 
                   if m["timestamp"] > threshold
               ]
   ```

### Phase 5: Integration with Existing Systems
1. Update CrewChatService
   ```python
   # apps/agents/websockets/services/chat_service.py
   class CrewChatService(ChatService):
       def __init__(self, *args, **kwargs):
           super().__init__(*args, **kwargs)
           self.resource_manager = CrewChatResourceManager()
           self.memory_manager = ChatHistoryManager()
           self.tool_manager = CrewChatToolManager(self)
           self.logger = CrewChatLogger(self.session_id)
           self.metrics = CrewChatMetrics()
           
       async def initialize_crew_chat(self):
           # Create chat session
           self.session = await CrewChatSession.objects.acreate(
               conversation=self.conversation,
               crew_execution=self.execution,
               status='active'
           )
           
           # Initialize resources
           await self.resource_manager.initialize_session(self.session.id)
           
           # Set up monitoring
           self.logger.log_event('chat_initialized')
           
       async def cleanup(self):
           await self.resource_manager.cleanup_session(self.session.id)
           await self.metrics.cleanup_old_metrics()
   ```

2. Enhance CrewChatContext
   ```python
   # apps/agents/chat/context.py
   class CrewChatContext:
       def __init__(self, service: CrewChatService):
           self.service = service
           self.memory_manager = service.memory_manager
           self.tool_manager = service.tool_manager
           
       async def add_message(self, message):
           self.memory_manager.add_message(message)
           await self.service.metrics.record_metric(
               'message_count', 
               len(self.memory_manager._history)
           )
           
       def get_context_for_task(self, task_index):
           return {
               "chat_history": self.memory_manager.get_context_window(),
               "tool_outputs": self.tool_manager.tool_outputs,
               "task_index": task_index
           }
   ```
3. Message Component Integration
   ```javascript:crew_chat.md
   // apps/agents/static/agents/js/components/crew_message.js
   class CrewMessage extends Message {
       constructor(content, agent, avatar = null) {
           super(content, true, avatar);
           this.agent = agent;
           this.toolOutputs = new Map();
       }
       
       // Override render to include agent-specific styling
       render(domId) {
           const element = super.render(domId);
           element.classList.add(`crew-agent-${this.agent}`);
           return element;
       }
   }
   ```

   4. Enhance WebSocket Consumer
   ```python
   # apps/agents/websockets/crew_consumer.py
   class CrewChatConsumer(AsyncWebsocketConsumer):
       async def receive_json(self, content):
           if content.get('type') == 'crew_message':
               await self.handle_crew_message(content)
           elif content.get('type') == 'tool_result':
               await self.handle_tool_result(content)
   ```

### Phase 6: Cleanup and Maintenance
1. Implement cleanup jobs
   ```python
   # apps/agents/tasks/cleanup.py
   @shared_task
   async def cleanup_inactive_sessions():
       threshold = timezone.now() - timedelta(
           hours=settings.INACTIVE_SESSION_THRESHOLD
       )
       sessions = await CrewChatSession.objects.filter(
           last_activity__lt=threshold,
           status='active'
       ).all()
       
       for session in sessions:
           service = CrewChatService.from_session(session)
           await service.cleanup()
   ```

2. Set up monitoring tasks
   ```python
   # apps/agents/tasks/monitoring.py
   @shared_task
   async def monitor_crew_chat_health():
       metrics = CrewChatMetrics()
       sessions = await CrewChatSession.objects.filter(
           status='active'
       ).all()
       
       for session in sessions:
           memory_usage = await get_session_memory_usage(session)
           await metrics.record_metric('memory_usage', memory_usage)
   ```

### Phase 7: Frontend Integration

1. Extend ChatApp for Crew Support
   ```javascript
   // apps/agents/static/agents/js/chat/app.js
   class ChatApp {
       constructor(config) {
           // Existing initialization...
           
           this.elements = {
               ...this.elements,
               crewSelect: document.getElementById('crew-select'),
               taskProgress: document.getElementById('task-progress'),
               agentRoleIndicator: document.getElementById('agent-role')
           };
           
           this.state = {
               currentParticipantType: null, // 'agent' or 'crew'
               currentTaskIndex: null,
               currentAgentRole: null
           };
       }
       
       async switchToCrewChat(crewId) {
           this.state.currentParticipantType = 'crew';
           await this.websocket.send({
               type: 'switch_participant',
               participant_type: 'crew',
               crew_id: crewId
           });
       }
   }
   ```

2. Add Crew-specific Message Components
   ```javascript
   // apps/agents/static/agents/js/components/crew_task_progress.js
   class CrewTaskProgress {
       constructor(container) {
           this.container = container;
           this.tasks = new Map();
       }
       
       updateTask(taskIndex, status, description) {
           const taskElement = this.getOrCreateTaskElement(taskIndex);
           taskElement.status = status;
           taskElement.innerHTML = this.renderTask(description, status);
       }
       
       renderTask(description, status) {
           return `
               <div class="task ${status}">
                   <span class="task-index">${taskIndex + 1}</span>
                   <span class="task-description">${description}</span>
                   <span class="task-status">${status}</span>
               </div>
           `;
       }
   }
   ```

3. Enhance Message Handler
   ```javascript
   // apps/agents/static/agents/js/services/message_handler.js
   class MessageHandler {
       async handleCrewMessage(message) {
           switch(message.type) {
               case 'crew_task_start':
                   this.taskProgress.updateTask(
                       message.task_index,
                       'running',
                       message.description
                   );
                   break;
                   
               case 'crew_agent_message':
                   const crewMessage = new CrewMessage(
                       message.content,
                       message.agent_role,
                       message.avatar
                   );
                   await this.messageList.addMessage(crewMessage);
                   break;
                   
               case 'crew_tool_result':
                   await this.toolOutputManager.handleCrewToolResult(message);
                   break;
           }
       }
   }
   ```

### Phase 8: State Management and Recovery

1. Implement State Manager
   ```python
   # apps/agents/chat/managers/state_manager.py
   class CrewStateManager:
       def __init__(self, session_id):
           self.session_id = session_id
           self.redis = get_redis_connection()
           
       async def save_state(self, state_data):
           key = f"crew_chat:{self.session_id}:state"
           await self.redis.hset(key, mapping=state_data)
           await self.redis.expire(key, settings.CREW_STATE_TTL)
           
       async def load_state(self):
           key = f"crew_chat:{self.session_id}:state"
           state = await self.redis.hgetall(key)
           return state or {}
           
       async def clear_state(self):
           key = f"crew_chat:{self.session_id}:state"
           await self.redis.delete(key)
   ```

2. Add Recovery Procedures
   ```python
   # apps/agents/chat/recovery.py
   class CrewChatRecovery:
       def __init__(self, service):
           self.service = service
           
       async def handle_reconnection(self):
           # Load previous state
           state = await self.service.state_manager.load_state()
           if not state:
               return
               
           # Recreate context
           await self.service.initialize_from_state(state)
           
           # Replay necessary messages
           await self.replay_messages(state.get('last_message_id'))
           
       async def handle_error_recovery(self, error):
           await self.service.logger.log_event(
               'error_recovery_started',
               error=str(error)
           )
           
           # Save current state
           await self.service.state_manager.save_state({
               'error': str(error),
               'recovery_time': timezone.now().isoformat()
           })
           
           # Attempt recovery based on error type
           if isinstance(error, ToolExecutionError):
               await self.recover_from_tool_error(error)
           elif isinstance(error, ConnectionError):
               await self.recover_from_connection_error(error)
   ```

### Phase 9: Error Handling and Validation

1. Add Error Boundaries
   ```javascript
   // apps/agents/static/agents/js/components/error_boundary.js
   class ChatErrorBoundary {
       constructor(component) {
           this.component = component;
           this.errorState = null;
       }
       
       async handleError(error) {
           this.errorState = {
               error,
               componentStack: error.stack,
               time: new Date().toISOString()
           };
           
           // Log error
           await this.logError();
           
           // Show user-friendly error message
           this.showErrorUI();
           
           // Attempt recovery
           await this.attemptRecovery();
       }
       
       showErrorUI() {
           const errorContainer = document.createElement('div');
           errorContainer.className = 'chat-error';
           errorContainer.innerHTML = `
               <div class="error-message">
                   <h4>Something went wrong</h4>
                   <p>${this.getErrorMessage()}</p>
                   <button onclick="window.location.reload()">
                       Restart Chat
                   </button>
               </div>
           `;
           this.component.container.appendChild(errorContainer);
       }
   }
   ```

2. Add Input Validation
   ```python
   # apps/agents/chat/validation.py
   class CrewChatValidator:
       def __init__(self, service):
           self.service = service
           
       async def validate_message(self, message):
           if len(message) > settings.MAX_MESSAGE_LENGTH:
               raise ValidationError("Message too long")
               
           if self.contains_sensitive_data(message):
               raise ValidationError("Message contains sensitive data")
               
       async def validate_tool_result(self, result):
           if not isinstance(result, dict):
               raise ValidationError("Invalid tool result format")
               
           if 'type' not in result or 'data' not in result:
               raise ValidationError("Missing required tool result fields")
   ```

3. Add Health Checks
   ```python
   # apps/agents/chat/health.py
   class CrewChatHealthCheck:
       def __init__(self, service):
           self.service = service
           
       async def check_health(self):
           checks = {
               'websocket': await self.check_websocket(),
               'database': await self.check_database(),
               'redis': await self.check_redis(),
               'memory': await self.check_memory_usage()
           }
           
           return all(checks.values()), checks
           
       async def check_memory_usage(self):
           usage = await self.service.metrics.get_memory_usage()
           return usage < settings.MAX_MEMORY_USAGE
   ```

## Things to Look Out For

### 1. Backward Compatibility
- Maintain existing kanban-based crew execution
- Preserve current agent chat functionality
- Keep existing WebSocket message formats
- Support current client JavaScript implementations

### 2. State Management
- Handle chat context persistence
- Manage crew execution state
- Track task progress and outputs
- Handle WebSocket disconnections

### 3. Performance Considerations
- Memory usage for chat history
- WebSocket message volume
- Task execution overhead
- Database load

### 4. Error Handling
- Crew execution failures
- WebSocket disconnections
- Invalid message formats
- Task timeouts

### 5. Security
- Input validation
- Access control
- Data persistence
- Client authentication

### 6. Edge Cases
- Long-running crew executions
- Large chat histories
- Multiple concurrent executions
- Task interruptions

### 7. Database Considerations
- Schema updates for crew chat support
- Conversation model extensions
- Relationship management
- Output storage strategy

### 8. Tool Management
- Tool display in chat context
- Output formatting
- Permission handling
- State persistence

### 9. Resource Management
- Memory optimization
- Resource cleanup
- Connection pooling
- Cache strategies

### 10. Monitoring & Debug
- Logging framework
- Debug information
- Performance metrics
- Error tracking

## Implementation Notes

### Maintaining Backward Compatibility
1. **Kanban Integration**
   ```python
   # Existing crew execution remains unchanged
   if not chat_context:
       return original_run_crew(task_id, crew, execution)
   ```

2. **WebSocket Messages**
   ```python
   # Preserve existing message formats
   {
       "type": "execution_update",
       "execution_id": execution_id,
       "status": status,
       "message": message,
       # New optional chat-specific fields
       "chat_context": optional_chat_context
   }
   ```
### Additional Message Types
- `crew_task_start`: Indicates start of a crew task
- `crew_task_end`: Indicates completion of a crew task
- `crew_agent_message`: Messages from specific crew agents
- `crew_tool_result`: Tool outputs in crew context

3. **Client API**
   ```javascript
   // Maintain existing event handlers
   socket.onmessage = function(event) {
       const data = JSON.parse(event.data);
       if (data.type === 'execution_update') {
           // Existing handler
           handleExecutionUpdate(data);
       } else if (data.type === 'chat_update') {
           // New chat-specific handler
           handleChatUpdate(data);
       }
   };
   ```

### Testing Strategy
1. **Unit Tests**
   - CrewChatContext functionality
   - Message routing
   - State management

2. **Integration Tests**
   - Chat flow with crew execution
   - WebSocket communication
   - Database interactions

3. **Compatibility Tests**
   - Existing kanban functionality
   - Agent chat features
   - Client implementations

## Migration Strategy

### Phase 1: Database Updates
1. Schema Migrations
   ```sql
   -- Add crew support to conversations
   ALTER TABLE conversations
   ADD COLUMN participant_type VARCHAR(50),
   ADD COLUMN crew_execution_id UUID REFERENCES crew_executions(id);
   ```

2. Data Migration
   ```python
   # Set existing conversations as agent-based
   for conv in Conversation.objects.all():
       conv.participant_type = 'agent'
       conv.save()
   ```

### Phase 2: Service Updates
1. Deploy new services with backward compatibility
2. Roll out database changes
3. Update client libraries
4. Enable new features progressively

### Phase 3: Client Updates
1. Deploy UI changes behind feature flags
2. Roll out JavaScript updates
3. Update documentation
4. Monitor for issues

## Monitoring Strategy

### 1. Logging
```python
# Structured logging for crew chat
{
    "event_type": "crew_chat",
    "conversation_id": "uuid",
    "crew_execution_id": "uuid",
    "task_index": 0,
    "agent_role": "role",
    "message_type": "type",
    "timestamp": "iso-time"
}
```

### 2. Metrics
- Chat response times
- Crew execution duration
- Memory usage
- Error rates
- Tool usage statistics

### 3. Debug Information
- Task execution traces
- Message flow diagrams
- State transitions
- Resource utilization

### 4. Error Tracking
- Exception handling
- Stack traces
- Context preservation
- Recovery procedures

## Resource Management

### 1. Memory Optimization
```python
class CrewChatContext:
    def __init__(self):
        self.max_history_size = settings.MAX_CHAT_HISTORY
        self._history = collections.deque(maxlen=self.max_history_size)
```

### 2. Connection Management
```python
class CrewChatService:
    def __init__(self):
        self.db_pool = DatabaseConnectionPool(
            max_connections=settings.MAX_DB_CONNECTIONS,
            timeout=settings.DB_TIMEOUT
        )
```

### 3. Cache Strategy
```python
class CrewStateCache:
    def __init__(self):
        self.cache = TTLCache(
            maxsize=settings.MAX_CREW_STATES,
            ttl=settings.CREW_STATE_TTL
        )
```

### 4. Cleanup Procedures
```python
async def cleanup_abandoned_sessions():
    """Cleanup crew chat sessions that have been inactive"""
    threshold = timezone.now() - timedelta(hours=settings.INACTIVE_SESSION_THRESHOLD)
    abandoned = CrewChatSession.objects.filter(
        last_activity__lt=threshold,
        status='active'
    )
    for session in abandoned:
        await cleanup_session_resources(session)

```
