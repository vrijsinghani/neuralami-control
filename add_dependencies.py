# add_dependencies.py
import subprocess

# Read the requirements.in file
with open('requirements.in', 'r') as f:
    lines = f.readlines()

# Filter out comments and empty lines
dependencies = [line.strip() for line in lines if line.strip() and not line.startswith('#')]

# Add each dependency using Poetry
for dep in dependencies:
    print(f"Adding dependency: {dep}")
    subprocess.run(f'poetry add {dep}', shell=True)