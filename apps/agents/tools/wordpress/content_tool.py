from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from .base import WordPressBaseSchema, WordPressBaseTool
from typing import Type
import aiohttp
import json
import asyncio
from bs4 import BeautifulSoup

class WordPressContentSchema(WordPressBaseSchema):
    post_id: int = Field(..., description="ID of post/page to update")
    content: str = Field(..., description="HTML content to set")
    allowed_tags: list = Field(
        default=["h1", "h2", "h3", "p", "ul", "ol", "li", "strong", "em", "a"],
        description="Allowed HTML tags for content sanitization"
    )

class WordPressContentTool(BaseTool, WordPressBaseTool):
    name: str = "WordPress Content Updater"
    description: str = """Updates main content of WordPress posts/pages with proper sanitization
    and SEO-friendly formatting. Maintains semantic HTML structure."""
    args_schema: Type[BaseModel] = WordPressContentSchema

    def _run(self, **kwargs) -> str:
        """Sync entry point for Celery"""
        return self._run_sync(self._async_update_content(**kwargs))

    async def _async_update_content(self, website_url: str, post_id: int,
                                  content: str, allowed_tags: list, **kwargs) -> str:
        session = await self._get_session(kwargs['auth_token'])
        
        try:
            # Sanitize HTML content
            sanitized = self._sanitize_html(content, allowed_tags)
            
            async with session.post(
                f"{website_url}/wp-json/wp/v2/posts/{post_id}",
                json={"content": sanitized}
            ) as response:
                if response.status == 200:
                    return json.dumps({
                        "success": True,
                        "post_id": post_id,
                        "content_length": len(sanitized),
                        "allowed_tags": allowed_tags
                    })
                return json.dumps({
                    "error": f"Content update failed: {response.status}",
                    "details": await response.text()
                })
        except Exception as e:
            return json.dumps({
                "error": "Content update failed",
                "message": str(e)
            })

    def _sanitize_html(self, html: str, allowed_tags: list) -> str:
        """Sanitize HTML while preserving SEO elements"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove disallowed tags but keep their content
        for tag in soup.find_all(True):
            if tag.name not in allowed_tags:
                tag.unwrap()
                
        # Clean up empty tags
        for tag in soup.find_all(True):
            if len(tag.get_text(strip=True)) == 0:
                tag.decompose()
                
        return str(soup) 