import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import transaction
from apps.seo_manager.models import SummarizerUsage as OldSummarizerUsage
from apps.summarizer.models import SummarizerUsage as NewSummarizerUsage

def migrate_data():
    """
    Migrate data from the old SummarizerUsage model to the new one.
    """
    print("Starting data migration...")
    
    # Get all records from the old model
    old_records = OldSummarizerUsage.objects.all()
    print(f"Found {old_records.count()} records to migrate.")
    
    # Migrate each record
    migrated_count = 0
    with transaction.atomic():
        for old_record in old_records:
            # Create a new record with the same data
            new_record = NewSummarizerUsage(
                user=old_record.user,
                query=old_record.query,
                compressed_content=old_record.compressed_content,
                response=old_record.response,
                created_at=old_record.created_at,
                duration=old_record.duration,
                content_token_size=old_record.content_token_size,
                content_character_count=old_record.content_character_count,
                total_input_tokens=old_record.total_input_tokens,
                total_output_tokens=old_record.total_output_tokens,
                model_used=old_record.model_used
            )
            new_record.save()
            migrated_count += 1
    
    print(f"Successfully migrated {migrated_count} records.")

if __name__ == "__main__":
    migrate_data() 