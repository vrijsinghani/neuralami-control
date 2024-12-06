from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0014_remove_crew_step_callback_remove_crew_task_callback'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='crew',
            name='tasks',
        ),
    ]
