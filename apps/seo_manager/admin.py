from django.contrib import admin
from .models import ClientGroup, Client, SEOData, AIProvider

@admin.register(ClientGroup)
class ClientGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'website_url', 'status', 'group')
    list_filter = ('status', 'group')
    search_fields = ('name', 'website_url')

@admin.register(SEOData)
class SEODataAdmin(admin.ModelAdmin):
    list_display = ('client', 'date', 'traffic', 'keywords')
    list_filter = ('client', 'date')
    date_hierarchy = 'date'

@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
    list_display = ('name', 'model', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'model')
