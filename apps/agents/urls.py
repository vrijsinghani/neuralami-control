from django.urls import path
from . import views
from . import views_agents
from . import views_tasks
from . import views_tools
from . import views_crews
from . import views_kanban
from . import views_chat
from .views_chat import ChatView


app_name = 'agents'

urlpatterns = [
    path('', views.crewai_home, name='crewai_home'),
    path('crews/', views.crew_list, name='crew_list'),
    path('crew/<int:crew_id>/', views.crew_detail, name='crew_detail'),
    path('crew/<int:crew_id>/kanban/', views_kanban.crew_kanban, name='crew_kanban'),
    path('crew/<int:crew_id>/start-execution/', views_kanban.start_execution, name='start_execution'),
    path('crew/<int:crew_id>/active-executions/', views_kanban.get_active_executions, name='get_active_executions'),
    path('crew/execution/<int:execution_id>/input/', views_kanban.submit_human_input, name='submit_human_input'),
    path('executions/', views.execution_list, name='execution_list'),
    path('execution/<int:execution_id>/', views_kanban.execution_detail, name='execution_detail'),
    path('execution/<int:execution_id>/status/', views_kanban.get_active_executions, name='execution_status'),
    path('execution/<int:execution_id>/submit_human_input/', views.submit_human_input, name='submit_human_input'),
    path('execution/<int:execution_id>/cancel/', views_kanban.cancel_execution, name='cancel_execution'),
    path('execution/<int:execution_id>/cancel/', views_kanban.cancel_execution, name='cancel_execution'),
    
    # Admin views
    path('manage/agents/', views_agents.manage_agents, name='manage_agents'),
    path('manage/agents/add/', views_agents.add_agent, name='add_agent'),
    path('manage/agents/edit/<int:agent_id>/', views_agents.edit_agent, name='edit_agent'),
    path('manage/agents/delete/<int:agent_id>/', views_agents.delete_agent, name='delete_agent'),
    
    path('manage/tasks/', views_tasks.manage_tasks, name='manage_tasks'),
    path('manage/tasks/add/', views_tasks.add_task, name='add_task'),
    path('manage/tasks/edit/<int:task_id>/', views_tasks.edit_task, name='edit_task'),
    path('manage/tasks/delete/<int:task_id>/', views_tasks.delete_task, name='delete_task'),
    
    path('manage/tools/', views_tools.manage_tools, name='manage_tools'),
    path('manage/tools/add/', views_tools.add_tool, name='add_tool'),
    path('manage/tools/edit/<int:tool_id>/', views_tools.edit_tool, name='edit_tool'),
    path('manage/tools/delete/<int:tool_id>/', views_tools.delete_tool, name='delete_tool'),
    path('tool-schema/<int:tool_id>/', views_tools.get_tool_schema, name='get_tool_schema'),
    path('test-tool/<int:tool_id>/', views_tools.test_tool, name='test_tool'),
    path('tool-status/<str:task_id>/', views_tools.get_tool_status, name='get_tool_status'),
    path('get_tool_info/', views_tools.get_tool_info, name='get_tool_info'),
    path('get_tool_schema/<int:tool_id>/', views_tools.get_tool_schema, name='get_tool_schema'),
    path('test_tool/<int:tool_id>/', views_tools.test_tool, name='test_tool'),  # Django 3.1+ automatically handles async views
    path('manage/crews/', views_crews.manage_crews, name='manage_crews'),
    path('manage/crews/add/', views_crews.crew_create_or_update, name='add_crew'),
    path('manage/crews/edit/<int:crew_id>/', views_crews.crew_create_or_update, name='edit_crew'),
    path('manage/crews/delete/<int:crew_id>/', views_crews.delete_crew, name='delete_crew'),
    path('manage/crews/update_agents/<int:crew_id>/', views_crews.update_crew_agents, name='update_crew_agents'),
    
    path('pipelines/', views.manage_pipelines, name='manage_pipelines'),
    path('manage/agents/card-view/', views_agents.manage_agents_card_view, name='manage_agents_card_view'),
    path('manage/crews/card-view/', views_crews.manage_crews_card_view, name='manage_crews_card_view'),
    
    path('connection-test/', views.connection_test, name='connection_test'),
    path('chat/', ChatView.as_view(), name='chat'),
    path('chat/<uuid:session_id>/', ChatView.as_view(), name='chat'),
    path('chat/<uuid:session_id>/delete/', views_chat.delete_conversation, name='delete_conversation'),
]
