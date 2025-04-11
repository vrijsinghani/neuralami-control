#!/bin/bash

# Run storage utility tests with different storage backends

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running storage utility tests with different storage backends...${NC}"

# Function to run tests with a specific storage backend
run_tests_with_backend() {
    backend_name=$1
    backend_setting=$2
    
    echo -e "\n${YELLOW}Testing with $backend_name storage backend...${NC}"
    echo "Setting DEFAULT_FILE_STORAGE=$backend_setting"
    
    # Create a temporary settings file
    cat > /tmp/temp_settings.py << EOF
# Temporary settings for testing storage backends
DEFAULT_FILE_STORAGE = '$backend_setting'
EOF
    
    # Run the tests with the temporary settings
    echo -e "${YELLOW}Running tests...${NC}"
    python manage.py test_storage_utils --verbose --settings=/tmp/temp_settings.py
    
    # Check the result
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Tests passed with $backend_name storage backend!${NC}"
    else
        echo -e "${RED}Tests failed with $backend_name storage backend!${NC}"
    fi
}

# Run tests with local filesystem storage
run_tests_with_backend "Local Filesystem" "django.core.files.storage.FileSystemStorage"

# Run tests with MinIO storage
run_tests_with_backend "MinIO" "core.minio_storage.MinIOStorage"

# Run tests with S3 storage (if configured)
# Uncomment the following line if you have S3 storage configured
# run_tests_with_backend "S3" "storages.backends.s3boto3.S3Boto3Storage"

echo -e "\n${YELLOW}All tests completed!${NC}"
