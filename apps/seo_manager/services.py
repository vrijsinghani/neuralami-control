from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request  # Add this import
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
  DateRange,
  Dimension,
  Metric,
  RunReportRequest,
)

def get_analytics_service(ga_credentials, request):
  print("Entering get_analytics_service")
  try:
      print("GA Credentials:", ga_credentials)
      print("User Email:", ga_credentials.user_email)
      credentials = Credentials(
          token=ga_credentials.access_token,
          refresh_token=ga_credentials.refresh_token,
          token_uri=ga_credentials.token_uri,
          client_id=ga_credentials.ga_client_id,
          client_secret=ga_credentials.client_secret,
          scopes=ga_credentials.scopes
      )
      print("Credentials created, refreshing...")
      credentials.refresh(Request())
      print("Credentials refreshed successfully.")
      client = BetaAnalyticsDataClient(credentials=credentials)
      print("Analytics client created successfully, client:", client)
      return client
  except RefreshError as e:
      print(f"Error refreshing credentials: {e}")
      raise e
  finally:
      print("Exiting get_analytics_service")

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