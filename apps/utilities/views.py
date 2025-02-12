from django.shortcuts import render
import json
import requests
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import APIEndpoint

# Create your views here.

@login_required
def test_endpoint(request):
    """View for testing API endpoints"""
    if request.method == 'POST':
        try:
            endpoint = request.POST.get('endpoint')
            method = request.POST.get('method', 'GET')
            auth_token = request.POST.get('auth_token')
            request_body = request.POST.get('request_body')
            
            headers = {}
            if auth_token:
                headers['Authorization'] = f'Bearer {auth_token}'
            
            # Add JSON content type header if body is present
            if request_body:
                headers['Content-Type'] = 'application/json'
                try:
                    # Validate JSON body
                    json_body = json.loads(request_body)
                except json.JSONDecodeError:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid JSON in request body'
                    })
            else:
                json_body = None
            
            # Make the request
            response = requests.request(
                method=method,
                url=endpoint,
                headers=headers,
                json=json_body if json_body else None,
                timeout=30
            )
            
            # Try to parse response as JSON
            try:
                response_data = response.json()
                is_json = True
            except:
                response_data = response.text
                is_json = False
            
            return JsonResponse({
                'success': True,
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'is_json': is_json,
                'response': response_data
            })
            
        except requests.RequestException as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    # Get saved endpoints for the current user
    saved_endpoints = APIEndpoint.objects.filter(created_by=request.user).order_by('name')
    return render(request, 'utilities/test_endpoint.html', {'saved_endpoints': saved_endpoints})
