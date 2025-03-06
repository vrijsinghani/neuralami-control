from django.contrib import admin
from .models import Organization, OrganizationMembership, Role, Permission

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description', 'owner__username')
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'is_system_role', 'created_at')
    list_filter = ('is_system_role', 'organization')
    search_fields = ('name', 'description')
    filter_horizontal = ('permissions',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('codename', 'name', 'category')
    list_filter = ('category',)
    search_fields = ('codename', 'name', 'description')

@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'status', 'created_at')
    list_filter = ('status', 'organization', 'role')
    search_fields = ('user__username', 'user__email', 'organization__name')
    readonly_fields = ('created_at', 'updated_at', 'invitation_sent_at', 'invitation_accepted_at')
