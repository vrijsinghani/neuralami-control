# Generated by Django 5.1.2 on 2025-01-09 22:56

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OptimizedImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('original_file', models.FileField(upload_to='optimized_images/original/')),
                ('optimized_file', models.FileField(upload_to='optimized_images/optimized/')),
                ('original_size', models.IntegerField(help_text='Size in bytes')),
                ('optimized_size', models.IntegerField(help_text='Size in bytes')),
                ('compression_ratio', models.FloatField(help_text='Compression ratio in percentage')),
                ('settings_used', models.JSONField(help_text='Optimization settings used')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Optimized Image',
                'verbose_name_plural': 'Optimized Images',
                'ordering': ['-created_at'],
            },
        ),
    ]
