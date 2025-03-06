from django.urls import path
from . import views

app_name = 'organizations'

urlpatterns = [
    path('settings/', views.organization_settings, name='settings'),
    path('settings/<uuid:org_id>/', views.organization_settings, name='settings_specific'),
    path('edit/<uuid:org_id>/', views.edit_organization, name='edit'),
    path('members/', views.organization_members, name='members'),
    path('switch/', views.switch_organization, name='switch_organization'),
    path('switcher/', views.organization_switcher, name='switcher'),
    path('toggle-status/<uuid:org_id>/', views.toggle_organization_status, name='toggle_status'),
] 