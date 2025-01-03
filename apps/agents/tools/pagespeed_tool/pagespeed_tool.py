import os
from typing import Any, Type, Set, Dict, Optional
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
from pydantic import BaseModel, Field
from crewai_tools import BaseTool
import dotenv

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

class PageSpeedToolSchema(BaseModel):
    """Input for PageSpeedTool."""
    url: str = Field(..., title="URL", description="Full URL of the page to analyze (e.g., https://example.com)")
    strategy: str = Field(
        default="mobile",
        title="Strategy",
        description="The analysis strategy: 'mobile' or 'desktop'"
    )
    categories: list = Field(
        default=["performance"],
        title="Categories",
        description="Categories to analyze: 'performance', 'accessibility', 'best-practices', 'seo', 'pwa'"
    )

class PageSpeedTool(BaseTool):
    name: str = "PageSpeed Analysis Tool"
    description: str = "A tool that analyzes web pages using Google PageSpeed Insights API to get Core Web Vitals and other performance metrics."
    args_schema: Type[BaseModel] = PageSpeedToolSchema
    tags: Set[str] = {"performance", "seo", "web vitals", "pagespeed"}
    api_key: str = Field(default=os.environ.get('PAGESPEED_API_KEY'))
    base_url: str = Field(default="https://www.googleapis.com/pagespeedonline/v5/runPagespeed")

    def __init__(self, **data):
        super().__init__(**data)
        if not self.api_key:
            logger.error("PAGESPEED_API_KEY is not set in the environment variables.")

    def _run(
        self,
        url: str,
        strategy: str = "mobile",
        categories: list = ["performance"],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Run PageSpeed analysis."""
        return self.get_pagespeed_data(url, strategy, categories)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def get_pagespeed_data(
        self, 
        url: str, 
        strategy: str = "mobile",
        categories: list = ["performance"]
    ) -> Dict[str, Any]:
        """Get PageSpeed Insights data with retry mechanism."""
        if not self.api_key:
            raise ValueError("PageSpeed API key is not set")

        params = {
            'url': url,
            'key': self.api_key,
            'strategy': strategy,
            'category': categories
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            return self._process_pagespeed_data(data)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching PageSpeed data for {url}: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response content: {e.response.text[:500]}...")
            raise

    def _process_pagespeed_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and structure PageSpeed data."""
        try:
            result = {
                'core_web_vitals': {
                    'lab_data': self._extract_lab_data(data),
                    'field_data': self._extract_field_data(data)
                },
                'performance_score': self._extract_performance_score(data),
                'opportunities': self._extract_opportunities(data),
                'diagnostics': self._extract_diagnostics(data),
                'passed_audits': self._extract_passed_audits(data)
            }

            # Add additional categories if present
            for category in ['accessibility', 'best-practices', 'seo', 'pwa']:
                score = self._extract_category_score(data, category)
                if score is not None:
                    result[f'{category}_score'] = score

            return result

        except Exception as e:
            logger.error(f"Error processing PageSpeed data: {str(e)}")
            return {}

    def _extract_lab_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract lab data metrics."""
        try:
            lab_data = data.get('lighthouseResult', {}).get('audits', {})
            metrics = {}
            
            metric_mapping = {
                'largest-contentful-paint': 'lcp',
                'cumulative-layout-shift': 'cls',
                'total-blocking-time': 'tbt',
                'interactive': 'tti',
                'speed-index': 'speed_index',
                'first-contentful-paint': 'fcp'
            }
            
            for audit_name, metric_name in metric_mapping.items():
                if audit_name in lab_data:
                    metrics[metric_name] = {
                        'value': lab_data[audit_name].get('numericValue'),
                        'score': lab_data[audit_name].get('score'),
                        'display_value': lab_data[audit_name].get('displayValue')
                    }
            
            return metrics
        except Exception as e:
            logger.error(f"Error extracting lab data: {str(e)}")
            return {}

    def _extract_field_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract CrUX field data if available."""
        try:
            field_data = data.get('loadingExperience', {}).get('metrics', {})
            metrics = {}
            
            metric_mapping = {
                'LARGEST_CONTENTFUL_PAINT_MS': 'lcp',
                'CUMULATIVE_LAYOUT_SHIFT_SCORE': 'cls',
                'FIRST_INPUT_DELAY_MS': 'fid',
                'INTERACTION_TO_NEXT_PAINT': 'inp'
            }
            
            for api_name, metric_name in metric_mapping.items():
                if api_name in field_data:
                    metrics[metric_name] = {
                        'percentile': field_data[api_name]['percentile'],
                        'distributions': field_data[api_name]['distributions'],
                        'category': field_data[api_name].get('category')
                    }
            
            return metrics
        except Exception as e:
            logger.error(f"Error extracting field data: {str(e)}")
            return {}

    def _extract_performance_score(self, data: Dict[str, Any]) -> Optional[float]:
        """Extract overall performance score."""
        try:
            return data.get('lighthouseResult', {}).get('categories', {}).get('performance', {}).get('score')
        except Exception:
            return None

    def _extract_category_score(self, data: Dict[str, Any], category: str) -> Optional[float]:
        """Extract score for a specific category."""
        try:
            return data.get('lighthouseResult', {}).get('categories', {}).get(category, {}).get('score')
        except Exception:
            return None

    def _extract_opportunities(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract improvement opportunities."""
        try:
            audits = data.get('lighthouseResult', {}).get('audits', {})
            opportunities = {}
            
            for audit_id, audit_data in audits.items():
                if audit_data.get('details', {}).get('type') == 'opportunity':
                    opportunities[audit_id] = {
                        'title': audit_data.get('title'),
                        'description': audit_data.get('description'),
                        'score': audit_data.get('score'),
                        'numeric_value': audit_data.get('numericValue'),
                        'display_value': audit_data.get('displayValue'),
                        'details': audit_data.get('details')
                    }
            
            return opportunities
        except Exception as e:
            logger.error(f"Error extracting opportunities: {str(e)}")
            return {}

    def _extract_diagnostics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract diagnostic information."""
        try:
            audits = data.get('lighthouseResult', {}).get('audits', {})
            diagnostics = {}
            
            for audit_id, audit_data in audits.items():
                if audit_data.get('details', {}).get('type') == 'diagnostic':
                    diagnostics[audit_id] = {
                        'title': audit_data.get('title'),
                        'description': audit_data.get('description'),
                        'score': audit_data.get('score'),
                        'details': audit_data.get('details')
                    }
            
            return diagnostics
        except Exception as e:
            logger.error(f"Error extracting diagnostics: {str(e)}")
            return {}

    def _extract_passed_audits(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract passed audits."""
        try:
            audits = data.get('lighthouseResult', {}).get('audits', {})
            passed = {}
            
            for audit_id, audit_data in audits.items():
                if audit_data.get('score') == 1:
                    passed[audit_id] = {
                        'title': audit_data.get('title'),
                        'description': audit_data.get('description')
                    }
            
            return passed
        except Exception as e:
            logger.error(f"Error extracting passed audits: {str(e)}")
            return {}
