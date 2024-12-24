from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.db.models import JSONField

class LiteLLMBaseModel(models.Model):
    """Abstract base model for LiteLLM models to ensure consistent database configuration"""
    class Meta:
        abstract = True
        managed = False  # Ensures Django won't try to create/modify tables
        default_permissions = ()  # Removes default permissions
        app_label = 'home'

    def save(self, *args, **kwargs):
        raise NotImplementedError("This model is read-only")

    def delete(self, *args, **kwargs):
        raise NotImplementedError("This model is read-only")

class LiteLLMSpendLog(LiteLLMBaseModel):
    """Model representing the LiteLLM spend logs table"""
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

    class Meta(LiteLLMBaseModel.Meta):
        db_table = 'LiteLLM_SpendLogs'

    def __str__(self):
        return f"SpendLog {self.request_id}"

class Last30dKeysBySpend(LiteLLMBaseModel):
    """Model representing the Last 30 Days Keys by Spend view"""
    api_key = models.TextField()  # Not using primary key for views
    key_alias = models.TextField(null=True)
    key_name = models.TextField(null=True)
    total_spend = models.FloatField(null=True)

    class Meta(LiteLLMBaseModel.Meta):
        db_table = 'Last30dKeysBySpend'
        ordering = ['-total_spend']

    def __str__(self):
        return f"Key {self.key_name or self.api_key}"

class Last30dModelsBySpend(LiteLLMBaseModel):
    """Model representing the Last 30 Days Models by Spend view"""
    model = models.TextField()  # Not using primary key for views
    total_spend = models.FloatField(null=True)

    class Meta(LiteLLMBaseModel.Meta):
        db_table = 'Last30dModelsBySpend'
        ordering = ['-total_spend']

    def __str__(self):
        return f"Model {self.model}"

class Last30dTopEndUsersSpend(LiteLLMBaseModel):
    """Model representing the Last 30 Days Top End Users by Spend view"""
    end_user = models.TextField()  # Not using primary key for views
    total_events = models.BigIntegerField(null=True)
    total_spend = models.FloatField(null=True)

    class Meta(LiteLLMBaseModel.Meta):
        db_table = 'Last30dTopEndUsersSpend'
        ordering = ['-total_spend']

    def __str__(self):
        return f"User {self.end_user}"
