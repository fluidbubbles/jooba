import json
import logging
from dataclasses import dataclass

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from app.core.config import settings
from app.services.exceptions import PermanentError, ProviderRateLimited, TransientError

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """You are an AI assistant for a recruiting tool. Classify the candidate's email reply into one of these categories:

- INTERESTED: The candidate expresses interest in the opportunity (wants to learn more, asks about the role, proposes a meeting).
- NOT_INTERESTED: The candidate declines (happy where they are, not looking, says no thanks).
- REFERRAL: The candidate refers someone else (mentions another person's name and/or email to contact instead).
- NEUTRAL: Anything else (asks a question without clear interest/disinterest, ambiguous response).

Reply ONLY with valid JSON:
{{"sentiment": "interested|not_interested|referral|neutral", "reasoning": "one sentence explaining why"}}

Candidate's reply:
---
{reply_text}
---"""

EXTRACT_REFERRAL_PROMPT = """Extract the referred person's contact information from this email reply.
The sender is referring someone else for a job opportunity.

Return ONLY valid JSON:
{{"name": "Full Name or null", "email": "email@example.com or null", "title": "Job Title or null", "company": "Company or null"}}

If a field cannot be determined, use null.

Email reply:
---
{reply_text}
---"""


@dataclass
class ClassificationResult:
    sentiment: str
    reasoning: str


@dataclass
class ReferralExtraction:
    name: str | None
    email: str | None
    title: str | None
    company: str | None


def _clean_opt_str(parsed: dict, key: str) -> str | None:
    """Extract an optional trimmed string from a parsed JSON dict."""
    value = parsed.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


class OpenAIClient:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)

    def _chat_completion(self, *, user_content: str, max_tokens: int):
        try:
            return self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": user_content}],
                temperature=0,
                max_tokens=max_tokens,
            )
        except AuthenticationError as exc:
            raise PermanentError(f"OpenAI authentication error: {exc}") from exc
        except RateLimitError as exc:
            raise ProviderRateLimited() from exc
        except APIError as exc:
            raise TransientError(f"OpenAI API error: {exc}") from exc

    def classify_reply(self, reply_text: str) -> ClassificationResult:
        """Classify a candidate reply using the configured OpenAI model."""
        response = self._chat_completion(
            user_content=CLASSIFY_PROMPT.format(reply_text=reply_text),
            max_tokens=150,
        )

        raw_content = response.choices[0].message.content
        if raw_content is None:
            raise TransientError("OpenAI returned empty content for classification")
        content = raw_content.strip()
        try:
            parsed = json.loads(content)
            return ClassificationResult(
                sentiment=parsed["sentiment"].lower(),
                reasoning=parsed.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
            raise TransientError(f"Failed to parse classification response: {content}") from exc

    def extract_referral(self, reply_text: str) -> ReferralExtraction:
        """Extract referred contact info from a referral reply."""
        response = self._chat_completion(
            user_content=EXTRACT_REFERRAL_PROMPT.format(reply_text=reply_text),
            max_tokens=200,
        )

        raw_content = response.choices[0].message.content
        if raw_content is None:
            raise TransientError("OpenAI returned empty content for referral extraction")
        content = raw_content.strip()
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise TypeError("expected JSON object")

            return ReferralExtraction(
                name=_clean_opt_str(parsed, "name"),
                email=_clean_opt_str(parsed, "email"),
                title=_clean_opt_str(parsed, "title"),
                company=_clean_opt_str(parsed, "company"),
            )
        except (json.JSONDecodeError, TypeError) as exc:
            raise TransientError(f"Failed to parse referral extraction response: {content}") from exc
