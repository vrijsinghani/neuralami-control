import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Type
from urllib.parse import urlparse

import requests
from django.core.cache import cache
from django.conf import settings
from langchain.document_loaders import PyMuPDFLoader
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import tempfile
logger = logging.getLogger(__name__)

class PDFExtractorSchema(BaseModel):
    """Input schema for PDFExtractorTool."""
    
    class Config:
        use_enum_values = True
        extra = "forbid"
        json_schema_extra = {
            "examples": [{"url": "https://example.com/sample.pdf", "use_cache": True}]
        }
    
    url: str = Field(
        ..., 
        description="The URL of the PDF to extract content from",
        examples=["https://example.com/sample.pdf"]
    )
    use_cache: bool = Field(
        default=True,
        description="Whether to use cached results if available"
    )

class PDFExtractorTool(BaseTool):
    name: str = "PDF Extractor Tool"
    description: str = "Extracts and processes text content from PDF files using PyMuPDF"
    args_schema: Type[BaseModel] = PDFExtractorSchema
    cache_timeout: int = getattr(settings, 'PDF_CACHE_TIMEOUT', 60 * 60 * 24 * 7)
    
    def __init__(self, **data):
        super().__init__(**data)

    def _run(self, **kwargs: Any) -> Dict:
        """Execute the PDF extraction pipeline."""
        try:
            params = self.args_schema(**kwargs)
            
            if params.use_cache:
                cache_key = f"pdf_extract:{hashlib.md5(params.url.encode()).hexdigest()}"
                cached_result = cache.get(cache_key)
                if cached_result:
                    logger.debug(f"Cache hit for PDF: {params.url}")
                    return {
                        'success': True,
                        'pdf_data': cached_result,
                        'cached': True
                    }

            # Download PDF to temporary file
            response = requests.get(params.url)
            response.raise_for_status()
            
            with tempfile.NamedTemporaryFile(suffix='.pdf') as temp_pdf:
                temp_pdf.write(response.content)
                temp_pdf.flush()
                
                # Use PyMuPDFLoader
                loader = PyMuPDFLoader(temp_pdf.name)
                documents = loader.load()
                
                # Process the documents
                result = {
                    'content': '\n\n'.join(doc.page_content for doc in documents),
                    'num_pages': len(documents)
                }
                
                if params.use_cache:
                    cache.set(cache_key, result, timeout=self.cache_timeout)
                
                return {
                    'success': True,
                    'pdf_data': result,
                    'cached': False
                }

        except Exception as e:
            logger.error(f"PDF Extractor tool error: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'pdf_data': {}
            }
