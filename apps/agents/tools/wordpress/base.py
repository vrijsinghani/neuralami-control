from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import aiohttp
import asyncio

class WordPressBaseSchema(BaseModel):
    website_url: str = Field(..., description="WordPress site URL")
    user_id: int = Field(..., description="ID of user initiating the change")
    auth_token: str = Field(..., description="WordPress REST API authentication token")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates for requests")

class WordPressBaseTool:
    """Shared WordPress tool functionality"""
    _session = None
    
    def _run_sync(self, coro):
        """Run async code in sync context for Celery"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    
    async def _get_session(self, auth_token: str):
        """Reusable aiohttp session with auth"""
        if not self._session:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {auth_token}"}
            )
        return self._session 