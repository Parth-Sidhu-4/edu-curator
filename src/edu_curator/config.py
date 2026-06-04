from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    llm_provider: str = "cerebras"
    cerebras_api_key: str | None = None
    hf_token: str | None = None
    extraction_model: str
    generation_model: str
    supabase_url: str | None = None
    supabase_key: str | None = None
    use_batch_api: bool = False
    # Phase 1: Alembic
    database_url: str | None = None
    # Phase 2: Ingestion
    playwright_enabled: bool = False
    # LiteLLM fallback config
    groq_api_key: str | None = None
    fallback_model: str = "llama-3.3-70b-versatile"
    litellm_fallback_enabled: bool = False
    # Langfuse tracing
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    # Redis cache
    redis_url: str | None = None
    llm_cache_enabled: bool = False
    llm_cache_ttl_seconds: int = 86400
    log_level: str = "INFO"


def load_settings(root: Path) -> Settings:
    load_dotenv(root / ".env")
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "cerebras").lower(),
        cerebras_api_key=os.getenv("CEREBRAS_API_KEY"),
        hf_token=os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN"),
        extraction_model=os.environ.get("EXTRACTION_MODEL", ""),
        generation_model=os.environ.get("GENERATION_MODEL", ""),
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_key=os.getenv("SUPABASE_KEY"),
        use_batch_api=os.getenv("USE_BATCH_API", "False").lower() in {"true", "1", "yes"},
        database_url=os.getenv("DATABASE_URL"),
        playwright_enabled=os.getenv("PLAYWRIGHT_ENABLED", "false").lower() in {"true", "1", "yes"},
        groq_api_key=os.getenv("GROQ_API_KEY"),
        fallback_model=os.getenv("LITELLM_FALLBACK_MODEL", "llama-3.3-70b-versatile"),
        litellm_fallback_enabled=os.getenv("LITELLM_FALLBACK_ENABLED", "False").lower()
        in {"true", "1", "yes"},
        langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        langfuse_host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        redis_url=os.getenv("REDIS_URL") or None,
        llm_cache_enabled=os.getenv("LLM_CACHE_ENABLED", "False").lower() in {"true", "1", "yes"},
        llm_cache_ttl_seconds=int(os.getenv("LLM_CACHE_TTL_SECONDS", "86400")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
