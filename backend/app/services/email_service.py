from app.core.config import settings
from app.models.candidate import Candidate
from app.models.sequence import SequenceStep
from app.utils.templates import append_unsubscribe_footer, replace_placeholders


class EmailService:
    @staticmethod
    def compose(step: SequenceStep, candidate: Candidate, unsubscribe_token: str) -> dict:
        """Compose an email from a sequence step + candidate data."""
        candidate_data = {
            "first_name": candidate.first_name or "",
            "last_name": candidate.last_name or "",
            "company": candidate.company or "",
            "title": candidate.title or "",
            "email": candidate.email,
        }

        subject = replace_placeholders(step.subject, candidate_data)
        body = replace_placeholders(step.body_html, candidate_data)

        unsubscribe_url = f"{settings.unsubscribe_base_url}/{unsubscribe_token}"
        body = append_unsubscribe_footer(body, unsubscribe_url)

        return {
            "to": candidate.email,
            "subject": subject,
            "body_html": body,
        }
