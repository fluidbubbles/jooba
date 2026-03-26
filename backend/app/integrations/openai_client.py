import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings

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
        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "user", "content": CLASSIFY_PROMPT.format(reply_text=reply_text)},
            ],
            temperature=0,
            max_tokens=150,
        )
        content = response.choices[0].message.content.strip()
        try:
            parsed = json.loads(content)
            return ClassificationResult(
                sentiment=parsed["sentiment"].lower(),
                reasoning=parsed.get("reasoning", ""),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse classification response: %s", content)
            return ClassificationResult(sentiment="neutral", reasoning="Classification parse error")
