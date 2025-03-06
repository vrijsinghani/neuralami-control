from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
from core.storage import SecureFileStorage

# Create a storage instance for organization logos
organization_logo_storage = SecureFileStorage(
    private=True,
    collection='organization_logos'
)

class Organization(models.Model):
    """
    A top-level entity that contains users, clients, and resources.
    Acts as the foundation for multi-tenancy in the application.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='owned_organizations'
    )
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)
    billing_email = models.EmailField(blank=True, null=True)
    billing_details = models.JSONField(default=dict, blank=True)
    max_clients = models.PositiveIntegerField(default=5)  # Default until subscription plans are implemented
    logo = models.ImageField(
        upload_to='', 
        storage=organization_logo_storage,
        blank=True, 
        null=True
    )
    
    def __str__(self):
        return self.name
        
    class Meta:
        ordering = ['name']
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'


class Permission(models.Model):
    """
    Represents a single permission that can be assigned to a role.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, help_text="For grouping related permissions")
    
    def __str__(self):
        return f"{self.name} ({self.codename})"
    
    class Meta:
        ordering = ['category', 'codename']
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'


class Role(models.Model):
    """
    Defines a set of permissions that can be assigned to organization members.
    Can be system-wide or specific to an organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='roles',
        null=True,
        blank=True,
        help_text="If null, this is a system-wide role"
    )
    is_system_role = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        Permission,
        related_name='roles'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        if self.organization:
            return f"{self.name} ({self.organization.name})"
        return f"{self.name} (System)"
    
    class Meta:
        unique_together = ('name', 'organization')
        ordering = ['organization', 'name']
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'


class OrganizationMembership(models.Model):
    """
    Represents the relationship between a user and an organization,
    including their role and invitation status.
    """
    MEMBERSHIP_STATUS_CHOICES = (
        ('invited', 'Invited'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, 
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organization_memberships'
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name='memberships'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_invitations'
    )
    status = models.CharField(
        max_length=20,
        choices=MEMBERSHIP_STATUS_CHOICES,
        default='invited'
    )
    invitation_sent_at = models.DateTimeField(null=True, blank=True)
    invitation_accepted_at = models.DateTimeField(null=True, blank=True)
    custom_permissions = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.user} in {self.organization} as {self.role}"
    
    class Meta:
        unique_together = ('organization', 'user')
        ordering = ['organization', 'user']
        verbose_name = 'Organization Membership'
        verbose_name_plural = 'Organization Memberships' 