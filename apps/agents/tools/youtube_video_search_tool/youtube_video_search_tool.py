from typing import Any, Optional, Type, Dict
from pydantic import BaseModel, Field
from apps.agents.tools.base_tool import BaseTool
from embedchain.models.data_type import DataType
import logging
import json
from django.conf import settings

logger = logging.getLogger(__name__)

class YoutubeVideoSearchToolSchema(BaseModel):
    """Input schema for YoutubeVideoSearchTool."""
    search_query: str = Field(
        ...,
        description="The search query to use when searching the Youtube Video content"
    )
    youtube_video_url: Optional[str] = Field(
        None,
        description="Optional youtube video URL to search. If not provided, will use pre-configured URL"
    )

class YoutubeVideoSearchTool(BaseTool):
    name: str = "Youtube Video Search Tool"
    description: str = "A tool that can be used to semantic search a query from Youtube Video content."
    args_schema: Type[BaseModel] = YoutubeVideoSearchToolSchema
    rag_instance: Optional[Any] = Field(default=None, exclude=True)
    youtube_video_url: Optional[str] = Field(default=None)
    
    def __init__(self, youtube_video_url: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        if youtube_video_url:
            self.youtube_video_url = youtube_video_url
            self.description = f"A tool that can be used to semantic search queries from the Youtube Video at: {youtube_video_url}"
            self._initialize_rag(youtube_video_url)

    def _initialize_rag(self, video_url: str) -> None:
        """Initialize RAG system with the video content"""
        try:
            # Initialize your RAG system here
            self.rag_instance = self._create_rag_instance()
            self.rag_instance.add(video_url, data_type=DataType.YOUTUBE_VIDEO)
            logger.debug(f"Initialized RAG system with video: {video_url}")
        except Exception as e:
            logger.error(f"Error initializing RAG system: {str(e)}")
            raise

    def _create_rag_instance(self) -> Any:
        """Create and return RAG instance with appropriate configuration"""
        # Implement your RAG instance creation logic here
        # This would contain the logic from your parent RagTool class
        pass

    def _run(
        self,
        search_query: str,
        youtube_video_url: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        try:
            # Initialize RAG with new URL if provided
            if youtube_video_url and youtube_video_url != self.youtube_video_url:
                self._initialize_rag(youtube_video_url)
                self.youtube_video_url = youtube_video_url
            
            # Ensure RAG is initialized
            if not self.rag_instance:
                if not self.youtube_video_url:
                    raise ValueError("No Youtube video URL provided or configured")
                self._initialize_rag(self.youtube_video_url)
            
            # Perform the search
            result = self.rag_instance.search(search_query)
            
            logger.debug(f"Youtube video search completed for query: {search_query[:50]}...")
            return str(result)

        except Exception as e:
            logger.error(f"Error in YoutubeVideoSearchTool: {str(e)}")
            return json.dumps({
                "error": "Youtube video search failed",
                "message": str(e)
            })
