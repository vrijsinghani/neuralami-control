from typing import List, Dict, Any
from apps.common.services.llm_service import LLMService
from apps.seo_audit.models import SEOAuditIssue, SEORemediationPlan
import logging
from apps.common.tools.user_activity_tool import user_activity_tool
import requests

logger = logging.getLogger(__name__)

class RemediationService:
    """Service for generating and managing SEO remediation plans"""

    def __init__(self, user=None):
        self.llm_service = LLMService(user=user)
        self.user = user
        
    async def generate_plan(
        self,
        url: str,
        issues: List[SEOAuditIssue],
        provider_type: str,
        model: str,
        client_profile: str = ""
    ) -> Dict[str, Any]:
        """Generate a remediation plan for given URL and issues"""
        try:
            logger.debug(f"Generating remediation plan for {url} with provider: {provider_type}, model: {model}")
            # Step 1: Analyze issues and create structured analysis
            analysis = await self._analyze_issues(
                provider_type=provider_type,
                model=model,
                url=url,
                issues=issues,
                client_profile=client_profile
            )
            # Step 2: Generate actionable recommendations
            recommendations = await self._generate_recommendations(
                provider_type=provider_type,
                model=model,
                analysis=analysis,
                issues=issues
            )
            # Step 3: Create validation steps
            validation_steps = await self._create_validation_steps(
                provider_type=provider_type,
                model=model,
                recommendations=recommendations
            )
            user_activity_tool.run(self.user, 'update', f"Generated remediation plan for {url}")

            return {
                'analysis': analysis,
                'recommendations': recommendations,
                'validation_steps': validation_steps,
                'metadata': {
                    'url': url,
                    'issue_count': len(issues),
                    'provider': provider_type,
                    'model': model
                }
            }

        except Exception as e:
            logger.error(f"Error generating remediation plan for {url}: {str(e)}")
            raise

    async def _analyze_issues(
        self, 
        provider_type: str,
        model: str,
        url: str,
        issues: List[SEOAuditIssue],
        client_profile: str
    ) -> Dict[str, Any]:
        """Analyze issues and create structured analysis"""
        
        prompt = self._create_analysis_prompt(issues, url, client_profile)
        
        response = await self.llm_service.get_completion(
            messages=[{"role": "user", "content": prompt}],
            provider_type=provider_type,
            model=model,
            response_format={
                "type": "json_object",
                "schema": {
                    "type": "object",
                    "properties": {
                        "critical_issues": {"type": "array"},
                        "high_priority": {"type": "array"},
                        "medium_priority": {"type": "array"},
                        "low_priority": {"type": "array"},
                        "summary": {"type": "string"},
                        "impact_analysis": {"type": "string"}
                    }
                }
            }
        )
        
        return response

    async def _generate_recommendations(
        self,
        provider_type: str,
        model: str,
        analysis: Dict[str, Any],
        issues: List[SEOAuditIssue]
    ) -> Dict[str, Any]:
        """Generate detailed recommendations based on analysis"""
        
        prompt = self._create_recommendations_prompt(analysis, issues)
        
        response = await self.llm_service.get_completion(
            messages=[{"role": "user", "content": prompt}],
            provider_type=provider_type,
            model=model,
            response_format={
                "type": "json_object",
                "schema": {
                    "type": "object",
                    "properties": {
                        "recommendations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "issue": {"type": "string"},
                                    "solution": {"type": "string"},
                                    "implementation_steps": {"type": "array"},
                                    "priority": {"type": "string"},
                                    "estimated_effort": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        )
        
        return response

    async def _create_validation_steps(
        self,
        provider_type: str,
        model: str,
        recommendations: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create validation steps for each recommendation"""
        
        prompt = self._create_validation_prompt(recommendations)
        
        response = await self.llm_service.get_completion(
            messages=[{"role": "user", "content": prompt}],
            provider_type=provider_type,
            model=model,
            response_format={
                "type": "json_object",
                "schema": {
                    "type": "object",
                    "properties": {
                        "validation_steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "recommendation_id": {"type": "integer"},
                                    "validation_steps": {"type": "array"},
                                    "success_criteria": {"type": "string"},
                                    "tools_needed": {"type": "array"}
                                }
                            }
                        }
                    }
                }
            }
        )
        
        return response

    def _create_analysis_prompt(
        self,
        issues: List[SEOAuditIssue],
        url: str,
        client_profile: str
    ) -> str:
        """Create prompt for issue analysis"""
        return f"""Analyze the following SEO issues for {url}:
        
Issues:
{self._format_issues(issues)}

Client Profile:
{client_profile}

Provide a structured analysis including:
1. Categorization of issues by severity
2. Impact assessment
3. Summary of key problems
4. Potential business impact

Use terminology that a marketer could understand, not too technical, but accurate and precise enough for reader to be able to research.
Give guidance for a Wordpress user.
Format the response as a JSON object with critical_issues, high_priority, medium_priority, low_priority arrays, plus summary and impact_analysis strings."""

    def _create_recommendations_prompt(
        self,
        analysis: Dict[str, Any],
        issues: List[SEOAuditIssue]
    ) -> str:
        """Create prompt for generating recommendations"""
        return f"""Based on this analysis:
{analysis}

Generate detailed recommendations that:
1. Address each issue with specific solutions
2. Include step-by-step implementation instructions
3. Prioritize fixes based on impact and effort
4. Consider dependencies between fixes

Use terminology that a marketer could understand, not too technical, but accurate and precise enough for reader to be able to research.
Give guidance for a Wordpress/Rank Math SEO/Site Kit user.
Format as JSON with recommendations array containing objects with issue, solution, implementation_steps, priority, and estimated_effort."""

    def _create_validation_prompt(self, recommendations: Dict[str, Any]) -> str:
        """Create prompt for validation steps"""
        return f"""For these recommendations:
{recommendations}

Create validation steps that:
1. Verify each fix was implemented correctly
2. Include specific testing steps
3. Define success criteria
4. List required validation tools

Use terminology that a marketer could understand, not too technical, but accurate and precise enough for reader to be able to research.
Give guidance for a Wordpress user.
Format as JSON with validation_steps array containing objects with recommendation_id, validation_steps array, success_criteria, and tools_needed array."""

    def _format_issues(self, issues: List[SEOAuditIssue]) -> str:
        """Format issues for prompt inclusion"""
        return "\n".join([
            f"- {issue.get_issue_type_display()} ({issue.get_severity_display()}): "
            f"{issue.details.get('issue', str(issue.details))}"
            for issue in issues
        ]) 