from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
  DateRange,
  Dimension,
  Metric,
  RunReportRequest,
)

# Import centralized OAuth utilities
from apps.seo_manager.oauth_utils import get_analytics_service as get_analytics_service_util, get_credentials
import logging

logger = logging.getLogger(__name__)

def get_analytics_service(ga_credentials, request):
  logger.info("Entering get_analytics_service")
  try:
      logger.info(f"GA Credentials: {ga_credentials}, User Email: {ga_credentials.user_email}")

      # Create a credentials dictionary to pass to the centralized utility
      credentials_dict = {
          'access_token': ga_credentials.access_token,
          'refresh_token': ga_credentials.refresh_token,
          'token_uri': ga_credentials.token_uri,
          'ga_client_id': ga_credentials.ga_client_id,
          'client_secret': ga_credentials.client_secret,
          'scopes': ga_credentials.scopes
      }

      # Use the centralized utility to create the analytics service
      client = get_analytics_service_util(get_credentials(credentials_dict, service_type='ga'))
      logger.info("Analytics client created successfully")
      return client
  except RefreshError as e:
      logger.error(f"Error refreshing credentials: {e}")
      raise e
  finally:
      logger.info("Exiting get_analytics_service")

def get_analytics_data(client, property_id, start_date, end_date):
  print("Entering get_analytics_data")
  print(f"Fetching analytics data for Property ID: {property_id}, Start Date: {start_date}, End Date: {end_date}")

  try:
      request = RunReportRequest(
          property=f"properties/{property_id}",
          dimensions=[Dimension(name="date")],
          metrics=[
              Metric(name="sessions"),
              Metric(name="screenPageViews")  # Changed from "pageviews" to "screenPageViews"
          ],
          date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
      )
      response = client.run_report(request)
      print("Analytics data fetched successfully.")
      return response
  except Exception as e:
      print(f"Error fetching analytics data: {e}")
      raise e
  finally:
      print("Exiting get_analytics_data")