#!/bin/bash

# Read the requirements.in file
while IFS= read -r line; do
    # Skip empty lines and comments
    if [[ -n "$line" && ! "$line" =~ ^# ]]; then
        echo "Adding dependency: $line"
        nohup poetry add "$line" >> poetry_add.log 2>&1 &
    fi
done < requirements.in

# Wait for all background jobs to finish
wait