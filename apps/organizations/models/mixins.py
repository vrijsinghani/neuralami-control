import logging
from django.db import models
from django.db.models.query import QuerySet

logger = logging.getLogger(__name__)

class OrganizationModelManager(models.Manager):
    """
    A model manager that automatically filters querysets based on the user's active organization.
    This ensures organization isolation at the query level without relying on view-level filtering.
    """
    def get_queryset(self):
        from ..utils import get_current_user, get_user_active_organization
        
        queryset = super().get_queryset()
        user = get_current_user()
        
        # Superusers can see all records when needed
        if user and user.is_superuser:
            return queryset
            
        # Regular users only see records from their organization
        if user and user.is_authenticated:
            org_id = get_user_active_organization(user)
            if org_id:
                logger.debug(f"Filtering queryset by organization: {org_id}")
                return queryset.filter(organization_id=org_id)
                
        # No organization context = no access (empty queryset)
        return queryset.none()


class OrganizationUnfilteredManager(models.Manager):
    """
    A model manager that does not filter by organization.
    This should be used only in administrative contexts or internal code where
    accessing records across organizations is explicitly needed.
    """
    pass


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
    
    # Organization-filtered manager - THIS IS NOW THE DEFAULT
    objects = OrganizationModelManager()
    
    # Unfiltered manager - use this explicitly only when needed
    unfiltered_objects = OrganizationUnfilteredManager()
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        # Ensure new objects get assigned to the current user's organization
        if not self.pk and not self.organization_id:
            from ..utils import get_current_user, get_current_organization
            user = get_current_user()
            
            if user and user.is_authenticated:
                # Try to get the organization from thread local storage first
                organization = get_current_organization()
                
                if organization:
                    self.organization = organization
                    logger.debug(f"Automatically set organization to {organization.name} for {self.__class__.__name__}")
                else:
                    # Fall back to querying the database for the user's active membership
                    try:
                        membership = user.organization_memberships.filter(status='active').first()
                        if membership:
                            self.organization = membership.organization
                            logger.debug(f"Automatically set organization to {membership.organization.name} for {self.__class__.__name__}")
                    except Exception as e:
                        logger.error(f"Error setting organization automatically: {e}")
        
        super().save(*args, **kwargs)

    @classmethod
    def get_for_organization(cls, organization_id, **kwargs):
        """
        Helper method to get objects for a specific organization.
        
        Args:
            organization_id: The organization ID to filter by
            **kwargs: Additional filter parameters
            
        Returns:
            QuerySet: Filtered queryset
        """
        return cls.unfiltered_objects.filter(organization_id=organization_id, **kwargs) 