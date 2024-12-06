from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import connections, transaction
from django.db.models import Q
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

        with transaction.atomic(using=target_db):
            # Copy Client Groups first (maintaining hierarchy)
            self.copy_client_groups(source_db, target_db)
            # Copy Clients and related data
            self.copy_clients(source_db, target_db)

        self.stdout.write(self.style.SUCCESS('Successfully completed clients database copy operation'))

    def copy_client_groups(self, source_db, target_db):
        """Copy client groups while maintaining parent-child relationships"""
        client_groups = list(ClientGroup.objects.using(source_db).all())
        if not client_groups:
            self.stdout.write(self.style.NOTICE("No ClientGroup objects to copy"))
            return

        # Create mapping of old PKs to new objects
        group_mapping = {}
        
        for group in client_groups:
            old_pk = group.pk
            existing_group = ClientGroup.objects.using(target_db).filter(name=group.name).first()
            
            if existing_group:
                # Update existing group
                existing_group.name = group.name
                existing_group.save(using=target_db)
                group_mapping[old_pk] = existing_group
            else:
                # Create new group
                group.pk = None
                group.parent = None  # Temporarily remove parent reference
                group.save(using=target_db)
                group_mapping[old_pk] = group

        # Update parent relationships
        for original_group in client_groups:
            if original_group.parent_id:
                new_group = group_mapping[original_group.pk]
                new_group.parent = group_mapping.get(original_group.parent_id)
                new_group.save(using=target_db)

        self.stdout.write(self.style.SUCCESS(f"Processed {len(client_groups)} ClientGroup objects"))

    def copy_clients(self, source_db, target_db):
        clients = list(Client.objects.using(source_db).all())
        if not clients:
            self.stdout.write(self.style.NOTICE("No Client objects to copy"))
            return

        for client in clients:
            # Try to find existing client by name
            existing_client = Client.objects.using(target_db).filter(
                Q(name=client.name) | Q(website_url=client.website_url)
            ).first()

            if existing_client:
                # Update existing client
                for field in client._meta.fields:
                    if field.name not in ['id', 'created_at']:
                        setattr(existing_client, field.name, getattr(client, field.name))
                existing_client.save(using=target_db)
                self.copy_related_data(client, existing_client, source_db, target_db)
            else:
                # Create new client
                old_pk = client.pk
                client.pk = None
                client.save(using=target_db)
                self.copy_related_data(Client.objects.using(source_db).get(pk=old_pk), client, source_db, target_db)

        self.stdout.write(self.style.SUCCESS(f"Processed {len(clients)} Client objects"))

    def copy_related_data(self, source_client, target_client, source_db, target_db):
        # Copy Google Analytics Credentials
        ga_creds = GoogleAnalyticsCredentials.objects.using(source_db).filter(client=source_client).first()
        if ga_creds:
            existing_ga = GoogleAnalyticsCredentials.objects.using(target_db).filter(client=target_client).first()
            if existing_ga:
                # Update existing credentials
                for field in ga_creds._meta.fields:
                    if field.name not in ['id', 'client']:
                        setattr(existing_ga, field.name, getattr(ga_creds, field.name))
                existing_ga.save(using=target_db)
            else:
                # Create new credentials
                ga_creds.pk = None
                ga_creds.client = target_client
                ga_creds.save(using=target_db)

        # Copy Search Console Credentials
        sc_creds = SearchConsoleCredentials.objects.using(source_db).filter(client=source_client).first()
        if sc_creds:
            existing_sc = SearchConsoleCredentials.objects.using(target_db).filter(client=target_client).first()
            if existing_sc:
                # Update existing credentials
                for field in sc_creds._meta.fields:
                    if field.name not in ['id', 'client']:
                        setattr(existing_sc, field.name, getattr(sc_creds, field.name))
                existing_sc.save(using=target_db)
            else:
                # Create new credentials
                sc_creds.pk = None
                sc_creds.client = target_client
                sc_creds.save(using=target_db)

        # Copy Targeted Keywords
        keywords = TargetedKeyword.objects.using(source_db).filter(client=source_client)
        for keyword in keywords:
            existing_keyword = TargetedKeyword.objects.using(target_db).filter(
                client=target_client,
                keyword=keyword.keyword
            ).first()
            
            if existing_keyword:
                # Update existing keyword
                for field in keyword._meta.fields:
                    if field.name not in ['id', 'client', 'created_at']:
                        setattr(existing_keyword, field.name, getattr(keyword, field.name))
                existing_keyword.save(using=target_db)
            else:
                # Create new keyword
                keyword.pk = None
                keyword.client = target_client
                keyword.save(using=target_db)

        # Copy SEO Data
        seo_data_entries = SEOData.objects.using(source_db).filter(client=source_client)
        for data in seo_data_entries:
            existing_data = SEOData.objects.using(target_db).filter(
                client=target_client,
                date=data.date
            ).first()
            
            if existing_data:
                # Update existing SEO data
                for field in data._meta.fields:
                    if field.name not in ['id', 'client']:
                        setattr(existing_data, field.name, getattr(data, field.name))
                existing_data.save(using=target_db)
            else:
                # Create new SEO data
                data.pk = None
                data.client = target_client
                data.save(using=target_db)

        # Copy SEO Projects
        projects = SEOProject.objects.using(source_db).filter(client=source_client)
        for project in projects:
            existing_project = SEOProject.objects.using(target_db).filter(
                client=target_client,
                title=project.title
            ).first()
            
            if existing_project:
                # Update existing project
                for field in project._meta.fields:
                    if field.name not in ['id', 'client', 'created_at']:
                        setattr(existing_project, field.name, getattr(project, field.name))
                existing_project.save(using=target_db)
            else:
                # Create new project
                project.pk = None
                project.client = target_client
                project.save(using=target_db)

        self.stdout.write(self.style.SUCCESS(f"Processed related data for Client: {target_client.name}")) 