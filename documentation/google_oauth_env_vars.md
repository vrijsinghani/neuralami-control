# Using Environment Variables for Google OAuth Credentials

This document explains how to use environment variables for Google OAuth credentials instead of JSON files.

## Overview

The application now supports two methods for providing Google OAuth credentials:

1. **JSON Files** (original method): Using `google_secrets.json` and `service-account.json` files
2. **Environment Variables** (new method): Using environment variables for all credential information

The environment variable approach is more secure and follows best practices for credential management.

## Converting JSON Files to Environment Variables

We've provided a utility script to help convert your existing JSON files to environment variables:

```bash
python scripts/json_to_env.py --client-secrets /path/to/google_secrets.json --service-account /path/to/service-account.json
```

This script will output environment variable settings that you can add to your `.env` file.

## Required Environment Variables

### Google OAuth Client Credentials

These variables replace the `google_secrets.json` file:

```
GOOGLE_OAUTH_USE_ENV=True
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_AUTH_URI=https://accounts.google.com/o/oauth2/auth
GOOGLE_OAUTH_TOKEN_URI=https://oauth2.googleapis.com/token
```

### Google Service Account Credentials

These variables replace the `service-account.json` file:

```
GOOGLE_SA_PROJECT_ID=your-project-id
GOOGLE_SA_PRIVATE_KEY_ID=your-private-key-id
GOOGLE_SA_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYour private key content with \n for newlines\n-----END PRIVATE KEY-----\n"
GOOGLE_SA_CLIENT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
GOOGLE_SA_CLIENT_ID=your-client-id
GOOGLE_SA_AUTH_URI=https://accounts.google.com/o/oauth2/auth
GOOGLE_SA_TOKEN_URI=https://oauth2.googleapis.com/token
GOOGLE_SA_AUTH_PROVIDER_CERT_URL=https://www.googleapis.com/oauth2/v1/certs
GOOGLE_SA_CLIENT_CERT_URL=https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com
```

## Enabling Environment Variable Mode

To use environment variables instead of JSON files, set the following in your `.env` file:

```
GOOGLE_OAUTH_USE_ENV=True
```

When this setting is enabled, the application will use the environment variables for OAuth credentials instead of looking for JSON files.

## Scope Configuration

The application now uses a centralized scope definition in the `OAuthManager` class. The scopes are defined as follows:

```python
OAUTH_SCOPES = {
    'analytics': {
        'readonly': 'https://www.googleapis.com/auth/analytics.readonly',
        'full': 'https://www.googleapis.com/auth/analytics'
    },
    'search_console': {
        'readonly': 'https://www.googleapis.com/auth/webmasters.readonly'
    },
    'adwords': {
        'full': 'https://www.googleapis.com/auth/adwords'
    },
    'common': {
        'openid': 'openid',
        'email': 'https://www.googleapis.com/auth/userinfo.email',
        'profile': 'https://www.googleapis.com/auth/userinfo.profile'
    }
}
```

### Scope Usage

The application uses the following scopes for each service:

- **Google Analytics**: `analytics.readonly` and `analytics` (full access)
- **Search Console**: `webmasters.readonly`
- **AdWords**: `adwords`

Both the readonly and full access scopes for Google Analytics are included to support future functionality for editing analytics data. This ensures that users only need to authorize once, even as new features are added.

## Troubleshooting

If you encounter issues with the environment variable approach:

1. Ensure `GOOGLE_OAUTH_USE_ENV` is set to `True`
2. Verify all required environment variables are set correctly
3. Check that the private key is properly formatted with `\n` for newlines
4. If using Docker, ensure the environment variables are properly passed to the container

If problems persist, you can revert to the JSON file approach by setting `GOOGLE_OAUTH_USE_ENV` to `False`.

## Security Considerations

When using environment variables for credentials:

1. Never commit your `.env` file to version control
2. Use a secure method to manage and distribute environment variables in production
3. Consider using a secrets management service for production environments
4. Regularly rotate credentials according to your security policies
