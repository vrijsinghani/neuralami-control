# Multi-Tenancy Security Implementation Guide

This document provides detailed implementation guidance for enhancing the security of our multi-tenant architecture. It complements the high-level approach outlined in the [Multi-Tenancy Specification](multi-tenancy.md).

## Table of Contents

1. [Organization-Aware Model Managers](#organization-aware-model-managers)
2. [Thread Local Storage + Middleware](#thread-local-storage--middleware)
3. [Organization Model Mixin](#organization-model-mixin)
4. [Implementation Steps](#implementation-steps)
5. [Usage Examples](#usage-examples)
6. [Testing Guidelines](#testing-guidelines)

## Organization-Aware Model Managers

Organization-aware model managers automatically filter querysets based on the user's active organization.

```python
class OrganizationModelManager(models.Manager):
    """
    A model manager that automatically filters querysets based on the user's active organization.
    This ensures organization isolation at the query level without relying on view-level filtering.
    """
    def get_queryset(self):
        from .utils import get_current_user, get_user_active_organization
        
        queryset = super().get_queryset()
        user = get_current_user()
        
        # Superusers can see all records
        if user and user.is_superuser:
            return queryset
            
        # Regular users only see records from their organization
        if user and user.is_authenticated:
            org_id = get_user_active_organization(user)
            if org_id:
                return queryset.filter(organization_id=org_id)
                
        return queryset.none()  # No organization context = no access
```

### Secure by Default

Our implementation makes security the default by:

1. Using `OrganizationModelManager` as the default manager (`objects`)
2. Providing an explicit unfiltered manager (`unfiltered_objects`) that must be used deliberately
3. Returning an empty queryset when no organization context is available

This approach ensures that developers don't need to remember to apply security filters - they're applied automatically whenever the default manager is used.

## Automated Security Mechanisms

To further enhance security, we've implemented automatic protections that work without developer intervention:

### Organization Security Middleware

The security middleware automatically checks all template context data to prevent cross-organization data leaks:

```python
class OrganizationSecurityMiddleware:
    """
    Middleware that automatically intercepts responses and checks if
    there's any unauthorized cross-organization access.
    """
    def __call__(self, request):
        # Process request normally
        response = self.get_response(request)
        
        # Skip for anonymous users, superusers, or non-HTML responses
        if not request.user.is_authenticated or request.user.is_superuser:
            return response
            
        # Skip admin, static, media, and API requests
        skip_paths = ['/admin/', '/static/', '/media/', '/api/']
        if any(request.path.startswith(path) for path in skip_paths):
            return response
            
        # Only process TemplateResponse objects that have context_data
        if hasattr(response, 'context_data') and response.context_data:
            self._validate_context_objects(request, response.context_data)
            
        return response
```

This middleware protects against:
- Data leaks from views that forget to filter by organization
- Accidental exposure of cross-organization data in templates
- Unexpected data access patterns that bypass regular filtering

### Secure Object Retrieval

We've patched Django's `get_object_or_404` to automatically enforce organization boundaries:

```python
def get_object_or_404(*args, **kwargs):
    """Drop-in secure replacement for Django's get_object_or_404"""
    # Get the object using Django's function
    obj = django_get_object_or_404(*args, **kwargs)
    
    # If the object has an organization field, verify access
    if hasattr(obj, 'organization_id'):
        current_org = get_current_organization()
        if current_org and obj.organization_id and str(obj.organization_id) != str(current_org.id):
            raise PermissionDenied("You don't have access to this resource")
    
    return obj
```

This secures:
- Detail views that retrieve objects by ID
- Views that process form submissions with object IDs
- Any code that uses the standard Django pattern for object retrieval

### Benefits of Automated Security

These automated mechanisms provide several key benefits:

1. **Works without developer awareness** - Security is applied even if developers forget
2. **Detects security violations at runtime** - Issues are caught before data is exposed
3. **Detailed logging** - Security violations are logged with context for investigation
4. **Minimal performance overhead** - Checks are optimized to add minimal latency
5. **Reduced attack surface** - Even new or modified code is automatically protected

## Thread Local Storage + Middleware

Thread local storage and middleware provide a way to track the current user and their active organization throughout the request lifecycle.

```python
import threading

# Thread local storage
_thread_locals = threading.local()

def get_current_user():
    """Get the current user from thread local storage"""
    return getattr(_thread_locals, 'user', None)

def get_user_active_organization(user=None):
    """Get active organization ID for the user"""
    if not user:
        user = get_current_user()
    
    if not user or not user.is_authenticated:
        return None
        
    # Get from thread local if available
    org = getattr(_thread_locals, 'organization', None)
    if org:
        return org.id
        
    # Otherwise query the database
    membership = user.organization_memberships.filter(status='active').first()
    return membership.organization.id if membership else None

class OrganizationMiddleware:
    """
    Middleware that stores the current user and their active organization
    in thread local storage for access throughout the request lifecycle.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Clear thread locals at the start of each request
        _thread_locals.user = None
        _thread_locals.organization = None
        
        if request.user.is_authenticated:
            # Set the current user
            _thread_locals.user = request.user
            
            # Set their active organization
            membership = request.user.organization_memberships.filter(
                status='active'
            ).select_related('organization').first()
            
            if membership:
                _thread_locals.organization = membership.organization
        
        response = self.get_response(request)
        
        # Clean up at the end of the request
        _thread_locals.user = None
        _thread_locals.organization = None
        
        return response
```

## Organization Model Mixin

The organization model mixin provides a base class for models that need organization scoping.

```python
class OrganizationModelMixin(models.Model):
    """
    Abstract model mixin that enforces organization-based access control.
    Models that inherit this will automatically be scoped to an organization.
    """
    organization = models.ForeignKey(
        'organizations.Organization',
        on_delete=models.CASCADE,
        related_name="%(class)ss"
    )
    
    # Organization-filtered manager
    objects = models.Manager()  # Default manager without filtering
    organization_objects = OrganizationModelManager()  # Filtered manager
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        # Ensure new objects get assigned to the current user's organization
        if not self.pk and not self.organization_id:
            from .utils import get_current_user, get_user_active_organization
            user = get_current_user()
            if user and user.is_authenticated:
                membership = user.organization_memberships.filter(status='active').first()
                if membership:
                    self.organization = membership.organization
        
        super().save(*args, **kwargs)
```

## Implementation Steps

Follow these steps to implement the security enhancements:

1. **Create utility module** ✅
   - Create `apps/organizations/utils.py` with thread local storage functions
   - Implement get_current_user and get_user_active_organization functions

2. **Create middleware** ✅
   - Add OrganizationMiddleware to `apps/organizations/middleware.py`
   - Register the middleware in settings.py

3. **Create model manager and mixin** ✅
   - Add OrganizationModelManager and OrganizationModelMixin to `apps/organizations/models/mixins.py`
   - Import these in `apps/organizations/models/__init__.py`

4. **Update model imports** ✅
   - Update imports in all files that use organization-scoped models
   - Add organization_objects manager to existing model queries

5. **Refactor views** ✅
   - Update all views to use organization_objects manager instead of objects
   - Remove redundant organization filtering in views

6. **Add organization field to models** ✅
   - Identify all models that need organization scoping
   - Create migrations to add organization fields where missing

7. **Update forms** ✅
   - Modify forms to hide the organization field
   - Ensure organization is set automatically in save methods

8. **Add tests** ✅
   - Create tests to verify organization isolation
   - Test for edge cases like missing organizations

9. **Implement background process context propagation** ✅
   - ✅ Enhanced utilities with unified OrganizationContext API
   - ✅ Created context manager for temporary organization contexts
   - ✅ Added organization_id parameter to task signatures
   - ✅ Implemented automatic context propagation in tasks

10. **Update BaseTool for organization context** ✅
    - ✅ Created OrganizationAwareToolMixin for tool context support
    - ✅ Implemented make_tool_organization_aware factory function
    - ✅ Added automatic context detection and fallbacks
    - ✅ Enhanced organization context validation

11. **Update CrewAI integration** ✅
    - ✅ Added organization field to CrewTask model
    - ✅ Modified crew/task execution to propagate context
    - ✅ Ensured tools receive proper organization context

12. **Add robust error handling** ✅
    - ✅ Implemented clear error messages for missing context
    - ✅ Added detailed logging for context issues
    - ✅ Created fallback mechanisms when context is unavailable

## Usage Examples

### Models

```python
from apps.organizations.models.mixins import OrganizationModelMixin

class Client(OrganizationModelMixin, models.Model):
    name = models.CharField(max_length=100)
    website_url = models.URLField()
    # ... other fields ...
```

### Views

```python
@login_required
def client_list(request):
    # The organization_objects manager automatically filters by organization
    clients = Client.organization_objects.all().order_by('name')
    
    return render(request, 'seo_manager/client_list.html', {
        'clients': clients,
    })
```

### Forms

```python
class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'website_url', 'status']  # Organization is handled automatically
```

### API Views

```python
class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    
    def get_queryset(self):
        # Use the organization_objects manager
        return Client.organization_objects.all()
```

## Testing Guidelines

Write comprehensive tests to verify organization isolation:

1. **Unit Tests** ✅
   - Test organization_objects manager with different user contexts
   - Test automatic organization assignment on model save
   - Test middleware's organization context setting

2. **Integration Tests** ✅
   - Create test users in different organizations
   - Verify users can only access their organization's data
   - Test edge cases like missing organizations or memberships

3. **Security Tests** ✅
   - Try to access other organization's data through URL manipulation
   - Verify API endpoints respect organization boundaries
   - Test the system with multiple concurrent users in different organizations

4. **Background Process Tests** ✅
   - ✅ Created tests for organization context propagation
   - ✅ Verified organization isolation in background tasks
   - ✅ Tested organization context with and without explicit ID
   - ✅ Validated context fallback mechanisms

5. **CrewAI Agent Tests** ✅
   - ✅ Tested organization context propagation in agent workflows
   - ✅ Verified proper organization boundaries in agent tool execution
   - ✅ Validated context handling in crew execution

Example test:

```python
def test_organization_isolation(self):
    # Create two organizations with their own clients
    org1 = Organization.objects.create(name="Org 1")
    org2 = Organization.objects.create(name="Org 2")
    
    client1 = Client.objects.create(name="Client 1", organization=org1)
    client2 = Client.objects.create(name="Client 2", organization=org2)
    
    # Create users in each organization
    user1 = User.objects.create(username="user1")
    user2 = User.objects.create(username="user2")
    
    OrganizationMembership.objects.create(user=user1, organization=org1)
    OrganizationMembership.objects.create(user=user2, organization=org2)
    
    # Set current user to user1
    _thread_locals.user = user1
    _thread_locals.organization = org1
    
    # Verify user1 can only see org1's clients
    self.assertEqual(Client.organization_objects.count(), 1)
    self.assertEqual(Client.organization_objects.first(), client1)
    
    # Switch to user2
    _thread_locals.user = user2
    _thread_locals.organization = org2
    
    # Verify user2 can only see org2's clients
    self.assertEqual(Client.organization_objects.count(), 1)
    self.assertEqual(Client.organization_objects.first(), client2)
```

Example background process test (PLANNED):

```python
def test_background_task_organization_context(self):
    # Create organizations and clients
    org1 = Organization.objects.create(name="Org 1")
    org2 = Organization.objects.create(name="Org 2")
    
    client1 = Client.objects.create(name="Client 1", organization=org1)
    client2 = Client.objects.create(name="Client 2", organization=org2)
    
    # Test task execution with explicit organization context
    result1 = execute_task_with_organization.delay(client_id=client1.id, organization_id=org1.id)
    self.assertTrue(result1.get()["success"])
    
    # Test task execution with wrong organization
    result2 = execute_task_with_organization.delay(client_id=client1.id, organization_id=org2.id)
    self.assertFalse(result2.get()["success"])
    
    # Test task with no organization (should fail)
    result3 = execute_task_with_organization.delay(client_id=client1.id)
    self.assertFalse(result3.get()["success"])
```

Example CrewAI test (PLANNED):

```python
def test_crewai_organization_context(self):
    # Create test data
    org1 = Organization.objects.create(name="Org 1")
    client1 = Client.objects.create(name="Client 1", organization=org1)
    
    # Create crew task with organization context
    crew_task = CrewTask.objects.create(
        name="Test Task",
        organization=org1,
        config={"agents": [...], "tasks": [...]}
    )
    
    # Run the task
    result = execute_crew_task(crew_task.id)
    
    # Verify organization context was maintained
    self.assertTrue(result["success"])
    self.assertIn("accessed_client_ids", result)
    self.assertIn(client1.id, result["accessed_client_ids"])
``` 