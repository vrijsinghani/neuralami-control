from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q
from django.db.models import Avg
import logging
from dateutil.relativedelta import relativedelta
import json
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from googleapiclient.discovery import build
import google.auth.transport.requests
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from django.urls import reverse
from django.conf import settings
from .exceptions import AuthError

logger = logging.getLogger(__name__)

class ClientGroup(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')

    def __str__(self):
        return self.name

class Client(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_hold', 'On Hold'),
    ]

    name = models.CharField(max_length=100)
    website_url = models.URLField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    group = models.ForeignKey(ClientGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='clients')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business_objectives = models.JSONField(default=list, blank=True)
    target_audience = models.TextField(blank=True, null=True)
    # New field
    client_profile = models.TextField(
        help_text="Detailed 300-500 word profile of the client's business, goals, and SEO strategy",
        blank=True
    )
    distilled_website = models.TextField(
        help_text="Distilled version of the client's website content for SEO purposes",
        blank=True
    )
    distilled_website_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The last time the distilled website content was modified or created"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.business_objectives is None:
            self.business_objectives = []

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self.pk:
            old_client = Client.objects.get(pk=self.pk)
            if old_client.distilled_website != self.distilled_website:
                self.distilled_website_date = timezone.now()
        else:
            if self.distilled_website:
                self.distilled_website_date = timezone.now()
        super().save(*args, **kwargs)
        
    def get_keyword_rankings_summary(self):
        """Get summary of current keyword rankings"""
        latest_rankings = KeywordRankingHistory.objects.filter(
            client=self,
            keyword__isnull=False,  # Only targeted keywords
            date=KeywordRankingHistory.objects.filter(
                client=self,
                keyword__isnull=False
            ).values('date').order_by('-date').first()['date']
        ).select_related('keyword')

        return {
            'total_keywords': latest_rankings.count(),
            'avg_position': latest_rankings.aggregate(
                Avg('average_position')
            )['average_position__avg'],
            'rankings': latest_rankings
        }

class SEOData(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='seo_data')
    date = models.DateField()
    traffic = models.IntegerField()
    keywords = models.IntegerField()
    rankings = models.JSONField()  # Store rankings as JSON

    class Meta:
        unique_together = ['client', 'date']

class AIProvider(models.Model):
    name = models.CharField(max_length=100)
    api_key = models.CharField(max_length=255)
    model = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class OAuthManager:
    """Manages OAuth operations for Google services"""
    
    @staticmethod
    def create_oauth_flow(request, state_key=None):
        """Create OAuth flow for Google services"""
        logger.info(f"Creating OAuth flow with state key: {state_key}")
        
        # Get the current domain and scheme
        scheme = request.scheme
        domain = request.get_host()
        
        # Use the same redirect URI that's configured in Google Console
        redirect_uri = f'{scheme}://{domain}/google/login/callback/'
        
        logger.info(f"Using redirect URI: {redirect_uri}")
        
        try:
            flow = Flow.from_client_secrets_file(
                settings.GOOGLE_CLIENT_SECRETS_FILE,
                scopes=[
                    'https://www.googleapis.com/auth/analytics.readonly',
                    'https://www.googleapis.com/auth/webmasters.readonly',
                    'openid',
                    'https://www.googleapis.com/auth/userinfo.email',
                    'https://www.googleapis.com/auth/userinfo.profile'
                ],
                state=state_key,
                redirect_uri=redirect_uri
            )
            
            # Store the redirect URI in session
            request.session['oauth_redirect_uri'] = redirect_uri
            request.session.modified = True  # Ensure session is saved
            
            logger.info(f"OAuth flow created successfully with redirect URI: {redirect_uri}")
            return flow
            
        except Exception as e:
            logger.error(f"Error creating OAuth flow: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def handle_oauth_callback(request, code, state):
        """Handle OAuth callback and return credentials"""
        try:
            # Get the stored redirect URI from session
            redirect_uri = request.session.get('oauth_redirect_uri')
            if not redirect_uri:
                raise AuthError("Missing redirect URI in session")
            
            flow = OAuthManager.create_oauth_flow(request, state_key=state)
            
            # Ensure the redirect URI matches
            flow.redirect_uri = redirect_uri
            
            # Fetch token with explicit redirect URI
            credentials = flow.fetch_token(
                code=code,
                redirect_uri=redirect_uri
            )
            
            # Clean up session
            request.session.pop('oauth_redirect_uri', None)
            
            return credentials
            
        except Exception as e:
            logger.error(f"OAuth callback error: {str(e)}")
            raise AuthError("Failed to complete OAuth flow")
    
    @staticmethod
    def credentials_to_dict(credentials):
        """Convert OAuth credentials to dictionary for session storage"""
        if hasattr(credentials, 'token'):
            # Handle Google OAuth2Credentials
            return {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
        else:
            # Handle OAuth2Token
            return {
                'token': credentials['access_token'],
                'refresh_token': credentials.get('refresh_token'),
                'token_uri': 'https://oauth2.googleapis.com/token',  # Standard Google OAuth2 token endpoint
                'client_id': credentials.get('client_id'),
                'client_secret': credentials.get('client_secret'),
                'scopes': credentials.get('scope', '').split(' ') if isinstance(credentials.get('scope'), str) else credentials.get('scope', [])
            }

class GoogleAnalyticsCredentials(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='ga_credentials')
    view_id = models.CharField(max_length=100, blank=True, null=True)
    access_token = models.TextField(blank=True, null=True)
    refresh_token = models.TextField(blank=True, null=True)
    token_uri = models.URLField(blank=True, null=True)
    ga_client_id = models.CharField(max_length=100, blank=True, null=True)
    client_secret = models.CharField(max_length=100, blank=True, null=True)
    use_service_account = models.BooleanField(default=False)
    service_account_json = models.TextField(blank=True, null=True)
    user_email = models.EmailField()
    scopes = models.JSONField(default=list)

    def __str__(self):
        return f"GA Credentials for {self.client.name}"

    @property
    def required_scopes(self):
        return ['https://www.googleapis.com/auth/analytics.readonly']

    def get_credentials(self):
        """Returns refreshed Google Analytics credentials"""
        try:
            if self.use_service_account and self.service_account_json:
                service_account_info = json.loads(self.service_account_json)
                return service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/analytics.readonly']
                )

            # For OAuth, create credentials from stored values
            if not all([self.refresh_token, self.token_uri, self.ga_client_id, self.client_secret]):
                logger.error("Missing required OAuth fields")
                return None

            credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri=self.token_uri,
                client_id=self.ga_client_id,
                client_secret=self.client_secret,
                scopes=['https://www.googleapis.com/auth/analytics.readonly']
            )

            # Always try to refresh if we have a refresh token
            if credentials.refresh_token:
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
                self.access_token = credentials.token
                self.save(update_fields=['access_token'])
                logger.info(f"Refreshed access token for {self.client.name}")

            return credentials

        except Exception as e:
            logger.error(f"Error getting credentials: {str(e)}")
            if 'invalid_grant' in str(e):
                self.access_token = None
                self.refresh_token = None
                self.save(update_fields=['access_token', 'refresh_token'])
                raise AuthError("OAuth credentials expired. Please re-authenticate.")
            return None

    def get_property_id(self):
        """Get the clean property ID without 'properties/' prefix"""
        if self.view_id:
            return self.view_id.replace('properties/', '')
        return None

    def get_service(self):
        """Returns an authenticated Analytics service"""
        try:
            credentials = self.get_credentials()
            if not credentials:
                return None

            return BetaAnalyticsDataClient(credentials=credentials)

        except Exception as e:
            logger.error(f"Error creating Analytics service: {str(e)}")
            return None

    def refresh_credentials(self):
        """Handle token refresh according to OAuth 2.0 spec"""
        try:
            if not self.refresh_token:
                raise AuthError("No refresh token available. Re-authorization required.")

            credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri=self.token_uri,
                client_id=self.ga_client_id,
                client_secret=self.client_secret,
                scopes=self.required_scopes
            )

            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
            
            # Update stored credentials
            self.access_token = credentials.token
            self.save(update_fields=['access_token'])
            
            return True
            
        except Exception as e:
            if 'invalid_grant' in str(e):
                # Clear credentials if refresh token is invalid
                self.access_token = None
                self.refresh_token = None
                self.save(update_fields=['access_token', 'refresh_token'])
                raise AuthError("Refresh token expired or revoked. Re-authorization required.")
            raise

    def save_oauth_credentials(self, credentials):
        """Save OAuth credentials from flow"""
        try:
            # Log the credentials we're trying to save
            logger.info(f"""
            Attempting to save OAuth credentials for {self.client.name}:
            Token: {'Present' if credentials.token else 'Missing'}
            Refresh Token: {'Present' if credentials.refresh_token else 'Missing'}
            Token URI: {credentials.token_uri if credentials.token_uri else 'Missing'}
            Client ID: {'Present' if credentials.client_id else 'Missing'}
            Client Secret: {'Present' if credentials.client_secret else 'Missing'}
            """)

            # Save all fields
            self.access_token = credentials.token
            self.refresh_token = credentials.refresh_token
            self.token_uri = credentials.token_uri
            self.ga_client_id = credentials.client_id
            self.client_secret = credentials.client_secret
            self.scopes = credentials.scopes
            self.use_service_account = False
            
            self.save()
            
            # Verify saved credentials
            saved_creds = self.get_credentials()
            if not saved_creds:
                raise ValueError("Failed to verify saved credentials")

            logger.info(f"Successfully saved and verified OAuth credentials for {self.client.name}")

        except Exception as e:
            logger.error(f"Error saving OAuth credentials: {str(e)}")
            raise

    def validate_credentials(self):
        """Validate stored credentials"""
        try:
            if not self.access_token and not self.refresh_token and not self.service_account_json:
                raise AuthError("No valid credentials found")
                
            credentials = self.get_credentials()
            if not credentials:
                raise AuthError("Failed to get valid credentials")
                
            return True
            
        except Exception as e:
            logger.error(f"Credential validation error: {str(e)}")
            raise AuthError(f"Credential validation failed: {str(e)}")

    def handle_oauth_response(self, credentials_dict):
        """Handle OAuth response and save credentials"""
        try:
            self.access_token = credentials_dict['token']
            self.refresh_token = credentials_dict['refresh_token']
            self.token_uri = credentials_dict['token_uri']
            self.ga_client_id = credentials_dict['client_id']
            self.client_secret = credentials_dict['client_secret']
            self.use_service_account = False
            self.scopes = credentials_dict['scopes']
            self.save()
            
            logger.info(f"Saved GA OAuth credentials for {self.client.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving GA OAuth credentials: {str(e)}", exc_info=True)
            raise AuthError(f"Failed to save credentials: {str(e)}")

    def handle_service_account(self, service_account_json):
        """Handle service account setup"""
        try:
            self.service_account_json = service_account_json
            self.use_service_account = True
            self.access_token = None
            self.refresh_token = None
            self.save()
            
            # Validate the service account works
            credentials = self.get_credentials()
            if not credentials:
                raise AuthError("Invalid service account credentials")
                
            return True
            
        except Exception as e:
            logger.error(f"Service account setup error: {str(e)}")
            raise AuthError(f"Failed to setup service account: {str(e)}")

class SearchConsoleCredentials(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='sc_credentials')
    property_url = models.TextField()
    access_token = models.TextField(blank=True, null=True)
    refresh_token = models.TextField(blank=True, null=True)
    token_uri = models.URLField(blank=True, null=True)
    sc_client_id = models.CharField(max_length=100, blank=True, null=True)
    client_secret = models.CharField(max_length=100, blank=True, null=True)
    service_account_json = models.TextField(blank=True, null=True)
    last_validated = models.DateTimeField(auto_now=True)
    user_email = models.EmailField(blank=True, null=True)

    def __str__(self):
        return f"Search Console Credentials for {self.client.name}"

    def get_credentials(self):
        """Returns refreshed Google OAuth2 credentials"""
        try:
            # Handle service account authentication
            if self.service_account_json:
                service_account_info = json.loads(self.service_account_json)
                return service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/webmasters.readonly']
                )

            # Handle OAuth2 authentication
            if not self.refresh_token:
                raise AuthError("No refresh token available. Reauthorization required.")

            credentials = Credentials(
                token=self.access_token,
                refresh_token=self.refresh_token,
                token_uri=self.token_uri,
                client_id=self.sc_client_id,
                client_secret=self.client_secret,
                scopes=['https://www.googleapis.com/auth/webmasters.readonly']
            )

            # Only refresh if token is expired or missing
            if not self.access_token or not credentials.valid:
                request = google.auth.transport.requests.Request()
                try:
                    credentials.refresh(request)
                    
                    # Update stored credentials
                    self.access_token = credentials.token
                    self.save(update_fields=['access_token'])
                    
                    logger.info(f"Successfully refreshed Search Console OAuth credentials for {self.client.name}")
                except Exception as e:
                    if 'invalid_grant' in str(e):
                        # Clear invalid credentials to force reauthorization
                        self.access_token = None
                        self.refresh_token = None
                        self.save(update_fields=['access_token', 'refresh_token'])
                        raise AuthError("Stored credentials are no longer valid. Please reauthorize Search Console access.")
                    raise

            return credentials

        except Exception as e:
            logger.error(f"Failed to refresh Search Console credentials for {self.client.name}: {str(e)}")
            raise AuthError(f"Failed to get valid Search Console credentials: {str(e)}")

    def get_service(self):
        """Returns an authenticated Search Console service"""
        try:
            credentials = self.get_credentials()
            if not credentials:
                logger.warning(f"No valid credentials available for {self.client.name}")
                return None
                
            return build('searchconsole', 'v1', credentials=credentials)
        except Exception as e:
            logger.error(f"Error creating Search Console service for {self.client.name}: {str(e)}")
            return None

    def get_property_url(self):
        """Parse and return the correct property URL format"""
        try:
            if isinstance(self.property_url, str):
                if '{' in self.property_url:
                    # Parse JSON-like string
                    data = json.loads(self.property_url.replace("'", '"'))
                    return data.get('url')  # Use get() to safely access 'url'
                return self.property_url
            elif isinstance(self.property_url, dict):
                return self.property_url.get('url')
            return self.property_url
        except Exception as e:
            logger.error(f"Error parsing property URL for {self.client.name}: {str(e)}")
            return None

    def save_oauth_credentials(self, credentials):
        """Save OAuth credentials from flow"""
        creds_dict = OAuthManager.credentials_to_dict(credentials)
        self.access_token = creds_dict['token']
        self.refresh_token = creds_dict['refresh_token']
        self.token_uri = creds_dict['token_uri']
        self.sc_client_id = creds_dict['client_id']
        self.client_secret = creds_dict['client_secret']
        self.save()

    def validate_credentials(self):
        """Validate stored credentials"""
        try:
            if not self.access_token and not self.refresh_token and not self.service_account_json:
                raise AuthError("No valid credentials found")
                
            credentials = self.get_credentials()
            if not credentials:
                raise AuthError("Failed to get valid credentials")
                
            return True
            
        except Exception as e:
            logger.error(f"Search Console credential validation error: {str(e)}")
            raise AuthError(f"Credential validation failed: {str(e)}")

    def handle_oauth_response(self, credentials_dict):
        """Handle OAuth response and save credentials"""
        try:
            self.access_token = credentials_dict['token']
            self.refresh_token = credentials_dict['refresh_token']
            self.token_uri = credentials_dict['token_uri']
            self.sc_client_id = credentials_dict['client_id']
            self.client_secret = credentials_dict['client_secret']
            self.save()
            
            logger.info(f"Saved SC OAuth credentials for {self.client.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving SC OAuth credentials: {str(e)}", exc_info=True)
            raise AuthError(f"Failed to save credentials: {str(e)}")

class SummarizerUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.TextField()
    compressed_content = models.TextField()
    response = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField()
    content_token_size = models.IntegerField()
    content_character_count = models.IntegerField()
    total_input_tokens = models.IntegerField()
    total_output_tokens = models.IntegerField()
    model_used = models.CharField(max_length=100)

class UserActivity(models.Model):
    CATEGORY_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('view', 'View'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('export', 'Export'),
        ('import', 'Import'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.category} - {self.action}"

class TargetedKeyword(models.Model):
    PRIORITY_CHOICES = [
        (1, 'Highest'),
        (2, 'High'),
        (3, 'Medium'),
        (4, 'Low'),
        (5, 'Lowest'),
    ]

    client = models.ForeignKey(
        Client, 
        on_delete=models.CASCADE,
        related_name='targeted_keywords'
    )
    keyword = models.CharField(max_length=255)
    priority = models.IntegerField(
        choices=PRIORITY_CHOICES,
        default=3,
        help_text="Priority level for this keyword"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_monthly_rankings(self, months=12):
        """Get monthly ranking history"""
        end_date = timezone.now().date()
        start_date = end_date - relativedelta(months=months)
        
        # logger.debug(
        #     f"Fetching monthly rankings for keyword '{self.keyword}' (ID: {self.id})"
        #     f"\nDate range: {start_date} to {end_date}"
        # )
        
        rankings = self.ranking_history.filter(
            date__gte=start_date,
            date__lte=end_date
        ).order_by('date')
        
        # logger.debug(f"Found {rankings.count()} ranking records")
        
        # Group by month and get the monthly record
        monthly_data = {}
        for ranking in rankings:
            month_key = ranking.date.strftime('%Y-%m')
            if month_key not in monthly_data:
                data = {
                    'date': ranking.date,
                    'position': float(ranking.average_position),
                    'impressions': int(ranking.impressions),
                    'clicks': int(ranking.clicks),
                    'ctr': float(ranking.ctr)
                }
                monthly_data[month_key] = data
                # logger.debug(
                #     f"Added data for {month_key}:"
                #     f"\nPosition: {data['position']}"
                #     f"\nImpressions: {data['impressions']}"
                #     f"\nClicks: {data['clicks']}"
                #     f"\nCTR: {data['ctr']}"
                # )
        
        result = [monthly_data[k] for k in sorted(monthly_data.keys())]
        # logger.debug(
        #     f"Returning {len(result)} months of data for {self.keyword}"
        # )
        return result

    def get_ranking_history(self):
        """Get all ranking history entries for this keyword"""
        return KeywordRankingHistory.objects.filter(
            Q(keyword=self) | 
            Q(keyword_text=self.keyword, client=self.client)
        ).order_by('-date')

    @property
    def current_position(self):
        """Get the most recent average position"""
        latest = self.get_ranking_history().first()
        return round(latest.average_position, 1) if latest else None

    def get_position_change(self, months=1):
        """Calculate position change over specified number of months"""
        history = self.get_ranking_history()[:2]  # Get latest two entries
        if len(history) < 2:
            return None
            
        current = history[0].average_position
        previous = history[1].average_position
        
        return round(previous - current, 1)

    @property
    def position_trend(self):
        """Returns trend indicator based on 30-day change"""
        change = self.get_position_change()
        if change is None:
            return 'neutral'
        if change > 0.5:  # Improved by more than 0.5 positions
            return 'up'
        if change < -0.5:  # Declined by more than 0.5 positions
            return 'down'
        return 'neutral'

    class Meta:
        unique_together = ['client', 'keyword']
        ordering = ['priority', 'keyword']

    def __str__(self):
        return f"{self.keyword} ({self.client.name})"

class KeywordRankingHistory(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='keyword_rankings'
    )
    keyword = models.ForeignKey(
        TargetedKeyword,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ranking_history'
    )
    keyword_text = models.CharField(
        max_length=255,
        help_text="Actual keyword text, useful when no TargetedKeyword reference exists"
    )
    date = models.DateField()
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    ctr = models.FloatField(
        verbose_name="Click-Through Rate",
        help_text="Click-through rate as a decimal (e.g., 0.15 for 15%)"
    )
    average_position = models.FloatField()
    
    class Meta:
        unique_together = ['client', 'keyword_text', 'date']
        ordering = ['-date']
        get_latest_by = 'date'
        indexes = [
            models.Index(fields=['-date']),  # Optimize date-based queries
            models.Index(fields=['client', '-date']),  # Optimize client+date queries
        ]

    @classmethod
    def get_rankings_for_period(cls, client, start_date, end_date, keyword=None):
        """Get rankings for a specific period with optimized querying"""
        query = cls.objects.select_related('keyword').filter(
            client=client,
            date__range=[start_date, end_date]
        )

        if keyword:
            query = query.filter(
                Q(keyword=keyword) | Q(keyword_text=keyword.keyword)
            )

        return query.order_by('date')

    def get_position_change(self):
        """Calculate position change from previous entry"""
        if not hasattr(self, '_position_change'):
            previous = KeywordRankingHistory.objects.filter(
                client=self.client,
                keyword_text=self.keyword_text,
                date__lt=self.date
            ).order_by('-date').values('average_position').first()

            self._position_change = (previous['average_position'] - self.average_position) if previous else 0
        return self._position_change

class SEOProject(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='seo_projects'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    implementation_date = models.DateField()
    completion_date = models.DateField(null=True, blank=True)
    targeted_keywords = models.ManyToManyField(
        TargetedKeyword,
        related_name='related_projects'
    )
    documentation_file = models.FileField(
        upload_to='seo_projects/%Y/%m/',
        null=True,
        blank=True
    )
    initial_rankings = models.JSONField(
        default=dict,
        help_text="Snapshot of keyword rankings before project implementation"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('planned', 'Planned'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('on_hold', 'On Hold'),
        ],
        default='planned'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-implementation_date']

    def __str__(self):
        return f"{self.title} - {self.client.name}"



    def _calculate_impressions_change(self, rankings):
        """Calculate the percentage change in impressions before and after implementation"""
        try:
            pre_imp = rankings.filter(
                date__lt=self.implementation_date
            ).aggregate(Avg('impressions'))['impressions__avg'] or 0

            post_imp = rankings.filter(
                date__gte=self.implementation_date
            ).aggregate(Avg('impressions'))['impressions__avg'] or 0

            if pre_imp == 0:
                return 100 if post_imp > 0 else 0
                
            return ((post_imp - pre_imp) / pre_imp) * 100
            
        except Exception as e:
            logger.error(f"Error calculating impressions change: {str(e)}")
            return 0

    def _calculate_clicks_change(self, rankings):
        """Calculate the percentage change in clicks before and after implementation"""
        try:
            pre_clicks = rankings.filter(
                date__lt=self.implementation_date
            ).aggregate(Avg('clicks'))['clicks__avg'] or 0

            post_clicks = rankings.filter(
                date__gte=self.implementation_date
            ).aggregate(Avg('clicks'))['clicks__avg'] or 0

            if pre_clicks == 0:
                return 100 if post_clicks > 0 else 0
                
            return ((post_clicks - pre_clicks) / pre_clicks) * 100
            
        except Exception as e:
            logger.error(f"Error calculating clicks change: {str(e)}")
            return 0

    # Add method to analyze project impact
    def analyze_impact(self):
        implementation_date = self.implementation_date
        pre_period = implementation_date - relativedelta(months=1)
        post_period = implementation_date + relativedelta(months=1)

        results = {}
        for keyword in self.targeted_keywords.all():
            rankings = keyword.ranking_history.filter(
                date__range=[pre_period, post_period]
            ).order_by('date')

            pre_avg = rankings.filter(date__lt=implementation_date).aggregate(
                Avg('average_position'))['average_position__avg']
            post_avg = rankings.filter(date__gte=implementation_date).aggregate(
                Avg('average_position'))['average_position__avg']

            results[keyword.keyword] = {
                'pre_implementation_avg': pre_avg,
                'post_implementation_avg': post_avg,
                'improvement': pre_avg - post_avg if pre_avg and post_avg else None,
                'impressions_change': self._calculate_impressions_change(rankings),
                'clicks_change': self._calculate_clicks_change(rankings)
            }

        return results