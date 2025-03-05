import os
import subprocess
import datetime

def get_version():
    """Get the current version based on build-time version or git state"""
    # First try to get version from environment (set during Docker build)
    build_version = os.getenv('VERSION')
    if build_version:
        # Get commit date from environment
        commit_date = os.getenv('COMMIT_DATE')
        if commit_date:
            # Convert Unix timestamp to datetime
            dt = datetime.datetime.fromtimestamp(int(commit_date))
            # Format as YYYYMMDD-HHMMSS
            date_str = dt.strftime('%Y%m%d-%H%M%S')
            return f"{build_version}-{date_str}"
        return build_version
        
    # If not in Docker (development), try git
    try:
        # Get the current commit hash (works with uncommitted changes)
        commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
        
        # Get the current working tree state hash (includes uncommitted changes)
        tree_hash = subprocess.check_output(['git', 'write-tree']).decode().strip()
        
        # Get commit timestamp
        commit_date = subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD']).decode().strip()
        dt = datetime.datetime.fromtimestamp(int(commit_date))
        date_str = dt.strftime('%Y%m%d-%H%M%S')
        
        # Create a unique version based on the current state
        version = f"{commit}-{tree_hash[:8]}-{date_str}"
        return version
    except Exception:
        # Fallback to current timestamp if git commands fail
        return datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

# Generate version on import
VERSION = get_version()
COMMIT = os.getenv('COMMIT', 'unknown')  # Use build-time commit if available
