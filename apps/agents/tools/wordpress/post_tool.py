from apps.agents.tools.base_tool import BaseTool
from pydantic import BaseModel, Field
from .base import WordPressBaseSchema, WordPressBaseTool
from typing import Type
import aiohttp
import json
import asyncio

class WordPressPostSchema(WordPressBaseSchema):
    title: str = Field(..., description="Post title")
    content: str = Field(..., description="HTML content for the new post")
    status: str = Field(default="draft", description="Post status: draft, publish, future")
    categories: list = Field(default=[], description="Category IDs for the post")
    tags: list = Field(default=[], description="Tag IDs for the post")
    meta_fields: dict = Field(default={}, description="Initial meta fields")

class WordPressPostTool(BaseTool, WordPressBaseTool):
    name: str = "WordPress Post Creator"
    description: str = """Creates new WordPress posts with SEO-optimized structure.
    
    Example usage:
    {
        "website_url": "https://blog.example.com",
        "user_id": 42,
        "auth_token": "wp_rest_token",
        "title": "New SEO Optimized Post",
        "content": "<h1>Main Heading</h1><p>Quality content...</p>",
        "status": "draft",
        "categories": [5],
        "tags": [12, 15],
        "meta_fields": {
            "meta_description": "Post description for search engines"
        }
    }"""
    args_schema: Type[BaseModel] = WordPressPostSchema

    def _run(self, **kwargs) -> str:
        """Sync entry point for Celery"""
        return self._run_sync(self._async_create_post(**kwargs))

    async def _async_create_post(self, website_url: str, title: str, 
                               content: str, **kwargs) -> str:
        session = await self._get_session(kwargs['auth_token'])
        
        post_data = {
            "title": title,
            "content": content,
            "status": kwargs.get('status', 'draft'),
            "categories": kwargs.get('categories', []),
            "tags": kwargs.get('tags', []),
            "meta": kwargs.get('meta_fields', {})
        }
        
        try:
            async with session.post(
                f"{website_url}/wp-json/wp/v2/posts",
                json=post_data
            ) as response:
                if response.status == 201:
                    data = await response.json()
                    return json.dumps({
                        "success": True,
                        "post_id": data.get('id'),
                        "edit_link": data.get('link')
                    })
                return json.dumps({
                    "error": f"Post creation failed: {response.status}",
                    "details": await response.text()
                })
        except Exception as e:
            return json.dumps({
                "error": "Post creation failed",
                "message": str(e)
            }) 