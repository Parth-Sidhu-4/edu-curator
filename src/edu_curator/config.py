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


def _get_clean_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().strip('"').strip("'")


def load_settings(root: Path) -> Settings:
    load_dotenv(root / ".env")
    
    # Pre-fetch sanitized values to prevent quotes/whitespace issues in any cloud host or shell
    llm_provider = _get_clean_env("LLM_PROVIDER", "cerebras").lower()
    cerebras_api_key = _get_clean_env("CEREBRAS_API_KEY")
    hf_token = _get_clean_env("HF_TOKEN") or _get_clean_env("HUGGINGFACE_HUB_TOKEN")
    extraction_model = _get_clean_env("EXTRACTION_MODEL", "")
    generation_model = _get_clean_env("GENERATION_MODEL", "")
    supabase_url = _get_clean_env("SUPABASE_URL")
    supabase_key = _get_clean_env("SUPABASE_KEY")
    use_batch_api = _get_clean_env("USE_BATCH_API", "False").lower() in {"true", "1", "yes"}
    database_url = _get_clean_env("DATABASE_URL")
    playwright_enabled = _get_clean_env("PLAYWRIGHT_ENABLED", "false").lower() in {"true", "1", "yes"}
    groq_api_key = _get_clean_env("GROQ_API_KEY")
    fallback_model = _get_clean_env("LITELLM_FALLBACK_MODEL", "llama-3.3-70b-versatile")
    litellm_fallback_enabled = _get_clean_env("LITELLM_FALLBACK_ENABLED", "False").lower() in {"true", "1", "yes"}
    langfuse_public_key = _get_clean_env("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key = _get_clean_env("LANGFUSE_SECRET_KEY")
    langfuse_host = _get_clean_env("LANGFUSE_HOST", "https://cloud.langfuse.com")
    redis_url = _get_clean_env("REDIS_URL")
    llm_cache_enabled = _get_clean_env("LLM_CACHE_ENABLED", "False").lower() in {"true", "1", "yes"}
    llm_cache_ttl_seconds = int(_get_clean_env("LLM_CACHE_TTL_SECONDS", "86400") or "86400")
    log_level = _get_clean_env("LOG_LEVEL", "INFO")

    return Settings(
        llm_provider=llm_provider,
        cerebras_api_key=cerebras_api_key,
        hf_token=hf_token,
        extraction_model=extraction_model,
        generation_model=generation_model,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        use_batch_api=use_batch_api,
        database_url=database_url,
        playwright_enabled=playwright_enabled,
        groq_api_key=groq_api_key,
        fallback_model=fallback_model,
        litellm_fallback_enabled=litellm_fallback_enabled,
        langfuse_public_key=langfuse_public_key,
        langfuse_secret_key=langfuse_secret_key,
        langfuse_host=langfuse_host,
        redis_url=redis_url or None,
        llm_cache_enabled=llm_cache_enabled,
        llm_cache_ttl_seconds=llm_cache_ttl_seconds,
        log_level=log_level,
    )
