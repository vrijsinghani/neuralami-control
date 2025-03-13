from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
import uuid

from apps.organizations.models import Organization, OrganizationMembership, Role, Permission
from apps.organizations.utils import OrganizationContext, get_current_organization, set_current_organization

User = get_user_model()

class OrganizationContextTests(TestCase):
    """Tests for organization context propagation."""
    
    def setUp(self):
        """Set up test data."""
        # Create users
        self.user1 = User.objects.create_user(username='user1', email='user1@example.com', password='password')
        self.user2 = User.objects.create_user(username='user2', email='user2@example.com', password='password')
        
        # Create organizations with owners
        self.org1 = Organization.objects.create(name='Org 1', owner=self.user1)
        self.org2 = Organization.objects.create(name='Org 2', owner=self.user2)
        
        # Create a system role for testing
        self.member_role = Role.objects.create(
            name='Member',
            is_system_role=True,
            description='Basic access to view and work with assigned clients'
        )
        
        # Create memberships
        OrganizationMembership.objects.create(
            user=self.user1,
            organization=self.org1,
            status='active',
            role=self.member_role
        )
        OrganizationMembership.objects.create(
            user=self.user2,
            organization=self.org2,
            status='active',
            role=self.member_role
        )
        
        # Create request factory for tests
        self.factory = RequestFactory()
    
    def test_organization_context_get_set(self):
        """Test basic get/set of organization context."""
        # Set organization context
        set_current_organization(self.org1)
        
        # Check it was set correctly
        current_org = get_current_organization()
        self.assertEqual(current_org, self.org1)
        
        # Change to a different organization
        set_current_organization(self.org2)
        
        # Check it changed
        current_org = get_current_organization()
        self.assertEqual(current_org, self.org2)
    
    def test_organization_context_manager(self):
        """Test organization context manager."""
        # Set initial context
        set_current_organization(self.org1)
        self.assertEqual(get_current_organization(), self.org1)
        
        # Use context manager to temporarily change
        with OrganizationContext.organization_context(self.org2.id):
            self.assertEqual(get_current_organization(), self.org2)
            
            # Nested context
            with OrganizationContext.organization_context(self.org1.id):
                self.assertEqual(get_current_organization(), self.org1)
            
            # Back to second context
            self.assertEqual(get_current_organization(), self.org2)
        
        # Back to original
        self.assertEqual(get_current_organization(), self.org1)
    
    def test_organization_context_unified_api(self):
        """Test the unified organization context API."""
        # Clear context to start fresh
        OrganizationContext.clear_current()
        self.assertIsNone(OrganizationContext.get_current())
        
        # Set context using API
        OrganizationContext.set_current(self.org1)
        self.assertEqual(OrganizationContext.get_current(), self.org1)
        
        # Test with organization ID instead of object
        OrganizationContext.set_current(self.org2.id)
        self.assertEqual(OrganizationContext.get_current().id, self.org2.id)
        
        # Test with mocked request
        request = self.factory.get('/')
        request.organization = self.org1
        self.assertEqual(OrganizationContext.get_current(request), self.org1)
        
        # Clear context
        OrganizationContext.clear_current()
        self.assertIsNone(OrganizationContext.get_current()) 