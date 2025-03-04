from django.conf import settings

def version_context(request):
    return {'VERSION': settings.VERSION}
