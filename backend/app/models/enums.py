from enum import Enum


class Module(str, Enum):
    hiring = "hiring"
    outreach = "outreach"
    attendance = "attendance"


class CallEventSource(str, Enum):
    webhook = "webhook"
    poll = "poll"
    mock = "mock"
    pipeline = "pipeline"  # the post-call transcript/scorecard pipeline, see post_call.py


class PostCallStatus(str, Enum):
    """Shared status shape for both Call.transcript_status and Call.scorecard_status."""

    pending = "pending"
    done = "done"
    failed = "failed"
    skipped = "skipped"
