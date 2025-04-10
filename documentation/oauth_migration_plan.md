# Google OAuth Migration Plan

This document outlines the plan for migrating the codebase to use the centralized OAuth implementation.

## Overview

We've created a centralized OAuth implementation that:

1. Uses a single source of truth for OAuth scopes in `OAuthManager.OAUTH_SCOPES`
2. Provides utility functions for creating credentials and services
3. Supports both file-based and environment variable-based credential storage
4. Includes both readonly and full access scopes for Google Analytics

## Completed Changes

- [x] Created `apps/seo_manager/env_credentials.py` for environment variable support
- [x] Enhanced `OAuthManager` in `apps/seo_manager/models.py` with centralized scope definitions
- [x] Created `apps/seo_manager/oauth_utils.py` as a single entry point for OAuth operations
- [x] Updated `apps/agents/tools/google_analytics_tool/generic_google_analytics_tool.py` to use the centralized OAuth utilities
- [x] Updated `apps/agents/tools/google_search_console_tool/generic_google_search_console_tool.py` to use the centralized OAuth utilities

## Remaining Files to Update

### Tool Files

- [ ] `apps/agents/tools/google_analytics_tool/google_analytics_tool.py`
- [ ] `apps/agents/tools/google_overview_tool/google_overview_tool.py`
- [ ] `apps/agents/tools/google_report_tool/google_ranking_data_tool.py`
- [ ] `apps/agents/tools/google_report_tool/google_rankings_tool.py`
- [ ] `apps/agents/tools/google_report_tool/google_report_tool.py`

### Core OAuth Files

- [ ] `apps/seo_manager/google_auth.py` - Update to use the centralized scope definitions
- [ ] `apps/seo_manager/services.py` - Update to use the centralized OAuth utilities

### View Files

- [ ] `apps/seo_manager/views/ads_views.py` - Update to use the centralized OAuth utilities
- [ ] `apps/seo_manager/views/analytics_views.py` - Update to use the centralized OAuth utilities
- [ ] `apps/seo_manager/views_analytics.py` (if this file exists)

## Migration Steps for Each File

For each file, follow these steps:

1. Import the centralized OAuth utilities:
   ```python
   from apps.seo_manager.oauth_utils import get_credentials, get_analytics_service, get_search_console_service, get_ads_service
   ```

2. Replace credential creation code with calls to the centralized utilities:
   ```python
   # Old code
   credentials = Credentials(
       token=credentials_dict.get('access_token'),
       refresh_token=credentials_dict.get('refresh_token'),
       token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
       client_id=credentials_dict.get('client_id'),
       client_secret=credentials_dict.get('client_secret'),
       scopes=['https://www.googleapis.com/auth/analytics.readonly']
   )
   
   # New code
   credentials = get_credentials(credentials_dict, service_type='ga')
   ```

3. Replace service creation code with calls to the centralized utilities:
   ```python
   # Old code
   service = build('searchconsole', 'v1', credentials=credentials)
   
   # New code
   service = get_search_console_service(credentials)
   ```

## Testing

After updating each file, test the functionality to ensure it works correctly:

1. Test with file-based credentials:
   - Set `GOOGLE_OAUTH_USE_ENV=False` in your `.env` file
   - Ensure the JSON files are correctly configured

2. Test with environment variable-based credentials:
   - Set `GOOGLE_OAUTH_USE_ENV=True` in your `.env` file
   - Ensure the environment variables are correctly set

3. Test with both readonly and full access scopes for Google Analytics:
   - Verify that both scopes are included in the OAuth flow
   - Verify that the application can access Google Analytics data

## Conclusion

This migration will standardize the OAuth implementation across the codebase, making it easier to maintain and update in the future. It will also ensure that the application is correctly requesting both readonly and full access scopes for Google Analytics, which will support future functionality for editing analytics data.
