from celery import shared_task
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile
from rest_framework.test import APIRequestFactory
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.db import models
from apps.api.views import ImageOptimizeView
from .models import OptimizedImage, OptimizationJob
import io
import os
import logging
from django.utils.datastructures import MultiValueDict

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()

@shared_task
def optimize_image(optimization_id):
    """
    Celery task to optimize a single image
    """
    optimization = None
    try:
        logger.info(f"Starting optimization task for ID: {optimization_id}")
        optimization = OptimizedImage.objects.select_related('job').get(id=optimization_id)
        job = optimization.job
        logger.info(f"Found optimization record: {optimization.original_file.name}")

        # Send initial status update
        send_optimization_update(optimization_id, {
            'status': 'processing',
            'message': 'Starting optimization...'
        })
        
        # Read the original file
        with default_storage.open(optimization.original_file.name, 'rb') as f:
            file_content = f.read()
        logger.info(f"Read original file, size: {len(file_content)} bytes")
        
        # Create a new file object
        file_obj = InMemoryUploadedFile(
            io.BytesIO(file_content),
            'image',
            os.path.basename(optimization.original_file.name),
            'image/jpeg',  # Default to JPEG, ImageOptimizeView will handle actual type
            len(file_content),
            None
        )
        
        # Process the image directly with ImageOptimizeView
        optimizer = ImageOptimizeView()
        
        # Create data dict that matches what the serializer expects
        data = {
            'image': file_obj,
            'quality': optimization.settings_used['quality'],
        }
        
        # Only add dimensions if they have actual values
        if optimization.settings_used.get('max_width'):
            data['max_width'] = int(optimization.settings_used['max_width'])
        if optimization.settings_used.get('max_height'):
            data['max_height'] = int(optimization.settings_used['max_height'])
        
        # Use the serializer directly
        serializer = optimizer.serializer_class(data=data)
        if not serializer.is_valid():
            raise Exception(f"Invalid data: {serializer.errors}")
            
        # Process with validated data
        response = optimizer.process_image(
            serializer.validated_data['image'],
            serializer.validated_data['quality'],
            serializer.validated_data.get('max_width'),
            serializer.validated_data.get('max_height')
        )
        
        if response.status_code == 200:
            # Let the model handle the file path
            optimized_filename = f"{os.path.splitext(os.path.basename(optimization.original_file.name))[0]}.webp"
            
            # Save directly through the model's FileField
            with io.BytesIO(response.content) as f:
                optimization.optimized_file.save(optimized_filename, f, save=False)
            
            # Calculate reduction
            optimized_size = len(response.content)
            reduction = ((optimization.original_size - optimized_size) / optimization.original_size) * 100
            
            # Update optimization record
            optimization.optimized_size = optimized_size
            optimization.compression_ratio = reduction
            optimization.status = 'completed'
            optimization.save()

            # Update job statistics
            if job:
                job.processed_files = OptimizedImage.objects.filter(
                    job=job, status='completed'
                ).count()
                job.total_optimized_size = OptimizedImage.objects.filter(
                    job=job, status='completed'
                ).aggregate(total=models.Sum('optimized_size'))['total'] or 0
                
                if job.processed_files == job.total_files:
                    job.status = 'completed'
                job.save()
                # Send job update with accurate completion status
                job_data = {
                    'status': job.status,
                    'job_id': job.id,
                    'processed_files': job.processed_files,
                    'total_files': job.total_files,
                    'completed_count': job.processed_files,
                    'progress_percentage': (job.processed_files / job.total_files * 100) if job.total_files > 0 else 0
                }
                send_job_update(job.id, job_data)
                logger.info(f"Sent job update: {job_data}")

            # Send completion update for individual optimization
            result = {
                'success': True,
                'status': 'completed',
                'optimization_id': optimization.id,
                'job_id': job.id if job else None,
                'file_name': os.path.basename(optimization.original_file.name),
                'original_size': optimization.original_size,
                'optimized_size': optimized_size,
                'reduction': round(reduction, 2),
                'download_url': optimization.optimized_file.url,
                'message': 'Optimization completed successfully'
            }
            
            # Send optimization update first
            send_optimization_update(optimization_id, result)
            logger.info(f"Sent completion update: {result}")
            
            # If this is the last file in the job, send final job update
            if job and job.status == 'completed':
                final_job_data = {
                    'status': 'completed',
                    'job_id': job.id,
                    'processed_files': job.total_files,
                    'total_files': job.total_files,
                    'completed_count': job.total_files,
                    'progress_percentage': 100.0,
                    'total_reduction': ((job.total_original_size - job.total_optimized_size) / job.total_original_size * 100) if job.total_original_size > 0 else 0
                }
                send_job_update(job.id, final_job_data)
                logger.info(f"Sent final job completion update: {final_job_data}")
            
            return result
        else:
            error_msg = response.data.get('message', 'Optimization failed')
            logger.error(f"Optimization failed: {error_msg}")
            raise Exception(error_msg)
            
    except Exception as e:
        logger.error(f"Error in optimize_image task: {str(e)}", exc_info=True)
        error_data = {
            'success': False,
            'status': 'failed',
            'message': str(e)
        }
        
        if optimization:
            optimization.status = 'failed'
            optimization.save()
            logger.info("Updated optimization status to failed")
            
            if job:
                job.processed_files = OptimizedImage.objects.filter(
                    job=job, status__in=['completed', 'failed']
                ).count()
                if job.processed_files == job.total_files:
                    job.status = 'failed'
                job.save()
                logger.info("Updated job status to failed")

                # Send job update
                job_update_data = {
                    'status': job.status,
                    'processed_files': job.processed_files,
                    'total_files': job.total_files,
                    'progress_percentage': job.progress_percentage
                }
                send_job_update(job.id, job_update_data)
                logger.info(f"Sent job update for failure: {job_update_data}")

        send_optimization_update(optimization_id, error_data)
        logger.info(f"Sent error update: {error_data}")
        return error_data

def send_optimization_update(optimization_id, data):
    """Send update to optimization-specific WebSocket group"""
    try:
        async_to_sync(channel_layer.group_send)(
            f"optimization_{optimization_id}",
            {
                'type': 'optimization_update',
                'data': data
            }
        )
    except Exception as e:
        logger.error(f"Error sending optimization update: {str(e)}", exc_info=True)

def send_job_update(job_id, data):
    """Send update to job-specific WebSocket group"""
    try:
        async_to_sync(channel_layer.group_send)(
            f"optimization_job_{job_id}",
            {
                'type': 'job_update',
                'data': data
            }
        )
    except Exception as e:
        logger.error(f"Error sending job update: {str(e)}", exc_info=True) 