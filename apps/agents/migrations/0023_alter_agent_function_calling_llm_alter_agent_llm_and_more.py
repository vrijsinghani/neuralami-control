# Generated by Django 4.2.9 on 2024-10-21 19:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0022_alter_agent_function_calling_llm_alter_agent_llm_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agent',
            name='function_calling_llm',
            field=models.CharField(blank=True, default='gemini/gemini-1.5-flash-latest', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='agent',
            name='llm',
            field=models.CharField(default='gemini/gemini-1.5-flash-latest', max_length=100),
        ),
        migrations.AlterField(
            model_name='crew',
            name='function_calling_llm',
            field=models.CharField(blank=True, default='gemini/gemini-1.5-flash-latest', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='crew',
            name='manager_llm',
            field=models.CharField(blank=True, default='gemini/gemini-1.5-flash-latest', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='crew',
            name='planning_llm',
            field=models.CharField(blank=True, default='gemini/gemini-1.5-flash-latest', max_length=100, null=True),
        ),
    ]
