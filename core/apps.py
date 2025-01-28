from django.apps import AppConfig
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils.module_loading import import_string
import logging
import time
import sys

logger = logging.getLogger('core.apps')

class StorageConfigError(RuntimeError):
    """Raised when storage configuration is invalid"""
    pass

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def _cleanup_test_files(self):
        """Clean up any leftover test files"""
        try:
            # List all files in storage
            _, files = default_storage.listdir('')
            
            # Find and delete any test files
            test_files = [f for f in files if f.startswith('_test_storage_')]
            for test_file in test_files:
                try:
                    default_storage.delete(test_file)
                    logger.info(f"Cleaned up test file: {test_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete test file {test_file}: {str(e)}")
                    
        except Exception as e:
            logger.warning(f"Error during test file cleanup: {str(e)}")

    def ready(self):
        """Verify storage configuration on startup"""
        from django.conf import settings
        
        # Skip storage verification if running migrations or collecting static
        if len(sys.argv) > 1:
            cmd = sys.argv[1]
            if cmd in ['migrate', 'collectstatic', 'makemigrations']:
                logger.info(f"Skipping storage verification during {cmd}")
                return
        
        # Clean up any leftover test files from previous runs
        self._cleanup_test_files()
        
        # Verify storage settings are configured
        if not hasattr(settings, 'DEFAULT_FILE_STORAGE'):
            raise StorageConfigError("DEFAULT_FILE_STORAGE not configured in settings!")
            
        if not hasattr(settings, 'STORAGE_BACKEND'):
            raise StorageConfigError("STORAGE_BACKEND not configured in settings!")
            
        logger.info("Verifying storage configuration...")
        logger.info(f"Using storage backend: {settings.STORAGE_BACKEND}")
        logger.info(f"DEFAULT_FILE_STORAGE: {settings.DEFAULT_FILE_STORAGE}")
        
        # Import and verify storage class
        try:
            storage_class = import_string(settings.DEFAULT_FILE_STORAGE)
            storage = storage_class()
            default_storage._wrapped = storage
        except Exception as e:
            logger.error(f"Storage initialization error: {str(e)}")
            raise StorageConfigError(f"Failed to initialize storage backend: {str(e)}")
        
        logger.info(f"Storage class initialized: {storage.__class__.__name__}")
        
        # Verify storage is working with a test file
        test_path = f"_test_storage_{int(time.time())}.txt"
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Test write
                default_storage.save(test_path, ContentFile("test content"))
                logger.info("Test file save successful")
                
                # Small delay to allow for eventual consistency
                time.sleep(1)
                
                # Verify file exists
                if not default_storage.exists(test_path):
                    raise StorageConfigError("Test file not found after save!")
                
                # Test read
                content = default_storage.open(test_path).read()
                if b"test content" not in content:
                    raise StorageConfigError("Test file content verification failed!")
                
                # Test delete and verify deletion
                default_storage.delete(test_path)
                time.sleep(1)  # Wait for deletion to propagate
                
                if default_storage.exists(test_path):
                    raise StorageConfigError("Test file still exists after deletion!")
                    
                logger.info("Storage verification complete")
                
                # Success - exit the retry loop
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    logger.error(f"Storage verification failed after {max_retries} attempts")
                    # Try to clean up before raising the error
                    try:
                        if default_storage.exists(test_path):
                            default_storage.delete(test_path)
                    except:
                        pass
                    raise StorageConfigError(f"Storage verification failed: {str(e)}")
                    
                logger.warning(f"Retry {retry_count}/{max_retries}: {str(e)}")
                # Try to clean up before retrying
                try:
                    if default_storage.exists(test_path):
                        default_storage.delete(test_path)
                except:
                    pass
                time.sleep(2)  # Wait before retrying
                
        # Final cleanup check
        self._cleanup_test_files() 