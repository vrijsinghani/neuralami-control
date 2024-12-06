import json
import os

import requests
from langchain.tools import tool
from unstructured.partition.html import partition_html
from trafilatura import fetch_url, extract, sitemaps, spider
from summarizer import summarize

class BrowserTools():

  @tool("Scrape and summarize website content")
  def scrape_and_summarize_website(website):
    """Useful to scrape and summarize a website content, just pass a string with
    only the full url, no need for a final slash `/`, eg: https://google.com or https://clearbit.com/about-us"""
    url = f"https://browserless.neuralami.com/content?token={os.environ['BROWSERLESS_API_KEY']}"
    payload = json.dumps({"url": website})
    headers = {'cache-control': 'no-cache', 'content-type': 'application/json'}
    print(f"Browsin': {website}")
    response = requests.request("POST", url, headers=headers, data=payload)
    content = extract(response.text)
    summary = summarize(content)
    print(f"summary: '{summary}'")
    content = summary

    return f'\nSummary of {website}: {content}\n'

  @tool("Scrape website content")
  def scrape_website(website):
    """Useful to scrape website content, just pass a string with
    only the full url, no need for a final slash `/`, eg: https://google.com or https://clearbit.com/about-us"""
    url = f"https://browserless.neuralami.com/content?token={os.environ['BROWSERLESS_API_KEY']}"
    payload = json.dumps({"url": website})
    headers = {'cache-control': 'no-cache', 'content-type': 'application/json'}
    print(f"Browsin': {website}")
    response = requests.request("POST", url, headers=headers, data=payload)
    content = extract(response.text)
    return f'\nContent of {website}: {content}\n'