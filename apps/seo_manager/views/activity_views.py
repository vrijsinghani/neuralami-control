from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from ..models import UserActivity

@login_required
def activity_log(request):
    activities = UserActivity.objects.all().order_by('-timestamp')
    return render(request, 'seo_manager/activity_log.html', {'activities': activities})
