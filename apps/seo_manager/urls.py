from django.urls import path, include
from . import views_analytics
from django.shortcuts import redirect
from .views import (
    KeywordListView, KeywordCreateView, KeywordUpdateView,
    ProjectListView, ProjectCreateView, ProjectDetailView
)
from .views import client_views, activity_views, analytics_views, business_objective_views, keyword_views, project_views, meta_tags_views, ranking_views, report_views, project_views, search_console_views

app_name = 'seo_manager'

# Redirect function for backward compatibility
def redirect_to_summarizer(request):
    return redirect('summarizer:summarize_view')

urlpatterns = [
    # Main URLs
    path('', client_views.dashboard, name='dashboard'),
    path('summarize/', redirect_to_summarizer, name='summarize_redirect'),
    
    # Client URLs
    path('clients/', include([
        path('', client_views.client_list, name='client_list'),
        path('add/', client_views.add_client, name='add_client'),
        path('<int:client_id>/', include([
            path('', client_views.client_detail, name='client_detail'),
            path('edit/', client_views.edit_client, name='edit_client'),
            path('delete/', client_views.delete_client, name='delete_client'),
            path('analytics/', views_analytics.client_analytics, name='client_analytics'),
            path('search-console/', search_console_views.client_search_console, name='client_search_console'),
            path('ads/', analytics_views.client_ads, name='client_ads'),
            path('dataforseo/', analytics_views.client_dataforseo, name='client_dataforseo'),   
            path('load-more-activities/', client_views.load_more_activities, name='load_more_activities'),
            path('export-activities/', client_views.export_activities, name='export_activities'),
            # Keyword Management URLs
            path('keywords/', include([
                path('', KeywordListView.as_view(), name='keyword_list'),
                path('add/', KeywordCreateView.as_view(), name='keyword_create'),
                path('import/', keyword_views.keyword_import, name='keyword_import'),
                path('<int:pk>/edit/', KeywordUpdateView.as_view(), name='keyword_update'),
                path('<int:pk>/rankings/', ranking_views.ranking_import, name='ranking_import'),
                path('search-console/', 
                     keyword_views.search_console_keywords, 
                     name='search_console_keywords'),
            ])),
            
            # SEO Project URLs
            path('projects/', include([
                path('', ProjectListView.as_view(), name='project_list'),
                path('add/', ProjectCreateView.as_view(), name='project_create'),
                path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
                path('<int:project_id>/edit/', project_views.edit_project, name='edit_project'),
                path('<int:project_id>/delete/', project_views.delete_project, name='delete_project'),
            ])),
            
            # Credentials URLs
            path('credentials/', include([
                # Google Analytics URLs
                path('ga/', include([
                    path('oauth/add/', 
                         analytics_views.add_ga_credentials_oauth, 
                         name='add_ga_credentials_oauth'),
                    path('service-account/add/', 
                         analytics_views.add_ga_credentials_service_account, 
                         name='add_ga_credentials_service_account'),
                    path('select-account/', 
                         analytics_views.select_analytics_account, 
                         name='select_analytics_account'),
                    path('remove/', 
                         analytics_views.remove_ga_credentials, 
                         name='remove_ga_credentials'),
                ])),
                
                # Search Console URLs
                path('sc/add/', 
                     search_console_views.add_sc_credentials, 
                     name='add_sc_credentials'),
                path('sc/remove/', 
                     search_console_views.remove_sc_credentials, 
                     name='remove_sc_credentials'),
            ])),
            
            # Business Objective URLs
            path('objectives/', include([
                path('add/', business_objective_views.add_business_objective, name='add_business_objective'),
                path('edit/<int:objective_index>/', business_objective_views.edit_business_objective, name='edit_business_objective'),
                path('delete/<int:objective_index>/', business_objective_views.delete_business_objective, name='delete_business_objective'),
                path('update-status/<int:objective_index>/', business_objective_views.update_objective_status, name='update_objective_status'),
            ])),
            
            # Profile URLs
            path('profile/', include([
                path('update/', client_views.update_client_profile, name='update_client_profile'),
                path('generate-magic/', client_views.generate_magic_profile, name='generate_magic_profile'),
                path('generation-complete/', client_views.profile_generation_complete, name='profile_generation_complete'),
            ])),
            
            # Meta Tags URLs
            path('meta-tags/', include([
                path('snapshot/', meta_tags_views.create_snapshot, name='create_meta_tags_snapshot'),
                path('task-status/<str:task_id>/', meta_tags_views.check_task_status, name='check_meta_tags_task_status'),
                path('', meta_tags_views.meta_tags, name='meta_tags_dashboard'),
            ])),
            
            # Rankings URLs
            path('rankings/', include([
                path('collect/', ranking_views.collect_rankings, name='collect_rankings'),
                path('report/', report_views.generate_report, name='generate_report'),
                path('backfill/', ranking_views.backfill_rankings, name='backfill_rankings'),
                path('manage/', ranking_views.ranking_data_management, name='ranking_data_management'),
                path('export-csv/', ranking_views.export_rankings_csv, name='export_rankings_csv'),
            ])),
            
            # Search Console URLs
            path('select-property/', 
                 analytics_views.select_search_console_property, 
                 name='select_search_console_property'),
            path('add-service-account/', 
                 analytics_views.add_sc_credentials_service_account, 
                 name='add_sc_credentials_service_account'),
            path('integrations/', client_views.client_integrations, name='client_integrations'),
            path('import-from-search-console/', 
                 keyword_views.import_from_search_console, 
                 name='import_from_search_console'),
            path('meta-tags/', meta_tags_views.meta_tags, name='meta_tags_dashboard'),
        ])),
    ])),
    
    # Other URLs
    path('activity-log/', activity_views.activity_log, name='activity_log'),
    path('create-meta-tags-snapshot-url/', meta_tags_views.create_snapshot_from_url, name='create_meta_tags_snapshot_url'),
    
    # OAuth URLs
    path('google/', include([
        path('login/callback/', 
             analytics_views.google_oauth_callback, 
             name='google_oauth_callback'),
        path('oauth/', include([
            path('init/<int:client_id>/<str:service_type>/', 
                 analytics_views.initiate_google_oauth, 
                 name='initiate_google_oauth'),
        ])),
    ])),
    path('clients/<int:client_id>/objectives/<int:objective_index>/update-status/',
         business_objective_views.update_objective_status, name='update_objective_status'),
]
