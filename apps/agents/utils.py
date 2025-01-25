import os
import importlib
from crewai.tools import BaseTool as CrewAIBaseTool
from langchain.tools import BaseTool as LangChainBaseTool
import logging
import crewai_tools
from typing import Optional
from django.core.cache import cache
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import re

logger = logging.getLogger(__name__)

def get_available_tools():
    tools_dir = os.path.join('apps', 'agents', 'tools')
    available_tools = []

    for root, dirs, files in os.walk(tools_dir):
        for item in dirs + files:
            if item.endswith('.py') and not item.startswith('__'):
                rel_path = os.path.relpath(os.path.join(root, item), tools_dir)
                module_path = os.path.splitext(rel_path)[0].replace(os.path.sep, '.')
                available_tools.append(module_path)

    return available_tools

def get_tool_classes(tool_path):
    module_path = f"apps.agents.tools.{tool_path}"
    if module_path.endswith('.py'):
        module_path = module_path[:-3]
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        logger.error(f"Failed to import module {module_path}: {e}")
        return []
    
    tool_classes = []
    for name, obj in module.__dict__.items():
        if isinstance(obj, type) and name.endswith('Tool'):
            try:
                if issubclass(obj, (CrewAIBaseTool, LangChainBaseTool)) or (hasattr(obj, '_run') and callable(getattr(obj, '_run'))):
                    if not any(issubclass(other, obj) and other != obj for other in module.__dict__.values() if isinstance(other, type)):
                        tool_classes.append(obj)
            except TypeError:
                # This can happen if obj is not a class or doesn't inherit from the expected base classes
                logger.warning(f"Skipping {name} as it's not a valid tool class")
    
    logger.debug(f"Found tool classes for {tool_path}: {[cls.__name__ for cls in tool_classes]}")
    return tool_classes

def get_tool_description(tool_class_obj):
    logger.debug(f"Attempting to get description for {tool_class_obj}")

    if hasattr(tool_class_obj, 'description'):
        description = getattr(tool_class_obj, 'description')
        if isinstance(description, str):
            logger.debug(f"Found description class attribute: {description}")
            return description

    if hasattr(tool_class_obj, 'name'):
        name = getattr(tool_class_obj, 'name')
        if isinstance(name, str):
            logger.debug(f"Found name class attribute: {name}")
            return name

    if hasattr(tool_class_obj, '__annotations__') and 'description' in tool_class_obj.__annotations__:
        description = tool_class_obj.__annotations__['description']
        if isinstance(description, str):
            logger.debug(f"Found description in class annotations: {description}")
            return description

    if hasattr(tool_class_obj, 'model_fields') and 'description' in tool_class_obj.model_fields:
        description = tool_class_obj.model_fields['description'].default
        if isinstance(description, str):
            #logger.debug(f"Found description in model_fields: {description}")
            return description

    if tool_class_obj.__doc__:
        docstring = tool_class_obj.__doc__.strip()
        logger.debug(f"Found docstring: {docstring}")
        return docstring

    #  Corrected schema handling: Access the description directly if it exists.
    if hasattr(tool_class_obj, 'schema') and callable(tool_class_obj.schema):
        try:
            schema = tool_class_obj.schema()
            if isinstance(schema, dict) and 'description' in schema and isinstance(schema['description'], str):
                 logger.debug(f"Found description in schema: {schema['description']}")
                 return schema['description']
        except Exception as e:
            logger.warning(f"Error getting schema for {tool_class_obj.__name__}: {str(e)}")


    default_description = f"A tool of type {tool_class_obj.__name__}"
    logger.debug(f"Using default description: {default_description}")
    return default_description

def get_tool_class_obj(tool_class, tool_subclass):
    try:
        module = importlib.import_module(f"apps.agents.tools.{tool_class}")  # Ensure correct module path
        return getattr(module, tool_subclass)
    except (ImportError, AttributeError) as e:
        logger.error(f"Error importing tool class: {e}")
        return None

def load_tool(tool_model) -> Optional[CrewAIBaseTool]:
    
    try:
        # Check if it's a pre-built CrewAI tool
        if hasattr(crewai_tools, tool_model.tool_class):
            logger.info(f"Loading pre-built CrewAI tool: {tool_model.tool_class}")
            tool_class = getattr(crewai_tools, tool_model.tool_class)
            return tool_class()

        # If not, try to import a custom tool
        full_module_path = f"apps.agents.tools.{tool_model.tool_class}"
        logger.info(f"Attempting to import custom tool module: {full_module_path}")
        module = importlib.import_module(full_module_path)
        tool_class = getattr(module, tool_model.tool_subclass)
        
        if issubclass(tool_class, CrewAIBaseTool):
            logger.info(f"Loaded custom tool: {tool_model.tool_subclass}")
            return tool_class()
        elif issubclass(tool_class, LangChainBaseTool):
            logger.info(f"Loaded and wrapped LangChain tool: {tool_model.tool_subclass}")
            # Wrap LangChain tool in CrewAI compatible class
            class WrappedLangChainTool(CrewAIBaseTool):
                name = tool_class.name
                description = get_tool_description(tool_class)

                def _run(self, *args, **kwargs):
                    return tool_class()(*args, **kwargs)

            return WrappedLangChainTool()
        else:
            raise ValueError(f"Unsupported tool class: {tool_class}")

    except ImportError as e:
        logger.error(f"Error importing tool module {full_module_path}: {str(e)}")
    except AttributeError as e:
        logger.error(f"Error finding tool class {tool_model.tool_subclass} in module {full_module_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error loading tool {full_module_path}.{tool_model.tool_subclass}: {str(e)}")
    
    return None

def get_tool_info(tool_model):
    
    full_module_path = f"apps.agents.tools.{tool_model.tool_class}"
    
    return {
        'module_path': full_module_path,
        'class_name': tool_model.tool_subclass
    }

class URLDeduplicator:
    def __init__(self):
        # Common CMS page identifiers
        self.cms_patterns = {
            'wordpress': [
                r'(?:page_id|p|post)=\d+',
                r'\d{4}/\d{2}/\d{2}',  # Date-based permalinks
                r'(?:category|tag)/[\w-]+',
            ],
            'woocommerce': [
                r'product=\d+',
                r'product-category/[\w-]+',
            ],
        }
        
        # Patterns that indicate filter/sort URLs
        self.filter_patterns = [
            # E-commerce filters
            r'product_type=\d+',
            r'prefilter=',
            r'filter\[.*?\]=',
            r'sort(?:by)?=',
            r'order=',
            r'view=',
            r'display=',
            # Pagination
            r'page=\d+',
            r'per_page=\d+',
            # Common parameters
            r'utm_.*?=',
        ]
        
        # Initialize sets for tracking seen URLs and content hashes
        self._seen_urls = set()
        self._seen_hashes = set()
        self._content_hashes = {}
        
    def should_process_url(self, url: str) -> bool:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # First check if it's a CMS page
        if self._is_cms_page(parsed.query):
            return True
            
        # For filter URLs, check both the filtered URL and the base URL
        if self._is_filter_url(parsed.query):
            # Create base URL without query parameters
            base_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                '',
                '',
                ''
            ))
            # Add base URL to seen URLs to avoid duplicate processing
            normalized_base = self._normalize_url(base_url)
            if normalized_base not in self._seen_urls:
                self._seen_urls.add(normalized_base)
                return True
            return False
            
        # If unclear, normalize and check if we've seen it
        normalized = self._normalize_url(url)
        return normalized not in self._seen_urls
        
    def _is_cms_page(self, query: str) -> bool:
        return any(
            re.search(pattern, query)
            for patterns in self.cms_patterns.values()
            for pattern in patterns
        )
        
    def _is_filter_url(self, query: str) -> bool:
        return any(
            re.search(pattern, query)
            for pattern in self.filter_patterns
        )
        
    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        # Keep only essential query parameters
        query_params = parse_qs(parsed.query)
        essential_params = {
            k: v for k, v in query_params.items()
            if not any(re.search(pattern, f"{k}={v[0]}") 
                      for pattern in self.filter_patterns)
        }
        query = urlencode(essential_params, doseq=True) if essential_params else ''
        
        return urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip('/'),
            '',
            query,
            ''
        ))
        
    def _hash_main_content(self, content: str) -> int:
        """Hash the main content, ignoring common dynamic elements"""
        # TODO: Implement content cleaning/normalization if needed
        return hash(content)
        
    def fallback_content_check(self, url: str, content: str) -> bool:
        """Use content hash as fallback for ambiguous cases"""
        if url not in self._content_hashes:
            content_hash = self._hash_main_content(content)
            if content_hash in self._seen_hashes:
                return False
            self._content_hashes[url] = content_hash
            self._seen_hashes.add(content_hash)
        return True
