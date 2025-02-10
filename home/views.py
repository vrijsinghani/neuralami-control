import logging
from datetime import datetime, timedelta

# Django imports
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (LoginView, PasswordChangeView,
                                     PasswordResetConfirmView, PasswordResetView)
from django.core.cache import cache
from django.db.models import Avg, Count, F, Sum, ExpressionWrapper, FloatField, DurationField, Case, When
from django.db.models.functions import TruncDay, Extract, Cast
from django.shortcuts import render, redirect
from django.utils import timezone

# Local imports
from home.forms import (LoginForm, RegistrationForm, UserPasswordChangeForm,
                       UserPasswordResetForm, UserSetPasswordForm)
from .models import (LiteLLMSpendLog, Last30dModelsBySpend,
                    Last30dTopEndUsersSpend, Last30dKeysBySpend)

# Setup logging
logger = logging.getLogger(__name__)

# Cache configuration
CACHE_VERSION = '1.0'  # Increment this to invalidate all caches

#
# Dashboard Views
#
def default(request):
  context = {
    'parent': 'dashboard',
    'segment': 'default'
  }
  return render(request, 'pages/dashboards/default.html', context)

#
# Profile Views
#
def profile_overview(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'profile',
    'segment': 'profile_overview'
  }
  return render(request, 'pages/profile/overview.html', context)


def new_user(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'users',
    'segment': 'new_user'
  }
  return render(request, 'pages/users/new-user.html', context)

#
# Account Management Views
#
def settings(request):
  context = {
    'parent': 'accounts',
    'segment': 'settings'
  }
  return render(request, 'pages/account/settings.html', context)

#
# Authentication Views
#

# Class-based authentication views
class IllustrationLoginView(LoginView):
    """Handle user login with illustration template."""
    template_name = 'authentication/signin/illustration.html'
    form_class = LoginForm

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('/seo/')
        return super().get(request, *args, **kwargs)

class IllustrationResetView(PasswordResetView):
    """Handle password reset with illustration template."""
    template_name = 'authentication/reset/illustration.html'
    form_class = UserPasswordResetForm

class UserPasswordResetConfirmView(PasswordResetConfirmView):
    """Handle password reset confirmation."""
    template_name = 'authentication/reset-confirm/basic.html'
    form_class = UserSetPasswordForm

class UserPasswordChangeView(PasswordChangeView):
    """Handle password change for authenticated users."""
    template_name = 'authentication/change/basic.html'
    form_class = UserPasswordChangeForm

# Function-based authentication views
def illustration_register(request):
    """Handle user registration with illustration template."""
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/accounts/login/illustration-login/')
    else:
        form = RegistrationForm()

    context = {'form': form}
    return render(request, 'authentication/signup/illustration.html', context)

def logout_view(request):
    """Handle user logout and redirect to login page."""
    logout(request)
    return redirect('/accounts/login/illustration-login/')

def basic_lock(request):
    """Render basic lock screen."""
    return render(request, 'authentication/lock/basic.html')

def cover_lock(request):
    """Render cover lock screen."""
    return render(request, 'authentication/lock/cover.html')

def illustration_lock(request):
    """Render illustration lock screen."""
    return render(request, 'authentication/lock/illustration.html')

def illustration_verification(request):
    """Render illustration verification screen."""
    return render(request, 'authentication/verification/illustration.html')

#
# Error Handlers
#
def error_404(request, exception=None):
  return render(request, 'authentication/error/404.html')

def error_500(request, exception=None):
  return render(request, 'authentication/error/500.html')

#
# LLM Analytics Dashboard
#

@staff_member_required
def llm_dashboard(request):
    """
    View for the LLM analytics dashboard showing spend and usage metrics.
    Uses read-only access to litellm_logs database with granular caching.
    """
    try:
        logger.debug("Processing LLM dashboard request")
        # Calculate date range
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Get base queryset for spend logs
        base_qs = LiteLLMSpendLog.objects.using('litellm_logs')\
            .filter(startTime__gte=start_date)

        # Get cached stats or calculate
        stats_key = f'llm_dashboard_stats_v{CACHE_VERSION}'
        stats = cache.get(stats_key)
        
        if stats is None:
            logger.debug("Cache miss for stats, calculating...")
            # Calculate basic stats
            stats = base_qs.aggregate(
                total_spend=Sum('spend'),
                total_tokens=Sum('total_tokens'),
                total_requests=Count('request_id')
            )
            
            # Calculate averages
            if stats['total_requests'] > 0:
                stats['avg_tokens_per_request'] = stats['total_tokens'] / stats['total_requests']
                stats['avg_spend_per_request'] = stats['total_spend'] / stats['total_requests']
            else:
                stats['avg_tokens_per_request'] = 0
                stats['avg_spend_per_request'] = 0

            # Cache the stats
            cache.set(stats_key, stats, 60 * 5)  # Cache for 5 minutes

        # Get cached daily metrics or calculate
        daily_key = f'llm_dashboard_daily_metrics_v{CACHE_VERSION}'
        daily_metrics = cache.get(daily_key)
        
        if daily_metrics is None:
            logger.debug("Cache miss for daily metrics, calculating...")
            # Calculate daily metrics
            daily_metrics = base_qs\
                .annotate(
                    day=TruncDay('startTime'),
                    latency=ExpressionWrapper(
                        Extract(F('endTime') - F('startTime'), 'epoch'),
                        output_field=FloatField()
                    )
                )\
                .values('day')\
                .annotate(
                    total_spend=Sum('spend'),
                    total_tokens=Sum('total_tokens'),
                    request_count=Count('request_id'),
                    avg_latency=Avg('latency')
                )\
                .order_by('day')

            # Process metrics
            daily_metrics = list(daily_metrics)
            for metric in daily_metrics:
                metric['avg_latency'] = round(float(metric['avg_latency'] or 0), 2)

            # Cache the metrics
            cache.set(daily_key, daily_metrics, 60 * 5)

        # Get cached top metrics or calculate
        top_key = f'llm_dashboard_top_metrics_v{CACHE_VERSION}'
        top_metrics = cache.get(top_key)
        
        if top_metrics is None:
            logger.debug("Cache miss for top metrics, calculating...")
            # Calculate model-specific metrics
            model_metrics = base_qs\
                .values('model')\
                .annotate(
                    total_spend=Sum('spend'),
                    total_tokens=Sum('total_tokens'),
                    prompt_tokens=Sum('prompt_tokens'),
                    completion_tokens=Sum('completion_tokens'),
                    request_count=Count('request_id'),
                    avg_latency=Avg(
                        Extract(F('endTime') - F('startTime'), 'epoch')
                    )
                )\
                .annotate(
                    avg_tokens_per_request=Case(
                        When(request_count__gt=0,
                             then=Cast(F('total_tokens'), FloatField()) / Cast(F('request_count'), FloatField())),
                        default=0,
                        output_field=FloatField()
                    ),
                    avg_spend_per_token=Case(
                        When(total_tokens__gt=0,
                             then=Cast(F('total_spend'), FloatField()) / Cast(F('total_tokens'), FloatField())),
                        default=0,
                        output_field=FloatField()
                    ),
                    prompt_completion_ratio=Case(
                        When(completion_tokens__gt=0,
                             then=Cast(F('prompt_tokens'), FloatField()) / Cast(F('completion_tokens'), FloatField())),
                        default=0,
                        output_field=FloatField()
                    ),
                )\
                .order_by('-total_spend')[:10]

            # Calculate time-based metrics
            time_metrics = base_qs\
                .annotate(
                    hour=Extract('startTime', 'hour'),
                    day_of_week=Extract('startTime', 'dow')
                )\
                .values('hour', 'day_of_week')\
                .annotate(
                    request_count=Count('request_id'),
                    avg_latency=Avg(
                        Extract(F('endTime') - F('startTime'), 'epoch')
                    )
                )\
                .order_by('day_of_week', 'hour')

            # Package metrics
            top_metrics = {
                'models': [
                    {
                        'model': m['model'][0] if isinstance(m['model'], list) else m['model'],  # Handle ArrayField
                        'total_spend': float(m['total_spend'] or 0),
                        'total_tokens': int(m['total_tokens'] or 0),
                        'request_count': int(m['request_count'] or 0),
                        'avg_tokens_per_request': float(m['avg_tokens_per_request'] or 0),
                        'avg_spend_per_token': float(m['avg_spend_per_token'] or 0),
                        'prompt_completion_ratio': float(m['prompt_completion_ratio'] or 0),
                        'avg_latency': float(m['avg_latency'] or 0),
                        # Add formatted versions for display
                        'total_spend_fmt': "${:,.2f}".format(float(m['total_spend'] or 0)),
                        'total_tokens_fmt': "{:,}".format(int(m['total_tokens'] or 0)),
                        'request_count_fmt': "{:,}".format(int(m['request_count'] or 0)),
                        'avg_tokens_per_request_fmt': "{:,.1f}".format(float(m['avg_tokens_per_request'] or 0)),
                        'avg_spend_per_token_fmt': "${:,.6f}".format(float(m['avg_spend_per_token'] or 0)),
                        'prompt_completion_ratio_fmt': "{:,.2f}".format(float(m['prompt_completion_ratio'] or 0)),
                        'avg_latency_fmt': "{:,.2f}".format(float(m['avg_latency'] or 0))
                    } for m in model_metrics
                ],
                'keys': list(Last30dKeysBySpend.objects.using('litellm_logs')
                    .values('api_key', 'key_alias', 'key_name', 'total_spend')[:10]),
                'users': list(Last30dTopEndUsersSpend.objects.using('litellm_logs')
                    .values('end_user', 'total_events', 'total_spend')[:10]),
                'time_metrics': list(time_metrics)
            }
            cache.set(top_key, top_metrics, 60 * 5)

        # Prepare metrics with both raw and formatted values
        global_metrics = {
            'total_spend': float(stats['total_spend'] or 0),
            'total_tokens': int(stats['total_tokens'] or 0),
            'total_requests': int(stats['total_requests'] or 0),
            'avg_tokens_per_request': float(stats['avg_tokens_per_request'] or 0),
            'avg_spend_per_request': float(stats['avg_spend_per_request'] or 0),
            'avg_spend_per_token': float(stats['total_spend'] / stats['total_tokens'] if stats['total_tokens'] else 0),
            # Add formatted versions
            'total_spend_fmt': "${:,.2f}".format(float(stats['total_spend'] or 0)),
            'total_tokens_fmt': "{:,}".format(int(stats['total_tokens'] or 0)),
            'total_requests_fmt': "{:,}".format(int(stats['total_requests'] or 0)),
            'avg_tokens_per_request_fmt': "{:,.1f}".format(float(stats['avg_tokens_per_request'] or 0)),
            'avg_spend_per_request_fmt': "${:,.4f}".format(float(stats['avg_spend_per_request'] or 0)),
            'avg_spend_per_token_fmt': "${:,.6f}".format(float(stats['total_spend'] / stats['total_tokens']*1000000 if stats['total_tokens'] else 0)),
            'prompt_tokens_percent': round(
                (base_qs.aggregate(Sum('prompt_tokens'))['prompt_tokens__sum'] or 0) * 100.0 /
                stats['total_tokens'], 1) if stats['total_tokens'] else 0,
        }

        context = {
            **global_metrics,
            'daily_metrics': [
                {
                    'day': d['day'],
                    'total_spend': float(d['total_spend'] or 0),
                    'total_tokens': int(d['total_tokens'] or 0),
                    'request_count': int(d['request_count'] or 0),
                    'avg_latency': float(d['avg_latency'] or 0),
                    # Add formatted versions
                    'total_spend_fmt': "${:,.2f}".format(float(d['total_spend'] or 0)),
                    'total_tokens_fmt': "{:,}".format(int(d['total_tokens'] or 0)),
                    'request_count_fmt': "{:,}".format(int(d['request_count'] or 0)),
                    'avg_latency_fmt': "{:,.2f}".format(float(d['avg_latency'] or 0))
                } for d in daily_metrics
            ],
            'model_metrics': top_metrics['models'],
            'top_keys': top_metrics['keys'],
            'top_users': top_metrics['users'],
        }
        
        # Get last 100 spend logs
        try:
            recent_logs = LiteLLMSpendLog.objects.using('litellm_logs')\
                .order_by('-endTime')[:100]\
                .values('call_type', 'spend', 'total_tokens', 'prompt_tokens', 
                       'completion_tokens', 'endTime', 'model')
            context['recent_logs'] = [{
                'call_type': log['call_type'],
                'spend': float(log['spend'] or 0),
                'total_tokens': int(log['total_tokens'] or 0),
                'prompt_tokens': int(log['prompt_tokens'] or 0),
                'completion_tokens': int(log['completion_tokens'] or 0),
                'endTime': log['endTime'],
                'model': log['model'][0] if isinstance(log['model'], list) else log['model']
            } for log in recent_logs]
        except Exception as e:
            logger.error(f"Error fetching recent logs: {str(e)}", exc_info=True)
            context['recent_logs'] = []
    
    except Exception as e:
        logger.error(f"Error in llm_dashboard view: {str(e)}", exc_info=True)
        context = {'error': str(e)}
    
    return render(request, 'home/llm-dashboard.html', context)
