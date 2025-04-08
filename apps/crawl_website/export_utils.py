"""
Utility functions for exporting crawl results to different formats.
These functions are used by both the web_crawler and sitemap_crawler.
"""
import io
import csv
import json
import logging
from datetime import datetime
from django.core.files.base import ContentFile
from .utils import sanitize_url_for_filename

logger = logging.getLogger(__name__)

def generate_text_content(results):
    """
    Generate text content from crawl results.

    Args:
        results (list): List of result dictionaries from the crawler

    Returns:
        str: Formatted text content
    """
    content_parts = []

    for item in results:
        # Start with the URL
        item_content = [f"URL: {item.get('url', '')}"]

        # Add title if available
        if 'title' in item and item['title']:
            item_content.append(f"Title: {item['title']}")

        # Add text content if available
        if 'text' in item and item['text']:
            item_content.append(f"\nContent:\n{item['text']}")

        # Add HTML content indicator if available
        if 'html' in item and item['html']:
            item_content.append("\nHTML: Available (not shown in text output)")

        # Add metadata if available
        if 'metadata' in item and item['metadata']:
            metadata_count = len(item['metadata']) if isinstance(item['metadata'], dict) else 0
            metadata_str = f"\nMetadata ({metadata_count} tags):\n"
            if isinstance(item['metadata'], dict):
                # Sort metadata keys for consistent output
                for i, (key, value) in enumerate(sorted(item['metadata'].items())):
                    metadata_str += f"  {i+1}. {key}: {value}\n"
            else:
                metadata_str += str(item['metadata'])
            item_content.append(metadata_str)

        # Add links if available
        if 'links' in item and item['links']:
            # Remove duplicate links while preserving order
            unique_links = []
            seen_hrefs = set()

            if isinstance(item['links'], list):
                for link in item['links']:
                    if isinstance(link, dict) and 'href' in link:
                        href = link.get('href', '')
                        if href and href not in seen_hrefs:
                            seen_hrefs.add(href)
                            unique_links.append(link)
                    elif isinstance(link, str) and link not in seen_hrefs:
                        seen_hrefs.add(link)
                        unique_links.append(link)

            links_str = f"\nLinks ({len(unique_links)}):\n"

            if unique_links:
                for i, link in enumerate(unique_links):  # Show all unique links
                    if isinstance(link, dict):
                        link_href = link.get('href', '')
                        link_text = link.get('text', '').strip()
                        if link_text:
                            links_str += f"  {i+1}. {link_href} - {link_text}\n"
                        else:
                            links_str += f"  {i+1}. {link_href}\n"
                    else:
                        links_str += f"  {i+1}. {link}\n"
            else:
                links_str += str(item['links'])
            item_content.append(links_str)

        # Add screenshot indicator if available
        if 'screenshot' in item and item['screenshot']:
            item_content.append("\nScreenshot: Available (not shown in text output)")

        # Join all parts with newlines
        content_parts.append("\n".join(item_content))

    # Join all items with a separator
    return "\n\n" + "="*50 + "\n\n".join(content_parts)

def generate_csv_content(results):
    """
    Generate CSV content from crawl results.

    Args:
        results (list): List of result dictionaries from the crawler

    Returns:
        str: CSV content as a string
    """
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer, dialect='excel', lineterminator='\n', quoting=csv.QUOTE_ALL)

    # Determine which columns to include based on the content in the results
    columns = ['URL', 'Title']
    has_text = any('text' in item for item in results)
    has_html = any('html' in item for item in results)
    has_metadata = any('metadata' in item for item in results)
    has_links = any('links' in item for item in results)
    has_screenshot = any('screenshot' in item for item in results)

    if has_text:
        columns.append('Text')
    if has_html:
        columns.append('HTML')
    if has_metadata:
        columns.append('Metadata')
    if has_links:
        columns.append('Links')
    if has_screenshot:
        columns.append('Screenshot')

    # Write the header row
    csv_writer.writerow(columns)

    # Write each result row
    for item in results:
        url_item = item.get('url', '')
        title_item = item.get('title', '')

        # Prepare the row data
        row_data = [url_item, title_item]

        # Add text content if available and requested
        if has_text:
            if 'text' in item and item['text']:
                # Truncate text to first 500 characters for CSV
                text = item['text'][:500] + '...' if len(item['text']) > 500 else item['text']
                # Replace newlines with spaces for CSV
                text = text.replace('\n', ' ').replace('\r', '')
                row_data.append(text)
            else:
                row_data.append('')

        # Add HTML content if available and requested
        if has_html:
            if 'html' in item and item['html']:
                # Just indicate HTML is available (too large for CSV)
                html_length = len(item['html'])
                row_data.append(f'HTML content available ({html_length} characters)')
            else:
                row_data.append('')

        # Add metadata if available and requested
        if has_metadata:
            if 'metadata' in item and item['metadata']:
                if isinstance(item['metadata'], dict):
                    # Format metadata with each tag on its own line
                    metadata_count = len(item['metadata'])
                    metadata_text = f"{metadata_count} metadata tags found:\n"

                    # Add each metadata tag on its own line
                    for i, (key, value) in enumerate(sorted(item['metadata'].items())):
                        if value:  # Only include non-empty values
                            # Clean the value to avoid CSV formatting issues
                            clean_value = str(value).replace('"', '').replace(',', ' ')
                            # Truncate very long values
                            if len(clean_value) > 100:
                                clean_value = clean_value[:100] + '...'
                            metadata_text += f"{i+1}. {key}: {clean_value}\n"

                    row_data.append(metadata_text)
                else:
                    row_data.append(str(item['metadata']))
            else:
                row_data.append('')

        # Add links if available and requested
        if has_links:
            if 'links' in item and item['links']:
                if isinstance(item['links'], list):
                    # Remove duplicate links while preserving order
                    unique_links = []
                    seen_hrefs = set()

                    for link in item['links']:
                        if isinstance(link, dict) and 'href' in link:
                            href = link.get('href', '')
                            if href and href not in seen_hrefs:
                                seen_hrefs.add(href)
                                unique_links.append(link)
                        elif isinstance(link, str) and link not in seen_hrefs:
                            seen_hrefs.add(link)
                            unique_links.append(link)

                    # Format all unique links for CSV output
                    links_count = len(unique_links)

                    # Create a properly formatted list of all links
                    # Use line breaks (\n) to separate links within the cell
                    links_text = f"{links_count} links found:\n"

                    for i, link in enumerate(unique_links):
                        if isinstance(link, dict) and 'href' in link:
                            # Format each link with its URL and text (if available)
                            link_href = link.get('href', '')
                            link_text = link.get('text', '').strip()

                            # Clean the link text to avoid CSV formatting issues
                            if link_text:
                                # Replace commas and quotes to avoid CSV parsing issues
                                clean_text = link_text.replace('"', '').replace(',', ' ')
                                # Truncate very long text
                                clean_text = clean_text[:50] + '...' if len(clean_text) > 50 else clean_text
                                links_text += f"{i+1}. {link_href} ({clean_text})\n"
                            else:
                                links_text += f"{i+1}. {link_href}\n"
                        elif isinstance(link, str):
                            links_text += f"{i+1}. {link}\n"

                    row_data.append(links_text)
                else:
                    row_data.append(str(item['links']))
            else:
                row_data.append('')

        # Add screenshot indicator if available and requested
        if has_screenshot:
            if 'screenshot' in item and item['screenshot']:
                row_data.append('Screenshot available')
            else:
                row_data.append('')

        # Write the row to the CSV
        csv_writer.writerow(row_data)

    # Get the CSV content
    return csv_buffer.getvalue()

def save_crawl_results(results, url, user_id, output_format, storage, save_as_csv=False):
    """
    Save crawl results to storage.

    Args:
        results (list): List of result dictionaries from the crawler
        url (str): The URL that was crawled
        user_id (int): The user ID
        output_format (str): The output format (text, html, json)
        storage: The storage backend to use
        save_as_csv (bool): Whether to also save as CSV

    Returns:
        tuple: (file_url, csv_url) URLs to the saved files
    """
    file_url = None
    csv_url = None

    try:
        # Determine filename suffix based on output format
        if output_format == 'json':
            file_suffix = 'json'
            # Save the list of result dictionaries directly
            content_to_save = json.dumps(results, indent=4)
        elif output_format == 'html':
            file_suffix = 'html'
            # Combine HTML content
            html_parts = []
            for item in results:
                # Get HTML content from 'html' key
                html_content = item.get('html', '')
                if html_content:
                    # Add URL as a header
                    url_header = f"<h2>URL: {item.get('url', '')}</h2>"
                    html_parts.append(f"{url_header}\n{html_content}")

            # Join all HTML parts with a separator
            content_to_save = '\n<hr>\n'.join(html_parts)
        else:  # Default to text
            file_suffix = 'txt'
            # Generate text content
            content_to_save = generate_text_content(results)

        sanitized_url = sanitize_url_for_filename(url)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}.{file_suffix}"
        file_path = storage.save(filename, ContentFile(content_to_save.encode('utf-8')))
        file_url = storage.url(file_path)
        logger.info(f"Output file saved to: {file_path} (format: {file_suffix})")

        # Save as CSV if requested
        if save_as_csv and output_format != 'json':
            try:
                csv_filename = f"{user_id}/crawled_websites/{sanitized_url}_{timestamp}.csv"
                csv_content = generate_csv_content(results)
                csv_path = storage.save(csv_filename, ContentFile(csv_content.encode('utf-8')))
                csv_url = storage.url(csv_path)
                logger.info(f"CSV file saved to: {csv_path}")
            except Exception as csv_save_err:
                logger.error(f"Error saving CSV results: {csv_save_err}", exc_info=True)
    except Exception as primary_save_err:
        logger.error(f"Error saving primary output file: {primary_save_err}", exc_info=True)
        # File saving failed, but task might still be successful
        # file_url remains None

    return file_url, csv_url
