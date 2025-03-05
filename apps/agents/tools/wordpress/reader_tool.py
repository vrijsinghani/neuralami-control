from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from apps.agents.tools.base_tool import BaseTool
import json
import logging
from .base import WordPressBaseTool
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

class WordPressReaderSchema(BaseModel):
    """Schema for WordPress content reading operations"""
    website_url: str = Field(..., description="WordPress site URL")
    auth_token: str = Field(..., description="WordPress REST API authentication token")
    
    # Search parameters
    search_query: Optional[str] = Field(
        default="",
        description="Search term to find specific content"
    )
    search_field: Optional[str] = Field(
        default="title",
        description="Field to search in (title, content, slug)"
    )
    
    # Listing parameters
    list_all: Optional[bool] = Field(
        default=True,
        description="List all posts/pages instead of searching"
    )
    post_type: Optional[str] = Field(
        default="post",
        description="Content type to retrieve (post, page)"
    )
    per_page: Optional[int] = Field(
        default=20,
        description="Number of items per page (max 100)"
    )
    page: Optional[int] = Field(
        default=1,
        description="Page number for pagination"
    )
    
    # Additional filters
    status: Optional[str] = Field(
        default="publish",
        description="Content status (publish, draft, private)"
    )
    order_by: Optional[str] = Field(
        default="date",
        description="Sort field (date, title, modified)"
    )
    order: Optional[str] = Field(
        default="desc",
        description="Sort order (asc, desc)"
    )

    model_config = ConfigDict(
        extra='forbid',
        arbitrary_types_allowed=True
    )

class WordPressReaderTool(BaseTool, WordPressBaseTool):
    name: str = "WordPress Content Reader"
    description: str = """Retrieves WordPress post/page information for editing purposes.
    
    Features:
    - Search by URL, title, or slug
    - List all posts/pages with filters
    - Get post IDs and metadata
    
    Example usage:
    {
        "website_url": "https://blog.example.com",
        "auth_token": "wp_rest_token",
        "search_query": "optimizing-seo",
        "search_field": "slug"
    }"""
    
    args_schema: type[BaseModel] = WordPressReaderSchema

    def _run(
        self,
        website_url: str,
        auth_token: str,
        search_query: str = "",
        search_field: str = "title",
        list_all: bool = True,
        post_type: str = "post",
        per_page: int = 20,
        page: int = 1,
        status: str = "publish",
        order_by: str = "date",
        order: str = "desc",
        **kwargs
    ) -> str:
        """Handle WordPress content reading operations with explicit parameters"""
        logger.debug(f"Running WordPress reader with parameters: website_url={website_url}, "
                    f"search_query={search_query}, list_all={list_all}, post_type={post_type}")
        
        # Create validated schema instance
        params = WordPressReaderSchema(
            website_url=website_url,
            auth_token=auth_token,
            search_query=search_query,
            search_field=search_field,
            list_all=list_all,
            post_type=post_type,
            per_page=per_page,
            page=page,
            status=status,
            order_by=order_by,
            order=order
        )
        
        # Pass validated parameters to async method
        return self._run_sync(self._async_get_post(
            website_url=params.website_url,
            auth_token=params.auth_token,
            search_query=params.search_query,
            search_field=params.search_field,
            list_all=params.list_all,
            post_type=params.post_type,
            per_page=params.per_page,
            page=params.page,
            status=params.status,
            order_by=params.order_by,
            order=params.order
        ))

    async def _async_get_post(
        self,
        website_url: str,
        auth_token: str,
        search_query: str = "",
        search_field: str = "title",
        list_all: bool = True,
        post_type: str = "post",
        per_page: int = 20,
        page: int = 1,
        status: str = "publish",
        order_by: str = "date",
        order: str = "desc"
    ) -> str:
        """Async method to fetch WordPress content"""
        # Create timeout object with longer durations
        timeout = aiohttp.ClientTimeout(
            total=30,  # Total timeout for the whole request
            connect=10,  # Timeout for connecting to the server
            sock_read=30  # Timeout for reading the response
        )
        
        # Get base session without timeout
        session = await self._get_session(auth_token)
        # Update session timeout
        session._timeout = timeout
        
        # Rest of the headers and params setup...
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json,*/*;q=0.9',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token.replace(" ", "")}'
        
        params = {
            'per_page': per_page,
            'page': page,
            'status': status,
            'orderby': order_by,
            'order': order
        }
        
        # Add search parameters if searching
        if search_query and not list_all:
            params['search'] = search_query
            if search_field in ['title', 'content', 'slug']:
                params['search_columns'] = [search_field]
        
        try:
            logger.debug(f"Attempting to fetch WordPress content from {website_url} with timeout {timeout}")
            async with session.get(
                f"{website_url}/wp-json/wp/v2/{post_type}s",
                params=params,
                headers=headers,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    total_posts = response.headers.get('X-WP-Total', '0')
                    total_pages = response.headers.get('X-WP-TotalPages', '0')
                    
                    return json.dumps({
                        'success': True,
                        'total_posts': total_posts,
                        'total_pages': total_pages,
                        'current_page': page,
                        'posts': [
                            {
                                'id': post.get('id'),
                                'title': post.get('title', {}).get('rendered', ''),
                                'slug': post.get('slug', ''),
                                'status': post.get('status', ''),
                                'link': post.get('link', ''),
                                'modified': post.get('modified', '')
                            }
                            for post in data
                        ]
                    })
                return json.dumps({
                    'error': f"API request failed with status {response.status}",
                    'details': await response.text()
                })
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout error fetching WordPress content: {str(e)}")
            return json.dumps({
                'error': "Request timed out",
                'message': "The request took too long to complete. Please try again."
            })
        except Exception as e:
            logger.error(f"Error fetching WordPress content: {str(e)}")
            return json.dumps({
                'error': "Failed to fetch WordPress content",
                'message': str(e)
            }) 