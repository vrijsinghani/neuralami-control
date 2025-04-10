from django.core.management.base import BaseCommand
from apps.seo_manager.models import Client
from apps.organizations.models import Organization
from apps.organizations.utils import OrganizationContext
import logging
import uuid

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test OAuth implementation'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Starting OAuth Test ==='))

        # Use the specific organization ID you mentioned
        org_id = '091a9243-73d4-4691-b143-298b2ecb3836'

        try:
            # Get the organization
            org = Organization.objects.get(id=uuid.UUID(org_id))
            self.stdout.write(f"Found organization: {org.name} (ID: {org.id})")

            # Use the proper OrganizationContext from utils
            with OrganizationContext.organization_context(org_id):
                self.stdout.write("Organization context set successfully")

                # Now we can use the models directly with the organization context
                clients = Client.objects.all()
                self.stdout.write(f"Found {clients.count()} clients for organization {org.name}")

                if not clients.exists():
                    self.stdout.write(self.style.ERROR("No clients found for this organization"))
                    return

                # List all clients
                self.stdout.write("\nClients:")
                for i, client in enumerate(clients[:5], 1):
                    self.stdout.write(f"{i}. {client.name} (ID: {client.id})")

                if clients.count() > 5:
                    self.stdout.write(f"...and {clients.count() - 5} more")

                # Test GA credentials
                self.stdout.write("\n=== Testing Google Analytics Credentials ===")
                clients_with_ga = Client.objects.filter(ga_credentials__isnull=False)

                if not clients_with_ga.exists():
                    self.stdout.write("No clients with Google Analytics credentials found")
                else:
                    self.stdout.write(f"Found {clients_with_ga.count()} clients with Google Analytics credentials")

                    for client in clients_with_ga[:3]:
                        self.stdout.write(f"\nClient: {client.name} (ID: {client.id})")

                        try:
                            # Get the credentials directly
                            ga_creds = client.ga_credentials
                            self.stdout.write(f"  - GA credentials ID: {ga_creds.id}")
                            self.stdout.write(f"  - Access token: {'Present' if ga_creds.access_token else 'Missing'}")
                            self.stdout.write(f"  - Refresh token: {'Present' if ga_creds.refresh_token else 'Missing'}")

                            # Test getting a service
                            service = ga_creds.get_service()
                            if service:
                                self.stdout.write(self.style.SUCCESS("    - GA service created successfully"))
                            else:
                                self.stdout.write(self.style.ERROR("    - Failed to create GA service"))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"    - Error: {str(e)}"))

                # Test SC credentials
                self.stdout.write("\n=== Testing Search Console Credentials ===")
                clients_with_sc = Client.objects.filter(sc_credentials__isnull=False)

                if not clients_with_sc.exists():
                    self.stdout.write("No clients with Search Console credentials found")
                else:
                    self.stdout.write(f"Found {clients_with_sc.count()} clients with Search Console credentials")

                    for client in clients_with_sc[:3]:
                        self.stdout.write(f"\nClient: {client.name} (ID: {client.id})")

                        try:
                            # Get the credentials directly
                            sc_creds = client.sc_credentials
                            self.stdout.write(f"  - SC credentials ID: {sc_creds.id}")
                            self.stdout.write(f"  - Access token: {'Present' if sc_creds.access_token else 'Missing'}")
                            self.stdout.write(f"  - Refresh token: {'Present' if sc_creds.refresh_token else 'Missing'}")

                            # Test getting a service
                            service = sc_creds.get_service()
                            if service:
                                self.stdout.write(self.style.SUCCESS("    - SC service created successfully"))
                            else:
                                self.stdout.write(self.style.ERROR("    - Failed to create SC service"))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"    - Error: {str(e)}"))

                # Test Ads credentials
                self.stdout.write("\n=== Testing Google Ads Credentials ===")
                clients_with_ads = Client.objects.filter(ads_credentials__isnull=False)

                if not clients_with_ads.exists():
                    self.stdout.write("No clients with Google Ads credentials found")
                else:
                    self.stdout.write(f"Found {clients_with_ads.count()} clients with Google Ads credentials")

                    for client in clients_with_ads[:3]:
                        self.stdout.write(f"\nClient: {client.name} (ID: {client.id})")

                        try:
                            # Get the credentials directly
                            ads_creds = client.ads_credentials
                            self.stdout.write(f"  - Ads credentials ID: {ads_creds.id}")
                            self.stdout.write(f"  - Access token: {'Present' if ads_creds.access_token else 'Missing'}")
                            self.stdout.write(f"  - Refresh token: {'Present' if ads_creds.refresh_token else 'Missing'}")

                            # Test getting credentials
                            creds = ads_creds.get_credentials()
                            if creds:
                                self.stdout.write(self.style.SUCCESS("    - Ads credentials created successfully"))
                            else:
                                self.stdout.write(self.style.ERROR("    - Failed to create Ads credentials"))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"    - Error: {str(e)}"))

        except Organization.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Organization with ID {org_id} not found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))

        self.stdout.write(self.style.SUCCESS('\n=== OAuth Test Complete ==='))
