from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from .base import WordPressBaseSchema, WordPressBaseTool

class WordPressMetaSchema(WordPressBaseSchema):
    post_id: int = Field(..., description="ID of post/page to update")
    meta_fields: Dict[str, str] = Field(
        ...,
        description="Meta fields to update. Valid keys: title, meta_description, og_title, og_description",
        example={"title": "New SEO Title", "meta_description": "Optimized description"}
    )

class WordPressMetaTool(BaseTool, WordPressBaseTool):
    name: str = "WordPress Meta Updater"
    description: str = """Updates SEO meta information on WordPress posts/pages including:
    - Title
    - Meta description
    - OpenGraph titles
    - OpenGraph descriptions
    
    Example usage:
    {
        "website_url": "https://blog.example.com",
        "user_id": 42,
        "auth_token": "wp_rest_token",
        "post_id": 123,
        "meta_fields": {
            "title": "New SEO Optimized Title",
            "meta_description": "Improved meta description for search engines"
        }
    }"""
    args_schema: Type[BaseModel] = WordPressMetaSchema

    def _run(self, **kwargs) -> str:
        """Sync entry point for Celery"""
        return self._run_sync(self._async_update_meta(**kwargs))

    async def _async_update_meta(self, website_url: str, post_id: int, 
                               meta_fields: Dict[str, str], **kwargs) -> str:
        session = await self._get_session(kwargs['auth_token'])
        
        valid_fields = {
            "title": "title",
            "meta_description": "meta:description",
            "og_title": "og:title",
            "og_description": "og:description"
        }
        
        updates = {
            "meta": {
                valid_fields[key]: value
                for key, value in meta_fields.items()
                if key in valid_fields
            }
        }
        
        try:
            async with session.post(
                f"{website_url}/wp-json/wp/v2/posts/{post_id}",
                json=updates
            ) as response:
                if response.status == 200:
                    return json.dumps({
                        "success": True,
                        "post_id": post_id,
                        "updated_fields": list(meta_fields.keys())
                    })
                return json.dumps({
                    "error": f"API request failed with status {response.status}",
                    "details": await response.text()
                })
        except Exception as e:
            return json.dumps({
                "error": "Meta update failed",
                "message": str(e)
            }) 