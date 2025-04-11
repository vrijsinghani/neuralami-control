import os
import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .models import FileInfo

class FileManagerViewsTest(TestCase):
    """Test the file manager views that use storage utility methods"""

    def setUp(self):
        """Set up test data"""
        # Create a test user
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )

        # Create a test client and log in
        self.client = Client()
        self.client.login(username='testuser', password='testpassword')

        # Create a test directory and files
        self.user_id = str(self.user.id)
        self.test_dir = f"{self.user_id}/test_folder_{uuid.uuid4().hex[:8]}/"
        default_storage.create_directory(self.test_dir)

        # Create some test files
        self.test_files = []
        for i in range(3):
            file_path = f"{self.test_dir}test_file_{i}.txt"
            default_storage.save(file_path, ContentFile(f"Content of test file {i}".encode()))
            self.test_files.append(file_path)

            # Create a FileInfo record for the file
            FileInfo.objects.create(
                user=self.user,
                path=file_path,
                filename=f"test_file_{i}.txt",
                file_type='txt',
                file_size=len(f"Content of test file {i}")
            )

        # Create a test subfolder
        self.test_subfolder = f"{self.test_dir}subfolder/"
        default_storage.create_directory(self.test_subfolder)

        # Create a test file in the subfolder
        self.subfolder_file = f"{self.test_subfolder}subfolder_file.txt"
        default_storage.save(self.subfolder_file, ContentFile(b"Content of subfolder file"))

        # Create a FileInfo record for the subfolder file
        FileInfo.objects.create(
            user=self.user,
            path=self.subfolder_file,
            filename="subfolder_file.txt",
            file_type='txt',
            file_size=len("Content of subfolder file")
        )

    def tearDown(self):
        """Clean up test data"""
        # Delete the test directory and all its contents
        default_storage.delete_directory(self.test_dir)

    def test_delete_folder(self):
        """Test the delete_folder view"""
        # Get the folder path relative to the user directory
        folder_path = self.test_subfolder[len(self.user_id)+1:-1]  # Remove user_id/ prefix and trailing /

        # Call the delete_folder view
        response = self.client.post(reverse('file_manager:delete_folder'), {
            'folder_path': folder_path
        })

        # Check the response
        self.assertEqual(response.status_code, 302)  # Redirect on success

        # Verify the folder is deleted
        self.assertFalse(default_storage.directory_exists(self.test_subfolder))

        # Verify the file in the subfolder is deleted from the database
        self.assertEqual(FileInfo.objects.filter(path=self.subfolder_file).count(), 0)

    def test_move_files(self):
        """Test the move_files view"""
        # Get the file path relative to the user directory
        file_path = self.test_files[0]

        # Get the target directory relative to the user directory
        target_dir = self.test_subfolder[len(self.user_id)+1:-1]  # Remove user_id/ prefix and trailing /

        # Call the move_files view
        response = self.client.post(reverse('file_manager:move_files'), {
            'file_paths[]': [file_path],
            'target_directory': target_dir
        })

        # Check the response
        self.assertEqual(response.status_code, 200)  # Success

        # Verify the file is moved
        new_path = f"{self.test_subfolder}{os.path.basename(file_path)}"
        self.assertTrue(default_storage.exists(new_path))
        self.assertFalse(default_storage.exists(file_path))

        # Verify the file info is updated in the database
        file_info = FileInfo.objects.get(filename=os.path.basename(file_path))
        self.assertEqual(file_info.path, new_path)

    def test_delete_files(self):
        """Test the delete_files view"""
        # Call the delete_files view
        response = self.client.post(reverse('file_manager:delete_files'), {
            'file_paths[]': self.test_files
        })

        # Check the response
        self.assertEqual(response.status_code, 200)  # Success

        # Verify the files are deleted
        for file_path in self.test_files:
            self.assertFalse(default_storage.exists(file_path))

        # Verify the file info is deleted from the database
        for file_path in self.test_files:
            self.assertEqual(FileInfo.objects.filter(path=file_path).count(), 0)