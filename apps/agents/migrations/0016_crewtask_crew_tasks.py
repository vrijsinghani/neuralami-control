# Create a new file: apps/agents/migrations/0016_crewtask_crew_tasks.py

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0015_remove_crew_tasks'),
    ]

    operations = [
        migrations.CreateModel(
            name='CrewTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('crew', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crew_tasks', to='agents.crew')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='agents.task')),
            ],
            options={
                'ordering': ['order'],
                'unique_together': {('crew', 'task')},
            },
        ),
        migrations.AddField(
            model_name='crew',
            name='tasks',
            field=models.ManyToManyField(through='agents.CrewTask', to='agents.Task'),
        ),
    ]