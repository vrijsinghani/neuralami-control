# Organization Context Migration to ContextVars

This document outlines the migration of the organization context management system from thread-local storage to ContextVars, enabling proper context isolation in both synchronous and asynchronous execution environments.

## Overview

The application has been updated to use Python's `contextvars` module for maintaining organization context across both synchronous and asynchronous code execution. This provides several benefits:

1. **Async Support**: Organization context now works correctly in async views, WebSockets, and Celery tasks
2. **Improved Isolation**: Context is properly maintained even when using async/await
3. **Better Performance**: Reduces overhead in async applications
4. **Django Channels Compatible**: Works seamlessly with WebSocket consumers
5. **Backward Compatible**: Continues to work with existing synchronous code

## Key Changes

1. **Replaced thread-local storage with ContextVars**
   - Added context variables for user and organization
   - Maintained thread-local storage for backward compatibility

2. **Updated Middleware**
   - Added async-compatible middleware for ASGI applications
   - Ensured context is properly set and cleared

3. **Enhanced Organization Context**
   - Updated context manager to work in both sync and async contexts
   - Added proper token management for async context switching

4. **Added Async Shortcuts**
   - Created async versions of common utility functions
   - Implemented async version of secure `get_object_or_404`

5. **Created Organization-Aware WebSocket Consumers**
   - Added `OrganizationAwareConsumer` base class
   - Updated all WebSocket consumers to use the new base class
   - Added proper context handling in connect/disconnect methods

## Using Organization Context in Different Environments

### In Synchronous Views

No changes are needed for existing synchronous views. The context management works the same way it did before.

```python
def my_view(request):
    # Context is already set by middleware
    current_org = get_current_organization()
    # ...
```

### In Asynchronous Views

Async views automatically have access to the organization context via ContextVars:

```python
async def my_async_view(request):
    # Context is set by async middleware
    current_org = get_current_organization()
    # ...
```

### In WebSocket Consumers

All WebSocket consumers should now inherit from `OrganizationAwareConsumer`:

```python
from apps.common.websockets.organization_consumer import OrganizationAwareConsumer

class MyConsumer(OrganizationAwareConsumer):
    async def connect(self):
        # Set organization context first (from session)
        await super().connect()
        
        # Your connection logic here
        self.group_name = "my_group"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        # Your disconnection logic here
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        
        # Clear organization context
        await super().disconnect(close_code)
        
    # Your other consumer methods...
```

For consumers that need to maintain JSON functionality:

```python
from apps.common.websockets.organization_consumer import OrganizationAwareConsumer

class OrganizationAwareJsonConsumer(OrganizationAwareConsumer):
    """Combines organization context with JSON handling"""
    
    async def send_json(self, content, close=False):
        await self.send(text_data=json.dumps(content), close=close)
        
    async def receive(self, text_data, **kwargs):
        try:
            data = json.loads(text_data)
            await self.receive_json(data)
        except json.JSONDecodeError:
            await self.send_json({"error": "Invalid JSON"})
            
    async def receive_json(self, content):
        """Override in subclasses"""
        pass

class MyJsonConsumer(OrganizationAwareJsonConsumer):
    async def connect(self):
        await super().connect()  # Sets organization context
        # Your connection logic
        await self.accept()
```

### In Background Tasks

For Celery tasks, explicitly pass and set the organization context:

```python
@shared_task
def my_task(data, organization_id=None):
    # First try to get organization from the model if not provided
    if not organization_id:
        try:
            # Use unfiltered_objects to bypass organization filtering
            from myapp.models import MyModel
            obj = MyModel.unfiltered_objects.get(id=data['model_id'])
            organization_id = obj.organization_id
        except Exception as e:
            logger.warning(f"Could not determine organization: {str(e)}")
    
    # Set organization context using context manager
    from apps.organizations.utils import OrganizationContext
    from contextlib import nullcontext
    
    # Use the context manager if we have an organization ID
    context_manager = OrganizationContext.organization_context(organization_id) if organization_id else nullcontext()
    
    with context_manager:
        # Use organization_objects inside the context
        obj = MyModel.organization_objects.get(id=data['model_id'])
        # Do work within organization context
        # ...
```

### When Using Tools

Update tool initialization to include organization context:

```python
def execute_tool(tool_name, inputs, organization_id=None):
    # Set organization context
    from apps.organizations.utils import OrganizationContext
    
    with OrganizationContext.organization_context(organization_id):
        tool = load_tool(tool_name)
        result = tool.run(**inputs)
        return result
```

## Updated Task and WebSocket Integration

When tasks need to send messages to WebSocket consumers, they should ensure proper organization context is maintained:

1. **Pass organization_id when sending messages to channels**:

```python
# Inside a task with organization context
def process_data(data_id, organization_id=None):
    # Set organization context as shown above
    with organization_context_manager:
        # Process data
        result = process_something(data_id)
        
        # Send to WebSocket with organization context
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"data_{data_id}",
            {
                "type": "data_update",
                "status": "complete",
                "result": result,
                # Include organization ID to help consumers set context if needed
                "organization_id": organization_id
            }
        )
```

2. **WebSocket consumers can receive the organization_id**:

```python
async def data_update(self, event):
    """Handle data update event from channel layer"""
    # Organization context is already set in connect() through OrganizationAwareConsumer
    # But you can access organization_id from the event if needed
    organization_id = event.get('organization_id')
    
    await self.send_json({
        'type': 'data_update',
        'status': event['status'],
        'result': event['result']
    })
```

## Implementation Details

### Context Variables Definition

```python
# In apps/organizations/utils.py
import contextvars

# Context variables for organization context
_user_var = contextvars.ContextVar('user', default=None)
_organization_var = contextvars.ContextVar('organization', default=None)
```

### Context Management Functions

```python
def get_current_user():
    # Try contextvars first
    user = _user_var.get()
    if user is not None:
        return user
    
    # Fall back to thread local for backward compatibility
    return getattr(_thread_locals, 'user', None)

def set_current_organization(organization):
    # Set in contextvars
    _organization_var.set(organization)
    
    # Also set in thread local for backward compatibility
    _thread_locals.organization = organization
```

### Context Manager for Organization

```python
@classmethod
@contextmanager
def organization_context(cls, organization_id):
    """
    Context manager for temporarily setting organization context.
    Works in both sync and async code thanks to ContextVars.
    """
    # Save tokens for restoring context later
    user_token = _user_var.set(_user_var.get())
    org_token = _organization_var.set(_organization_var.get())
    
    try:
        # Import here to avoid circular imports
        from apps.organizations.models import Organization
        
        # Get the organization object
        organization = Organization.objects.get(id=organization_id)
        # Set as current
        cls.set_current(organization)
        yield organization
    finally:
        # Restore previous context using tokens
        _user_var.reset(user_token)
        _organization_var.reset(org_token)
```

### Organization-Aware WebSocket Consumer

```python
class OrganizationAwareConsumer(AsyncWebsocketConsumer):
    """
    Base WebSocket consumer that sets organization context from session.
    """
    
    async def set_organization_context(self):
        """Set organization context based on session data"""
        if not OrganizationContext:
            return False
            
        try:
            # Get session from scope
            session = self.scope.get('session', {})
            
            # Get organization ID from session
            org_id = session.get('active_organization_id')
            
            if not org_id:
                return False
                
            # Get organization object and set as current
            organization = await self.get_organization(org_id)
            if organization:
                OrganizationContext.set_current(organization)
                return True
                
            return False
        except Exception as e:
            return False
            
    async def connect(self):
        """Connect and set organization context"""
        await self.set_organization_context()
        
    async def disconnect(self, close_code):
        """Disconnect and clear organization context"""
        await self.clear_organization_context()
```

## Async Middleware Registration

In your `settings.py`, update the middleware configuration to include the async versions:

```python
# For a mixed sync/async application with Django Channels
MIDDLEWARE = [
    # ...
    'apps.organizations.middleware.OrganizationMiddleware',
    'apps.organizations.middleware.OrganizationSecurityMiddleware',
    # ...
]

# Optional async middleware list for ASGI applications
ASGI_MIDDLEWARE = [
    # ...
    'apps.organizations.middleware.OrganizationMiddlewareAsync',
    'apps.organizations.middleware.OrganizationSecurityMiddlewareAsync',
    # ...
]
```

## Migration Checklist

1. ✅ Update organization utils.py to use ContextVars
2. ✅ Add async versions of middleware classes
3. ✅ Update get_object_or_404 for async support
4. ✅ Update client utilities to be async compatible
5. ✅ Create OrganizationAwareConsumer base class
6. ✅ Update all WebSocket consumers to use OrganizationAwareConsumer

If deploying this update, ensure that:

1. All WebSocket consumers are updated to handle organization context
2. Celery tasks explicitly pass and set organization context
3. Background tasks include organization context
4. Testing includes both synchronous and asynchronous paths

## WebSocket Consumer Updates

The following WebSocket consumers were updated:

1. **BaseWebSocketConsumer**: Updated to inherit from OrganizationAwareConsumer
2. **ChatConsumer**: Updated connect/disconnect methods to handle organization context
3. **ResearchConsumer**: Updated to directly inherit from OrganizationAwareConsumer
4. **MetaTagsTaskConsumer**: Updated to use OrganizationAwareConsumer
5. **ConnectionTestConsumer**: Updated to use OrganizationAwareConsumer  
6. **CrewExecutionConsumer**: Updated to use OrganizationAwareConsumer
7. **SEOAuditConsumer**: Updated to use OrganizationAwareConsumer
8. **CrewKanbanConsumer**: Updated to use OrganizationAwareConsumer
9. **OptimizationConsumer**: Created OrganizationAwareJsonConsumer for JSON support

## Troubleshooting

If you encounter issues with organization context:

1. **Missing Context**: Check if `organization_id` is being passed to async functions
2. **Leaking Context**: Ensure context is being properly reset after use
3. **WebSocket Issues**: Verify that consumers are setting context from scope
4. **Task Issues**: Make sure Celery tasks are being passed organization context
5. **No Organization in Session**: WebSocket connections that don't have organization ID in the session will operate without organization context

## References

- [Python ContextVars documentation](https://docs.python.org/3/library/contextvars.html)
- [Django Channels and context variables](https://channels.readthedocs.io/en/stable/topics/authentication.html)
- [Asynchronous Django](https://docs.djangoproject.com/en/4.1/topics/async/) 