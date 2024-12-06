#!/bin/bash

print_directory_structure() {
    local dir=$1
    local current_depth=$2
    local max_depth=3
    local exclude_dirs=$3

    if [ $current_depth -gt $max_depth ]; then
        return
    fi

    for item in "$dir"/*; do
        if [[ -d "$item" ]]; then
            local dirname=$(basename "$item")
            if [[ ! " $exclude_dirs " =~ " $dirname " ]]; then
                printf "%*s%s/\n" $((($current_depth - 1) * 4)) '' "$dirname"
                if [ $current_depth -lt $max_depth ]; then
                    print_directory_structure "$item" $(($current_depth + 1)) "$exclude_dirs"
                fi
            fi
        fi
    done
}

# Directories to exclude (space-separated)
exclude_dirs=".git node_modules .vscode"

# Starting directory (use "." for current directory)
start_dir="."

echo "$(basename "$(pwd)")/"
print_directory_structure "$start_dir" 1 "$exclude_dirs"
