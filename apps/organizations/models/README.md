# Organization Models Package

This package contains the core models for organization-based multi-tenancy.

## Structure

- `__init__.py` - Re-exports all models for convenient imports
- `base.py` - Contains the core models (Organization, Role, Permission, OrganizationMembership)
- `mixins.py` - Contains the OrganizationModelMixin and OrganizationModelManager for use in other models

## Usage

### Importing Models

```python
# Import directly from the package
from apps.organizations.models import Organization, OrganizationMembership

# Or import specific models from their modules
from apps.organizations.models.base import Organization
from apps.organizations.models.mixins import OrganizationModelMixin
```

### Applying the Mixin to Models

To make a model organization-aware, inherit from the OrganizationModelMixin:

```python
from django.db import models
from apps.organizations.models import OrganizationModelMixin

class MyModel(OrganizationModelMixin, models.Model):
    name = models.CharField(max_length=100)
    # other fields...
    
    # The organization field is automatically added by the mixin
```

### Security by Default

The mixin provides two managers with different security properties:

- `objects` - The **default** manager that automatically filters by the current user's organization. This ensures organization data isolation by default.

- `unfiltered_objects` - An unfiltered manager that should be used only in administrative contexts where accessing records across organizations is explicitly needed.

```python
# Secure by default - Only shows objects from the user's current organization
my_objects = MyModel.objects.all()

# For admin purposes only - CAUTION: Shows objects across all organizations
all_objects = MyModel.unfiltered_objects.all()
```

### Important Security Note

Always use the default `objects` manager for regular application code. The `unfiltered_objects` manager should only be used in:

1. Admin interfaces
2. Management commands
3. Data migration scripts
4. Cross-organization reporting (by superusers only)

Accidental use of `unfiltered_objects` could lead to data leakage between organizations!

## Thread-Local Storage

The organization context is maintained in thread-local storage and set/cleared by the OrganizationMiddleware for each request. 