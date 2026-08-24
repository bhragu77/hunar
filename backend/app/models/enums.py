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


class AttendanceStatus(str, Enum):
    pending = "pending"
    present = "present"
    absent = "absent"
    unreachable = "unreachable"


class AttendanceSource(str, Enum):
    supervisor_call = "supervisor_call"
    missed_call = "missed_call"
    manual = "manual"
    worker_call = "worker_call"
