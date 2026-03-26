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
{"sentiment": "interested|not_interested|referral|neutral", "reasoning": "one sentence explaining why"}

Candidate's reply:
---
{reply_text}
---"""


@dataclass
class ClassificationResult:
    sentiment: str
    reasoning: str


class OpenAIClient:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key)

    def classify_reply(self, reply_text: str) -> ClassificationResult:
        """Classify a candidate reply using the configured OpenAI model."""
        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "user", "content": CLASSIFY_PROMPT.format(reply_text=reply_text)},
                ],
                temperature=0,
                max_tokens=150,
            )
        except AuthenticationError as exc:
            raise PermanentError(f"OpenAI authentication error: {exc}") from exc
        except RateLimitError as exc:
            raise ProviderRateLimited() from exc
        except APIError as exc:
            raise TransientError(f"OpenAI API error: {exc}") from exc

        raw_content = response.choices[0].message.content
        if raw_content is None:
            logger.warning("OpenAI returned empty content for classification")
            return ClassificationResult(sentiment="neutral", reasoning="Empty response from classifier")
        content = raw_content.strip()
        try:
            parsed = json.loads(content)
            return ClassificationResult(
                sentiment=parsed["sentiment"].lower(),
                reasoning=parsed.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
            logger.warning("Failed to parse classification response: %s", content)
            return ClassificationResult(sentiment="neutral", reasoning="Classification parse error")
