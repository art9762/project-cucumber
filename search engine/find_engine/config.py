"""Конфигурация из окружения (.env). Секреты — только отсюда, никогда из кода."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database
    db_url: str = "postgresql+asyncpg://findengine:findengine@localhost:5432/findengine"

    # Secrets / credentials
    github_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "find-engine/0.1"

    # HTTP behavior
    http_timeout: float = 30.0
    http_max_retries: int = 3

    # Sources config (comma-separated in env)
    github_topics: str = "ai,llm,machine-learning,agents"
    reddit_subreddits: str = "MachineLearning,LocalLLaMA,artificial,singularity"
    arxiv_categories: str = "cs.AI,cs.LG,cs.CL"
    hn_query: str = 'AI OR LLM OR "machine learning"'
    hn_min_points: int = 10

    # Scheduler cron per source ("" disables)
    cron_arxiv: str = ""
    cron_hackernews: str = ""
    cron_github: str = ""
    cron_reddit: str = ""

    @property
    def github_topic_list(self) -> list[str]:
        return _split(self.github_topics)

    @property
    def reddit_subreddit_list(self) -> list[str]:
        return _split(self.reddit_subreddits)

    @property
    def arxiv_category_list(self) -> list[str]:
        return _split(self.arxiv_categories)

    def cron_for(self, source: str) -> str:
        return {
            "arxiv": self.cron_arxiv,
            "hackernews": self.cron_hackernews,
            "github": self.cron_github,
            "reddit": self.cron_reddit,
        }.get(source, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
