# Generated by Django 5.1.2 on 2025-01-18 21:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0009_remove_is_active_field'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Sales',
        ),
    ]
