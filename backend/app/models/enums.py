from enum import Enum


class Module(str, Enum):
    hiring = "hiring"
    outreach = "outreach"
    attendance = "attendance"


class CallEventSource(str, Enum):
    webhook = "webhook"
    poll = "poll"
    mock = "mock"
