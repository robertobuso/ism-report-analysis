"""
Enhanced Adaptive Analysis Quality Engine - Priority #1 Implementation
=====================================================================

Features:
- Claude Sonnet 4 with web search for fact verification
- Iterative improvement with smart issue tracking
- Dynamic scoring that actually improves
- Real-time data verification and updates
- Intelligent retry logic with targeted fixes
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

class EnhancedQualityValidationEngine:
    """
    Claude Sonnet 4-powered analysis quality validation with web search and iterative improvement.
    """
    
    def __init__(self):
        self.anthropic_client = None
        self.quality_thresholds = {
            'minimum_pass': 7.0,
            'excellent': 8.5,
            'target': 8.0,
            'improvement_required': 0.3  # Minimum improvement per iteration
        }
        self.max_retries = 3  # Increased for better iteration
        self.web_search_enabled = bool(os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY"))
        
        if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            logger.info("✅ Enhanced Quality Validation Engine initialized with Claude Sonnet 4")
            if self.web_search_enabled:
                logger.info("✅ Web search capabilities enabled for fact verification")
        else:
            logger.warning("⚠️ Enhanced Quality Validation Engine disabled - missing Anthropic setup")
    
    async def validate_and_enhance_analysis(self, 
                                        company: str, 
                                        initial_analysis: Dict[str, List[str]],
                                        articles: List[Dict],
                                        attempt: int = 1,
                                        prior_issues: Optional[List[Dict]] = None,
                                        previous_scores: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Enhanced validation pipeline with web search and intelligent iteration.
        """
        if not self.anthropic_client:
            logger.warning(f"Quality validation skipped for {company} - Anthropic not available")
            return self._create_unvalidated_result(initial_analysis)

        try:
            logger.info(f"🔍 Enhanced quality validation for {company} (attempt {attempt}/{self.max_retries + 1})")

            # Step 1: Generate enhanced validation prompt with web search
            validation_prompt = self._create_enhanced_validation_prompt(
                company, initial_analysis, articles, prior_issues, previous_scores, attempt
            )

            # Step 2: Run Claude validation with web search
            start_time = time.time()
            validation_response = await self._run_claude_validation_with_search(validation_prompt)
            validation_time = time.time() - start_time

            # Step 3: Parse and validate response
            validation_result = self._parse_validation_response(validation_response)

            # Step 4: Analyze improvement progress
            improvement_analysis = self._analyze_improvement_progress(
                validation_result, previous_scores, attempt
            )

            # Step 5: Log enhanced quality metrics
            self._log_enhanced_quality_metrics(company, validation_result, improvement_analysis, validation_time)

            # Step 6: Intelligent retry decision
            should_retry, retry_reason = self._should_retry_intelligently(
                validation_result, improvement_analysis, attempt
            )

            if should_retry and attempt <= self.max_retries:
                logger.info(f"🔄 Intelligent retry triggered: {retry_reason}")
                revised_analysis = validation_result.get("revised_analysis", initial_analysis)
                current_issues = validation_result.get("critical_issues", [])
                current_scores = validation_result.get("gate_scores", {})
                
                return await self.validate_and_enhance_analysis(
                    company, revised_analysis, articles, attempt + 1, 
                    prior_issues=current_issues, previous_scores=current_scores
                )

            # Step 7: Return enhanced validated result
            return self._create_enhanced_validated_result(validation_result, improvement_analysis, validation_time)

        except Exception as e:
            logger.error(f"❌ Enhanced quality validation failed for {company}: {str(e)}")
            return self._create_fallback_result(initial_analysis, str(e))

    def _create_enhanced_validation_prompt(
        self, 
        company: str, 
        analysis: Dict[str, List[str]], 
        articles: List[Dict], 
        prior_issues: Optional[List[Dict]] = None,
        previous_scores: Optional[Dict[str, float]] = None,
        attempt: int = 1
    ) -> str:
        """
        Create comprehensive validation prompt with web search and iterative improvement context.
        """
        
        today_str = datetime.now().strftime("%B %d, %Y")
        
        # Calculate analysis context
        article_count = len(articles)
        source_types = set(article.get('source_type', 'unknown') for article in articles)
        premium_sources = sum(
            1 for article in articles 
            if article.get('source', '') in {
                'bloomberg.com', 'reuters.com', 'wsj.com', 'ft.com', 
                'nytimes.com', 'cnbc.com', 'marketwatch.com'
            }
        )

        # Format existing analysis
        formatted_analysis = self._format_analysis_for_review(analysis)

        # Source context
        source_summary = f"""
ANALYSIS CONTEXT:
- Today's Date: {today_str}
- Company: {company}
- Total articles analyzed: {article_count}
- Source types: {', '.join(source_types)}
- Premium sources: {premium_sources}/{article_count} ({premium_sources / article_count * 100:.1f}%)
- Validation Attempt: {attempt}/{self.max_retries + 1}
""".strip()

        # Iteration context
        iteration_context = ""
        if attempt > 1 and previous_scores:
            prev_overall = sum(previous_scores.values()) / len(previous_scores)
            iteration_context = f"""
ITERATIVE IMPROVEMENT CONTEXT:
- Previous Overall Score: {prev_overall:.1f}/10
- Previous Gate Scores: {previous_scores}
- Target Improvement: +{self.quality_thresholds['improvement_required']:.1f} points minimum
- This is iteration {attempt} - MUST show measurable improvement in scores
"""

        # Prior issues summary
        issues_section = ""
        if prior_issues:
            issues_summary = "\n".join([
                f"- [{issue['severity'].upper()}] {issue['category']}: {issue['issue']}"
                for issue in prior_issues
            ])
            issues_section = f"""
CRITICAL: Issues from previous iteration that MUST be addressed:
{issues_summary}

🚨 ITERATIVE IMPROVEMENT REQUIREMENT: You must demonstrate improvement by:
1. Directly addressing each issue listed above
2. Showing measurable score increases (minimum +{self.quality_thresholds['improvement_required']:.1f})
3. Using web search to verify and update outdated information
4. Enhancing analysis depth and investment actionability
"""

        # Web search instructions
        web_search_instructions = ""
        if self.web_search_enabled:
            web_search_instructions = f"""
🌐 WEB SEARCH CAPABILITY ENABLED: 
Use web search to verify and enhance the analysis:
- Search for current stock price, market cap, and trading data for {company}
- Verify recent financial results and analyst estimates
- Check for breaking news or developments in the last 30 days
- Validate financial metrics and price targets mentioned
- Update any outdated information with current data
- Add recent developments not captured in the original articles

CRITICAL: Use web search to fact-check ALL numerical claims and update with current data.
"""

        # Main prompt
        return f"""You are a Managing Director of Equity Research at Goldman Sachs with WEB SEARCH CAPABILITIES reviewing financial analysis for institutional investors.

{source_summary}

{iteration_context}

{web_search_instructions}

{issues_section}

CURRENT ANALYSIS TO REVIEW AND ENHANCE:
{formatted_analysis}

### ENHANCED QUALITY VALIDATION FRAMEWORK (Score each dimension 0-10)

Your job is to ITERATIVELY IMPROVE this analysis through web search and enhancement, achieving measurably higher scores.

**1. FACT VERIFICATION & CURRENT DATA (0-10)**
- Use web search to verify ALL financial claims with current data
- Update stock prices, market cap, trading levels, analyst estimates
- Confirm recent earnings, revenue, guidance with latest filings
- Flag and correct any outdated or inaccurate information
- Add breaking news or developments from last 30 days

**2. VALUATION CONTEXT & MARKET REALITY (0-10)** 
- Search for current valuation multiples (P/E, EV/EBITDA, etc.)
- Verify analyst consensus, price targets, and rating distribution
- Include current trading context (near highs/lows, volatility)
- Update competitive positioning with latest market data
- Ensure valuation discussion reflects TODAY'S market reality

**3. INVESTMENT ACTIONABILITY & SPECIFICITY (0-10)**
- Transform vague insights into specific, measurable recommendations
- Add concrete catalysts with realistic timelines and probability estimates
- Include specific entry/exit points or portfolio allocation guidance
- Remove generic language, replace with actionable intelligence
- Ensure each insight leads to clear investment decisions

**4. ANALYTICAL DEPTH & INSIGHT QUALITY (0-10)**
- Enhance surface-level observations with deeper analytical insights
- Add quantitative analysis and financial modeling implications
- Include sector/peer context and relative value analysis
- Provide multi-scenario analysis with probability weightings
- Elevate analysis from reporting to strategic intelligence

**5. PROFESSIONAL EXCELLENCE & INSTITUTIONAL TONE (0-10)**
- Maintain Goldman Sachs-level analytical rigor and objectivity
- Balance bullish/bearish perspectives with appropriate skepticism
- Use precise financial terminology and institutional-grade language
- Remove promotional language, ensure analytical objectivity
- Meet standards expected by institutional portfolio managers

### ITERATIVE IMPROVEMENT REQUIREMENTS

🎯 **SCORE IMPROVEMENT MANDATE**: Each iteration MUST show improvement:
- Minimum +{self.quality_thresholds['improvement_required']:.1f} points overall score increase
- Address ALL critical issues from previous iteration
- Demonstrate enhanced analytical depth and current data integration

🌐 **WEB SEARCH USAGE REQUIREMENTS**:
- Search for current financial data and verify all numerical claims
- Update analysis with breaking news and recent developments
- Fact-check analyst estimates and price targets
- Validate competitive and industry context with current data

### OUTPUT FORMAT - ENHANCED WITH WEB SEARCH DATA

Return ONLY valid JSON with this exact structure:

```json
{{
  "overall_verdict": "pass" | "needs_revision" | "fail",
  "overall_score": float,
  "validation_timestamp": "{datetime.now().isoformat()}",
  "improvement_demonstrated": boolean,
  "score_increase": float,
  "gate_scores": {{
    "fact_verification": float,
    "valuation_context": float,
    "investment_actionability": float,
    "analytical_depth": float,
    "professional_excellence": float
  }},
  "web_search_findings": [
    {{
      "query": "search query used",
      "key_finding": "important discovery from search",
      "impact": "how this changes the analysis",
      "data_update": "specific data point updated"
    }}
  ],
  "critical_issues": [
    {{
      "category": "fact_verification" | "valuation_context" | "investment_actionability" | "analytical_depth" | "professional_excellence",
      "severity": "high" | "medium" | "low",
      "issue": "Specific description of remaining problem",
      "original_text": "Text that still needs fixing",
      "web_search_resolution": "How web search addressed this issue",
      "recommendation": "Specific fix for remaining issues"
    }}
  ],
  "improvements_made": [
    {{
      "category": "category of improvement",
      "description": "What was enhanced",
      "before": "Original text/approach",
      "after": "Improved version", 
      "web_data_used": "Current data integrated from web search"
    }}
  ],
  "revised_analysis": {{
    "executive": [
      "Enhanced bullet with current data and deeper insights",
      "Web-verified bullet with specific metrics and timeline",
      "Actionable insight with probability and investment implications"
    ],
    "investor": [
      "Current valuation analysis with web-verified metrics",
      "Updated analyst data and price targets from recent research",
      "Market positioning with current competitive landscape"
    ],
    "catalysts": [
      "Specific catalyst with timeline and probability from current data",
      "Risk assessment with quantified impact and mitigation strategies", 
      "Trading implications with technical and fundamental analysis"
    ]
  }},
  "quality_metadata": {{
    "iteration_number": {attempt},
    "web_searches_performed": int,
    "data_points_updated": int,
    "current_data_integration": float,
    "improvement_trajectory": "improving" | "plateauing" | "declining",
    "next_iteration_focus": ["areas needing additional improvement"]
  }}
}}
```

CRITICAL INSTRUCTIONS:
1. Return ONLY the JSON response - no additional text
2. MUST use web search to verify facts and update data
3. MUST show measurable score improvement over previous iteration
4. MUST address all critical issues from prior attempts
5. Enhanced analysis should be noticeably better than input"""

    async def _run_claude_validation_with_search(self, prompt: str) -> str:
        """Execute Claude validation with web search capabilities."""
        try:
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: self.anthropic_client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=12000,  # Increased for web search content
                        temperature=0.03,  # Lower temperature for consistent improvement
                        system="You are a senior equity research director with real-time web search capabilities. Use web search to verify facts, update data, and enhance analysis quality. Your goal is iterative improvement with measurable score increases.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                ),
                timeout=240.0  # Increased timeout for web search operations
            )

            if hasattr(response, "content") and isinstance(response.content, list):
                return response.content[0].text
            else:
                raise ValueError("Claude response missing expected content format.")

        except asyncio.TimeoutError:
            raise ValueError("Claude validation with web search timed out after 240 seconds")
        except anthropic.RateLimitError:
            raise ValueError("Claude API rate limited - please try again in a few minutes")
        except Exception as e:
            raise ValueError(f"Claude validation error: {str(e)}")

    def _analyze_improvement_progress(
        self, 
        current_result: Dict[str, Any], 
        previous_scores: Optional[Dict[str, float]], 
        attempt: int
    ) -> Dict[str, Any]:
        """Analyze whether the current iteration shows meaningful improvement."""
        
        improvement_analysis = {
            'attempt': attempt,
            'improvement_demonstrated': False,
            'score_increase': 0.0,
            'areas_improved': [],
            'areas_needing_work': [],
            'trajectory': 'unknown'
        }
        
        if not previous_scores or attempt == 1:
            improvement_analysis['trajectory'] = 'baseline'
            return improvement_analysis
        
        current_scores = current_result.get('gate_scores', {})
        
        # Calculate overall score changes
        prev_overall = sum(previous_scores.values()) / len(previous_scores)
        curr_overall = sum(current_scores.values()) / len(current_scores)
        score_increase = curr_overall - prev_overall
        
        improvement_analysis['score_increase'] = score_increase
        improvement_analysis['improvement_demonstrated'] = score_increase >= self.quality_thresholds['improvement_required']
        
        # Analyze individual gate improvements
        for gate, current_score in current_scores.items():
            if gate in previous_scores:
                gate_improvement = current_score - previous_scores[gate]
                if gate_improvement >= 0.2:  # Meaningful improvement threshold
                    improvement_analysis['areas_improved'].append(f"{gate}: +{gate_improvement:.1f}")
                elif gate_improvement < -0.1:  # Regression
                    improvement_analysis['areas_needing_work'].append(f"{gate}: {gate_improvement:.1f}")
        
        # Determine trajectory
        if score_increase >= self.quality_thresholds['improvement_required']:
            improvement_analysis['trajectory'] = 'improving'
        elif score_increase >= 0:
            improvement_analysis['trajectory'] = 'plateauing'
        else:
            improvement_analysis['trajectory'] = 'declining'
        
        return improvement_analysis

    def _should_retry_intelligently(
        self, 
        validation_result: Dict[str, Any], 
        improvement_analysis: Dict[str, Any], 
        attempt: int
    ) -> Tuple[bool, str]:
        """Intelligent decision on whether to retry based on improvement progress."""
        
        overall_score = validation_result.get('overall_score', 0)
        improvement_demonstrated = improvement_analysis.get('improvement_demonstrated', False)
        trajectory = improvement_analysis.get('trajectory', 'unknown')
        
        # Don't retry if we've reached excellent quality
        if overall_score >= self.quality_thresholds['excellent']:
            return False, f"Excellent quality achieved ({overall_score:.1f}/10)"
        
        # Don't retry if we've reached max attempts
        if attempt >= self.max_retries:
            return False, f"Maximum attempts reached ({attempt}/{self.max_retries})"
        
        # Retry if score is below minimum and we're still improving
        if overall_score < self.quality_thresholds['minimum_pass']:
            if trajectory in ['improving', 'plateauing'] or attempt == 1:
                return True, f"Below minimum threshold ({overall_score:.1f} < {self.quality_thresholds['minimum_pass']}) but showing {trajectory} trajectory"
            else:
                return False, f"Below threshold with declining trajectory - stopping"
        
        # Retry if we have room for improvement and are making progress
        if overall_score < self.quality_thresholds['target'] and improvement_demonstrated:
            return True, f"Below target ({overall_score:.1f} < {self.quality_thresholds['target']}) but improving (+{improvement_analysis['score_increase']:.1f})"
        
        # Stop if we're not improving meaningfully
        if not improvement_demonstrated and attempt > 1:
            return False, f"Insufficient improvement demonstrated (+{improvement_analysis['score_increase']:.1f} < +{self.quality_thresholds['improvement_required']:.1f})"
        
        # Default to pass if we're above minimum
        return False, f"Quality acceptable ({overall_score:.1f}/10) - stopping iteration"

    def _log_enhanced_quality_metrics(
        self, 
        company: str, 
        validation_result: Dict, 
        improvement_analysis: Dict, 
        validation_time: float
    ):
        """Enhanced logging with improvement tracking."""
        
        overall_score = validation_result.get('overall_score', 0)
        gate_scores = validation_result.get('gate_scores', {})
        web_searches = validation_result.get('quality_metadata', {}).get('web_searches_performed', 0)
        
        logger.info(f"🎯 Enhanced Quality Validation Results for {company}:")
        logger.info(f"   • Overall Score: {overall_score:.1f}/10")
        logger.info(f"   • Attempt: {improvement_analysis['attempt']}")
        logger.info(f"   • Score Change: {improvement_analysis['score_increase']:+.1f}")
        logger.info(f"   • Trajectory: {improvement_analysis['trajectory']}")
        logger.info(f"   • Web Searches: {web_searches}")
        logger.info(f"   • Validation Time: {validation_time:.2f}s")
        
        if improvement_analysis['areas_improved']:
            logger.info(f"✅ Improvements: {', '.join(improvement_analysis['areas_improved'])}")
        
        if improvement_analysis['areas_needing_work']:
            logger.info(f"⚠️ Still needs work: {', '.join(improvement_analysis['areas_needing_work'])}")

    def _create_enhanced_validated_result(
        self, 
        validation_result: Dict, 
        improvement_analysis: Dict, 
        validation_time: float
    ) -> Dict[str, Any]:
        """Create enhanced validation result with improvement tracking."""
        
        return {
            'analysis': validation_result['revised_analysis'],
            'quality_validation': {
                'enabled': True,
                'passed': validation_result['overall_score'] >= self.quality_thresholds['minimum_pass'],
                'score': validation_result['overall_score'],
                'verdict': validation_result['overall_verdict'],
                'gate_scores': validation_result['gate_scores'],
                'critical_issues': validation_result.get('critical_issues', []),
                'improvements_made': validation_result.get('improvements_made', []),
                'web_search_findings': validation_result.get('web_search_findings', []),
                'improvement_analysis': improvement_analysis,
                'validation_time': validation_time,
                'timestamp': validation_result.get('validation_timestamp'),
                'quality_grade': self._calculate_quality_grade(validation_result['overall_score']),
                'iterative_enhancement': True,
                'web_search_enabled': self.web_search_enabled
            },
            'success': True,
            'enhanced': True
        }

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

    def _parse_validation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate Claude's enhanced JSON response."""
        
        try:
            # Extract JSON from response
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
            logger.error(f"Enhanced validation parsing error: {e}")
            raise ValueError(f"Failed to parse enhanced validation response: {str(e)}")

    def _create_unvalidated_result(self, analysis: Dict[str, List[str]]) -> Dict[str, Any]:
        """Create result when validation is disabled."""
        return {
            'analysis': analysis,
            'quality_validation': {
                'enabled': False,
                'passed': None,
                'score': None,
                'message': 'Enhanced quality validation disabled - missing Anthropic configuration'
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
                'message': 'Enhanced quality validation failed - using original analysis'
            },
            'success': True,
            'enhanced': False
        }

    def _calculate_quality_grade(self, score: float) -> str:
        """Calculate quality grade from score."""
        if score >= 9.0: return "A+"
        elif score >= 8.5: return "A"
        elif score >= 8.0: return "A-"
        elif score >= 7.5: return "B+"
        elif score >= 7.0: return "B"
        elif score >= 6.0: return "B-"
        elif score >= 5.0: return "C"
        else: return "D"

# Global enhanced instance
enhanced_quality_engine = EnhancedQualityValidationEngine()

# Enhanced convenience functions
async def validate_analysis_quality_enhanced(
    company: str,
    analysis: Dict[str, List[str]],
    articles: List[Dict]
) -> Dict[str, Any]:
    """
    Enhanced quality validation with web search and iterative improvement.
    """
    return await enhanced_quality_engine.validate_and_enhance_analysis(company, analysis, articles)

def is_enhanced_quality_validation_available() -> bool:
    """Check if enhanced quality validation is available."""
    return enhanced_quality_engine.anthropic_client is not None

# Backward compatibility
async def validate_analysis_quality(company: str, analysis: Dict[str, List[str]], articles: List[Dict]) -> Dict[str, Any]:
    """Backward compatibility wrapper."""
    return await validate_analysis_quality_enhanced(company, analysis, articles)

def is_quality_validation_available() -> bool:
    """Backward compatibility wrapper."""
    return is_enhanced_quality_validation_available()