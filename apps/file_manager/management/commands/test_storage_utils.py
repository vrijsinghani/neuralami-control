import os
import uuid
import time
import logging
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from apps.file_manager.storage import PathManager

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test storage utility methods to ensure they work with any storage backend'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            help='User ID to use for testing. If not provided, a test directory will be used.'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        parser.add_argument(
            '--no-cleanup',
            action='store_true',
            help='Do not clean up test files after running tests'
        )

    def handle(self, **options):
        self.verbose = options.get('verbose', False)
        self.no_cleanup = options.get('no_cleanup', False)

        self.stdout.write(self.style.SUCCESS('Testing storage utility methods...'))

        # Determine the test directory
        user_id = options.get('user_id')
        if user_id:
            # Use the provided user ID
            self.stdout.write(f'Using user ID: {user_id}')
            self.test_root = f"{user_id}/test_storage_{uuid.uuid4().hex[:8]}/"
        else:
            # Use a special test directory
            self.test_root = f"TEST_USER/test_storage_{uuid.uuid4().hex[:8]}/"

        self.stdout.write(f'Using test directory: {self.test_root}')

        # Create a PathManager instance
        user_id = options.get('user_id')
        self.path_manager = PathManager(user_id=user_id)

        # Create the test root directory
        try:
            # Extract the relative path without user_id
            if user_id and self.test_root.startswith(f"{user_id}/"):
                rel_path = self.test_root[len(f"{user_id}/"):]
            else:
                rel_path = self.test_root

            self.path_manager.create_directory(rel_path)
            self.log_success(f"Created test root directory: {self.test_root}")
        except Exception as e:
            self.log_error(f"Failed to create test root directory: {str(e)}")
            return

        # Run the tests
        try:
            self.run_tests()
        finally:
            # Clean up
            if not self.no_cleanup:
                self.stdout.write('Cleaning up test files...')
                try:
                    # Extract the relative path without user_id
                    if user_id and self.test_root.startswith(f"{user_id}/"):
                        rel_path = self.test_root[len(f"{user_id}/"):]
                    else:
                        rel_path = self.test_root

                    self.path_manager.delete_directory(rel_path)
                    self.log_success(f"Cleaned up test directory: {self.test_root}")
                except Exception as e:
                    self.log_error(f"Failed to clean up test directory: {str(e)}")

    def run_tests(self):
        """Run all test methods"""
        # Track test results
        self.passed = 0
        self.failed = 0
        self.skipped = 0

        # Get all test methods
        test_methods = [method for method in dir(self) if method.startswith('test_') and callable(getattr(self, method))]

        # Run each test method
        for method_name in sorted(test_methods):
            self.stdout.write(f"\nRunning {method_name}...")
            try:
                method = getattr(self, method_name)
                method()
                self.passed += 1
                self.log_success(f"{method_name} passed")
            except Exception as e:
                self.failed += 1
                self.log_error(f"{method_name} failed: {str(e)}")
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))

        # Print summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(f"Test Summary: {self.passed} passed, {self.failed} failed, {self.skipped} skipped")
        if self.failed == 0:
            self.stdout.write(self.style.SUCCESS("All tests passed!"))
        else:
            self.stdout.write(self.style.ERROR(f"{self.failed} tests failed!"))

    def log_success(self, message):
        """Log a success message"""
        self.stdout.write(self.style.SUCCESS(f"✓ {message}"))

    def log_error(self, message):
        """Log an error message"""
        self.stdout.write(self.style.ERROR(f"✗ {message}"))

    def log_info(self, message):
        """Log an info message"""
        if self.verbose:
            self.stdout.write(f"  {message}")

    def assert_true(self, condition, message):
        """Assert that a condition is true"""
        if not condition:
            raise AssertionError(message)

    def assert_false(self, condition, message):
        """Assert that a condition is false"""
        if condition:
            raise AssertionError(message)

    def assert_equal(self, expected, actual, message):
        """Assert that two values are equal"""
        if expected != actual:
            raise AssertionError(f"{message}: expected {expected}, got {actual}")

    def assert_in(self, item, collection, message):
        """Assert that an item is in a collection"""
        if item not in collection:
            raise AssertionError(f"{message}: {item} not found in {collection}")

    def assert_not_in(self, item, collection, message):
        """Assert that an item is not in a collection"""
        if item in collection:
            raise AssertionError(f"{message}: {item} found in {collection}")

    def _get_rel_path(self, path):
        """Get the relative path without user_id"""
        user_id = getattr(self.path_manager, 'user_id', None)
        if user_id and path.startswith(f"{user_id}/"):
            return path[len(f"{user_id}/"):]
        return path

    def test_create_directory(self):
        """Test creating a directory"""
        # Create a test directory
        test_dir = f"{self.test_root}test_create_directory/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Verify the directory exists
        exists = self.path_manager.directory_exists(rel_test_dir)
        self.assert_true(exists, f"Directory {test_dir} should exist")
        self.log_info(f"Directory exists: {exists}")

        # Create a nested directory
        nested_dir = f"{test_dir}nested/"
        rel_nested_dir = self._get_rel_path(nested_dir)
        self.path_manager.create_directory(rel_nested_dir)
        self.log_info(f"Created nested directory: {nested_dir}")

        # Verify the nested directory exists
        exists = self.path_manager.directory_exists(rel_nested_dir)
        self.assert_true(exists, f"Nested directory {nested_dir} should exist")
        self.log_info(f"Nested directory exists: {exists}")

    def test_directory_exists(self):
        """Test checking if a directory exists"""
        # Create a test directory
        test_dir = f"{self.test_root}test_directory_exists/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Test existing directory
        exists = self.path_manager.directory_exists(rel_test_dir)
        self.assert_true(exists, f"Directory {test_dir} should exist")
        self.log_info(f"Directory exists: {exists}")

        # Test non-existent directory
        non_existent_dir = f"{self.test_root}non_existent/"
        rel_non_existent_dir = self._get_rel_path(non_existent_dir)
        exists = self.path_manager.directory_exists(rel_non_existent_dir)
        self.assert_false(exists, f"Directory {non_existent_dir} should not exist")
        self.log_info(f"Non-existent directory exists: {exists}")

    def test_list_directory(self):
        """Test listing a directory"""
        # Create a test directory with files and subdirectories
        test_dir = f"{self.test_root}test_list_directory/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Create a subdirectory
        subdir = f"{test_dir}subdir/"
        rel_subdir = self._get_rel_path(subdir)
        self.path_manager.create_directory(rel_subdir)
        self.log_info(f"Created subdirectory: {subdir}")

        # Create some files
        for i in range(3):
            file_path = f"{test_dir}file_{i}.txt"
            rel_file_path = self._get_rel_path(file_path)
            self.path_manager.secure_storage.save(rel_file_path, ContentFile(f"Content of file {i}".encode()))
            self.log_info(f"Created file: {file_path}")

        # List the directory
        contents = self.path_manager.list_directory(rel_test_dir)
        self.log_info(f"Listed directory contents: {contents}")

        # Extract directories and files from contents
        dirs = [item['name'] for item in contents if item['type'] == 'directory']
        files = [item['name'] for item in contents if item['type'] == 'file']
        self.log_info(f"Extracted dirs={dirs}, files={files}")

        # Verify the results
        self.assert_in("subdir", dirs, "Subdirectory should be in the list")
        self.assert_equal(1, len(dirs), "Should have 1 subdirectory")
        self.assert_equal(3, len(files), "Should have 3 files")

        for i in range(3):
            self.assert_in(f"file_{i}.txt", files, f"file_{i}.txt should be in the list")

    def test_delete_directory(self):
        """Test deleting a directory"""
        # Create a test directory with files and subdirectories
        test_dir = f"{self.test_root}test_delete_directory/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Create a subdirectory
        subdir = f"{test_dir}subdir/"
        rel_subdir = self._get_rel_path(subdir)
        self.path_manager.create_directory(rel_subdir)
        self.log_info(f"Created subdirectory: {subdir}")

        # Create some files
        for i in range(3):
            file_path = f"{test_dir}file_{i}.txt"
            rel_file_path = self._get_rel_path(file_path)
            self.path_manager.secure_storage.save(rel_file_path, ContentFile(f"Content of file {i}".encode()))
            self.log_info(f"Created file: {file_path}")

        # Create a file in the subdirectory
        subdir_file = f"{subdir}subdir_file.txt"
        rel_subdir_file = self._get_rel_path(subdir_file)
        self.path_manager.secure_storage.save(rel_subdir_file, ContentFile(b"Content of subdir file"))
        self.log_info(f"Created file in subdirectory: {subdir_file}")

        # Delete the directory
        deleted_count = self.path_manager.delete_directory(rel_test_dir)
        self.log_info(f"Deleted directory: {test_dir}, deleted {deleted_count} files")

        # Verify the directory is deleted
        exists = self.path_manager.directory_exists(rel_test_dir)
        self.assert_false(exists, f"Directory {test_dir} should not exist after deletion")
        self.log_info(f"Directory exists after deletion: {exists}")

        # Verify the subdirectory is deleted
        exists = self.path_manager.directory_exists(rel_subdir)
        self.assert_false(exists, f"Subdirectory {subdir} should not exist after deletion")
        self.log_info(f"Subdirectory exists after deletion: {exists}")

        # Verify the files are deleted
        for i in range(3):
            file_path = f"{test_dir}file_{i}.txt"
            rel_file_path = self._get_rel_path(file_path)
            exists = self.path_manager.secure_storage.exists(rel_file_path)
            self.assert_false(exists, f"File {file_path} should not exist after deletion")
            self.log_info(f"File exists after deletion: {exists}")

        # Verify the file in the subdirectory is deleted
        exists = self.path_manager.secure_storage.exists(rel_subdir_file)
        self.assert_false(exists, f"File {subdir_file} should not exist after deletion")
        self.log_info(f"File in subdirectory exists after deletion: {exists}")

        # Verify the deleted count
        self.assert_equal(4, deleted_count, "Should have deleted 4 files")

    def test_batch_delete(self):
        """Test batch deleting files"""
        # Create a test directory
        test_dir = f"{self.test_root}test_batch_delete/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Create some files
        file_paths = []
        rel_file_paths = []
        for i in range(5):
            file_path = f"{test_dir}batch_file_{i}.txt"
            rel_file_path = self._get_rel_path(file_path)
            self.path_manager.secure_storage.save(rel_file_path, ContentFile(f"Content of batch file {i}".encode()))
            file_paths.append(file_path)
            rel_file_paths.append(rel_file_path)
            self.log_info(f"Created file: {file_path}")

        # Batch delete the files
        deleted_count = self.path_manager.batch_delete(rel_file_paths)
        self.log_info(f"Batch deleted files, deleted {deleted_count} files")

        # Verify the files are deleted
        for file_path, rel_file_path in zip(file_paths, rel_file_paths):
            exists = self.path_manager.secure_storage.exists(rel_file_path)
            self.assert_false(exists, f"File {file_path} should not exist after batch deletion")
            self.log_info(f"File exists after batch deletion: {exists}")

        # Verify the deleted count
        self.assert_equal(5, deleted_count, "Should have deleted 5 files")

    def test_get_nested_directory_structure(self):
        """Test getting a nested directory structure"""
        # Create a test directory structure
        test_dir = f"{self.test_root}test_nested_structure/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Create some subdirectories
        subdirs = [
            f"{test_dir}subdir1/",
            f"{test_dir}subdir2/",
            f"{test_dir}subdir1/subsubdir1/",
            f"{test_dir}subdir1/subsubdir2/",
            f"{test_dir}subdir2/subsubdir3/"
        ]

        rel_subdirs = [self._get_rel_path(subdir) for subdir in subdirs]

        for subdir, rel_subdir in zip(subdirs, rel_subdirs):
            self.path_manager.create_directory(rel_subdir)
            self.log_info(f"Created subdirectory: {subdir}")

        # Create some files
        files = [
            f"{test_dir}file1.txt",
            f"{test_dir}subdir1/file2.txt",
            f"{test_dir}subdir1/subsubdir1/file3.txt",
            f"{test_dir}subdir2/file4.txt"
        ]

        rel_files = [self._get_rel_path(file_path) for file_path in files]

        for file_path, rel_file_path in zip(files, rel_files):
            self.path_manager.secure_storage.save(rel_file_path, ContentFile(f"Content of {os.path.basename(file_path)}".encode()))
            self.log_info(f"Created file: {file_path}")

        # Get the nested directory structure
        structure = self.path_manager.get_nested_directory_structure()
        self.log_info(f"Got nested directory structure: {structure}")

        # Verify the structure
        self.assert_equal(1, len(structure), "Should have 1 root directory")
        root = structure[0]
        self.assert_equal("Home", root["name"], "Root directory should be named 'Home'")
        self.assert_equal("", root["path"], "Root directory should have empty path")
        self.assert_equal(2, len(root["directories"]), "Root directory should have 2 subdirectories")

        # Find subdir1 and subdir2
        subdir1 = None
        subdir2 = None
        for subdir in root["directories"]:
            if subdir["name"] == "subdir1":
                subdir1 = subdir
            elif subdir["name"] == "subdir2":
                subdir2 = subdir

        self.assert_true(subdir1 is not None, "subdir1 should be in the structure")
        self.assert_true(subdir2 is not None, "subdir2 should be in the structure")

        # Verify subdir1
        self.assert_equal("subdir1", subdir1["name"], "subdir1 should be named 'subdir1'")
        self.assert_equal("subdir1", subdir1["path"], "subdir1 should have path 'subdir1'")
        self.assert_equal(2, len(subdir1["directories"]), "subdir1 should have 2 subdirectories")

        # Verify subdir2
        self.assert_equal("subdir2", subdir2["name"], "subdir2 should be named 'subdir2'")
        self.assert_equal("subdir2", subdir2["path"], "subdir2 should have path 'subdir2'")
        self.assert_equal(1, len(subdir2["directories"]), "subdir2 should have 1 subdirectory")

    def test_file_operations(self):
        """Test basic file operations"""
        # Create a test directory
        test_dir = f"{self.test_root}test_file_operations/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Create a file
        file_path = f"{test_dir}test_file.txt"
        rel_file_path = self._get_rel_path(file_path)
        content = "This is a test file."
        self.path_manager.secure_storage.save(rel_file_path, ContentFile(content.encode()))
        self.log_info(f"Created file: {file_path}")

        # Verify the file exists
        exists = self.path_manager.secure_storage.exists(rel_file_path)
        self.assert_true(exists, f"File {file_path} should exist")
        self.log_info(f"File exists: {exists}")

        # Verify the file content
        with self.path_manager.secure_storage._open(rel_file_path, 'r') as f:
            file_content = f.read()
        self.assert_equal(content, file_content, "File content should match")
        self.log_info(f"File content: {file_content}")

        # Verify the file size
        size = self.path_manager.secure_storage.size(rel_file_path)
        self.assert_equal(len(content), size, "File size should match content length")
        self.log_info(f"File size: {size}")

        # Delete the file
        self.path_manager.secure_storage.delete(rel_file_path)
        self.log_info(f"Deleted file: {file_path}")

        # Verify the file is deleted
        exists = self.path_manager.secure_storage.exists(rel_file_path)
        self.assert_false(exists, f"File {file_path} should not exist after deletion")
        self.log_info(f"File exists after deletion: {exists}")

    def test_performance(self):
        """Test performance of storage operations"""
        # Create a test directory
        test_dir = f"{self.test_root}test_performance/"
        rel_test_dir = self._get_rel_path(test_dir)
        self.path_manager.create_directory(rel_test_dir)
        self.log_info(f"Created directory: {test_dir}")

        # Measure time to create 10 files
        start_time = time.time()
        file_paths = []
        rel_file_paths = []
        for i in range(10):
            file_path = f"{test_dir}perf_file_{i}.txt"
            rel_file_path = self._get_rel_path(file_path)
            self.path_manager.secure_storage.save(rel_file_path, ContentFile(f"Content of performance file {i}".encode()))
            file_paths.append(file_path)
            rel_file_paths.append(rel_file_path)
        create_time = time.time() - start_time
        self.log_info(f"Time to create 10 files: {create_time:.4f} seconds")

        # Measure time to list directory
        start_time = time.time()
        contents = self.path_manager.list_directory(rel_test_dir)
        list_time = time.time() - start_time
        self.log_info(f"Time to list directory: {list_time:.4f} seconds")
        files = [item['name'] for item in contents if item['type'] == 'file']
        self.assert_equal(10, len(files), "Should have 10 files")

        # Measure time to batch delete files
        start_time = time.time()
        deleted_count = self.path_manager.batch_delete(rel_file_paths)
        delete_time = time.time() - start_time
        self.log_info(f"Time to batch delete 10 files: {delete_time:.4f} seconds")
        self.assert_equal(10, deleted_count, "Should have deleted 10 files")

        # Log performance metrics
        self.log_info(f"Performance metrics:")
        self.log_info(f"  Create 10 files: {create_time:.4f} seconds ({create_time/10:.4f} seconds per file)")
        self.log_info(f"  List directory: {list_time:.4f} seconds")
        self.log_info(f"  Batch delete 10 files: {delete_time:.4f} seconds ({delete_time/10:.4f} seconds per file)")

    def test_error_handling(self):
        """Test error handling in storage operations"""
        # Test deleting a non-existent file
        non_existent_file = f"{self.test_root}non_existent_file.txt"
        rel_non_existent_file = self._get_rel_path(non_existent_file)
        try:
            self.path_manager.secure_storage.delete(rel_non_existent_file)
            self.log_info(f"Deleted non-existent file without error: {non_existent_file}")
        except Exception as e:
            self.log_error(f"Error deleting non-existent file: {str(e)}")
            # This should not raise an error, so fail the test
            self.assert_true(False, "Deleting a non-existent file should not raise an error")

        # Test batch deleting with some non-existent files
        existing_file = f"{self.test_root}existing_file.txt"
        rel_existing_file = self._get_rel_path(existing_file)
        self.path_manager.secure_storage.save(rel_existing_file, ContentFile(b"Existing file"))

        rel_file_paths = [
            rel_existing_file,
            self._get_rel_path(f"{self.test_root}non_existent_file1.txt"),
            self._get_rel_path(f"{self.test_root}non_existent_file2.txt")
        ]

        try:
            deleted_count = self.path_manager.batch_delete(rel_file_paths)
            self.log_info(f"Batch deleted with non-existent files, deleted {deleted_count} files")
            # Should have deleted only the existing file
            self.assert_equal(1, deleted_count, "Should have deleted only the existing file")
        except Exception as e:
            self.log_error(f"Error batch deleting with non-existent files: {str(e)}")
            # This should not raise an error, so fail the test
            self.assert_true(False, "Batch deleting with some non-existent files should not raise an error")

        # Test deleting a non-existent directory
        non_existent_dir = f"{self.test_root}non_existent_dir/"
        rel_non_existent_dir = self._get_rel_path(non_existent_dir)
        try:
            deleted_count = self.path_manager.delete_directory(rel_non_existent_dir)
            self.log_info(f"Deleted non-existent directory without error: {non_existent_dir}, deleted {deleted_count} files")
            # Should have deleted 0 files
            self.assert_equal(0, deleted_count, "Should have deleted 0 files from non-existent directory")
        except Exception as e:
            self.log_error(f"Error deleting non-existent directory: {str(e)}")
            # This should not raise an error, so fail the test
            self.assert_true(False, "Deleting a non-existent directory should not raise an error")
