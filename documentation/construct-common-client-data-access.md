# Common Client Data Access Implementation Guide

## Overview

This document outlines the approach for creating a centralized client data access utility that adheres to the multi-tenancy security model while providing consistent access to client data across different contexts (HTTP requests, WebSockets, background tasks, etc.). The goal is to maintain this code in a single location to avoid duplication and ensure consistent security practices.

## Current State Analysis

Our analysis of the current codebase reveals several patterns for accessing client data:

1. **Direct implementations in multiple modules**: 
   - `crew.py`'s `get_client_data` function 
   - `client_utils.py`'s `ClientDataUtils` class
   - `views_tools.py`'s client attribute methods
   - `manager.py`'s `ClientDataManager` class

2. **Different context handling**:
   - HTTP request context (middleware-based)
   - WebSocket context (outside HTTP processing)
   - Background task context (Celery)
   - CLI commands

3. **Credential security challenges**:
   - Secure credential storage and retrieval
   - Proper property ID/URL extraction methods
   - Fallback mechanisms for missing fields

## Requirements

The common client data access utility should fulfill the following requirements:

### Functional Requirements

1. **Unified API**: Provide a consistent interface for all components to access client data
2. **Multi-context Support**: 
   - HTTP requests via middleware
   - WebSockets connection handling
   - Background tasks execution
   - CLI commands
3. **Complete Data Access**: Retrieve all client attributes and relationships, including:
   - Basic client information (name, URL, etc.)
   - Business objectives and target audience
   - Analytics credentials and property IDs
   - Search Console credentials and property URLs
   - Related SEO projects and targeted keywords
4. **Credential Handling**: Consistent extraction of credentials with proper fallback mechanisms
5. **Method Propagation**: Support for calling methods like `get_property_id()` and `get_property_url()`

### Security Requirements

1. **Organization Boundaries**: Strictly enforce organization boundaries through:
   - Organization-aware model access
   - Proper context propagation
   - Secure object retrieval methods
2. **Context Preservation**: Maintain organization context across different execution environments
3. **Explicit Context Support**: Allow explicit organization_id override for special cases
4. **Security First**: Default to most secure approach with deliberate opt-out when necessary
5. **Audit Trail**: Log all client data access with organization context for security auditing

### Technical Requirements

1. **Synchronous and Asynchronous APIs**: Support both sync and async operations
2. **Efficient Caching**: Cache client data appropriately to minimize database access
3. **Graceful Error Handling**: Clear error messages and fallback mechanisms
4. **Comprehensive Logging**: Detailed logging for debugging and auditing
5. **Performance Optimization**: Minimize performance impact with proper caching and query optimization

## Architecture

The common client data access utility should follow this architectural approach:

### Core Components

1. **ClientDataUtils**: Centralized service for all client data operations
   - Replaces individual implementations across the codebase
   - Provides sync and async interfaces
   - Handles organization context securely

2. **OrganizationContextManager**: Manages organization context across execution environments
   - Compatible with middleware-based context tracking
   - Provides WebSocket context handling
   - Supports explicit context setting for background tasks

3. **CredentialManager**: Specializes in secure credential handling
   - Consistent extraction of credentials and properties
   - Manages property ID and URL retrieval
   - Provides fallback mechanisms

### Context Handling 

1. **HTTP Request Context**: 
   - Use existing middleware and thread local storage
   - Access organization from request object

2. **WebSocket Context**:
   - Extract organization context during handshake
   - Pass context through WebSocket consumer
   - Store context in WebSocket scope

3. **Background Task Context**:
   - Pass organization_id in task parameters
   - Explicitly set context at task start
   - Support context manager for task execution

## Implementation Strategy

### Phase 1: Create Core Service

1. Develop `ClientDataUtils` with organization context awareness
2. Implement both sync and async interfaces
3. Handle organization boundary enforcement

### Phase 2: Integrate Existing Code

1. Refactor `client_utils.py` to use the new service
2. Update WebSocket consumers to use the service
3. Modify task code to use the service with explicit context

### Phase 3: Extend and Optimize

1. Add comprehensive caching layer
2. Implement detailed logging and auditing
3. Optimize query performance

## Usage Patterns

The service should support these usage patterns:

### HTTP Request Context

```python
# Automatic organization context from request
client_data = ClientDataUtils.get_client_data(client_id)
```

### WebSocket Context

```python
# Organization context from WebSocket handshake
client_data = await ClientDataUtils.get_client_data_async(
    client_id, organization_id=self.scope.get('organization_id')
)
```

### Background Task Context

```python
# Explicit organization context in task
# Assumes OrganizationContext is available and provides organization_context manager
try:
    from apps.organizations.utils import OrganizationContext
    with OrganizationContext.organization_context(organization_id):
        # Calls within this block will use the specified organization_id
        client = ClientDataUtils.get_client_by_id(client_id) 
        if client:
            client_data = ClientDataUtils.get_client_data(client)
        # ... other operations needing organization context ...
except ImportError:
    # Fallback if OrganizationContext is not available or needed differently
    # Pass organization_id directly if the context manager isn't used/available
    client = ClientDataUtils.get_client_by_id(client_id, organization_id=organization_id)
    if client:
        client_data = ClientDataUtils.get_client_data(client, organization_id=organization_id)

```

## Migration Plan

1. Create the new service without disrupting existing code
2. Update each component one at a time to use the new service
3. Run comprehensive tests for each migrated component
4. Phase out old implementations once migration is complete

## Testing Strategy

1. **Unit Tests**: Verify each service method works with proper organization context
2. **Integration Tests**: Test service across different context types
3. **Security Tests**: Verify organization boundaries are properly enforced
4. **Performance Tests**: Measure impact on application performance

## Conclusion

This centralized approach will eliminate code duplication, ensure consistent security practices, and make future maintenance easier by having a single source of truth for client data access logic. 