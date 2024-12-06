from .exceptions import AuthError
from django.shortcuts import redirect
from django.contrib import messages

class GoogleAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, AuthError):
            messages.error(request, str(exception))
            return redirect('seo_manager:client_list')
        return None 