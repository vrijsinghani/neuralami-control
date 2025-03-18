"""
Custom MinIO storage backend that addresses 403 errors with head_object operations.

This module provides a storage class that fixes issues with MinIO rejecting
head_object operations for certain file types while still allowing get_object
and list_objects operations.
"""

import logging
from storages.backends.s3boto3 import S3Boto3Storage
from botocore.exceptions import ClientError
from django.core.files.base import ContentFile

logger = logging.getLogger('core.storage')

class MinIOStorage(S3Boto3Storage):
    """
    MinIO-specific S3Boto3Storage backend that properly handles 403 errors
    with head_object operations on certain file types.
    """
    
    def exists(self, name):
        """
        Override the exists method to handle 403 Forbidden errors when checking
        file existence by trying alternative approaches (list_objects).
        
        Args:
            name: The file path to check
            
        Returns:
            Boolean indicating if file exists
        """
        try:
            # Try standard approach first (uses head_object)
            return super().exists(name)
        except ClientError as e:
            # Check if this is a 403 error
            if getattr(e, 'response', {}).get('Error', {}).get('Code') == '403':
                logger.warning(f"Got 403 when checking if file exists, trying list_objects: {name}")
                
                try:
                    # Use list_objects_v2 to check if file exists
                    # This works because our test showed list_objects succeeds even for image files
                    paginator = self.connection.meta.client.get_paginator('list_objects_v2')
                    
                    # Handle directory structure in the path
                    prefix = name
                    for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                        for obj in page.get('Contents', []):
                            if obj['Key'] == name:
                                logger.info(f"File exists (confirmed via list_objects): {name}")
                                return True
                    
                    return False
                except Exception as alt_error:
                    logger.error(f"Alternative file existence check failed: {str(alt_error)}")
                    return False
            
            # For any other error, log it and assume file doesn't exist
            logger.error(f"Error checking if file exists: {name}, error: {str(e)}")
            return False
            
    def _open(self, name, mode='rb'):
        """
        Override the _open method to handle 403 Forbidden errors by using get_object
        directly instead of S3File which uses head_object that can fail with 403.
        
        Args:
            name: The file path to open
            mode: File open mode (ignored for S3)
            
        Returns:
            A Django file-like object
        """
        try:
            # Try standard approach first
            return super()._open(name, mode)
        except ClientError as e:
            # Check if this is a 403 error
            if getattr(e, 'response', {}).get('Error', {}).get('Code') == '403':
                logger.warning(f"Got 403 when opening file, trying direct get_object: {name}")
                
                try:
                    # Use get_object directly instead of the boto3 resource
                    response = self.connection.meta.client.get_object(
                        Bucket=self.bucket_name, 
                        Key=name
                    )
                    
                    content = response['Body'].read()
                    file_obj = ContentFile(content)
                    file_obj.name = name
                    
                    logger.info(f"Successfully opened file using direct get_object: {name}")
                    return file_obj
                except Exception as alt_error:
                    logger.error(f"Alternative open method failed: {str(alt_error)}")
                    raise
            
            # Re-raise the original error
            raise
