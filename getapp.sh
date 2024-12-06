#!/bin/bash

# Check if a port number is provided as an argument
if [ -z "$1" ]; then
  echo "Usage: $0 <port_number>"
  exit 1
fi

port_number=$1

# Extract the application name using sed
app_name=$(sudo ss -tulnp | grep $port_number | sed 's/.*("\([^"]*\)".*/\1/')

# Check if an application name was found
if [ -z "$app_name" ]; then
  echo "No application found listening on port $port_number"
  exit 1
fi

# Print the application name
echo $app_name


