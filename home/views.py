from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView, PasswordResetView, PasswordChangeView, PasswordResetConfirmView
from home.forms import RegistrationForm, LoginForm, UserPasswordResetForm, UserSetPasswordForm, UserPasswordChangeForm
from django.contrib.auth import logout
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from datetime import datetime, timedelta
from django.db.models import Sum, Count
from django.db.models.functions import TruncDay
from .models import LiteLLMSpendLog, Last30dModelsBySpend, Last30dTopEndUsersSpend, Last30dKeysBySpend
from json import dumps
from django.utils.safestring import mark_safe

# Dashboard
def default(request):
  context = {
    'parent': 'dashboard',
    'segment': 'default'
  }
  return render(request, 'pages/dashboards/default.html', context)

def automotive(request):
  context = {
    'parent': 'dashboard',
    'segment': 'automotive'
  }
  return render(request, 'pages/dashboards/automotive.html', context)

def smart_home(request):
  context = {
    'parent': 'dashboard',
    'segment': 'smart_home'
  }
  return render(request, 'pages/dashboards/smart-home.html', context)

def crm(request):
  context = {
    'parent': 'dashboard',
    'segment': 'crm'
  }
  return render(request, 'pages/dashboards/crm.html', context)

# Dashboard -> VR
def vr_default(request):
  context = {
    'parent': 'dashboard',
    'sub_parent': 'vr',
    'segment': 'vr_default'
  }
  return render(request, 'pages/dashboards/vr/vr-default.html', context)

def vr_info(request):
  context = {
    'parent': 'dashboard',
    'sub_parent': 'vr',
    'segment': 'vr_info'
  }
  return render(request, 'pages/dashboards/vr/vr-info.html', context)

# Pages
def messages(request):
  context = {
    'parent': 'pages',
    'segment': 'messages'
  }
  return render(request, 'pages/pages/messages.html', context)

def widgets(request):
  context = {
    'parent': 'pages',
    'segment': 'widgets'
  }
  return render(request, 'pages/pages/widgets.html', context)

def charts_page(request):
  context = {
    'parent': 'pages',
    'segment': 'charts'
  }
  return render(request, 'pages/pages/charts.html', context)

def sweet_alerts(request):
  context = {
    'parent': 'pages',
    'segment': 'sweet_alerts'
  }
  return render(request, 'pages/pages/sweet-alerts.html', context)

def notifications(request):
  context = {
    'parent': 'pages',
    'segment': 'notifications'
  }
  return render(request, 'pages/pages/notifications.html', context)

def pricing_page(request):
  return render(request, 'pages/pages/pricing-page.html')

def rtl(request):
  return render(request, 'pages/pages/rtl-page.html')

# Pages -> Profile
def profile_overview(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'profile',
    'segment': 'profile_overview'
  }
  return render(request, 'pages/profile/overview.html', context)

def teams(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'profile',
    'segment': 'teams'
  }
  return render(request, 'pages/profile/teams.html', context)

def projects(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'profile',
    'segment': 'projects'
  }
  return render(request, 'pages/profile/projects.html', context)

# Pages -> Users
def reports(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'users',
    'segment': 'reports'
  }
  return render(request, 'pages/users/reports.html', context)

def new_user(request):
  context = {
    'parent': 'pages',
    'sub_parent': 'users',
    'segment': 'new_user'
  }
  return render(request, 'pages/users/new-user.html', context)

# Pages -> Accounts
def settings(request):
  context = {
    'parent': 'accounts',
    'segment': 'settings'
  }
  return render(request, 'pages/account/settings.html', context)

def billing(request):
  context = {
    'parent': 'accounts',
    'segment': 'billing'
  }
  return render(request, 'pages/account/billing.html', context)

def invoice(request):
  context = {
    'parent': 'accounts',
    'segment': 'invoice'
  }
  return render(request, 'pages/account/invoice.html', context)

def security(request):
  context = {
    'parent': 'accounts',
    'segment': 'security'
  }
  return render(request, 'pages/account/security.html', context)

# Pages -> Projects
def general(request):
  context = {
    'parent': 'projects',
    'segment': 'general'
  }
  return render(request, 'pages/projects/general.html', context)

def timeline(request):
  context = {
    'parent': 'projects',
    'segment': 'timeline'
  }
  return render(request, 'pages/projects/timeline.html', context)

def new_project(request):
  context = {
    'parent': 'projects',
    'segment': 'new_project'
  }
  return render(request, 'pages/projects/new-project.html', context)

# Applications
def kanban(request):
  context = {
    'parent': 'applications',
    'segment': 'kanban'
  }
  return render(request, 'pages/applications/kanban.html', context)

def wizard(request):
  context = {
    'parent': 'applications',
    'segment': 'wizard'
  }
  return render(request, 'pages/applications/wizard.html', context)

def datatables(request):
  context = {
    'parent': 'applications',
    'segment': 'datatables'
  }
  return render(request, 'pages/applications/datatables.html', context)

def calendar(request):
  context = {
    'parent': 'applications',
    'segment': 'calendar'
  }
  return render(request, 'pages/applications/calendar.html', context)

def analytics(request):
  context = {
    'parent': 'applications',
    'segment': 'analytics'
  }
  return render(request, 'pages/applications/analytics.html', context)

# Ecommerce
def overview(request):
  context = {
    'parent': 'ecommerce',
    'segment': 'overview'
  }
  return render(request, 'pages/ecommerce/overview.html', context)

def referral(request):
  context = {
    'parent': 'ecommerce',
    'segment': 'referral'
  }
  return render(request, 'pages/ecommerce/referral.html', context)

# Ecommerce -> Products
def new_product(request):
  context = {
    'parent': 'ecommerce',
    'sub_parent': 'products',
    'segment': 'new_product'
  }
  return render(request, 'pages/ecommerce/products/new-product.html', context)

def edit_product(request):
  context = {
    'parent': 'ecommerce',
    'sub_parent': 'products',
    'segment': 'edit_product'
  }
  return render(request, 'pages/ecommerce/products/edit-product.html', context)

def product_page(request):
  context = {
    'parent': 'ecommerce',
    'sub_parent': 'products',
    'segment': 'product_page'
  }
  return render(request, 'pages/ecommerce/products/product-page.html', context)

def products_list(request):
  context = {
    'parent': 'ecommerce',
    'sub_parent': 'products',
    'segment': 'products_list'
  }
  return render(request, 'pages/ecommerce/products/products-list.html', context)

# Ecommerce -> Orders
def order_list(request):
  context = {
    'parent': 'ecommerce',
    'sub_parent': 'orders',
    'segment': 'order_list'
  }
  return render(request, 'pages/ecommerce/orders/list.html', context)

def order_details(request):
  context = {
    'parent': 'ecommerce',
    'sub_parent': 'orders',
    'segment': 'order_details'
  }
  return render(request, 'pages/ecommerce/orders/details.html', context)

# Team
def team_messages(request):
  context = {
    'parent': 'team',
    'segment': 'team_messages'
  }
  return render(request, 'pages/team/messages.html', context)

def team_new_user(request):
  context = {
    'parent': 'team',
    'segment': 'team_new_user'
  }
  return render(request, 'pages/team/new-user.html', context)

def team_overview(request):
  context = {
    'parent': 'team',
    'segment': 'team_overview'
  }
  return render(request, 'pages/team/overview.html', context)

def team_projects(request):
  context = {
    'parent': 'team',
    'segment': 'team_projects'
  }
  return render(request, 'pages/team/projects.html', context)

def team_reports(request):
  context = {
    'parent': 'team',
    'segment': 'team_reports'
  }
  return render(request, 'pages/team/reports.html', context)

def team_teams(request):
  context = {
    'parent': 'team',
    'segment': 'team_teams'
  }
  return render(request, 'pages/team/teams.html', context)

# Authentication -> Register
def basic_register(request):
  if request.method == 'POST':
    form = RegistrationForm(request.POST)
    if form.is_valid():
      form.save()
      return redirect('/accounts/login/basic-login/')
  else:
    form = RegistrationForm()
  
  context = {'form': form}
  return render(request, 'authentication/signup/basic.html', context)

def cover_register(request):
  if request.method == 'POST':
    form = RegistrationForm(request.POST)
    if form.is_valid():
      form.save()
      return redirect('/accounts/login/cover-login/')
  else:
    form = RegistrationForm()

  context = {'form': form}
  return render(request, 'authentication/signup/cover.html', context)

def illustration_register(request):
  if request.method == 'POST':
    form = RegistrationForm(request.POST)
    if form.is_valid():
      form.save()
      return redirect('/accounts/login/illustration-login/')
  else:
    form = RegistrationForm()

  context = {'form': form}
  return render(request, 'authentication/signup/illustration.html', context)

# Authentication -> Login
class BasicLoginView(LoginView):
  template_name = 'authentication/signin/basic.html'
  form_class = LoginForm

class CoverLoginView(LoginView):
  template_name = 'authentication/signin/cover.html'
  form_class = LoginForm

class IllustrationLoginView(LoginView):
  template_name = 'authentication/signin/illustration.html'
  form_class = LoginForm

# Authentication -> Reset
class BasicResetView(PasswordResetView):
  template_name = 'authentication/reset/basic.html'
  form_class = UserPasswordResetForm

class CoverResetView(PasswordResetView):
  template_name = 'authentication/reset/cover.html'
  form_class = UserPasswordResetForm

class IllustrationResetView(PasswordResetView):
  template_name = 'authentication/reset/illustration.html'
  form_class = UserPasswordResetForm


class UserPasswordResetConfirmView(PasswordResetConfirmView):
  template_name = 'authentication/reset-confirm/basic.html'
  form_class = UserSetPasswordForm

class UserPasswordChangeView(PasswordChangeView):
  template_name = 'authentication/change/basic.html'
  form_class = UserPasswordChangeForm

# Authentication -> Lock
def basic_lock(request):
  return render(request, 'authentication/lock/basic.html')

def cover_lock(request):
  return render(request, 'authentication/lock/cover.html')

def illustration_lock(request):
  return render(request, 'authentication/lock/illustration.html')

# Authentication -> Verification
def basic_verification(request):
  return render(request, 'authentication/verification/basic.html')

def cover_verification(request):
  return render(request, 'authentication/verification/cover.html')

def illustration_verification(request):
  return render(request, 'authentication/verification/illustration.html')

# Error
def error_404(request,exception=None ):
  return render(request, 'authentication/error/404.html')

def error_500(request, exception=None):
  return render(request, 'authentication/error/500.html')

def logout_view(request):
  logout(request)
  return redirect('/accounts/login/basic-login/')


@staff_member_required
def llm_dashboard(request):
    try:
        # Get date range with timezone
        from django.utils import timezone
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        # Basic stats
        total_spend = LiteLLMSpendLog.objects.using('litellm_logs')\
            .filter(startTime__gte=start_date)\
            .aggregate(total=Sum('spend'))['total'] or 0
        
        total_tokens = LiteLLMSpendLog.objects.using('litellm_logs')\
            .filter(startTime__gte=start_date)\
            .aggregate(total=Sum('total_tokens'))['total'] or 0
        
        total_requests = LiteLLMSpendLog.objects.using('litellm_logs')\
            .filter(startTime__gte=start_date)\
            .count()

        # Daily spend query
        daily_spend = LiteLLMSpendLog.objects.using('litellm_logs')\
            .filter(startTime__gte=start_date)\
            .annotate(day=TruncDay('startTime'))\
            .values('day')\
            .annotate(total_spend=Sum('spend'))\
            .order_by('day')

        # Prepare chart data
        dates = []
        spends = []
        for d in daily_spend:
            dates.append(d['day'].strftime('%Y-%m-%d'))
            spends.append(float(d['total_spend']))

        context = {
          'total_spend': round(total_spend, 2),
          'total_tokens': total_tokens,
          'total_requests': total_requests,
          'daily_spend': [{'day': datetime.strptime(date, '%Y-%m-%d'), 
                  'total_spend': spend} 
                for date, spend in zip(dates, spends)],
          'top_models': Last30dModelsBySpend.objects.using('litellm_logs').all()[:10],
          'top_keys': Last30dKeysBySpend.objects.using('litellm_logs').all()[:10],
        }
        
        # Debug print
        print("Chart data:")
        print("Labels:", dates)
        print("Values:", spends)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        context = {'error': str(e)}
    
    return render(request, 'home/llm-dashboard.html', context)