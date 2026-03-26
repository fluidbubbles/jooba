from enum import Enum


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    REPLIED = "replied"
    COMPLETED = "completed"
    BOUNCED = "bounced"
    OPTED_OUT = "opted_out"
    PAUSED = "paused"


class Sentiment(str, Enum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    REFERRAL = "referral"
    NEUTRAL = "neutral"


class SequenceStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class EmailDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


VALID_TRANSITIONS: dict[EnrollmentStatus, list[EnrollmentStatus]] = {
    EnrollmentStatus.ACTIVE: [
        EnrollmentStatus.REPLIED,
        EnrollmentStatus.COMPLETED,
        EnrollmentStatus.BOUNCED,
        EnrollmentStatus.OPTED_OUT,
        EnrollmentStatus.PAUSED,
    ],
    EnrollmentStatus.PAUSED: [
        EnrollmentStatus.ACTIVE,
        EnrollmentStatus.OPTED_OUT,
    ],
    EnrollmentStatus.REPLIED: [],
    EnrollmentStatus.COMPLETED: [],
    EnrollmentStatus.BOUNCED: [],
    EnrollmentStatus.OPTED_OUT: [],
}
