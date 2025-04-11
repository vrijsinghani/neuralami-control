# File Manager Tests

This directory contains tests for the file manager app, including:

1. Django unit tests for the file manager views
2. Management command for testing storage utility methods

## Running Django Unit Tests

To run the Django unit tests for the file manager views, use the following command:

```bash
python manage.py test apps.file_manager
```

These tests verify that the file manager views work correctly with the storage utility methods.

## Running Storage Utility Tests

To test the storage utility methods directly, use the management command:

```bash
python manage.py test_storage_utils
```

See the [management command README](management/commands/README.md) for more details on the storage utility tests.

## Testing with Different Storage Backends

To test with different storage backends, you can use the provided shell script:

```bash
./apps/file_manager/management/commands/run_storage_tests.sh
```

This script will run the storage utility tests with different storage backends configured in Django settings.

## Manual Testing

You can also manually test the file manager views by:

1. Starting the Django development server:
   ```bash
   python manage.py runserver
   ```

2. Navigating to the file manager in your browser:
   ```
   http://localhost:8000/file-manager/
   ```

3. Testing the various file operations (create folder, upload file, delete file, etc.)

## Troubleshooting

If you encounter issues with the tests, try the following:

1. Check the Django logs for any errors.
2. Verify that your storage backend is properly configured in Django settings.
3. Ensure that the storage backend has the necessary permissions to create, read, and delete files.
4. Run the tests with verbose output:
   ```bash
   python manage.py test apps.file_manager -v 2
   ```
5. Run the storage utility tests with verbose output:
   ```bash
   python manage.py test_storage_utils --verbose
   ```
