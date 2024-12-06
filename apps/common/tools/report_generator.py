import json
from typing import Dict, Any
from datetime import datetime

class ReportGenerator:
    @staticmethod
    def generate_seo_report(audit_results: Dict[str, Any], recommendations: str = None) -> str:
        """Generate a comprehensive SEO audit report."""
        report = []
        report.append("=== SEO Audit Report ===")
        report.append(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Crawl Statistics
        if 'crawl_stats' in audit_results:
            report.append("=== Crawl Statistics ===")
            stats = audit_results['crawl_stats']
            report.append(f"Total Pages Crawled: {stats.get('total_pages', 0)}")
            report.append(f"Total Links Found: {stats.get('total_links', 0)}")
            report.append(f"Crawl Time: {stats.get('crawl_time', 0):.2f} seconds\n")

        # Basic Requirements
        report.append("=== Basic Requirements ===")
        report.append(f"SSL Certificate: {'✓ Valid' if audit_results.get('ssl_issues', {}).get('valid_certificate', False) else '✗ Invalid'}")
        report.append(f"Sitemap: {'✓ Present' if audit_results.get('sitemap_present', False) else '✗ Missing'}")
        report.append(f"Robots.txt: {'✓ Present' if audit_results.get('robots_txt_present', False) else '✗ Missing'}\n")

        # Broken Links
        broken_links = audit_results.get('broken_links', [])
        if broken_links:
            report.append("=== Broken Links ===")
            for link in broken_links:
                status = f"(Status: {link['status_code']})" if link.get('status_code') else "(Connection Failed)"
                report.append(f"Source: {link['source_page']}")
                report.append(f"Broken Link: {link['broken_link']} {status}\n")

        # Duplicate Content
        duplicate_content = audit_results.get('duplicate_content', [])
        if duplicate_content:
            report.append("=== Duplicate Content Issues ===")
            for dup in duplicate_content:
                report.append(f"Page: {dup['page_url']}")
                report.append(f"Issue Type: {dup['issue_type']}")
                if dup.get('duplicate_with'):
                    report.append(f"Duplicate With: {dup['duplicate_with']}\n")

        # Meta Tag Issues
        meta_issues = audit_results.get('meta_tag_issues', [])
        if meta_issues:
            report.append("=== Meta Tag Issues ===")
            for issue in meta_issues:
                report.append(f"Page: {issue['page_url']}")
                if issue.get('missing_meta'):
                    report.append(f"Missing Meta Tags: {', '.join(issue['missing_meta'])}")
                if issue.get('duplicate_meta'):
                    report.append(f"Duplicate Meta Tags: {', '.join(issue['duplicate_meta'])}")
                if issue.get('meta_length_issues'):
                    for tag, length in issue['meta_length_issues'].items():
                        report.append(f"{tag.title()} Length: {length} characters")
                report.append("")

        # Page Speed Issues
        if 'page_speed_issues' in audit_results and audit_results['page_speed_issues']:
            report.append("=== Page Speed Issues ===")
            for page, issues in audit_results['page_speed_issues'].items():
                report.append(f"Page: {page}")
                for issue, details in issues.items():
                    report.append(f"{issue}: {details}")
                report.append("")

        # Mobile Friendliness
        report.append("=== Mobile Friendliness ===")
        report.append(f"Mobile Friendly: {'✓ Yes' if audit_results.get('mobile_friendly', True) else '✗ No'}\n")

        # LLM Recommendations
        if recommendations:
            report.append("=== AI-Generated Recommendations ===")
            report.append(recommendations)

        return "\n".join(report)

    @staticmethod
    def generate_json_report(audit_results: Dict[str, Any], recommendations: str = None) -> str:
        """Generate a JSON format report."""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "audit_results": audit_results,
            "recommendations": recommendations
        }
        return json.dumps(report_data, indent=2)
