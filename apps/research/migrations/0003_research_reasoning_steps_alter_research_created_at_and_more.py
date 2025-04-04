# Generated by Django 5.1.5 on 2025-02-17 16:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('research', '0002_research_guidance'),
    ]

    operations = [
        migrations.AddField(
            model_name='research',
            name='reasoning_steps',
            field=models.JSONField(default=list),
        ),
        migrations.AlterField(
            model_name='research',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='research',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=20),
        ),
    ]
