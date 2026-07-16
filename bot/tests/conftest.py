import pytest
from launch11bot.db.memory_repo import InMemoryRepo
from launch11bot.pipeline.orchestrator import Orchestrator


class FakeSettings:
    def __init__(self):
        self.max_context_messages = 40
        self.claude_max_tokens = 8000
        self.max_artifact_bytes = 20000
        self.max_session_artifact_bytes = 200000
        self.allowed_user_ids = {424242}
        self.beta_allowlist = set()  # empty => billing is the only gate (Phase 3)


@pytest.fixture
def repo():
    return InMemoryRepo()


@pytest.fixture
def orch(repo):
    return Orchestrator(repo, FakeSettings())
