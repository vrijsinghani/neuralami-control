from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, UpdateView, CreateView, DeleteView
from .models.base import Organization, OrganizationMembership, Role, Permission
from .forms import OrganizationForm
from .utils import set_current_organization, get_current_organization
import logging

logger = logging.getLogger(__name__)

@login_required
def organization_settings(request, org_id=None):
    """
    View for organization settings page.
    If org_id is not provided, uses the user's current organization.
    """
    # Get the organization, either by ID or current context
    if org_id:
        organization = get_object_or_404(Organization, pk=org_id)
        # Check if user is a member of this organization
        if not request.user.organization_memberships.filter(organization=organization, status='active').exists():
            messages.error(request, "You don't have access to this organization.")
            return redirect('dashboard')
    else:
        organization = get_current_organization()
        if not organization:
            messages.error(request, "You need to be part of an organization to access settings.")
            return redirect('dashboard')
    
    # Get user's membership to check permissions
    try:
        user_membership = OrganizationMembership.objects.get(user=request.user, organization=organization, status='active')
        is_owner = organization.owner == request.user
        is_admin = user_membership.role.permissions.filter(codename='manage_organization').exists()
    except OrganizationMembership.DoesNotExist:
        is_owner = False
        is_admin = False
    
    members = OrganizationMembership.objects.filter(organization=organization).select_related('user', 'role')
    
    return render(request, 'organizations/settings.html', {
        'organization': organization,
        'members': members,
        'is_owner': is_owner,
        'is_admin': is_admin,
        'active_membership': user_membership,
    })

@login_required
@require_POST
def toggle_organization_status(request, org_id):
    """
    Toggle the active status of an organization.
    Only organization owners and admins can change organization status.
    """
    organization = get_object_or_404(Organization, pk=org_id)
    
    # Check if user has permission to modify organization status
    try:
        membership = OrganizationMembership.objects.get(
            user=request.user, 
            organization=organization, 
            status='active'
        )
        is_owner = organization.owner == request.user
        is_admin = membership.role.permissions.filter(codename='manage_organization').exists()
        
        if not (is_owner or is_admin):
            messages.error(request, "You don't have permission to change organization status.")
            return redirect('organizations:settings_specific', org_id=org_id)
            
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You are not a member of this organization.")
        return redirect('dashboard')
    
    # Toggle the status
    organization.is_active = not organization.is_active
    organization.save()
    
    # Log the action
    action = "activated" if organization.is_active else "deactivated"
    logger.info(
        f"Organization {organization.name} {action} by {request.user.username}"
    )
    
    # Show appropriate message
    status_message = "activated" if organization.is_active else "deactivated"
    messages.success(request, f"Organization has been {status_message} successfully.")
    
    return redirect('organizations:settings_specific', org_id=org_id)

@login_required
@require_POST
def switch_organization(request):
    """
    View to switch the user's active organization.
    """
    org_id = request.POST.get('organization_id')
    redirect_url = request.POST.get('redirect_url', 'dashboard')
    
    if not org_id:
        messages.error(request, "No organization specified.")
        return HttpResponseRedirect(redirect_url)
    
    # Check if the user is a member of this organization
    try:
        membership = request.user.organization_memberships.get(
            organization_id=org_id,
            status='active'
        )
        
        # Set this as the user's active organization in session
        request.session['active_organization_id'] = str(membership.organization.id)
        request.session['active_organization_name'] = membership.organization.name
        
        # Update thread-local storage for current request
        set_current_organization(membership.organization)
        
        messages.success(request, f"Now viewing {membership.organization.name}")
        logger.info(f"User {request.user.username} switched to organization {membership.organization.name}")
        
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You are not a member of this organization.")
        logger.warning(f"User {request.user.username} attempted to switch to unauthorized organization {org_id}")
    
    return HttpResponseRedirect(redirect_url)

@login_required
def organization_switcher(request):
    """
    View to render the organization switcher component.
    """
    user_memberships = request.user.organization_memberships.filter(
        status='active'
    ).select_related('organization', 'role')
    
    current_org = get_current_organization()
    
    return render(request, 'organizations/components/organization_switcher.html', {
        'memberships': user_memberships,
        'current_organization': current_org,
    })

@login_required
def organization_members(request):
    """
    View for organization members management page.
    Lists members and allows admins to manage them.
    """
    # Get the user's active organization memberships
    user_memberships = request.user.organization_memberships.filter(status='active')
    
    if not user_memberships.exists():
        messages.warning(request, "You don't belong to any organization. Please contact an administrator.")
        return redirect('home')
    
    # For now, use the first active organization
    active_membership = user_memberships.first()
    organization = active_membership.organization
    
    # Check if user is owner or admin
    is_owner = organization.owner == request.user
    is_admin = active_membership.role.permissions.filter(codename='manage_members').exists()
    
    if not is_owner and not is_admin:
        messages.error(request, "You don't have permission to manage organization members.")
        return redirect('organizations:settings')
    
    # Get organization members
    members = OrganizationMembership.objects.filter(
        organization=organization
    ).select_related('user', 'role').order_by('user__username')
    
    # Paginate members
    paginator = Paginator(members, 10)
    page_number = request.GET.get('page', 1)
    members_page = paginator.get_page(page_number)
    
    # Get available roles for dropdown
    available_roles = Role.objects.filter(
        organization=organization
    ) | Role.objects.filter(is_system_role=True)
    
    context = {
        'organization': organization,
        'members': members_page,
        'is_owner': is_owner,
        'is_admin': is_admin,
        'active_membership': active_membership,
        'available_roles': available_roles,
    }
    
    return render(request, 'organizations/members.html', context)

@login_required
def edit_organization(request, org_id):
    """
    View for editing organization details.
    Only organization owners and admins can edit organization details.
    """
    organization = get_object_or_404(Organization, pk=org_id)
    
    # Check if user has permission to edit organization
    try:
        membership = OrganizationMembership.objects.get(
            user=request.user, 
            organization=organization, 
            status='active'
        )
        is_owner = organization.owner == request.user
        is_admin = membership.role.permissions.filter(codename='manage_organization').exists()
        
        if not (is_owner or is_admin):
            messages.error(request, "You don't have permission to edit this organization.")
            return redirect('organizations:settings_specific', org_id=org_id)
            
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You are not a member of this organization.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = OrganizationForm(request.POST, request.FILES, instance=organization)
        if form.is_valid():
            form.save()
            
            # Log the action
            logger.info(f"Organization {organization.name} updated by {request.user.username}")
            
            messages.success(request, "Organization details updated successfully.")
            return redirect('organizations:settings_specific', org_id=org_id)
    else:
        form = OrganizationForm(instance=organization)
    
    return render(request, 'organizations/edit_organization.html', {
        'form': form,
        'organization': organization,
        'is_owner': is_owner,
        'is_admin': is_admin,
    })
