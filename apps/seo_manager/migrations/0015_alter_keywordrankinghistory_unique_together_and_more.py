# Generated by Django 4.2.9 on 2024-10-28 13:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('seo_manager', '0014_client_client_profile_targetedkeyword_seoproject_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='keywordrankinghistory',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='keywordrankinghistory',
            name='client',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, related_name='keyword_rankings', to='seo_manager.client'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='keywordrankinghistory',
            name='keyword_text',
            field=models.CharField(default='NA', help_text='Actual keyword text, useful when no TargetedKeyword reference exists', max_length=255),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='keywordrankinghistory',
            name='keyword',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ranking_history', to='seo_manager.targetedkeyword'),
        ),
        migrations.AlterUniqueTogether(
            name='keywordrankinghistory',
            unique_together={('client', 'keyword_text', 'date')},
        ),
    ]
