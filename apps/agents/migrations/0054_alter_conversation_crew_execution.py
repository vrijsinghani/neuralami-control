# Generated by Django 5.1.5 on 2025-03-04 20:33

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0053_alter_agent_function_calling_llm_alter_agent_llm_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conversation',
            name='crew_execution',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chat_conversations', to='agents.crewexecution'),
        ),
    ]
