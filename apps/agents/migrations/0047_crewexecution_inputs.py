# Generated by Django 5.1.2 on 2025-01-18 21:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0046_remove_crewexecution_inputs_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='crewexecution',
            name='inputs',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
