# Generated by Django 5.1.2 on 2024-12-16 16:56

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0036_remove_crewexecution_current_task_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agent',
            name='function_calling_llm',
            field=models.CharField(blank=True, default='gemini/gemini-exp-1206', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='agent',
            name='llm',
            field=models.CharField(default='gemini/gemini-exp-1206', max_length=100),
        ),
        migrations.AlterField(
            model_name='crew',
            name='function_calling_llm',
            field=models.CharField(blank=True, default='gemini/gemini-exp-1206', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='crew',
            name='manager_llm',
            field=models.CharField(blank=True, default='gemini/gemini-exp-1206', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='crew',
            name='planning_llm',
            field=models.CharField(blank=True, default='gemini/gemini-exp-1206', max_length=100, null=True),
        ),
        migrations.CreateModel(
            name='TokenUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('prompt_tokens', models.IntegerField(default=0)),
                ('completion_tokens', models.IntegerField(default=0)),
                ('total_tokens', models.IntegerField(default=0)),
                ('model', models.CharField(max_length=100)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='token_usage', to='agents.conversation')),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='agents.chatmessage')),
                ('tool_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='agents.toolrun')),
            ],
            options={
                'indexes': [models.Index(fields=['conversation', 'timestamp'], name='agents_toke_convers_113fb0_idx')],
            },
        ),
    ]
