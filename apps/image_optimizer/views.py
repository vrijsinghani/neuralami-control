from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.conf import settings

from .models import OptimizedImage, OptimizationJob
from apps.api.views import ImageOptimizeView

import os
import json
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """Dashboard view showing optimization statistics and recent optimizations"""
    recent_optimizations = OptimizedImage.objects.filter(user=request.user).order_by('-created_at')[:10]
    
    # Calculate overall statistics
    total_optimizations = OptimizedImage.objects.filter(user=request.user).count()
    total_saved = OptimizedImage.objects.filter(
        user=request.user, 
        status='completed'
    ).values_list('original_size', 'optimized_size')
    
    total_original = sum(orig for orig, _ in total_saved)
    total_optimized = sum(opt for _, opt in total_saved)
    avg_reduction = ((total_original - total_optimized) / total_original * 100) if total_original > 0 else 0
    
    context = {
        'recent_optimizations': recent_optimizations,
        'total_optimizations': total_optimizations,
        'avg_reduction': round(avg_reduction, 2),
        'total_saved_mb': round((total_original - total_optimized) / (1024 * 1024), 2)
    }
    
    return render(request, 'image_optimizer/dashboard.html', context)

@login_required
def optimize(request):
    """Main optimization interface"""
    return render(request, 'image_optimizer/optimize.html')

@login_required
@require_http_methods(["POST"])
def handle_upload(request):
    """Handle image upload and optimization"""
    try:
        logger.info(f"Received upload request from user: {request.user.username}")
        logger.info(f"Files in request: {request.FILES}")
        logger.info(f"POST data: {request.POST}")
        
        if 'file' not in request.FILES:
            logger.error("No file found in request")
            return JsonResponse({'success': False, 'message': 'No file was uploaded'}, status=400)

        uploaded_file = request.FILES['file']
        logger.info(f"Processing file: {uploaded_file.name} ({uploaded_file.size} bytes)")
        
        quality = int(request.POST.get('quality', 80))
        max_width = request.POST.get('max_width')
        max_height = request.POST.get('max_height')
        job_id = request.POST.get('job_id')
        
        logger.info(f"Parameters: quality={quality}, max_width={max_width}, max_height={max_height}, job_id={job_id}")

        # Convert empty strings to None
        max_width = int(max_width) if max_width else None
        max_height = int(max_height) if max_height else None

        # Get or create optimization job
        if job_id:
            logger.info(f"Using existing job: {job_id}")
            job = OptimizationJob.objects.get(id=job_id)
        else:
            logger.info("Creating new optimization job")
            job = OptimizationJob.objects.create(
                user=request.user,
                settings_used={
                    'quality': quality,
                    'max_width': max_width if max_width is not None else '',
                    'max_height': max_height if max_height is not None else ''
                },
                status='processing'
            )
            logger.info(f"Created new job: {job.id}")

        # Save original file
        user_path = str(request.user.id)
        original_path = default_storage.save(
            os.path.join(user_path, 'original_images', uploaded_file.name),
            uploaded_file
        )
        original_size = uploaded_file.size
        logger.info(f"Saved original file: {original_path} ({original_size} bytes)")

        # Update job statistics
        job.total_files += 1
        job.total_original_size += original_size
        job.save()
        logger.info(f"Updated job statistics: total_files={job.total_files}, total_size={job.total_original_size}")

        # Create optimization record
        optimization = OptimizedImage.objects.create(
            user=request.user,
            job=job,
            original_file=original_path,
            optimized_file='',  # Will be set after processing
            original_size=original_size,
            optimized_size=original_size,  # Initial value, will be updated after processing
            compression_ratio=0.0,  # Initial value, will be updated after processing
            settings_used={
                'quality': quality,
                'max_width': max_width if max_width is not None else '',
                'max_height': max_height if max_height is not None else ''
            },
            status='processing'
        )
        logger.info(f"Created optimization record: {optimization.id}")

        # Start Celery task
        from .tasks import optimize_image
        task = optimize_image.delay(optimization.id)
        logger.info(f"Started optimization task: {task.id}")

        # Return initial response
        response_data = {
            'success': True,
            'message': 'File uploaded and queued for optimization',
            'optimization_id': optimization.id,
            'job_id': job.id,
            'task_id': task.id,
            'file_name': uploaded_file.name,
            'original_size': original_size,
            'status': 'processing'
        }
        logger.info(f"Sending response: {response_data}")
        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error processing image: {str(e)}'
        }, status=500)

@login_required
def optimization_history(request):
    """View for displaying optimization history"""
    optimizations = OptimizedImage.objects.filter(user=request.user)
    return render(request, 'image_optimizer/history.html', {'optimizations': optimizations})
