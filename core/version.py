import os
import subprocess
import datetime

def get_version():
    """Get the current version based on build-time version or git state"""
    # First try to get version from environment (set during Docker build)
    build_version = os.getenv('VERSION')
    if build_version:
        return build_version
        
    # If not in Docker (development), try git
    try:
        # Get the current commit hash (works with uncommitted changes)
        commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
        
        # Get the current working tree state hash (includes uncommitted changes)
        tree_hash = subprocess.check_output(['git', 'write-tree']).decode().strip()
        
        # Create a unique version based on the current state
        version = f"{commit}-{tree_hash[:8]}"
        return version
    except Exception:
        # Fallback to timestamp if git commands fail
        return datetime.datetime.now().strftime('%Y%m%d%H%M%S')

# Generate version on import
VERSION = get_version()
COMMIT = os.getenv('COMMIT', 'unknown')  # Use build-time commit if available
