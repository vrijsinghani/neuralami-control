from django.urls import path
from home import views
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView


urlpatterns = [
  # Dashboard - Make login page the default landing page
  path('', views.IllustrationLoginView.as_view(template_name='authentication/signin/illustration.html'), name='index'),
  path('accounts/register/illustration-register/', views.illustration_register, name="illustration_register"),
  # Authentication -> Login
  path('accounts/login/illustration-login/', views.IllustrationLoginView.as_view(), name="illustration_login"),
  # Authentication -> Reset
  path('accounts/reset/illustration-reset/', views.IllustrationResetView.as_view(), name="illustration_reset"),

  path('accounts/password-change/', views.UserPasswordChangeView.as_view(), name='password_change'),
  path('accounts/password-change-done/', auth_views.PasswordChangeDoneView.as_view(
      template_name='authentication/done/change-done.html'
  ), name="password_change_done"),
  path('accounts/password-reset-done/', auth_views.PasswordResetDoneView.as_view(
      template_name='authentication/done/basic.html'
  ), name='password_reset_done'),
  path('accounts/password-reset-confirm/<uidb64>/<token>/', 
      views.UserPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
  path('accounts/password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(
      template_name='authentication/complete/basic.html'
  ), name='password_reset_complete'),

  # Authentication -> Lock
  path('accounts/lock/illustration-lock/', views.illustration_lock, name='illustration_lock'),
  # Authentication -> Verification
  path('accounts/verification/illustration-verification/', views.illustration_verification, name="illustration_verification"),
  # Error
  path('error/404/', views.error_404, name="error_404"),
  path('error/500/', views.error_500, name="error_500"),
  path('logout/', views.logout_view, name="logout"),
  path('llm-dashboard/', views.llm_dashboard, name='llm-dashboard'),

]
