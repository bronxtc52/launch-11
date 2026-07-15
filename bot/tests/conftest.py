import pytest
from launch11bot.db.memory_repo import InMemoryRepo
from launch11bot.pipeline.orchestrator import Orchestrator


class FakeSettings:
    max_context_messages = 40
    max_artifact_bytes = 20000
    max_session_artifact_bytes = 200000
    allowed_user_ids = {201374791}


@pytest.fixture
def repo():
    return InMemoryRepo()


@pytest.fixture
def orch(repo):
    return Orchestrator(repo, FakeSettings())
