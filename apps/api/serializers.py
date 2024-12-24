from rest_framework import serializers
#from apps.api.models import *

try:
    from apps.common.models import Sales
except:
    pass

class SalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sales
        fields = '__all__'

# Tool Serializers
class GoogleAnalyticsToolSerializer(serializers.Serializer):
    client_id = serializers.IntegerField(required=True)
    start_date = serializers.CharField(default="28daysAgo")
    end_date = serializers.CharField(default="today") 
    metrics = serializers.CharField(default="totalUsers,sessions")
    dimensions = serializers.CharField(default="date")
    dimension_filter = serializers.CharField(required=False, allow_null=True)
    metric_filter = serializers.CharField(default="sessions>10")
    currency_code = serializers.CharField(required=False, allow_null=True)
    keep_empty_rows = serializers.BooleanField(default=False)
    limit = serializers.IntegerField(default=1000)
    offset = serializers.IntegerField(required=False, allow_null=True)
    data_format = serializers.ChoiceField(
        choices=['raw', 'summary', 'compact'],
        default='raw'
    )
    top_n = serializers.IntegerField(required=False, allow_null=True)
    time_granularity = serializers.ChoiceField(
        choices=['daily', 'weekly', 'monthly', 'auto'],
        default='auto'
    )
    aggregate_by = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True
    )
    metric_aggregation = serializers.ChoiceField(
        choices=['sum', 'average', 'min', 'max'],
        default='sum'
    )
    include_percentages = serializers.BooleanField(default=False)
    normalize_metrics = serializers.BooleanField(default=False)
    round_digits = serializers.IntegerField(required=False, allow_null=True)
    include_period_comparison = serializers.BooleanField(default=False)
    detect_anomalies = serializers.BooleanField(default=False)
    moving_average_window = serializers.IntegerField(required=False, allow_null=True)
