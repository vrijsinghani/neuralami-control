#!/usr/bin/env python3
import requests
import json
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CRAWL4AI_URL = "https://crawl4ai.neuralami.com"
CRAWL4AI_API_KEY = "crawl4aiNeuralami1"

def test_crawl():
    # Headers
    headers = {
        "Authorization": f"Bearer {CRAWL4AI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Basic request data
    request_data = {
        "urls": "https://neuralami.com",
        "priority": 10,
        "extraction_config": {
            "type": "basic",
            "params": {
                "output_format": "markdown_v2",  # Changed to markdown
                "word_count_threshold": 0,
                "only_text": False,
                "bypass_cache": True,
                "process_iframes": True,
                "excluded_tags": ["script", "style", "noscript"],
                "html2text": {
                    "ignore_links": False,
                    "ignore_images": False,
                    "body_width": 0,
                    "unicode_snob": True,
                    "protect_links": True,
                    "bypass_tables": False,
                    "single_line_break": True
                },
                "markdown": {
                    "enabled": True,
                    "gfm": True,
                    "tables": True,
                    "breaks": True,
                    "smartLists": True,
                    "smartypants": True,
                    "xhtml": True
                }
            }
        },
        "crawler_params": {
            "headless": True,
            "page_timeout": 30000,
            "simulate_user": True,
            "magic": True,
            "semaphore_count": 5,
            "remove_overlay_elements": True,
            "override_navigator": True,
            "wait_for": "main, #main, .main, #content, .content, article, .post-content",
            "delay_before_return_html": 5.0,
            "wait_until": "networkidle0",
            "javascript": True,
            "scroll": True,
            "wait_for_selector_timeout": 10000,
            "verbose": True
        }
    }

    try:
        # Submit crawl task
        logger.info("Submitting crawl task...")
        response = requests.post(
            f"{CRAWL4AI_URL}/crawl",
            headers=headers,
            json=request_data
        )
        response.raise_for_status()
        task_data = response.json()
        task_id = task_data["task_id"]
        logger.info(f"Task submitted successfully. Task ID: {task_id}")

        # Poll for results
        logger.info("Polling for results...")
        timeout = 300
        start_time = time.time()
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task {task_id} timed out")

            result_response = requests.get(
                f"{CRAWL4AI_URL}/task/{task_id}",
                headers=headers
            )
            result_response.raise_for_status()
            status = result_response.json()

            if status["status"] == "completed":
                logger.info("Task completed successfully!")
                result = status.get("result", {})
                
                # Log available keys
                logger.info(f"Available content keys: {list(result.keys())}")
                
                # Log markdown content
                logger.info("\n=== MARKDOWN CONTENT ===")
                markdown_v2 = result.get("markdown_v2", {})
                if isinstance(markdown_v2, dict):
                    markdown_content = markdown_v2.get("raw_markdown", "")
                else:
                    markdown_content = str(markdown_v2)
                
                if not markdown_content:
                    markdown = result.get("markdown", "")
                    if isinstance(markdown, dict):
                        markdown_content = markdown.get("raw_markdown", "")
                    else:
                        markdown_content = str(markdown)
                
                logger.info(markdown_content)
                logger.info("=== END MARKDOWN CONTENT ===\n")
                
                # Save markdown to file
                with open("crawl_markdown.md", "w", encoding='utf-8') as f:
                    f.write(markdown_content)
                logger.info("Full markdown saved to crawl_markdown.md")
                
                # Save full response to file for inspection
                with open("crawl_response.json", "w", encoding='utf-8') as f:
                    json.dump(status, f, indent=2)
                logger.info("Full response saved to crawl_response.json")
                
                break
            elif status["status"] == "failed":
                raise Exception(f"Task failed: {status.get('error', 'Unknown error')}")
            
            logger.info("Still waiting for results...")
            time.sleep(2)

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)

if __name__ == "__main__":
    test_crawl() 