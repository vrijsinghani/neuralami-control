from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField

# Create your models here.
class LiteLLMSpendLog(models.Model):
    request_id = models.TextField(primary_key=True)
    call_type = models.TextField()
    api_key = ArrayField(models.TextField())
    spend = models.FloatField(default=0.0, db_column='spend')
    total_tokens = models.IntegerField(default=0)
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    startTime = models.DateTimeField()
    endTime = models.DateTimeField()
    completionStartTime = models.DateTimeField(null=True)
    model = ArrayField(models.TextField())
    model_id = ArrayField(models.TextField(), null=True)
    model_group = ArrayField(models.TextField(), null=True)
    api_base = ArrayField(models.TextField(), null=True)
    user = ArrayField(models.TextField(), null=True)
    metadata = JSONField(null=True, default=dict)
    cache_hit = ArrayField(models.TextField(), null=True)
    cache_key = ArrayField(models.TextField(), null=True)
    request_tags = JSONField(null=True, default=list)
    team_id = models.TextField(null=True)
    end_user = models.TextField(null=True)
    requester_ip_address = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = 'LiteLLM_SpendLogs'
        app_label = 'home'

class Last30dKeysBySpend(models.Model):
    api_key = models.TextField(null=True)
    key_alias = models.TextField(null=True)
    key_name = models.TextField(null=True)
    total_spend = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = 'Last30dKeysBySpend'
        app_label = 'home'

class Last30dModelsBySpend(models.Model):
    model = models.TextField(null=True)
    total_spend = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = 'Last30dModelsBySpend'
        app_label = 'home'

class Last30dTopEndUsersSpend(models.Model):
    end_user = models.TextField(null=True)
    total_events = models.BigIntegerField(null=True)
    total_spend = models.FloatField(null=True)

    class Meta:
        managed = False
        db_table = 'Last30dTopEndUsersSpend'
        app_label = 'home'

# Create your models here.
