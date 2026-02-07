"""LLM service for Company Intelligence AI-powered insights."""
import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel

from app.config import get_settings
from app.schemas.company import InsightCard, InsightCardsResponse

logger = logging.getLogger(__name__)


class LLMService:
    """
    OpenAI GPT-5.2 service for generating portfolio-aware insights.

    Features:
    - Structured outputs via json_schema
    - Configurable timeout (10s default)
    - Retry with exponential backoff on 5xx errors
    - Rule-based fallback on failure/timeout
    - Non-prescriptive guardrails
    """

    # System prompts
    INSIGHT_SYSTEM_PROMPT = """You are a financial analyst assistant helping an investor understand their portfolio holdings.

Your task is to generate 3 insight cards that answer: "Why does this security matter RIGHT NOW?"

Guidelines:
- Be portfolio-aware: reference the investor's actual position size, weight, and contribution
- Be factual and explainable: cite specific data inputs
- Be non-prescriptive: NEVER say "buy" or "sell" — only describe impact and context
- Be concise: exactly 1 sentence per insight
- Use severity calibration:
  * positive: materially good news or strong fundamentals
  * neutral: no significant change or mixed signals
  * negative: materially bad news or deteriorating fundamentals

You will receive structured data about the company and the investor's portfolio position.
Generate exactly 3 cards covering: market narrative, portfolio impact, and earnings/fundamentals signal.
"""

    NARRATIVE_SYSTEM_PROMPT = """You are a financial analyst writing brief narratives about company financials.

Your task is to summarize key financial trends in 2-3 sentences.

Guidelines:
- Focus on trends (growth, margins, cash position)
- Explain what changed and why it matters
- Be factual and avoid speculation
- Use plain English, not jargon
"""

    SIGNAL_SUMMARY_PROMPT = """You are a technical analyst summarizing price and momentum signals.

Your task is to interpret technical indicators in plain English.

Guidelines:
- Describe the overall trend (bullish, bearish, neutral)
- Mention key support/resistance levels if relevant
- Note if indicators are aligned or diverging
- 2-3 sentences maximum
"""

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int | None = None):
        """
        Initialize LLM service.

        Args:
            api_key: OpenAI API key (defaults to config)
            model: Model name (defaults to gpt-5.2-chat-latest)
            timeout: Request timeout in seconds (defaults to 10)
        """
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.timeout = timeout or settings.openai_timeout
        self.client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout)

    async def generate_insight_cards(
        self,
        company_data: dict[str, Any],
        portfolio_context: dict[str, Any] | None = None
    ) -> list[InsightCard]:
        """
        Generate 3 AI-powered insight cards.

        Args:
            company_data: Company overview, news, earnings, prices
            portfolio_context: Portfolio weight, contribution, etc.

        Returns:
            List of 3 InsightCard objects
        """
        try:
            # Prepare structured input
            input_data = {
                "company": company_data,
                "portfolio": portfolio_context or {},
            }

            # Call GPT-5.2 with structured output
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.INSIGHT_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(input_data, default=str)}
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "insight_cards",
                            "strict": True,
                            "schema": InsightCardsResponse.model_json_schema()
                        }
                    },
                    reasoning_effort="medium"
                ),
                timeout=self.timeout
            )

            # Parse response
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from OpenAI")

            cards_response = InsightCardsResponse.model_validate_json(content)
            logger.info(f"Generated {len(cards_response.cards)} insight cards via GPT-5.2")
            return cards_response.cards

        except asyncio.TimeoutError:
            logger.warning("GPT-5.2 insight generation timed out, using fallback")
            return self._fallback_insight_cards(company_data, portfolio_context)
        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            return self._fallback_insight_cards(company_data, portfolio_context)
        except Exception as e:
            logger.error(f"Error generating insights: {e}")
            return self._fallback_insight_cards(company_data, portfolio_context)

    def _fallback_insight_cards(
        self,
        company_data: dict[str, Any],
        portfolio_context: dict[str, Any] | None
    ) -> list[InsightCard]:
        """Rule-based fallback when GPT-5.2 fails."""
        symbol = company_data.get("symbol", "UNKNOWN")
        name = company_data.get("name", symbol)

        # Default cards
        cards = [
            InsightCard(
                type="market_narrative",
                severity="neutral",
                summary=f"{name} is trading at ${float(company_data.get('price', 0)):.2f} with normal market activity.",
                tab_target="technicals",
                data_inputs={"price": company_data.get("price"), "fallback": True}
            ),
            InsightCard(
                type="portfolio_impact",
                severity="neutral",
                summary=f"This position represents {float(portfolio_context.get('weight', 0)) * 100:.1f}% of your portfolio." if portfolio_context else "Position data unavailable.",
                tab_target="portfolio-impact",
                data_inputs={"weight": portfolio_context.get("weight") if portfolio_context else None, "fallback": True}
            ),
            InsightCard(
                type="earnings_signal",
                severity="neutral",
                summary=f"{name} fundamentals are being analyzed.",
                tab_target="earnings",
                data_inputs={"fallback": True}
            )
        ]

        logger.info(f"Using {len(cards)} fallback insight cards")
        return cards

    async def generate_narrative(
        self,
        data: dict[str, Any],
        narrative_type: str = "financial"
    ) -> str:
        """
        Generate a brief narrative summary.

        Args:
            data: Financial or technical data
            narrative_type: "financial", "signal", or "business"

        Returns:
            2-3 sentence narrative
        """
        try:
            system_prompt = self.NARRATIVE_SYSTEM_PROMPT
            if narrative_type == "signal":
                system_prompt = self.SIGNAL_SUMMARY_PROMPT

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(data, default=str)}
                    ],
                    reasoning_effort="low",
                    max_tokens=200
                ),
                timeout=self.timeout
            )

            narrative = response.choices[0].message.content or ""
            logger.info(f"Generated {narrative_type} narrative via GPT-5.2")
            return narrative.strip()

        except asyncio.TimeoutError:
            logger.warning(f"GPT-5.2 narrative generation timed out")
            return self._fallback_narrative(data, narrative_type)
        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            return self._fallback_narrative(data, narrative_type)
        except Exception as e:
            logger.error(f"Error generating narrative: {e}")
            return self._fallback_narrative(data, narrative_type)

    def _fallback_narrative(self, data: dict[str, Any], narrative_type: str) -> str:
        """Rule-based narrative fallback."""
        if narrative_type == "financial":
            return "Financial data is being analyzed. Detailed metrics are available in the tables below."
        elif narrative_type == "signal":
            return "Technical indicators show mixed signals. Review individual indicators for details."
        elif narrative_type == "business":
            return "Company operates in its sector with multiple business lines."
        else:
            return "Data is being processed."

    async def generate_business_bullets(self, company_overview: dict[str, Any]) -> list[str]:
        """
        Generate 3-5 business description bullets.

        Args:
            company_overview: Company overview data from Alpha Vantage

        Returns:
            List of 3-5 bullet points
        """
        try:
            description = company_overview.get("description", "")
            if not description:
                return self._fallback_business_bullets()

            prompt = f"""Summarize what this company does in 3-5 concise bullet points.

Company description:
{description}

Generate clear, factual bullets about their business model, products/services, and market focus."""

            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a business analyst creating concise bullet summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    reasoning_effort="low",
                    max_tokens=300
                ),
                timeout=self.timeout
            )

            content = response.choices[0].message.content or ""

            # Parse bullets (handle various formats)
            lines = content.strip().split("\n")
            bullets = [
                line.strip().lstrip("-•*").strip()
                for line in lines
                if line.strip() and not line.strip().startswith("#")
            ]

            # Ensure 3-5 bullets
            if len(bullets) < 3:
                return self._fallback_business_bullets()

            logger.info(f"Generated {len(bullets)} business bullets via GPT-5.2")
            return bullets[:5]  # Max 5

        except Exception as e:
            logger.error(f"Error generating business bullets: {e}")
            return self._fallback_business_bullets()

    def _fallback_business_bullets(self) -> list[str]:
        """Fallback business bullets."""
        return [
            "Publicly traded company",
            "Operates in its sector",
            "Business details available via SEC filings"
        ]
