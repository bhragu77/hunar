from app.providers.base import Agent, Call, CallResult, VoiceProvider

_MOCK_AGENTS: list[Agent] = [
    Agent(
        id="agent_mock_001",
        name="Recruiting Screener",
        voice_persona="friendly_professional",
        language="en-US",
        custom_variables={"role_title": "string", "min_experience_years": "number"},
        result_schema={"interested": "boolean", "years_experience": "number", "notes": "string"},
    ),
    Agent(
        id="agent_mock_002",
        name="Interview Scheduler",
        voice_persona="warm_efficient",
        language="en-US",
        custom_variables={"candidate_name": "string", "available_slots": "string"},
        result_schema={"slot_confirmed": "string", "reschedule_requested": "boolean"},
    ),
    Agent(
        id="agent_mock_003",
        name="Attendance Confirmation",
        voice_persona="neutral_concise",
        language="en-IN",
        custom_variables={"interview_date": "string", "interviewer_name": "string"},
        result_schema={"will_attend": "boolean", "cancellation_reason": "string"},
    ),
]


class MockProvider(VoiceProvider):
    """Returns believable fake data with no external calls, so the app runs standalone."""

    def list_agents(self) -> list[Agent]:
        return list(_MOCK_AGENTS)

    def get_agent(self, agent_id: str) -> Agent:
        for agent in _MOCK_AGENTS:
            if agent.id == agent_id:
                return agent
        raise ValueError(f"Unknown mock agent id: {agent_id}")

    def create_call(self, agent_id: str, phone_number: str) -> Call:
        self.get_agent(agent_id)  # validates the id, raises if unknown
        return Call(id="call_mock_001", agent_id=agent_id, phone_number=phone_number, status="queued")

    def get_call(self, call_id: str) -> Call:
        return Call(id=call_id, agent_id="agent_mock_001", phone_number="+10000000000", status="completed")

    def get_call_result(self, call_id: str) -> CallResult:
        return CallResult(
            call_id=call_id,
            transcript="Hello, this is a mock call transcript.",
            structured_data={"interested": True, "years_experience": 3, "notes": "Mock result."},
        )
