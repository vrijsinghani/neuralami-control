#!/usr/bin/env python3
"""
Test script for the Playwright API service.
"""
import argparse
import json
import os
import sys
import time
import requests

def test_health(base_url):
    """Test the health endpoint."""
    try:
        response = requests.get(f"{base_url}/health")
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "ok":
            print("✅ Health check passed")
            return True
        else:
            print(f"❌ Health check failed: {data}")
            return False
    except Exception as e:
        print(f"❌ Health check failed: {str(e)}")
        return False

def test_scrape(base_url, api_key=None):
    """Test the scrape endpoint."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "url": "https://example.com",
        "formats": ["text", "html", "links"],
        "timeout": 30000
    }
    
    try:
        print(f"Testing scrape with payload: {json.dumps(payload, indent=2)}")
        response = requests.post(
            f"{base_url}/api/scrape",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            print("✅ Scrape test passed")
            print(f"Retrieved formats: {list(data.get('data', {}).keys())}")
            return True
        else:
            print(f"❌ Scrape test failed: {data.get('error')}")
            return False
    except Exception as e:
        print(f"❌ Scrape test failed: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test the Playwright API service")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the service")
    parser.add_argument("--api-key", help="API key for authentication")
    parser.add_argument("--wait", type=int, default=0, help="Wait seconds before testing (for container startup)")
    args = parser.parse_args()
    
    if args.wait > 0:
        print(f"Waiting {args.wait} seconds for service to start...")
        time.sleep(args.wait)
    
    print(f"Testing service at {args.url}")
    
    health_ok = test_health(args.url)
    if not health_ok:
        print("Health check failed, skipping scrape test")
        sys.exit(1)
    
    scrape_ok = test_scrape(args.url, args.api_key)
    if not scrape_ok:
        sys.exit(1)
    
    print("All tests passed!")
    sys.exit(0)

if __name__ == "__main__":
    main()
