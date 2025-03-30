# Multi-Tenancy & Organization-Based Access Control Specification

## Implementation Progress

We have completed the following key components of the multi-tenancy implementation:

1. Created the core Organization model with all required fields
2. Implemented the OrganizationMembership model for user-organization relationships
3. Created the Role and Permission models for access control
4. Defined system roles (Owner, Admin, Member) with appropriate permissions
5. Modified the Client model to support organization-based access
6. Set up admin interfaces for all new models
7. Updated client views to filter by organization and enforce access control
8. Created data migration to assign existing clients to organizations
9. Implemented basic organization settings page
10. Implemented architectural security enhancements:
   - ✅ Created Organization Model Mixin for standardized organization relationships
   - ✅ Implemented thread-local storage for organization context
   - ✅ Added organization middleware for automatic context tracking
   - ✅ Built organization-aware model managers for automatic filtering
   - ✅ Applied mixin to Client model as first secured model
   - ✅ Added security middleware for automatic cross-organization access prevention
   - ✅ Created secure get_object_or_404 replacement for automatic organization validation
11. Extended organization isolation to additional models:
   - ✅ Applied OrganizationModelMixin to SEOAuditResult model
   - ✅ Applied OrganizationModelMixin to Research model
12. Implemented organization switching and context awareness:
   - ✅ Created organization switcher component in navigation
   - ✅ Added persistent organization context indicator in UI
   - ✅ Implemented session-based organization context tracking
13. Added organization status management:
   - ✅ Implemented organization status toggle functionality
   - ✅ Added UI controls for activating/deactivating organizations
   - ✅ Enhanced middleware to enforce restrictions on inactive organizations

Next steps:
1. ✅ Implement organization context propagation for asynchronous processes:
   - ✅ Add explicit organization context passing to background tasks
   - ✅ Enhance BaseTool to automatically set organization context
   - ✅ Implement organization context for CrewAI agent execution
   - ✅ Create unified context management approach for all execution environments
   - ✅ Add organization_id parameter to all tool execution calls
   - ✅ Modify organization context utilities to support both request and background contexts
2. ✅ Apply the OrganizationModelMixin to remaining models:
   - ✅ Research model
   - ✅ SEOAuditResult model
   - ✅ Client model
   - ✅ OptimizedImage model
   - ✅ OptimizationJob model
3. Implement invitation system for new members

## Overview

This document outlines the implementation of a multi-tenant architecture for our application, enabling users to create organizations, invite team members, and control access to clients and features based on roles and permissions.

### Goals

- Enable users to create organizations and invite others
- Implement role-based permissions within organizations
- Restrict client access based on organization membership
- Support subscription plans with different limits and features
- Provide a seamless experience across all applications
- Maintain data isolation between organizations

## Terminology

- **Organization**: A top-level entity that contains users, clients, and resources
- **Member**: A user who belongs to an organization with a specific role
- **Role**: A set of permissions that define what actions a member can perform
- **Subscription Plan**: A package of features and limits assigned to an organization
- **Client**: A customer entity that belongs to an organization

## Data Models

### Organization

```
- id: UUID
- name: String
- description: Text (optional)
- created_at: DateTime
- updated_at: DateTime
- subscription_plan: ForeignKey to SubscriptionPlan
- owner: ForeignKey to User
- is_active: Boolean
- settings: JSONField (for organization-specific settings)
- billing_email: String (optional)
- billing_details: JSONField (optional)
- max_clients: Integer (derived from subscription)
- logo: ImageField (optional)
```

### Organization Membership

```
- id: UUID
- organization: ForeignKey to Organization
- user: ForeignKey to User
- role: ForeignKey to Role
- created_at: DateTime
- updated_at: DateTime
- invited_by: ForeignKey to User
- status: String (invited, active, suspended)
- invitation_sent_at: DateTime (optional)
- invitation_accepted_at: DateTime (optional)
- custom_permissions: JSONField (for user-specific permission overrides)
```

### Role

```
- id: UUID
- name: String
- organization: ForeignKey to Organization (null for system roles)
- is_system_role: Boolean
- permissions: ManyToMany to Permission
- created_at: DateTime
- updated_at: DateTime
- description: Text
```

### Permission

```
- id: UUID
- codename: String (unique)
- name: String
- description: Text
- category: String (for grouping related permissions)
```

### Client Modifications

```
- organization: ForeignKey to Organization
- created_by: ForeignKey to User
- assigned_to: ForeignKey to User (optional)
- visibility: String (organization, restricted)
- allowed_members: ManyToMany to OrganizationMembership (for restricted visibility)
```

### Subscription Plan

```
- id: UUID
- name: String
- description: Text
- price_monthly: Decimal
- price_yearly: Decimal
- max_clients: Integer
- max_members: Integer
- features: JSONField
- is_active: Boolean
```

## Core Functionality

### User Registration & Organization Creation

The system should allow users to register and create their own organization, becoming the organization owner by default.

### Invitation System

Organizations should be able to invite new members, specifying their roles during invitation. Users should be able to accept or decline invitations.

### User Experience

The UI should provide intuitive organization management, clear indication of permissions, and easy switching between organizations for users who belong to multiple.

#### Organization Context UI

For users who belong to multiple organizations, the system must make the active organization context clear:

1. **Active Organization Indicator**
   - Prominently display the current active organization in the header/navigation
   - Use visual cues (color, icon) to reinforce the active context
   - Show organization logo if available

2. **Context-Aware Actions**
   - When creating new resources (clients, projects, etc.), explicitly show "Creating [resource] for [Organization Name]"
   - Include organization context in confirmation dialogs: "This will be created in [Organization Name]"
   - Display organization name in breadcrumbs for all resources

3. **Organization Switcher**
   - Implement an easily accessible organization switcher in the main navigation
   - Show all organizations the user belongs to with roles
   - Provide visual distinction for the active organization
   - Allow setting a default/preferred organization

4. **Transitional Guidance**
   - After switching organizations, show a brief confirmation: "Now viewing [Organization Name]"
   - Redirect to appropriate landing page for the selected organization
   - Maintain clear separation between organizations in all views

These UI elements are critical for preventing confusion about which organization resources belong to, particularly when users work across multiple organizations.

### Client Access Control

Access to clients should be restricted based on organization membership and user roles. Organizations should be able to control client visibility and assignments.

### Subscription Management

Organizations should have subscription plans that determine their limits and available features. Upgrades and downgrades should be handled seamlessly.

## Security Considerations

### Data Isolation

Complete isolation of data between organizations must be enforced at all levels, including database queries, API endpoints, and UI.

### Access Control Enforcement

The permission system must be consistently enforced across all applications, with proper checks at the view, template, and API levels.

## Cross-Application Integration

The multi-tenancy system must work consistently across all applications, with shared components for organization context and permission checking.

## Implementation Phases

### Phase 1: Core Organization Model

#### Checklist - Phase 1

- [x] Create Organization model
  - [x] Define required fields: name, description, created_at, updated_at
  - [x] Add owner foreign key to User
  - [x] Add is_active boolean field
  - [x] Include settings JSONField for organization configuration
  - [x] Add logo ImageField
  - NOTE: Used UUID as primary key for all models to ensure uniqueness across instances.

- [x] Create OrganizationMembership model
  - [x] Define organization and user foreign keys
  - [x] Add role foreign key
  - [x] Include status field with invited/active/suspended options
  - [x] Add invitation tracking fields
  - [x] Include invited_by foreign key
  - NOTE: Added unique_together constraint for organization and user to prevent duplicate memberships.

- [x] Create basic Role model
  - [x] Define name and description fields
  - [x] Add organization foreign key (null for system roles)
  - [x] Include is_system_role flag
  - NOTE: Added unique_together constraint for name and organization to enforce unique role names within an organization.

- [x] Define system roles
  - [x] Owner: Full control over organization
  - [x] Admin: Manage members and clients
  - [x] Member: Basic access to assigned clients
  - NOTE: Created a data migration to define system roles with appropriate permissions. Used a comprehensive set of permissions organized by category (organization, members, clients).

- [x] Modify Client model
  - [x] Add organization foreign key
  - [x] Add created_by foreign key to track creator
  - [x] Update database migrations
  - NOTE: Added organization and created_by fields to the Client model with null=True to allow for a smooth migration of existing data.

- [x] Create admin interfaces
  - [x] Admin interface for organizations
  - [x] Admin interface for memberships
  - [x] Admin interface for roles
  - NOTE: Created admin interfaces with useful filtering and search capabilities.

- [x] Update client views
  - [x] Filter clients by organization in all listing views
  - [x] Add organization field to client creation forms
  - [x] Set organization automatically based on user
  - [x] Update client detail views to check organization access
  - NOTE: Implemented organization filtering across all client-related views. Made sure that users can only access clients that belong to their organization. Applied organization checks to client list, detail, edit, and delete views.

- [x] Create organization settings page
  - [x] Basic organization profile editing
    - [x] View organization details
    - [x] Edit organization name, description, and logo
    - [x] Update organization settings
  - [x] Member listing and management
  - [x] Organization status controls
  - NOTE: Created a complete organization settings page with profile information, editing capabilities, member listing, and organization status controls.

- [x] Implement data migration
  - [x] Create default organization for each existing user
  - [x] Assign existing clients to appropriate organizations
  - [x] Set up initial roles for existing users
  - NOTE: Created migration that successfully assigned all clients to organizations. Used a sophisticated approach that first tries to use the created_by field, then falls back to user activity data, and finally to admin users if no other match is found.

### Phase 2: Invitation & Member Management

#### Checklist - Phase 2

- [ ] Implement invitation system
  - [ ] Create invitation email templates
  - [ ] Add send invitation functionality
  - [ ] Build invitation acceptance page
  - [ ] Handle invitation expiration and resending
  - [ ] Support bulk invitations

- [ ] Create member management UI
  - [ ] List members with roles and status
  - [ ] Add interface for inviting new members
  - [ ] Include controls for changing member roles
  - [ ] Add member removal functionality
  - [ ] Create member profile view within organization

- [x] Add organization switching capability
  - [x] Create organization switcher component
    - [x] Show all available organizations with roles
    - [x] Highlight active organization
    - [x] Display organization logo when available
  - [x] Add to navigation/header
    - [x] Make organization context visible at all times
    - [x] Add visual cues for active organization
  - [x] Save last active organization preference
  - [x] Handle switching context seamlessly
    - [x] Show confirmation of organization switch
    - [x] Redirect to appropriate dashboard
  - [x] Add context indicators to resource creation flows
    - [x] Show active organization in global navigation
    - [x] Add organization name to all key interfaces

- [ ] Implement user profile enhancements
  - [ ] Show organizations user belongs to
  - [ ] Display pending invitations
  - [ ] Add organization-specific settings

- [ ] Create email notification system
  - [ ] Send notifications for new invitations
  - [ ] Alert for role changes
  - [ ] Notify about organization status changes

- [ ] Implement basic permission enforcement
  - [ ] Add permission checking to client views
  - [ ] Restrict organization management to owners/admins
  - [ ] Hide UI elements based on permissions

### Phase 3: Advanced Permissions

#### Checklist - Phase 3

- [ ] Create Permission model
  - [ ] Define codename, name, description fields
  - [ ] Add category field for grouping
  - [ ] Build comprehensive permission list

- [ ] Enhance Role model
  - [ ] Add many-to-many relationship with Permission
  - [ ] Support custom organization-specific roles
  - [ ] Create role management UI

- [ ] Implement granular permission system
  - [ ] Define all required permissions across applications
  - [ ] Group permissions by category
  - [ ] Create permission management interface

- [ ] Add client-specific permissions
  - [ ] Implement visibility controls (organization-wide vs. restricted)
  - [ ] Add allowed_members field for restricted visibility
  - [ ] Create client assignment functionality

- [ ] Create permission management UI
  - [ ] Role editing interface
  - [ ] Permission visualization
  - [ ] Permission assignment to roles

- [ ] Implement permission checking infrastructure
  - [ ] Create centralized permission checking service
  - [ ] Add permission decorators for views
  - [ ] Implement template-level permission checks
  - [ ] Add API endpoint permission validation

- [ ] Add permission audit logging
  - [ ] Track permission changes
  - [ ] Log access attempts
  - [ ] Create permission audit reports

### Phase 4: Subscription Management

#### Checklist - Phase 4

- [ ] Create SubscriptionPlan model
  - [ ] Define name, description, pricing fields
  - [ ] Add limits (max_clients, max_members)
  - [ ] Include features JSONField
  - [ ] Set is_active flag

- [ ] Add subscription relationship to Organization
  - [ ] Create subscription_plan foreign key
  - [ ] Add billing information fields
  - [ ] Include derived limits fields

- [ ] Implement plan limits enforcement
  - [ ] Check client count against max_clients
  - [ ] Verify member count against max_members
  - [ ] Create limit exceeded notifications
  - [ ] Implement grace periods for overages

- [ ] Build subscription management UI
  - [ ] Plan comparison interface
  - [ ] Upgrade/downgrade workflow
  - [ ] Billing history view
  - [ ] Payment method management

- [ ] Create usage tracking system
  - [ ] Track client and member counts
  - [ ] Monitor feature usage
  - [ ] Build usage visualization
  - [ ] Create admin reports on usage

- [ ] Implement feature flag system
  - [ ] Control feature access based on subscription
  - [ ] Create consistent feature checking
  - [ ] Add upgrade prompts for premium features

- [ ] Add billing integration
  - [ ] Connect to payment processor
  - [ ] Handle subscription events
  - [ ] Generate invoices and receipts
  - [ ] Process plan changes

## Testing Strategy

### Unit Testing

#### Checklist - Unit Tests

- [ ] Test organization creation and validation
- [ ] Test membership creation and roles
- [ ] Test permission checking logic
- [ ] Test client filtering and access control
- [ ] Test subscription limit enforcement
- [ ] Test invitation process
- [ ] Test migration process

### Integration Testing

#### Checklist - Integration Tests

- [ ] Test end-to-end invitation flow
- [ ] Test organization switching
- [ ] Test permission enforcement across apps
- [ ] Test subscription upgrade/downgrade
- [ ] Test client sharing between members
- [ ] Test admin capabilities
- [ ] Test user experience flows

### User Acceptance Testing

#### Checklist - UAT

- [ ] Create test scenarios for different user roles
- [ ] Design UAT script for organization setup
- [ ] Develop UAT script for member management
- [ ] Create UAT script for permission testing
- [ ] Prepare UAT for subscription management
- [ ] Design UAT for client access control
- [ ] Document expected behaviors for all scenarios

## Additional Considerations

### Analytics & Reporting

#### Checklist - Reporting Features

- [ ] Update analytics to segment by organization
- [ ] Create organization-level dashboards
- [ ] Implement usage reports for admins
- [ ] Add member activity tracking
- [ ] Create client utilization reports
- [ ] Build subscription utilization metrics
- [ ] Support aggregated vs. granular reporting views

### API Considerations

#### Checklist - API Updates

- [ ] Add organization context to all API endpoints
- [ ] Update authentication to include organization
- [ ] Create organization-aware rate limiting
- [ ] Document multi-tenant API requirements
- [ ] Implement API permission checks
- [ ] Version API for backward compatibility
- [ ] Create organization management API endpoints

### Performance Optimization

#### Checklist - Performance Measures

- [ ] Analyze query performance with organization filtering
- [ ] Implement caching for permission checks
- [ ] Create indexes for organization-related queries
- [ ] Optimize membership lookups
- [ ] Plan for database scaling with multiple organizations
- [ ] Monitor performance metrics during implementation
- [ ] Create performance test suite

## Migration Strategy

### Data Migration

#### Checklist - Migration Tasks

- [ ] Create default organization for each existing user
- [ ] Assign existing clients to appropriate organizations
- [ ] Set up initial roles for existing users
- [ ] Migrate existing permissions
- [ ] Preserve existing capabilities during transition
- [ ] Validate data integrity post-migration
- [ ] Create rollback plan for migration issues

### User Experience During Migration

#### Checklist - Transition Experience

- [ ] Design transition notification for users
- [ ] Create documentation explaining new system
- [ ] Implement guided tour of new features
- [ ] Provide support contact for migration issues
- [ ] Create FAQ for common questions
- [ ] Plan phased rollout to manage risk
- [ ] Monitor system during transition period

## Future Enhancements

### Potential Future Features

- [ ] Organization templates for quick setup
- [ ] Cross-organization collaboration features
- [ ] Advanced audit and compliance reporting
- [ ] Organization-specific branding throughout UI
- [ ] Custom dashboards per organization
- [ ] Organization merge/split capabilities
- [ ] Advanced billing and invoicing features

## Documentation Requirements

### Documentation Checklist

- [ ] Create administrator guide for multi-tenancy
- [ ] Write user documentation for organizations
- [ ] Develop role and permission reference
- [ ] Create subscription management guide
- [ ] Document client sharing best practices
- [ ] Create developer guide for permission system
- [ ] Design onboarding guide for new organization setup

## Architectural Security Enhancement

The current implementation relies on view-level filtering for organization-based access control, which poses significant security risks. Any missed filter in a view could expose data from other organizations. We will implement a more robust, multi-layered security approach.

### Recommended Architecture

We will implement a layered defense approach with four key components:

1. **Organization-Aware Model Managers**
   - ✅ Custom model managers that automatically filter querysets by organization
   - ✅ **Security By Default**: The default `objects` manager automatically filters by organization
   - ✅ Explicit `unfiltered_objects` manager for admin use only
   - ✅ Protection at the query level rather than relying on view-level filtering

2. **Thread Local Storage + Middleware**
   - ✅ Middleware to track the current user and their active organization
   - ✅ Thread local storage to make organization context available throughout the request lifecycle
   - ✅ Consistent access to the user's active organization from anywhere in the code

3. **Organization Model Mixin**
   - ✅ Base model mixin for all organization-scoped models
   - ✅ Automatic organization assignment for new records
   - ✅ Standardized field definitions and access patterns

4. **Automated Security Mechanisms**
   - ✅ **Security Middleware**: Automatically checks for cross-organization data access in all responses
   - ✅ **Secure get_object_or_404**: Drop-in replacement that adds organization checks automatically
   - Both mechanisms work without developers needing to remember to use them

### Context Propagation for Background Processes

We have successfully implemented organization context propagation for background processes, tools, and agents. This ensures that security boundaries are maintained across all execution environments, including asynchronous operations.

1. **Unified Organization Context API**
   ```python
   class OrganizationContext:
       @classmethod
       def get_current(cls, request=None):
           """Get organization from multiple possible sources"""
           # Try request first (highest priority)
           if request and hasattr(request, 'organization'):
               return request.organization
               
           # Try thread local storage
           org = get_current_organization()
           if org:
               return org
               
           # Get from current user's membership
           user = get_current_user()
           if user and user.is_authenticated:
               return get_user_active_organization(user)
               
           return None
       
       @classmethod
       def set_current(cls, organization, request=None):
           """Set organization in all relevant storage mechanisms"""
           # Set in thread local storage
           set_current_organization(organization)
           
           # Set in request if provided
           if request:
               request.organization = organization
       
       @classmethod
       @contextmanager
       def organization_context(cls, organization_id):
           """Context manager for temporarily setting organization context"""
           previous_org = get_current_organization()
           try:
               organization = Organization.objects.get(id=organization_id)
               cls.set_current(organization)
               yield organization
           finally:
               # Restore previous context
               cls.set_current(previous_org)
   ```

2. **Organization-Aware Tasks**
   ```python
   @organization_aware_task()
   def my_task(arg1, arg2, organization_id=None):
       """
       A task that automatically handles organization context
       
       This task will have the correct organization context set
       based on the organization_id parameter
       """
       # Task execution happens within the correct organization context
       # ...
       
   # Calling the task with organization context
   my_task.delay(arg1, arg2, organization_id=org.id)
   ```

3. **Organization-Aware Tools**
   ```python
   # Make any tool organization-aware
   OrganizationAwareTool = make_tool_organization_aware(OriginalTool)
   
   # Use it with organization context
   tool = OrganizationAwareTool(organization_id=org.id)
   result = tool.run(...)
   ```

4. **CrewAI Integration**
   ```python
   # The CrewTask model now includes organization context
   class CrewTask(models.Model):
       crew = models.ForeignKey(Crew, on_delete=models.CASCADE)
       task = models.ForeignKey(Task, on_delete=models.CASCADE)
       order = models.PositiveIntegerField(default=0)
       organization = models.ForeignKey('organizations.Organization', 
                                       on_delete=models.CASCADE,
                                       null=True, blank=True)
   ```

5. **Tool Execution with Organization Context**
   ```python
   # Tool execution automatically includes organization context
   def run_tool(tool_id, inputs, organization_id=None):
       """Run a tool with organization context"""
       # Set organization context for this execution
       if organization_id:
           OrganizationContext.set_current(organization_id)
           
       # Load and run the tool with proper context
       tool = load_tool_in_task(tool_model, organization_id)
       result = tool.run(**inputs)
       return result
   ```

This implementation ensures:

- Organization context is properly propagated to background tasks
- Tools automatically receive and maintain organization context
- CrewAI agents operate within the correct organizational boundaries
- Security is maintained across synchronous and asynchronous execution
- Error handling appropriately handles missing or invalid organization context

### Security Benefits

This architectural approach provides multiple layers of security:

- **Defense in Depth**: Organization filtering happens at multiple levels, not just in views
- **Fail Secure**: The default behavior is to deny access unless explicitly granted
- **Consistent Policy**: The same access control logic applies across the application
- **Reduced Surface Area**: Fewer places where organization checks can be missed
- **Cleaner Code**: Views don't need to implement explicit organization filtering logic
- **Secure by Default**: Developers don't need to remember to apply security filters
- **Passive Protection**: Security middleware and patched Django shortcuts provide automatic protection

### Implementation Details

For detailed implementation instructions, code examples, and best practices, see the [Multi-Tenancy Security Implementation Guide](multitenancy-security.md). 