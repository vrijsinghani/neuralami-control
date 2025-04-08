# Playwright Scraper API Service

A self-hosted API service for web scraping using Playwright, designed to be deployed in Portainer Swarm.

## Features

- Scrape websites using Playwright's powerful browser automation
- Support for multiple output formats (text, HTML, links, metadata, screenshots)
- Configurable options (mobile emulation, stealth mode, custom headers)
- Simple API key authentication
- Docker-based deployment for easy scaling

## Local Development

### Prerequisites

- Docker and Docker Compose

### Running Locally

1. Clone this repository
2. Navigate to the project directory
3. Set the desired port (optional):

```bash
export PORT=8100  # Or any other port you prefer
```

4. Run with Docker Compose:

```bash
docker-compose up --build
```

The API will be available at http://localhost:${PORT} (default is 8000 if PORT is not set)

5. Test the service:

```bash
# Install test dependencies
pip install requests

# Run the test script
./test_service.py --url http://localhost:${PORT} --api-key your_api_key_here --wait 5
```

## API Usage

### Scrape Endpoint

```
POST /api/scrape
```

#### Request Body

```json
{
  "url": "https://example.com",
  "formats": ["text", "html", "links", "metadata", "screenshot"],
  "timeout": 30000,
  "waitFor": "#content",
  "selector": "main",
  "headers": {
    "User-Agent": "Custom User Agent"
  },
  "mobile": false,
  "stealth": true,
  "cache": true
}
```

#### Response

```json
{
  "success": true,
  "data": {
    "text": "...",
    "html": "...",
    "links": [...],
    "metadata": {...},
    "screenshot": "base64-encoded-image"
  }
}
```

## Deployment in Portainer Swarm

1. Build and push the Docker image to your registry:

```bash
docker build -t your-registry.com/playwright-api:latest .
docker push your-registry.com/playwright-api:latest
```

2. In Portainer, create a new stack
3. Use the `portainer-stack.yml` file as a template
4. Set the environment variables:
   - `REGISTRY_URL`: Your Docker registry URL
   - `API_KEY`: Your secret API key for authentication
   - `PORT`: (Optional) The port to run the service on (default: 8000)
   - `STACK_NAME`: (Optional) The name of the stack (default: playwright)

### Nginx Reverse Proxy Configuration

Two Nginx configuration options are provided:

#### Option 1: Standard Nginx Configuration

A standard Nginx configuration is provided in `nginx-config.conf`. To use it:

1. Copy the configuration to your Nginx server:

```bash
scp nginx-config.conf your-server:/etc/nginx/conf.d/playwright.conf
```

2. Edit the configuration to match your domain and SSL certificates:

```bash
ssh your-server
sudo nano /etc/nginx/conf.d/playwright.conf
```

3. Test the configuration and reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

#### Option 2: SWAG Proxy Configuration

If you're using the SWAG (Secure Web Application Gateway) container, a proxy configuration file is provided in `playwright.subdomain.conf`. To use it:

1. Copy the configuration to your SWAG proxy-confs directory:

```bash
cp playwright.subdomain.conf /path/to/swag/nginx/proxy-confs/
```

2. Edit the configuration to match your domain and network settings:

```bash
nano /path/to/swag/nginx/proxy-confs/playwright.subdomain.conf
```

3. Enable the configuration by removing the .sample extension (if you renamed it) or creating a symlink:

```bash
# If your file is already named correctly, you can skip this step
# If you need to enable it from a .sample file:
mv /path/to/swag/nginx/proxy-confs/playwright.subdomain.conf.sample /path/to/swag/nginx/proxy-confs/playwright.subdomain.conf
```

4. Restart the SWAG container:

```bash
docker restart swag
```

Both configurations include:

- SSL/TLS configuration
- Proxy settings with appropriate timeouts for long-running scraping operations
- WebSocket support
- Health check endpoint configuration

## Integration with NeuralAMI Control

This service is designed to work with the PlaywrightAdapter in the NeuralAMI Control system. To configure the adapter to use this service:

1. Update your Django settings to include:

```python
# In settings.py
PLAYWRIGHT_API_URL = "http://your-playwright-service-url/api"
PLAYWRIGHT_API_KEY = "your_api_key_here"
```

2. The PlaywrightAdapter will automatically use these settings to connect to your self-hosted service.

## Security Considerations

- Always use a strong API key in production
- Consider implementing rate limiting for production use
- For sensitive data, use HTTPS and consider network isolation
