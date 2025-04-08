# Playwright Adapter Guide

## Overview

The Playwright Adapter is an extension to the Scraper Service architecture that allows you to use an externally hosted Playwright service for web scraping. This adapter provides an alternative to the FireCrawl adapter, giving you more flexibility and redundancy in your web scraping capabilities.

## Configuration

### Environment Variables

The Playwright Adapter uses the following environment variables:

```
PLAYWRIGHT_API_URL='https://your-playwright-service.example.com/api'
PLAYWRIGHT_API_KEY='your-playwright-api-key'
```

You can set these variables in your `.env` file or in your environment.

### Django Settings

The adapter reads its configuration from Django settings:

```python
# Playwright service configuration
PLAYWRIGHT_API_URL = os.getenv('PLAYWRIGHT_API_URL')
PLAYWRIGHT_API_KEY = os.getenv('PLAYWRIGHT_API_KEY')
```

These settings are already added to your `settings.py` file.

## Using the Playwright Adapter

### Basic Usage

You can use the Playwright Adapter with the `scrape_url` function:

```python
from apps.agents.utils.scrape_url import scrape_url

result = scrape_url(
    url="https://example.com",
    output_type="text,html",
    adapter_name="playwright"  # Specify the adapter name
)
```

### Advanced Usage

For more control, you can use the ScraperService directly:

```python
from apps.agents.utils.scraper_service import ScraperService

# Initialize the service with the Playwright adapter
scraper_service = ScraperService(adapter_name="playwright")

# Scrape a URL
result = scraper_service.scrape(
    url="https://example.com",
    output_types=["text", "html", "links"],
    timeout=30000,
    stealth=True
)
```

### Supported Parameters

The Playwright Adapter supports the following parameters:

- `url`: The URL to scrape
- `formats`: List of formats to return (text, html, links, metadata, full)
- `timeout`: Timeout in milliseconds
- `wait_for`: Wait for element or time in milliseconds
- `css_selector`: CSS selector to extract content from
- `headers`: Custom headers to send with the request
- `mobile`: Whether to use mobile user agent
- `stealth`: Whether to use stealth mode
- `cache`: Whether to use cached results

## Setting Up a Playwright Service

To use the Playwright Adapter, you need to set up an external Playwright service that exposes an API for web scraping. Here's a basic outline of how to set up such a service:

1. Create a new Node.js project
2. Install Playwright: `npm install playwright`
3. Create an Express server: `npm install express`
4. Implement an API endpoint for scraping

Here's a simple example of a Playwright service:

```javascript
const express = require('express');
const { chromium } = require('playwright');
const app = express();
const port = process.env.PORT || 3000;

app.use(express.json());

app.post('/api/scrape', async (req, res) => {
  const { url, formats, timeout, waitFor, selector, headers, mobile, stealth } = req.body;
  
  const browser = await chromium.launch();
  const context = await browser.newContext({
    userAgent: mobile ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1' : undefined,
  });
  
  if (headers) {
    await context.setExtraHTTPHeaders(headers);
  }
  
  const page = await context.newPage();
  
  try {
    await page.goto(url, { timeout: timeout || 30000 });
    
    if (waitFor) {
      if (typeof waitFor === 'number') {
        await page.waitForTimeout(waitFor);
      } else {
        await page.waitForSelector(waitFor);
      }
    }
    
    const result = {
      success: true,
      data: {}
    };
    
    // Extract content based on requested formats
    for (const format of formats) {
      if (format === 'text') {
        const content = selector ? 
          await page.textContent(selector) : 
          await page.textContent('body');
        result.data.text = content;
      }
      
      if (format === 'html' || format === 'raw_html') {
        const content = await page.content();
        result.data.html = content;
      }
      
      if (format === 'links') {
        const links = await page.evaluate(() => {
          return Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.href);
        });
        result.data.links = links;
      }
      
      if (format === 'metadata') {
        const metadata = await page.evaluate(() => {
          return {
            title: document.title,
            description: document.querySelector('meta[name="description"]')?.content || '',
            language: document.documentElement.lang || '',
          };
        });
        result.data.metadata = {
          ...metadata,
          statusCode: 200
        };
      }
      
      if (format === 'screenshot') {
        const screenshot = await page.screenshot({ encoding: 'base64' });
        result.data.screenshot = `data:image/png;base64,${screenshot}`;
      }
    }
    
    res.json(result);
  } catch (error) {
    res.status(500).json({
      success: false,
      error: error.message
    });
  } finally {
    await browser.close();
  }
});

app.listen(port, () => {
  console.log(`Playwright service listening at http://localhost:${port}`);
});
```

You can deploy this service to a server or cloud platform of your choice.

## Conclusion

The Playwright Adapter provides a flexible and powerful way to integrate an external Playwright service into your web scraping architecture. By using this adapter, you can take advantage of Playwright's capabilities while maintaining compatibility with your existing code.

For more information on the Scraper Service architecture, see the [Scraper Service Guide](scraper_service_guide.md).
