# Multi-Tenancy Tool Migration Checklist

## Background
We're migrating to a multi-tenancy architecture, which requires modifying tools to not accept `client_id` directly, but instead receive specific client attributes that they need to operate. This avoids potential client security issues in a multi-tenant environment.

## Tools to Modify

### 1. ClientProfileTool ✅ DONE
- **File**: `apps/agents/tools/client_profile_tool/client_profile_tool.py`
- **Current Input**: `client_id: int`
- **New Input**: 
  - `website_url: str`
  - `client_name: str` (for logging)
- **Changes**:
  - Completely removed direct Client model dependency
  - Removed database saving functionality (moved to view level)
  - Removed client_id parameter
  - Added client_name for better context in logs
  - Returns distilled website content for saving at view level
  - Returns HTML-formatted profile for convenience

### 2. GoogleAnalyticsTool ✅ DONE
- **File**: `apps/agents/tools/google_analytics_tool/google_analytics_tool.py`
- **Current Input**: `start_date: str, end_date: str, client_id: int`
- **New Input**:
  - `start_date: str`
  - `end_date: str`
  - `analytics_property_id: str`
  - `analytics_credentials: Dict[str, Any]`
- **Changes**:
  - Removed dependency on Client model
  - Directly creates credentials from provided dictionary
  - Made client_id optional and only for reference
  - Includes property_id in return value for better traceability

### 3. GoogleOverviewTool ✅ DONE
- **File**: `apps/agents/tools/google_overview_tool/google_overview_tool.py`
- **Current Input**: `client_id: int, days_ago: int`
- **New Input**:
  - `days_ago: int`
  - `analytics_property_id: str`
  - `analytics_credentials: Dict[str, Any]`
  - `search_console_property_url: str`
  - `search_console_credentials: Dict[str, Any]`
- **Changes**:
  - Removed dependency on Client model
  - Directly creates credentials objects from provided dictionaries
  - Creates both analytics and search console services directly
  - Added more explicit validation for required attributes
  - Made client_id optional and only for reference
  - Improved return value structure with more information
  - Updated to use GenericGoogleSearchConsoleTool for Search Console API calls

### 4. GoogleReportTool ✅ DONE
- **File**: `apps/agents/tools/google_report_tool/google_report_tool.py`
- **Current Input**: `start_date: str, end_date: str, client_id: int`
- **New Input**:
  - `start_date: str`
  - `end_date: str`
  - `analytics_property_id: str`
  - `analytics_credentials: dict` (must include `ga_client_id`, `client_secret`, `refresh_token`)
  - `search_console_property_url: str`
  - `search_console_credentials: dict` (must include `sc_client_id`, `client_secret`, `refresh_token`)
- **Changes**:
  - Removed dependency on Client model
  - Removed direct database queries and model method calls
  - Added methods for creating services directly from credentials dictionaries
  - Added explicit validation for required credential fields
  - Made client_id optional and only for reference
  - Updated the returned JSON with additional context
  - Improved error handling with more specific error messages
  - Added proper credential refresh logic
  - Uses correct field names in credentials (`ga_client_id` for Analytics, `sc_client_id` for Search Console, with shared `client_secret` and `refresh_token` fields)

### 5. GoogleRankingsTool ✅ DONE
- **File**: `apps/agents/tools/google_report_tool/google_rankings_tool.py`
- **Current Input**: `start_date: str, end_date: str, client_id: int`
- **New Input**:
  - `start_date: Optional[str]` (if None, uses last 12 months)
  - `end_date: Optional[str]` (if None, uses last 12 months)
  - `search_console_property_url: str`
  - `search_console_credentials: dict` (must include `sc_client_id`, `client_secret`, `refresh_token`)
- **Changes**:
  - **Fully removed** client_id parameter to adhere to multi-tenancy pattern
  - **Removed all database operations** from the tool (moved to view and command layers)
  - Made the tool stateless, only fetching data and returning it to the caller
  - Added enhanced data structure in the return value with period information
  - Made start_date and end_date optional to support backfill use cases
  - Improved error handling with specific error messages
  - Added proper credential refresh logic
  - Changed return type to JSON string for consistency with other tools
  - Added detailed information in the response about fetched periods and data

### 6. GenericGoogleAnalyticsTool ✅ DONE
- **File**: `apps/agents/tools/google_analytics_tool/generic_google_analytics_tool.py`
- **Current Input**: `client_id: int` and other parameters
- **New Input**:
  - `analytics_property_id: str`
  - `analytics_credentials: dict`
  - Other tool-specific parameters depending on the function
- **Changes**:
  - Removed direct Client model dependency
  - Added validation for required credential fields
  - Implemented token refresh logic using google.auth.transport.requests
  - Enhanced error handling with specific error messages
  - Made client_id optional and only used for reference/logging
  - Updated return structure to include property_id for better traceability
  - Added more detailed logging for troubleshooting

### 7. GenericGoogleSearchConsoleTool ✅ DONE
- **File**: `apps/agents/tools/google_search_console_tool/generic_google_search_console_tool.py`
- **Current Input**: `client_id: int` and other parameters
- **New Input**:
  - `search_console_property_url: str`
  - `search_console_credentials: dict`
  - Other tool-specific parameters (dimensions, filters, etc.)
- **Changes**:
  - Removed dependency on Client model
  - Updated schema to use explicit parameters instead of **kwargs
  - Changed return type to JSON string to match other tools
  - Added detailed validation of credentials and parameters
  - Implemented token refresh logic
  - Enhanced error handling with specific error messages
  - Made client_id optional and only for reference
  - Used sc_client_id field (instead of client_id) for credential validation
  - Used proper inheritance from local BaseTool class
  - Improved logging for better debugging

### 8. SEOAuditTool ✅ ALREADY COMPLIANT
- **File**: `apps/agents/tools/seo_audit_tool/seo_audit_tool.py`
- **Note**: This tool is already designed in a client-agnostic way, using only the website URL and does not depend on client_id. It can serve as a reference model for other tools.

## Views to Update

### 1. Client Views
- **File**: `apps/seo_manager/views/client_views.py`
- **Functions**:
  - `generate_magic_profile`
  - Other functions that call these tools

### 2. Analytics Views
- **File**: `apps/seo_manager/views/analytics_views.py`
- **Functions**: Functions that use Google Analytics tools

### 3. Search Console Views
- **File**: `apps/seo_manager/views/search_console_views.py`
- **Functions**: Functions that use Search Console tools

### 4. Tool Test Views
- **File**: `apps/agents/views_tools.py`
- **Functions**: `test_tool` function and similar functions

## JavaScript Files to Update

### 1. Client Detail JavaScript
- **File**: `apps/seo_manager/static/seo_manager/js/client_detail.js`
- **Usage**: Functions making AJAX calls to tool endpoints

### 2. Meta Tags Dashboard
- **File**: `apps/seo_manager/templates/seo_manager/meta_tags/meta_tags_dashboard.html`
- **Usage**: JavaScript functions that pass client_id

## Command Files to Update

### 1. Backfill Rankings Command
- **File**: `apps/seo_manager/management/commands/backfill_rankings.py`
- **Usage**: Calls tools directly with client.id

## Implementation Strategy

1. For each tool:
   - Update the schema class to remove `client_id` and add needed attributes
   - Update the `_run()` method to work with these attributes
   - Remove any direct `Client.objects.get(id=client_id)` calls
   
2. For each view:
   - Obtain the client using the `client_id` from the request
   - Extract needed attributes from the client model
   - Pass these attributes to the tool instead of just the `client_id`

3. For JavaScript:
   - Update AJAX calls to include required client attributes instead of just the client_id
   - These attributes will be provided by the server-side template rendering

4. For commands:
   - Update to extract and pass required attributes

## Best Practices for Credential Handling

When implementing multi-tenancy in tools that require credentials (like Google Analytics or Search Console tools), follow these practices:

### 1. Credential Validation

Always validate that all required credential fields are present before attempting to use them:

```python
# Example credential validation for Google Analytics
ga_required_fields = ['ga_client_id', 'client_secret', 'refresh_token']
ga_missing_fields = [field for field in ga_required_fields if field not in analytics_credentials]
if ga_missing_fields:
    missing_fields_str = ', '.join(ga_missing_fields)
    logger.error(f"Missing required Google Analytics credential fields: {missing_fields_str}")
    raise ValueError(f"Incomplete Google Analytics credentials. Missing: {missing_fields_str}")

# Example credential validation for Search Console
sc_required_fields = ['sc_client_id', 'client_secret', 'refresh_token']
sc_missing_fields = [field for field in sc_required_fields if field not in search_console_credentials]
if sc_missing_fields:
    missing_fields_str = ', '.join(sc_missing_fields)
    logger.error(f"Missing required Search Console credential fields: {missing_fields_str}")
    raise ValueError(f"Incomplete Search Console credentials. Missing: {missing_fields_str}")
```

### 2. Token Refresh Logic

Implement token refresh logic to handle expired access tokens:

```python
# Example token refresh implementation for Google Analytics
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Create credentials object
creds = Credentials(
    token=credentials.get('access_token'),
    refresh_token=credentials.get('refresh_token'),
    token_uri=credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
    client_id=credentials.get('ga_client_id'),
    client_secret=credentials.get('client_secret'),
    scopes=credentials.get('scopes', ['https://www.googleapis.com/auth/analytics.readonly'])
)

# Example for Search Console
# sc_creds = Credentials(
#     token=credentials.get('access_token'),
#     refresh_token=credentials.get('refresh_token'),
#     token_uri=credentials.get('token_uri', 'https://oauth2.googleapis.com/token'),
#     client_id=credentials.get('sc_client_id'),
#     client_secret=credentials.get('client_secret'),
#     scopes=credentials.get('scopes', ['https://www.googleapis.com/auth/webmasters.readonly'])
# )

# Try to refresh token if needed
if creds.refresh_token:
    try:
        logger.debug("Attempting to refresh token")
        request = Request()
        creds.refresh(request)
        logger.debug("Successfully refreshed token")
    except Exception as refresh_error:
        error_message = str(refresh_error)
        logger.error(f"Failed to refresh token: {error_message}")
        if "invalid_grant" in error_message.lower():
            raise ValueError("Credentials have expired or are invalid. Please reconnect the account.")
```

### 3. Enhanced Error Handling

Provide specific error messages based on the type of error encountered:

```python
# Example error handling in the main try/except block
try:
    # Tool logic here
except Exception as e:
    logger.error(f"Error in Tool: {str(e)}")
    logger.exception(e)  # Log full error details
    
    # Create detailed error message based on exception content
    error_message = str(e)
    detailed_message = "Failed to execute tool"
    
    if "credentials" in error_message.lower() or "authentication" in error_message.lower() or "401" in error_message:
        detailed_message = "Authentication failed. Please check your credentials."
        if "expired" in error_message.lower() or "invalid_grant" in error_message.lower():
            detailed_message = "Credentials have expired. Please reconnect your accounts."
    elif "quota" in error_message.lower() or "rate limit" in error_message.lower() or "429" in error_message:
        detailed_message = "API quota exceeded. Please try again later."
    elif "permission" in error_message.lower() or "403" in error_message:
        detailed_message = "Permission denied. Ensure you have the correct access permissions."
    
    return {
        'success': False,
        'error': detailed_message,
        'error_details': str(e)
    }
```

### 4. Debug Logging

Add detailed logging to track credential handling and service creation:

```python
# Example debug logging for credential handling
logger.debug(f"Creating service with property_id: {property_id}")
logger.debug(f"Credentials available fields: {', '.join(credentials.keys())}")
```

## Service Initialization Patterns

When creating service clients in multi-tenant tools, follow these patterns:

### 1. Isolate Service Creation in Try/Except Blocks

Wrap each service creation in its own try/except block for better error isolation:

```python
# Example of isolated service creation
try:
    # Create Analytics client
    analytics_client = BetaAnalyticsDataClient(credentials=analytics_creds)
    logger.debug("Successfully created Analytics client")
except Exception as e:
    logger.error(f"Failed to create Analytics client: {str(e)}")
    raise ValueError(f"Failed to initialize Analytics: {str(e)}")

try:
    # Create Search Console client
    search_console_client = build('searchconsole', 'v1', credentials=sc_creds)
    logger.debug("Successfully created Search Console client")
except Exception as e:
    logger.error(f"Failed to create Search Console client: {str(e)}")
    raise ValueError(f"Failed to initialize Search Console: {str(e)}")
```

### 2. Validate Service Initialization

Always verify that services were created successfully before proceeding:

```python
if not all([analytics_client, search_console_client, analytics_property_id, search_console_property_url]):
    raise ValueError("Failed to initialize required services")
```

## Return Value Standards

Ensure consistent return value patterns across all tools:

### 1. Success Response Structure

```python
return {
    'success': True,
    'data': {
        # Tool-specific data
    },
    # Include relevant properties for reference
    'analytics_property_id': analytics_property_id,
    'start_date': start_date,
    'end_date': end_date
}
```

### 2. Error Response Structure

```python
return {
    'success': False,
    'error': detailed_message,  # User-friendly error message
    'error_details': str(e)     # Technical details for debugging
}
```

### 3. Remove Client ID from Returns

When returning results, remove `client_id` if it's not needed:

```python
# Before
return {
    'success': True,
    'data': data,
    'client_id': client_id  # Remove this
}

# After
return {
    'success': True,
    'data': data
    # client_id is removed
}
```

## Type Handling for API Parameters

When working with APIs that expect specific data types:

1. Always convert numeric values to strings for APIs that expect string parameters:

```python
# If analytics_property_id is received as an integer, convert to string
if analytics_property_id is not None and not isinstance(analytics_property_id, str):
    analytics_property_id = str(analytics_property_id)
```

2. Ensure client_id is completely removed from inputs when not needed:

```python
# Remove client_id from inputs if present
if 'client_id' in serialized_inputs:
    del serialized_inputs['client_id']
```

## Testing Multi-Tenant Tools

1. Test each modified tool independently
2. Test views that call these tools
3. Verify JavaScript functionality
4. Test commands that use these tools 
5. Test specific error cases:
   - Missing credential fields
   - Expired credentials
   - Invalid property IDs
   - Permission issues 

## Modifying Views for Multi-Tenancy

When updating views to work with multi-tenant tools, follow these patterns:

### 1. Extract Client Attributes Instead of Passing client_id

```python
# Before
def some_view(request, client_id):
    tool = GoogleAnalyticsTool()
    results = tool.run(client_id=client_id)
    return JsonResponse(results)

# After
def some_view(request, client_id):
    try:
        # Get the client
        client = Client.objects.get(id=client_id)
        
        # Extract needed credentials
        analytics_credentials = get_client_attributes(client, 'analytics_credentials')
        
        # Get the property ID
        analytics_property_id = client.googleanalyticscredentials.property_id
        
        # Run the tool with extracted attributes
        tool = GoogleAnalyticsTool()
        results = tool.run(
            analytics_property_id=analytics_property_id,
            analytics_credentials=analytics_credentials
        )
        
        return JsonResponse(results)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
```

### 2. Use Helper Functions for Attribute Extraction

Create reusable functions to extract client attributes:

```python
def get_client_attributes(client, attribute_type=None):
    """
    Extract client attributes needed for tools while respecting the org context.
    """
    attributes = {}
    
    if attribute_type == 'analytics_credentials' or attribute_type is None:
        # Extract Google Analytics credentials
        try:
            ga_creds = client.googleanalyticscredentials
            if ga_creds:
                attributes['analytics_credentials'] = get_safe_model_attributes(ga_creds)
                attributes['analytics_property_id'] = ga_creds.property_id
        except ObjectDoesNotExist:
            pass
    
    if attribute_type == 'search_console_credentials' or attribute_type is None:
        # Extract Search Console credentials
        try:
            sc_creds = client.googlesearchconsolecredentials
            if sc_creds:
                attributes['search_console_credentials'] = get_safe_model_attributes(sc_creds)
                attributes['search_console_property_url'] = sc_creds.property_url
        except ObjectDoesNotExist:
            pass
    
    return attributes
```

### 3. Test Tool Endpoint Pattern

For tool testing endpoints, follow this pattern:

```python
@login_required
def test_tool(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=400)
    
    try:
        # Parse inputs
        data = json.loads(request.body)
        tool_name = data.get('tool_name')
        inputs = data.get('inputs', {})
        client_id = data.get('client_id')
        
        # Get client attributes if client_id is provided
        client_attributes = {}
        if client_id:
            client = Client.objects.get(id=client_id)
            client_attributes = get_client_attributes(client)
        
        # Add client attributes to inputs
        inputs.update(client_attributes)
        
        # Make sure complex objects are properly serialized
        serialized_inputs = {}
        for key, value in inputs.items():
            # Skip client_id as it's not needed by the tools directly
            if key == 'client_id':
                continue
                
            # Convert non-string values to strings if needed
            if key == 'analytics_property_id' and value is not None and not isinstance(value, str):
                serialized_inputs[key] = str(value)
            else:
                serialized_inputs[key] = value
        
        # Run the tool
        tool_result = run_tool.delay(tool_name, serialized_inputs)
        return JsonResponse({'task_id': tool_result.id})
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```

## Common Issues and Fixes During Migration

When migrating tools to multi-tenancy, watch for these common issues:

### 1. Type Mismatches

**Issue**: APIs often expect specific types (e.g., Google Analytics API expects string IDs, but they may be stored as integers in the database).

**Fix**: Always ensure proper type conversion before passing values to APIs:
```python
# Convert property_id to string if it's not already
if property_id is not None and not isinstance(property_id, str):
    property_id = str(property_id)
```

### 2. Missing Credential Fields

**Issue**: When directly passing credential objects, some required fields might be missing.

**Fix**: Validate all required fields before using credentials and provide clear error messages:
```python
required_fields = ['access_token', 'refresh_token', 'ga_client_id', 'client_secret']
missing_fields = [field for field in required_fields if not credentials.get(field)]
if missing_fields:
    raise ValueError(f"Missing required credential fields: {', '.join(missing_fields)}")
```

### 3. Expired Tokens

**Issue**: Access tokens expire and need refreshing.

**Fix**: Implement token refresh logic and provide clear error messages:
```python
if creds.refresh_token:
    try:
        request = Request()
        creds.refresh(request)
    except Exception as e:
        if 'invalid_grant' in str(e).lower():
            raise ValueError("Credentials have expired. Please reconnect your account.")
```

### 4. Serialization of Complex Objects

**Issue**: Complex objects might not serialize correctly when passed to Celery tasks.

**Fix**: Ensure proper serialization of all inputs:
```python
# Properly serialize complex objects
for key, value in inputs.items():
    if isinstance(value, dict):
        serialized_inputs[key] = json.dumps(value)
    else:
        serialized_inputs[key] = value
```

### 5. Backward Compatibility

**Issue**: During migration, some code might still expect `