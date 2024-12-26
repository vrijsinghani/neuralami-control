import json
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime
import pandas as pd
import logging
import io
import base64
from django.conf import settings
import os
import matplotlib.pyplot as plt
import seaborn as sns

logger = logging.getLogger(__name__)

class SlackMessageFormatter:
    """Format tool outputs and messages for Slack using Block Kit."""
    
    @staticmethod
    def format_field_name(field: str) -> str:
        """Format a field name for display."""
        return field.replace('_', ' ').title()

    @staticmethod
    def _find_table_data(data: Any) -> Optional[List[Dict]]:
        """Find table-like data in the result."""
        if isinstance(data, dict):
            # Check common patterns in our API responses
            if 'analytics_data' in data and isinstance(data['analytics_data'], list):
                return data['analytics_data']
            if 'data' in data and isinstance(data['data'], list):
                return data['data']
            if 'results' in data and isinstance(data['results'], list):
                return data['results']
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            return data
        return None

    @staticmethod
    def _find_time_series_data(data: Any) -> Optional[Tuple[List[str], List[Dict]]]:
        """Find time series data in the result."""
        table_data = SlackMessageFormatter._find_table_data(data)
        if not table_data:
            return None

        # Look for date/time fields
        date_fields = []
        metric_fields = []
        
        # Check first row for field types
        sample = table_data[0]
        for field, value in sample.items():
            field_lower = field.lower()
            # Check if field name suggests it's a date
            if any(date_hint in field_lower for date_hint in ['date', 'time', 'day', 'month', 'year']):
                try:
                    # Verify we can parse the date
                    pd.to_datetime(sample[field])
                    date_fields.append(field)
                except:
                    continue
            # For GA4 data, we know certain fields are metrics
            elif field in ['newUsers', 'totalUsers', 'sessions', 'screenPageViews', 'bounceRate', 'engagedSessions']:
                metric_fields.append(field)
            # Otherwise check if it's numeric
            elif isinstance(value, (int, float)) or (isinstance(value, str) and value.replace('.', '').isdigit()):
                metric_fields.append(field)

        if not date_fields or not metric_fields:
            return None

        return date_fields, metric_fields

    @staticmethod
    def _create_chart(data: List[Dict], date_field: str, metric_fields: List[str]) -> bytes:
        """Create a time series chart and return the bytes."""
        try:
            import seaborn as sns
            logger.info(f"Creating chart with date_field: {date_field}, metrics: {metric_fields}")
            
            df = pd.DataFrame(data)
            df[date_field] = pd.to_datetime(df[date_field])
            df = df.sort_values(date_field)
            
            # Convert metrics to numeric
            for metric in metric_fields:
                if df[metric].dtype == 'object':
                    df[metric] = pd.to_numeric(df[metric].str.replace(',', ''), errors='coerce')
            
            # Set seaborn style
            sns.set_style("whitegrid")
            plt.figure(figsize=(10, 6))
            
            # Create plot using seaborn
            for metric in metric_fields:
                sns.lineplot(data=df, x=date_field, y=metric, marker='o', label=metric)
            
            plt.title('Time Series Analysis')
            plt.xticks(rotation=45)
            plt.tight_layout()
            
            # Save to bytes
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=150)
            plt.close()
            buffer.seek(0)
            return buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Error creating chart: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def format_table(data: List[Dict]) -> List[Dict]:
        """Format data as a Slack section block with fields."""
        if not data:
            return [{"type": "section", "text": {"type": "mrkdwn", "text": "No data available"}}]

        blocks = []
        
        # Add header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Data Summary"
            }
        })

        # Group related fields together
        for row in data:
            text_parts = []
            for key, value in row.items():
                if isinstance(value, (int, float)):
                    formatted_value = f"{value:,}"
                elif isinstance(value, str) and any(date_hint in key.lower() for date_hint in ['date', 'time', 'day']):
                    try:
                        date = pd.to_datetime(value)
                        formatted_value = date.strftime('%Y-%m-%d')
                    except:
                        formatted_value = value
                else:
                    formatted_value = str(value)
                
                text_parts.append(f"*{SlackMessageFormatter.format_field_name(key)}*: {formatted_value}")
            
            # Join all fields with newlines
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(text_parts)
                }
            })
            
            # Add divider between rows
            blocks.append({"type": "divider"})

        if len(data) > 10:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"_Showing 10 of {len(data)} rows_"
                }]
            })

        return blocks

    @staticmethod
    def _format_analytics_data(data: List[Dict]) -> List[Dict]:
        """Special formatter for analytics data."""
        if not data:
            return []
            
        blocks = []
        
        # Add header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Analytics Data Summary"
            }
        })

        # Add context about the data
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "📊 Showing analytics data with all available metrics"
            }]
        })

        blocks.append({"type": "divider"})

        # Convert data to a more readable format
        df = pd.DataFrame(data)
        
        # Create a section for each row of data
        for _, row in df.iterrows():
            # Split fields into two columns
            fields = []
            for col in df.columns:
                value = row[col]
                # Format numbers with commas
                if isinstance(value, (int, float)):
                    if str(value).endswith('.0'):  # Integer values
                        formatted_value = f"{int(value):,}"
                    else:  # Float values
                        formatted_value = f"{value:,.2f}"
                else:
                    formatted_value = str(value)
                
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{SlackMessageFormatter.format_field_name(col)}*\n{formatted_value}"
                })
            
            blocks.append({
                "type": "section",
                "fields": fields
            })
            
            blocks.append({"type": "divider"})

        # If we have numeric columns, add summary statistics
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
        if not numeric_cols.empty:
            blocks.append({
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Summary Statistics"
                }
            })

            for col in numeric_cols:
                col_name = SlackMessageFormatter.format_field_name(col)
                total = df[col].sum()
                avg = df[col].mean()
                
                if str(total).endswith('.0'):  # Integer values
                    total_str = f"{int(total):,}"
                    avg_str = f"{avg:,.1f}"
                else:  # Float values
                    total_str = f"{total:,.2f}"
                    avg_str = f"{avg:,.2f}"

                blocks.append({
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*{col_name}*\n• Total: {total_str}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Statistics*\n• Average: {avg_str}"
                        }
                    ]
                })

        return blocks

    @staticmethod
    def format_tool_result(result: Any) -> Union[str, List[Dict]]:
        """Format a tool result for Slack using blocks where appropriate."""
        try:
            # Parse result if it's a string
            data = json.loads(result) if isinstance(result, str) else result
            logger.info(f"Formatting tool result. Data type: {type(data)}")
            
            # Try to find table data
            table_data = SlackMessageFormatter._find_table_data(data)
            if table_data:
                logger.info(f"Found table data with {len(table_data)} rows")
                blocks = []
                
                # Check if it's time series data first
                time_series_info = SlackMessageFormatter._find_time_series_data(data)
                if time_series_info:
                    date_fields, metric_fields = time_series_info
                    logger.info(f"Found time series data with date fields: {date_fields}, metric fields: {metric_fields}")
                    
                    # Create summary section
                    df = pd.DataFrame(table_data)
                    summary_blocks = []
                    for metric in metric_fields:
                        metric_name = SlackMessageFormatter.format_field_name(metric)
                        total = df[metric].sum()
                        avg = df[metric].mean()
                        max_val = df[metric].max()
                        max_date = df.loc[df[metric].idxmax(), date_fields[0]]
                        
                        summary_blocks.append({
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{metric_name}*\n• Total: {total:,.0f}\n• Average: {avg:,.1f}\n• Peak: {max_val:,.0f} on {max_date}"
                            }
                        })
                    
                    blocks.extend(summary_blocks)
                    
                    try:
                        # Create chart
                        chart_bytes = SlackMessageFormatter._create_chart(table_data, date_fields[0], metric_fields)
                        blocks.append({
                            "type": "image",
                            "title": {
                                "type": "plain_text",
                                "text": "Time Series Chart"
                            },
                            "image_url": f"attachment://chart.png",
                            "alt_text": "Time Series Chart"
                        })
                    except Exception as e:
                        logger.error(f"Error creating chart: {str(e)}", exc_info=True)
                        # Continue without the chart
                    
                    logger.info(f"Returning {len(blocks)} blocks")
                    return blocks[:50]  # Ensure we don't exceed Slack's block limit
                
                # If not time series, check if it's analytics data
                elif any('sessionSource' in row for row in table_data):
                    blocks.extend(SlackMessageFormatter._format_analytics_data(table_data[:10]))
                    return blocks[:50]
                
                # Regular table data
                else:
                    return SlackMessageFormatter.format_table(table_data[:10])[:50]
            
            # If no table data found, format as code block
            return f"```\n{json.dumps(data, indent=2)}\n```"
            
        except Exception as e:
            logger.error(f"Error formatting tool result: {str(e)}", exc_info=True)
            return str(result)
