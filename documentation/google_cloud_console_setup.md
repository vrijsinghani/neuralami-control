# Google Cloud Console Setup for OAuth Scopes

This document provides instructions for setting up your Google Cloud Console project to support the OAuth scopes required by the application.

## Required OAuth Scopes

The application requires the following OAuth scopes:

- **Google Analytics**:
  - `https://www.googleapis.com/auth/analytics.readonly` (Read-only access to Google Analytics data)
  - `https://www.googleapis.com/auth/analytics` (Full access to Google Analytics data)

- **Google Search Console**:
  - `https://www.googleapis.com/auth/webmasters.readonly` (Read-only access to Search Console data)

- **Google Ads**:
  - `https://www.googleapis.com/auth/adwords` (Access to Google Ads data)

- **User Information**:
  - `openid` (OpenID Connect)
  - `https://www.googleapis.com/auth/userinfo.email` (View user email)
  - `https://www.googleapis.com/auth/userinfo.profile` (View user profile)

## Setting Up OAuth Scopes in Google Cloud Console

1. **Go to the Google Cloud Console**:
   - Navigate to [https://console.cloud.google.com/](https://console.cloud.google.com/)
   - Select your project

2. **Navigate to OAuth Consent Screen**:
   - Go to "APIs & Services" > "OAuth consent screen"
   - If you haven't set up the consent screen yet, select the appropriate user type (Internal or External) and fill in the required information

3. **Add Scopes**:
   - Scroll down to the "Scopes" section
   - Click "Add or Remove Scopes"
   - Add the following scopes:
     - `https://www.googleapis.com/auth/analytics.readonly`
     - `https://www.googleapis.com/auth/analytics`
     - `https://www.googleapis.com/auth/webmasters.readonly`
     - `https://www.googleapis.com/auth/adwords`
     - `openid`
     - `https://www.googleapis.com/auth/userinfo.email`
     - `https://www.googleapis.com/auth/userinfo.profile`
   - Click "Update"

4. **Save Changes**:
   - Click "Save and Continue" to save your changes

5. **Enable APIs**:
   - Go to "APIs & Services" > "Library"
   - Search for and enable the following APIs:
     - Google Analytics API
     - Google Analytics Data API
     - Google Analytics Admin API
     - Search Console API
     - Google Ads API

## Verifying OAuth Scopes

After setting up the OAuth scopes, you can verify that they are correctly configured by:

1. **Checking the OAuth Consent Screen**:
   - Go to "APIs & Services" > "OAuth consent screen"
   - Verify that all required scopes are listed under "Scopes"

2. **Testing the OAuth Flow**:
   - Run the test script: `python manage.py shell < scripts/test_oauth_reauthorization.py`
   - Verify that both analytics scopes are included in the OAuth flow

3. **Reauthorizing Your Google Accounts**:
   - Go to the client integrations page
   - Disconnect and reconnect your Google Analytics, Search Console, and Ads accounts
   - Verify that the correct scopes are requested during the authorization process

## Troubleshooting

If you encounter issues with OAuth scopes:

1. **Scope Not Granted**:
   - If a scope is not granted during authorization, check that it is enabled in your Google Cloud Console project
   - Verify that the scope is included in the OAuth consent screen

2. **Scope Change Warning**:
   - If you see a "Scope has changed" warning, it means that the scopes requested by your application do not match the scopes configured in your Google Cloud Console project
   - Update your Google Cloud Console project to include all required scopes

3. **Verification Required**:
   - If your project is in External user type and requires verification, you may need to submit your project for verification to use certain scopes
   - Follow the verification process in the Google Cloud Console
