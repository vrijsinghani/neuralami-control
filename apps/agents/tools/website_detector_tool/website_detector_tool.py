# detect_platform.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import json

# Load platforms from JSON file
with open("platforms.json", "r") as f:
    PLATFORMS = json.load(f)["platforms"]

def check_platform(url, html_content, soup, headers, cookies, domain):
    for platform in PLATFORMS:
        for check in platform["checks"]:
            # HTML content check
            if "html" in check:
                if check["html"] in html_content:
                    if "additional" in check and check["additional"] not in html_content:
                        continue
                    return platform["name"]

            # Meta tag check
            if "meta" in check:
                meta = soup.find("meta", {"name": check["meta"]["name"], "content": lambda x: x and check["meta"]["value"] in x.lower()})
                if meta:
                    return platform["name"]

            # Header check
            if "header" in check:
                for header_key, header_value in check["header"].items():
                    if header_key in headers and (header_value is None or header_value in headers[header_key]):
                        return platform["name"]

            # Cookie check
            if "cookie" in check:
                if any(check["cookie"] in cookie for cookie in cookies):
                    return platform["name"]

            # Domain check
            if "domain" in check:
                if check["domain"] in domain:
                    return platform["name"]

            # Path check (e.g., /wp-admin/)
            if "path" in check:
                try:
                    path_response = requests.get(url + check["path"], timeout=5, allow_redirects=False)
                    if path_response.status_code in [200, 301, 302]:
                        return platform["name"]
                except requests.RequestException:
                    continue

    return "Unknown or custom platform"

def detect_platform(url):
    try:
        # Normalize URL
        if not url.startswith("http"):
            url = "https://" + url
        
        # Fetch the webpage
        response = requests.get(url, timeout=10, allow_redirects=True)
        headers = response.headers
        html_content = response.text.lower()  # Case-insensitive matching
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Parse URL and cookies
        parsed_url = urlparse(response.url)
        domain = parsed_url.netloc
        cookies = response.cookies.keys()

        # Detect platform
        platform = check_platform(url, html_content, soup, headers, cookies, domain)
        return platform

    except requests.RequestException as e:
        return f"Error: Could not fetch site - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

# Test cases
test_urls = [
    "https://wordpress.com",
    "https://shopify.com",
    "https://wix.com",
    "https://squarespace.com",
    "https://joomla.org",
    "https://drupal.org",
    "https://magento.com",
    "https://typo3.org",
    "https://craftcms.com",
    "https://nextjs.org",
    "https://gohugo.io",
    "https://jekyllrb.com",
    "https://hexo.io",
    "https://getpelican.com",
    "https://kentico.com",
    "https://liferay.com",
]

for url in test_urls:
    platform = detect_platform(url)
    print(f"{url} -> {platform}")