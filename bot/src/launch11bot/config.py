from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .tg.access import parse_allowed


class Settings(BaseSettings):
    launch11_bot_token: SecretStr
    anthropic_api_key: SecretStr
    launch11_model: str = "claude-sonnet-5"
    database_url: str = "postgresql://launch11:launch11@localhost:5432/launch11"
    allowed_tg_user_ids: str = ""
    sentry_dsn: str = ""

    max_context_messages: int = 40
    max_artifact_bytes: int = 20_000
    max_session_artifact_bytes: int = 200_000
    claude_timeout_s: float = 90.0
    claude_max_retries: int = 2

    # billing (Phase 3)
    free_runs: int = 1
    stars_price: int = 100
    stars_label: str = "Прогон пайплайна"
    beta_allowlist_ids: str = ""  # optional rollout kill-switch; empty => billing is the only gate
    owner_ids: str = ""           # owners: unlimited runs, never billed, never beta-gated

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_user_ids(self) -> set[int]:
        return parse_allowed(self.allowed_tg_user_ids)

    @property
    def beta_allowlist(self) -> set[int]:
        return parse_allowed(self.beta_allowlist_ids)

    @property
    def owners(self) -> set[int]:
        return parse_allowed(self.owner_ids)
