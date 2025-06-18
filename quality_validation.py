"""
Adaptive Analysis Quality Engine - Priority #1 Implementation
============================================================

Uses Claude Sonnet 4 to validate and enhance financial analysis quality
ensuring consistent PayPal-level output across all companies.
"""

import os
import json
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.error("Anthropic library required for quality validation: pip install anthropic")

class QualityValidationEngine:
    """
    Claude Sonnet 4-powered analysis quality validation and enhancement.
    """
    
    def __init__(self):
        self.anthropic_client = None
        self.quality_thresholds = {
            'minimum_pass': 7.0,
            'excellent': 8.5,
            'target': 8.0
        }
        self.max_retries = 2
        
        if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            logger.info("✅ Quality Validation Engine initialized with Claude Sonnet 4")
        else:
            logger.warning("⚠️ Quality Validation Engine disabled - missing Anthropic setup")
    
    async def validate_and_enhance_analysis(self, 
                                        company: str, 
                                        initial_analysis: Dict[str, List[str]],
                                        articles: List[Dict],
                                        attempt: int = 1) -> Dict[str, Any]:
        """
        Main quality validation and enhancement pipeline.
        Includes adaptive retry logic using revised analysis.
        """
        
        if not self.anthropic_client:
            logger.warning(f"Quality validation skipped for {company} - Anthropic not available")
            return self._create_unvalidated_result(initial_analysis)
        
        try:
            logger.info(f"🔍 Starting quality validation for {company} (attempt {attempt}/{self.max_retries + 1})")

            # Step 1: Generate validation prompt
            validation_prompt = self._create_validation_prompt(company, initial_analysis, articles)
            
            # Step 2: Run Claude validation
            start_time = time.time()
            validation_response = await self._run_claude_validation(validation_prompt)
            validation_time = time.time() - start_time
            
            # Step 3: Parse and validate response
            validation_result = self._parse_validation_response(validation_response)
            
            # Step 4: Log quality metrics
            self._log_quality_metrics(company, validation_result, validation_time)
            
            # Step 5: Determine if retry is needed
            score = validation_result.get("overall_score", 0)
            passed = score >= self.quality_thresholds["minimum_pass"]
            
            if not passed and attempt <= self.max_retries:
                logger.warning(
                    f"🔄 Quality score {score:.1f} below threshold "
                    f"{self.quality_thresholds['minimum_pass']}, retrying with revised analysis..."
                )
                revised = validation_result.get("revised_analysis", initial_analysis)
                return await self.validate_and_enhance_analysis(company, revised, articles, attempt + 1)
            
            # Step 6: Return final validated result
            return self._create_validated_result(validation_result, validation_time)
        
        except Exception as e:
            logger.error(f"❌ Quality validation failed for {company}: {str(e)}")
            return self._create_fallback_result(initial_analysis, str(e))

    
    def _create_validation_prompt(self, 
                                company: str, 
                                analysis: Dict[str, List[str]], 
                                articles: List[Dict]) -> str:
        """
        Create comprehensive validation prompt for Claude.
        """
        
        # Calculate analysis context
        article_count = len(articles)
        source_types = set(article.get('source_type', 'unknown') for article in articles)
        premium_sources = sum(1 for article in articles 
                            if article.get('source', '') in [
                                'bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 
                                'nytimes.com', 'cnbc.com', 'marketwatch.com'
                            ])
        
        # Format analysis for review
        formatted_analysis = self._format_analysis_for_review(analysis)
        
        # Create source summary
        source_summary = f"""
ANALYSIS CONTEXT:
- Total articles analyzed: {article_count}
- Source types: {', '.join(source_types)}
- Premium sources: {premium_sources}/{article_count} ({premium_sources/article_count*100:.1f}%)
- Company: {company}
        """.strip()
        
        return f"""You are a Managing Director of Equity Research at Goldman Sachs reviewing a draft financial analysis for institutional investors.

{source_summary}

DRAFT ANALYSIS TO REVIEW:
{formatted_analysis}

Your job is to validate this analysis against professional investment standards and enhance it for institutional-grade quality.

### QUALITY VALIDATION FRAMEWORK (Score each dimension 0-10)

**1. FACT VERIFICATION & ACCURACY**
- Use web search to verify ALL numerical claims (stock returns, price levels, financial metrics)
- Check current stock price and trading levels
- Verify analyst price targets, ratings, and estimates  
- Confirm financial data (revenue, earnings, margins) from recent filings
- Flag any unverifiable or outdated claims

**2. VALUATION CONTEXT & RISK ASSESSMENT**
- Ensure current stock price and valuation metrics are stated
- Include proper risk context (near highs/lows, volatility, beta)
- Verify P/E ratios, EV/EBITDA, and other valuation multiples
- Check analyst consensus and price target ranges
- Assess whether valuation discussion matches current market reality

**3. PROBABILITY DISCIPLINE & METHODOLOGY**
- Remove unsupported probability percentages ("70% probability of success")
- Replace with appropriate qualitative language ("likely", "possible", "uncertain")
- Only allow probabilities if clear methodology is provided
- Ensure forecasts are appropriately hedged and sourced

**4. INVESTMENT ACTIONABILITY & SPECIFICITY**
- Ensure insights lead to clear investment implications
- Replace vague statements with specific, actionable insights
- Include concrete catalysts with realistic timelines
- Provide measurable risk/reward assessments
- Remove generic "monitor developments" type language

**5. PROFESSIONAL TONE & INSTITUTIONAL QUALITY**
- Remove promotional or hype language
- Ensure analytical objectivity and professional skepticism
- Maintain institutional-grade gravitas
- Remove speculative or sensational claims
- Ensure consistent professional financial terminology

### CRITICAL VALIDATION CHECKS
- Is the stock price/performance data current and accurate?
- Are strategic developments properly sourced and contextualized?
- Do financial projections have reasonable basis?
- Are competitive dynamics accurately represented?
- Is regulatory/business risk properly assessed?

### ENHANCEMENT REQUIREMENTS
- Each bullet point should be investment-actionable
- Include specific financial metrics where available
- Provide timeline context for key developments
- Balance bullish and bearish perspectives appropriately
- Cite sources naturally without overwhelming the analysis

### OUTPUT FORMAT
Return ONLY a valid JSON response with this exact structure:

```json
{{
  "overall_verdict": "pass" | "needs_revision" | "fail",
  "overall_score": float,
  "validation_timestamp": "{datetime.now().isoformat()}",
  "gate_scores": {{
    "fact_verification": float,
    "valuation_context": float,
    "probability_discipline": float, 
    "investment_actionability": float,
    "professional_tone": float
  }},
  "critical_issues": [
    {{
      "category": "fact_verification" | "valuation_context" | "probability_discipline" | "investment_actionability" | "professional_tone",
      "severity": "high" | "medium" | "low",
      "issue": "Specific description of the problem",
      "original_text": "Exact text that needs fixing",
      "web_search_finding": "What web search revealed (if applicable)",
      "recommendation": "How to fix this issue"
    }}
  ],
  "enhancements_made": [
    "List of specific improvements made to the analysis"
  ],
  "revised_analysis": {{
    "executive": [
      "Enhanced bullet point 1 with specific metrics and sources",
      "Enhanced bullet point 2 with investment implications",
      "Enhanced bullet point 3 with timeline and risk context"
    ],
    "investor": [
      "Enhanced investor insight 1 with valuation context",
      "Enhanced investor insight 2 with analyst data", 
      "Enhanced investor insight 3 with market positioning"
    ],
    "catalysts": [
      "Enhanced catalyst 1 with probability and timeline",
      "Enhanced catalyst 2 with risk quantification",
      "Enhanced catalyst 3 with market impact assessment"
    ]
  }},
  "quality_metadata": {{
    "target_score": 8.0,
    "improvement_areas": ["List areas for future enhancement"],
    "validation_confidence": float,
    "sources_verified": int
  }}
}}
CRITICAL: Return ONLY the JSON response. No additional text or explanation."""

    def _format_analysis_for_review(self, analysis: Dict[str, List[str]]) -> str:
        """Format analysis sections for Claude review."""
        
        formatted = "CURRENT ANALYSIS:\n\n"
        
        section_headers = {
            'executive': '**EXECUTIVE SUMMARY**',
            'investor': '**INVESTOR INSIGHTS**', 
            'catalysts': '**CATALYSTS & RISKS**'
        }
        
        for section_key, bullets in analysis.items():
            header = section_headers.get(section_key, f'**{section_key.upper()}**')
            formatted += f"{header}\n"
            
            for i, bullet in enumerate(bullets, 1):
                # Strip any existing HTML formatting for Claude review
                clean_bullet = bullet.replace('<strong>', '').replace('</strong>', '')
                clean_bullet = clean_bullet.replace('<em>', '').replace('</em>', '')
                clean_bullet = clean_bullet.replace('&amp;', '&')
                formatted += f"{i}. {clean_bullet}\n"
            
            formatted += "\n"
        
        return formatted

    async def _run_claude_validation(self, prompt: str) -> str:
        """Execute Claude validation with proper error handling."""
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.anthropic_client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=8000,
                        temperature=0.05,
                        system="You are a senior equity research editor with web search capabilities, validating financial analysis for institutional investors.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                ),
                timeout=180.0
            )

            # Extract .content[0].text safely
            if hasattr(response, "content") and isinstance(response.content, list):
                return response.content[0].text
            else:
                raise ValueError("Claude response is missing expected content format.")

        except asyncio.TimeoutError:
            raise ValueError("Claude validation timed out after 180 seconds")
        except anthropic.RateLimitError:
            raise ValueError("Claude API rate limited - please try again in a few minutes")
        except Exception as e:
            raise ValueError(f"Claude validation error: {str(e)}")

    def _parse_validation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate Claude's JSON response."""
        
        try:
            # Extract JSON from response (handle markdown formatting)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in Claude response")
            
            json_text = response_text[json_start:json_end]
            result = json.loads(json_text)
            
            # Validate required fields
            required_fields = ['overall_verdict', 'overall_score', 'gate_scores', 'revised_analysis']
            for field in required_fields:
                if field not in result:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate score ranges
            if not (0 <= result['overall_score'] <= 10):
                raise ValueError(f"Invalid overall_score: {result['overall_score']}")
            
            for gate, score in result['gate_scores'].items():
                if not (0 <= score <= 10):
                    raise ValueError(f"Invalid gate score for {gate}: {score}")
            
            # Validate revised analysis structure
            revised = result['revised_analysis']
            required_sections = ['executive', 'investor', 'catalysts']
            for section in required_sections:
                if section not in revised or not isinstance(revised[section], list):
                    raise ValueError(f"Invalid revised_analysis section: {section}")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            logger.error(f"Response text: {response_text[:500]}...")
            raise ValueError(f"Invalid JSON in Claude response: {str(e)}")
        except Exception as e:
            logger.error(f"Validation parsing error: {e}")
            raise ValueError(f"Failed to parse validation response: {str(e)}")

    def _log_quality_metrics(self, company: str, validation_result: Dict, validation_time: float):
        """Log detailed quality metrics for monitoring."""
        
        overall_score = validation_result.get('overall_score', 0)
        gate_scores = validation_result.get('gate_scores', {})
        issues = validation_result.get('critical_issues', [])
        
        logger.info(f"🎯 Quality Validation Results for {company}:")
        logger.info(f"   • Overall Score: {overall_score:.1f}/10")
        logger.info(f"   • Verdict: {validation_result.get('overall_verdict', 'unknown')}")
        logger.info(f"   • Validation Time: {validation_time:.2f}s")
        
        logger.info(f"📊 Gate Scores:")
        for gate, score in gate_scores.items():
            logger.info(f"   • {gate}: {score:.1f}/10")
        
        if issues:
            logger.info(f"⚠️ Issues Found: {len(issues)}")
            for issue in issues:
                severity = issue.get('severity', 'unknown')
                category = issue.get('category', 'unknown')
                logger.info(f"   • {severity.upper()} {category}: {issue.get('issue', 'No description')}")
        
        # Log to structured format for monitoring
        quality_log = {
            'timestamp': datetime.now().isoformat(),
            'company': company,
            'overall_score': overall_score,
            'gate_scores': gate_scores,
            'validation_time': validation_time,
            'issues_count': len(issues),
            'verdict': validation_result.get('overall_verdict'),
            'passed_threshold': overall_score >= self.quality_thresholds['minimum_pass']
        }
        
        # You can extend this to write to a monitoring system
        logger.info(f"📈 Quality Metrics: {json.dumps(quality_log)}")

    def _create_validated_result(self, validation_result: Dict, validation_time: float) -> Dict[str, Any]:
        """Create successful validation result."""
        
        return {
            'analysis': validation_result['revised_analysis'],
            'quality_validation': {
                'enabled': True,
                'passed': validation_result['overall_score'] >= self.quality_thresholds['minimum_pass'],
                'score': validation_result['overall_score'],
                'verdict': validation_result['overall_verdict'],
                'gate_scores': validation_result['gate_scores'],
                'critical_issues': validation_result.get('critical_issues', []),
                'enhancements_made': validation_result.get('enhancements_made', []),
                'validation_time': validation_time,
                'timestamp': validation_result.get('validation_timestamp'),
                'quality_grade': self._calculate_quality_grade(validation_result['overall_score'])
            },
            'success': True,
            'enhanced': True
        }

    def _create_unvalidated_result(self, analysis: Dict[str, List[str]]) -> Dict[str, Any]:
        """Create result when validation is disabled."""
        
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': False,
                'passed': None,
                'score': None,
                'message': 'Quality validation disabled - missing Anthropic configuration'
            },
            'success': True,
            'enhanced': False
        }

    def _create_fallback_result(self, analysis: Dict[str, List[str]], error: str) -> Dict[str, Any]:
        """Create fallback result when validation fails."""
        
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': True,
                'passed': False,
                'score': None,
                'error': error,
                'message': 'Quality validation failed - using original analysis'
            },
            'success': True,
            'enhanced': False
        }

    def _calculate_quality_grade(self, score: float) -> str:
        """Calculate quality grade from score."""
        
        if score >= 9.0:
            return "A+"
        elif score >= 8.5:
            return "A"
        elif score >= 8.0:
            return "A-"
        elif score >= 7.5:
            return "B+"
        elif score >= 7.0:
            return "B"
        elif score >= 6.0:
            return "B-"
        elif score >= 5.0:
            return "C"
        else:
            return "D"

# Global instance
quality_engine = QualityValidationEngine()

# Convenience functions for integration
async def validate_analysis_quality(
    company: str,
    analysis: Dict[str, List[str]],
    articles: List[Dict]
) -> Dict[str, Any]:
    """
    Convenience function for quality validation.
    """
    return await quality_engine.validate_and_enhance_analysis(company, analysis, articles)

def is_quality_validation_available() -> bool:
    """Check if quality validation is available."""
    return quality_engine.anthropic_client is not None
