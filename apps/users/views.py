from django.shortcuts import render, redirect, get_object_or_404
from apps.users.models import Profile
from apps.users.forms import ProfileForm, QuillFieldForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.contrib import messages
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
import logging

logger = logging.getLogger(__name__)

# Create your views here.


@login_required
def profile(request):
    profile = get_object_or_404(Profile, user=request.user)
    form = QuillFieldForm(instance=profile)
    if request.method == 'POST':

        if request.POST.get('email'):
            request.user.email = request.POST.get('email')
            request.user.save()

        for attribute, value in request.POST.items():
            if attribute == 'csrfmiddlewaretoken':
                continue

            setattr(profile, attribute, value)
            profile.save()

        messages.success(request, 'Profile updated successfully')
        return redirect(request.META.get('HTTP_REFERER'))

    context = {
        'page_title': 'Profile',
        'segment': 'profile',
        'parent': 'apps',
        'form': form
    }
    return render(request, 'pages/apps/user-profile.html', context)


@login_required
def upload_avatar(request):
    profile = get_object_or_404(Profile, user=request.user)
    if request.method == 'POST':
        profile.avatar = request.FILES.get('avatar')
        profile.save()
        messages.success(request, 'Avatar uploaded successfully')
    return redirect(request.META.get('HTTP_REFERER'))


@login_required
def change_password(request):
    user = request.user
    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_new_password = request.POST.get('confirm_new_password')

        if new_password == confirm_new_password:
            if check_password(request.POST.get('current_password'), user.password):
                user.set_password(new_password)
                user.save()
                messages.success(request, 'Password changed successfully')
            else:
                messages.error(request, "Old password doesn't match!")
        else:
            messages.error(request, "Password doesn't match!")

    return redirect(request.META.get('HTTP_REFERER'))


@login_required
def change_mode(request):
    profile = get_object_or_404(Profile, user=request.user)
    if profile.dark_mode:
        profile.dark_mode = False
    else:
        profile.dark_mode = True
    
    profile.save()

    return redirect(request.META.get('HTTP_REFERER'))


@login_required
def regenerate_token(request):
    """View to regenerate a user's API token"""
    if request.method != 'POST':
        return JsonResponse({
            'error': 'Only POST method is allowed',
            'success': False
        }, status=405)
    
    try:
        profile = request.user.profile
        token = profile.regenerate_token()
        
        return JsonResponse({
            'token': token.key,
            'message': 'API token regenerated successfully',
            'success': True
        })
    except Exception as e:
        logger.error(f"Error regenerating token for user {request.user.id}: {str(e)}")
        return JsonResponse({
            'error': 'Failed to regenerate token',
            'message': str(e),
            'success': False
        }, status=500)
