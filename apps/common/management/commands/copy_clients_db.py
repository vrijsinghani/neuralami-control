from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections
from apps.seo_manager.models import (
    Client,
    GoogleAnalyticsCredentials,
    SearchConsoleCredentials,
    TargetedKeyword,
    SEOData,
    ClientGroup,
    SEOProject,
)

class Command(BaseCommand):
    help = 'Copy Client and related data from source database to target database'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default='default', help='Source database')
        parser.add_argument('--target', type=str, required=True, help='Target database')

    def handle(self, *args, **options):
        source_db = options['source']
        target_db = options['target']

        # Check databases
        if source_db not in connections:
            self.stderr.write(self.style.ERROR(f"Source database '{source_db}' is not configured"))
            return
        if target_db not in connections:
            self.stderr.write(self.style.ERROR(f"Target database '{target_db}' is not configured"))
            return

        # Copy Client Groups
        self.copy_client_groups(source_db, target_db)

        # Copy Clients and related data
        self.copy_clients(source_db, target_db)

        self.stdout.write(self.style.SUCCESS('Successfully completed clients database copy operation'))

    def copy_client_groups(self, source_db, target_db):
        client_groups = list(ClientGroup.objects.using(source_db).all())
        if not client_groups:
            self.stdout.write(self.style.NOTICE("No ClientGroup objects to copy"))
            return

        for group in client_groups:
            group.pk = None  # Reset primary key to create a new instance
            group.save(using=target_db)  # Save to target database

        self.stdout.write(self.style.SUCCESS(f"Copied {len(client_groups)} ClientGroup objects"))

    def copy_clients(self, source_db, target_db):
        clients = list(Client.objects.using(source_db).all())
        if not clients:
            self.stdout.write(self.style.NOTICE("No Client objects to copy"))
            return

        for client in clients:
            # Copy Client
            client.pk = None  # Reset primary key to create a new instance
            client.save(using=target_db)  # Save to target database

            # Copy related data
            self.copy_related_data(client, source_db, target_db)

        self.stdout.write(self.style.SUCCESS(f"Copied {len(clients)} Client objects"))

    def copy_related_data(self, client, source_db, target_db):
        # Copy Google Analytics Credentials
        ga_credentials = GoogleAnalyticsCredentials.objects.using(source_db).filter(client=client).first()
        if ga_credentials:
            ga_credentials.pk = None  # Reset primary key
            ga_credentials.client = client  # Associate with new client
            ga_credentials.save(using=target_db)

        # Copy Search Console Credentials
        sc_credentials = SearchConsoleCredentials.objects.using(source_db).filter(client=client).first()
        if sc_credentials:
            sc_credentials.pk = None  # Reset primary key
            sc_credentials.client = client  # Associate with new client
            sc_credentials.save(using=target_db)

        # Copy Targeted Keywords
        targeted_keywords = TargetedKeyword.objects.using(source_db).filter(client=client)
        for keyword in targeted_keywords:
            keyword.pk = None  # Reset primary key
            keyword.client = client  # Associate with new client
            keyword.save(using=target_db)

        # Copy SEO Data
        seo_data = SEOData.objects.using(source_db).filter(client=client)
        for data in seo_data:
            data.pk = None  # Reset primary key
            data.client = client  # Associate with new client
            data.save(using=target_db)

        # Copy SEO Projects
        seo_projects = SEOProject.objects.using(source_db).filter(client=client)
        for project in seo_projects:
            project.pk = None  # Reset primary key
            project.client = client  # Associate with new client
            project.save(using=target_db)

        self.stdout.write(self.style.SUCCESS(f"Copied related data for Client: {client.name}")) 