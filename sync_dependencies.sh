#!/bin/bash

# Get list of explicitly installed packages from poetry (not dependencies)
current_packages=$(poetry show --tree | grep '^\w' | awk '{print $1}')

# Get list of desired packages from requirements.in
desired_packages=$(grep -v '^#' requirements.in | grep -v '^$' | awk '{print $1}' | sed 's/>=.*$//' | sed 's/>.*$//' | sed 's/==.*$//')

# Remove packages that are explicitly installed but not in requirements.in
for package in $current_packages; do
    if ! echo "$desired_packages" | grep -q "^$package$"; then
        echo "Checking if we should remove: $package"
        # Only remove if it was explicitly installed (in pyproject.toml)
        if grep -q "^$package = " pyproject.toml; then
            echo "Removing package: $package"
            poetry remove "$package"
        else
            echo "Skipping $package as it's a dependency"
        fi
    fi
done

# Add packages from requirements.in
while IFS= read -r line; do
    # Skip empty lines and comments
    if [[ -n "$line" && ! "$line" =~ ^# ]]; then
        echo "Adding/updating dependency: $line"
        poetry add "$line"
    fi
done < requirements.in 