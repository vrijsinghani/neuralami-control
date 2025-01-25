import aiohttp
import asyncio
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def validate_wordpress_setup(website_url: str, auth_token: str = None):
    """
    Validate WordPress installation and authentication with browser-like headers
    """
    # Browser-like headers
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json,*/*;q=0.9',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }
    
    if auth_token:
        auth_token = auth_token.replace(" ", "")
        default_headers['Authorization'] = f'Bearer {auth_token}'

    async with aiohttp.ClientSession(headers=default_headers) as session:
        endpoints = [
            '/wp-json',
            '/wp-json/wp/v2/posts',
            '/wp-json/wp/v2/pages'
        ]

        logger.info(f"Testing WordPress installation at: {website_url}")
        logger.info("=" * 50)

        for endpoint in endpoints:
            url = f"{website_url.rstrip('/')}{endpoint}"
            try:
                logger.info(f"\nTesting endpoint: {endpoint}")
                logger.info("-" * 30)
                
                async with session.get(url) as response:
                    logger.info(f"Status: {response.status}")
                    text = await response.text()
                    
                    if response.status == 200:
                        logger.info("✅ Success!")
                        # Only show first 200 chars of response
                        logger.info(f"Response preview: {text[:200]}...")
                    else:
                        logger.info(f"❌ Response: {text}")
                    
                    logger.info(f"Response Headers: {dict(response.headers)}")

            except Exception as e:
                logger.error(f"Error testing {endpoint}: {str(e)}")

async def main():
    website_url = "https://theme-test.neuralami.site"
    auth_token = "0DVa ONhb JdoI C7Jr gMqh M87j"  # Your token
    
    await validate_wordpress_setup(website_url, auth_token)

if __name__ == "__main__":
    asyncio.run(main())

#qB20 kMHX FyaU hnZV UREZ UFzu