#!/usr/bin/env python
"""
Utility script to convert Google OAuth JSON files to environment variables.

This script reads the Google OAuth client secrets file and service account file,
and outputs the environment variable settings that can be added to a .env file.

Usage:
    python json_to_env.py --client-secrets /path/to/google_secrets.json --service-account /path/to/service-account.json

The script will output environment variable settings that can be copied to a .env file.
"""

import argparse
import json
import os
import sys

def convert_client_secrets_to_env(file_path):
    """Convert Google OAuth client secrets file to environment variables."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if 'web' not in data:
            print("Error: Invalid client secrets file format. Expected 'web' key.")
            return None
        
        web_data = data['web']
        env_vars = {
            'GOOGLE_OAUTH_USE_ENV': 'True',
            'GOOGLE_OAUTH_CLIENT_ID': web_data.get('client_id', ''),
            'GOOGLE_OAUTH_CLIENT_SECRET': web_data.get('client_secret', ''),
            'GOOGLE_OAUTH_AUTH_URI': web_data.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
            'GOOGLE_OAUTH_TOKEN_URI': web_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        }
        
        return env_vars
    
    except Exception as e:
        print(f"Error reading client secrets file: {str(e)}")
        return None

def convert_service_account_to_env(file_path):
    """Convert Google service account file to environment variables."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Replace newlines in private key with literal \n for environment variable
        private_key = data.get('private_key', '').replace('\n', '\\n')
        
        env_vars = {
            'GOOGLE_SA_PROJECT_ID': data.get('project_id', ''),
            'GOOGLE_SA_PRIVATE_KEY_ID': data.get('private_key_id', ''),
            'GOOGLE_SA_PRIVATE_KEY': private_key,
            'GOOGLE_SA_CLIENT_EMAIL': data.get('client_email', ''),
            'GOOGLE_SA_CLIENT_ID': data.get('client_id', ''),
            'GOOGLE_SA_AUTH_URI': data.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
            'GOOGLE_SA_TOKEN_URI': data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            'GOOGLE_SA_AUTH_PROVIDER_CERT_URL': data.get('auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
            'GOOGLE_SA_CLIENT_CERT_URL': data.get('client_x509_cert_url', ''),
        }
        
        return env_vars
    
    except Exception as e:
        print(f"Error reading service account file: {str(e)}")
        return None

def format_env_vars(env_vars):
    """Format environment variables for .env file."""
    lines = []
    for key, value in env_vars.items():
        # Quote values that contain spaces or special characters
        if ' ' in value or '\n' in value or '"' in value or "'" in value:
            # Escape double quotes
            value = value.replace('"', '\\"')
            lines.append(f'{key}="{value}"')
        else:
            lines.append(f'{key}={value}')
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description='Convert Google OAuth JSON files to environment variables.')
    parser.add_argument('--client-secrets', help='Path to Google OAuth client secrets file')
    parser.add_argument('--service-account', help='Path to Google service account file')
    
    args = parser.parse_args()
    
    if not args.client_secrets and not args.service_account:
        parser.print_help()
        sys.exit(1)
    
    all_env_vars = {}
    
    if args.client_secrets:
        client_env_vars = convert_client_secrets_to_env(args.client_secrets)
        if client_env_vars:
            all_env_vars.update(client_env_vars)
            print("\n=== Google OAuth Client Environment Variables ===")
            print(format_env_vars(client_env_vars))
    
    if args.service_account:
        service_env_vars = convert_service_account_to_env(args.service_account)
        if service_env_vars:
            all_env_vars.update(service_env_vars)
            print("\n=== Google Service Account Environment Variables ===")
            print(format_env_vars(service_env_vars))
    
    if all_env_vars:
        print("\n=== All Environment Variables ===")
        print(format_env_vars(all_env_vars))
        
        print("\nCopy these environment variables to your .env file.")
        print("Then set GOOGLE_OAUTH_USE_ENV=True to use environment variables instead of JSON files.")

if __name__ == '__main__':
    main()
