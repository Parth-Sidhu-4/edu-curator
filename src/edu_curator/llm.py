"""LLM client — Cerebras-compatible chat completions with retry/backoff.

Retry policy (for 429 / 5xx):
  Up to MAX_RETRIES attempts with exponential backoff starting at RETRY_BASE_S
  seconds.  A jitter of ±20 % is applied to avoid thundering-herd.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from edu_curator.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 10  # total attempts (1 initial + 9 retries)
RETRY_BASE_S = 8.0  # first back-off delay in seconds
RETRY_JITTER = 0.20  # ±20 % random jitter
RETRYABLE_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ChatResult:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached: bool = False


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def cerebras_public_models() -> list[dict]:
    request = Request(
        "https://api.cerebras.ai/public/v1/models",
        headers={"Accept": "application/json", "User-Agent": "edu-curator/1.0"},
        method="GET",
    )
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data.get("data", [])


def _log_trace_work(
    settings: Settings,
    messages: list[dict[str, str]],
    result: ChatResult,
    latency_ms: int,
    stage: str,
    topic_sn: int | None,
    model: str | None = None,
) -> None:
    """Blocking inner implementation — always called from a background thread."""
    # (same body as before — moved here so _log_trace never blocks the caller)
    import uuid
    from datetime import datetime
    from pathlib import Path

    trace_id = str(uuid.uuid4())
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    prompt_tokens = result.prompt_tokens or 0
    completion_tokens = result.completion_tokens or 0
    total_tokens = prompt_tokens + completion_tokens

    trace_record = {
        "id": trace_id,
        "ts": ts,
        "stage": stage,
        "topic_sn": topic_sn,
        "model": model
        if model is not None
        else (
            settings.extraction_model
            if stage in {"extract", "extract_batch"}
            else settings.generation_model
        ),
        "prompt": messages,
        "response": result.content,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
    }

    # 1. Local backup writing
    import os
    if os.getenv("LOG_LLM_LOCALLY", "true").lower() in ("true", "1", "yes"):
        try:
            from pathlib import Path
            log_dir = Path(__file__).resolve().parents[2] / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "llm_traces.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(trace_record) + "\n")
        except Exception as exc:
            logger.error(f"Failed to write local trace log: {exc}")

    # 2. Write to repository (Supabase or local JSON fallback)
    try:
        from edu_curator.storage import get_table
        from edu_curator.schemas import LLMTrace

        tbl = get_table("llm_traces", LLMTrace, settings)
        tbl.write([LLMTrace.model_validate(trace_record)])
    except Exception as exc:
        logger.warning(
            f"Failed to write trace to llm_traces repository: {exc}"
        )


def _log_trace(
    settings: Settings,
    messages: list[dict[str, str]],
    result: ChatResult,
    latency_ms: int,
    stage: str,
    topic_sn: int | None,
    model: str | None = None,
) -> None:
    """Fire-and-forget wrapper: runs _log_trace_work in a daemon thread.

    This ensures that DB/file I/O for tracing never adds latency to the
    LLM call path — critical for throughput at scale.
    """
    import threading
    t = threading.Thread(
        target=_log_trace_work,
        args=(settings, messages, result, latency_ms, stage, topic_sn, model),
        daemon=True,
        name="LogTraceWriter",
    )
    t.start()



_redis_client = None
_redis_client_initialized = False


def _get_redis_client(settings: Settings):
    global _redis_client, _redis_client_initialized
    if not _redis_client_initialized:
        if settings.llm_cache_enabled and settings.redis_url:
            try:
                import redis

                # decode_responses=True returns string instead of bytes from redis
                _redis_client = redis.Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0
                )
                logger.info("Connected to Redis cache.")
            except Exception as exc:
                logger.warning(f"Failed to connect to Redis cache: {exc}")
        _redis_client_initialized = True
    return _redis_client


_http_session = None


def _get_http_session():
    global _http_session
    if _http_session is None:
        import requests
        from requests.adapters import HTTPAdapter
        _http_session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=10)
        _http_session.mount("https://", adapter)
    return _http_session


def _try_litellm_fallback(
    settings: Settings,
    messages: list[dict[str, str]],
    temperature: float,
    json_mode: bool,
    redis_client,
    cache_key: str | None,
    stage: str = "unknown",
    topic_sn: int | None = None,
) -> ChatResult | None:
    if not settings.litellm_fallback_enabled or not settings.fallback_model:
        return None

    print(f"  [llm-fallback] Attempting LiteLLM fallback with model: {settings.fallback_model} ...", flush=True)
    start_time = time.perf_counter()
    try:
        import litellm
        litellm.set_verbose = False

        api_key = settings.groq_api_key
        model_name = settings.fallback_model
        if not model_name.startswith(("groq/", "openai/", "anthropic/")):
            model_name = f"groq/{model_name}"

        response = litellm.completion(
            model=model_name,
            messages=messages,
            temperature=temperature,
            api_key=api_key,
            response_format={"type": "json_object"} if json_mode else None
        )

        content = response.choices[0].message.content
        usage = getattr(response, "usage", {})
        chat_res = ChatResult(
            content=content,
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
        )

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        _log_trace(
            settings=settings,
            messages=messages,
            result=chat_res,
            latency_ms=latency_ms,
            stage=stage,
            topic_sn=topic_sn,
            model=model_name,
        )

        if redis_client and cache_key:
            try:
                cache_value = {
                    "content": chat_res.content,
                    "prompt_tokens": chat_res.prompt_tokens,
                    "completion_tokens": chat_res.completion_tokens,
                }
                redis_client.setex(
                    cache_key,
                    settings.llm_cache_ttl_seconds,
                    json.dumps(cache_value),
                )
                logger.debug("Cached fallback result in Redis.")
            except Exception:
                pass

        logger.info("Fallback successful!")
        return chat_res
    except Exception as fallback_exc:
        logger.error(f"Fallback failed: {fallback_exc}")
        return None


def chat_json(
    settings: Settings,
    messages: list[dict[str, str]],
    model: str,
    stage: str = "unknown",
    topic_sn: int | None = None,
    temperature: float = 0,
    json_mode: bool = True,
    bypass_cache: bool = False,
) -> ChatResult:
    """Call the Cerebras chat-completions endpoint with automatic retry on 429 / 5xx.

    Raises RuntimeError after all retries are exhausted.
    """
    if settings.llm_provider != "cerebras":
        raise ValueError(f"Unsupported provider for now: {settings.llm_provider}")
    if not settings.cerebras_api_key:
        raise ValueError("CEREBRAS_API_KEY is missing")

    # 1. Check Redis Cache
    redis_client = _get_redis_client(settings)
    cache_key = None
    if redis_client and not bypass_cache:
        try:
            import hashlib

            input_data = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "json_mode": json_mode,
            }
            input_json = json.dumps(input_data, sort_keys=True)
            cache_key = f"llm_cache:{hashlib.sha256(input_json.encode('utf-8')).hexdigest()}"

            cached_val = redis_client.get(cache_key)
            if cached_val:
                cached_dict = json.loads(cached_val)
                logger.info(f"LLM cache HIT! Returning cached response (key: {cache_key[:12]}...).")
                return ChatResult(
                    content=cached_dict["content"],
                    prompt_tokens=cached_dict.get("prompt_tokens"),
                    completion_tokens=cached_dict.get("completion_tokens"),
                    cached=True,
                )
        except Exception as exc:
            logger.warning(f"Redis cache read failed: {exc}")
    elif redis_client and bypass_cache:
        # Calculate cache_key even when bypassing so we overwrite it with new results
        try:
            import hashlib
            input_data = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "json_mode": json_mode,
            }
            input_json = json.dumps(input_data, sort_keys=True)
            cache_key = f"llm_cache:{hashlib.sha256(input_json.encode('utf-8')).hexdigest()}"
        except Exception:
            pass

    payload: dict = {"model": model, "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "edu-curator/1.0",
    }

    last_exc: Exception | None = None
    start_time = time.perf_counter()

    for attempt in range(MAX_RETRIES):
        try:
            session = _get_http_session()
            resp = session.post(
                "https://api.cerebras.ai/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=120,
            )
            if resp.status_code != 200:
                import io
                from urllib.error import HTTPError
                fp = io.BytesIO(resp.content)
                raise HTTPError(
                    url="https://api.cerebras.ai/v1/chat/completions",
                    code=resp.status_code,
                    msg=resp.reason,
                    hdrs=resp.headers,
                    fp=fp
                )
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            chat_result = ChatResult(
                content=raw,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            _log_trace(settings, messages, chat_result, latency_ms, stage, topic_sn)

            # Store in Redis Cache if enabled
            if redis_client and cache_key:
                try:
                    cache_value = {
                        "content": chat_result.content,
                        "prompt_tokens": chat_result.prompt_tokens,
                        "completion_tokens": chat_result.completion_tokens,
                    }
                    redis_client.setex(
                        cache_key,
                        settings.llm_cache_ttl_seconds,
                        json.dumps(cache_value),
                    )
                    logger.debug(
                        f"Cached successful result in Redis (TTL: {settings.llm_cache_ttl_seconds}s)."
                    )
                except Exception as cache_exc:
                    logger.warning(f"Failed to write to Redis: {cache_exc}")

            return chat_result
        except HTTPError as exc:
            if settings.litellm_fallback_enabled:
                fallback_res = _try_litellm_fallback(
                    settings,
                    messages,
                    temperature,
                    json_mode,
                    redis_client,
                    cache_key,
                    stage=stage,
                    topic_sn=topic_sn,
                )
                if fallback_res is not None:
                    return fallback_res
            retryable = exc.code in RETRYABLE_CODES
            last_exc = exc
            try:
                err_body = exc.read().decode("utf-8")
                last_exc = RuntimeError(f"HTTPError {exc.code}: {exc.reason} - Response: {err_body}")
            except Exception:
                pass
            if not retryable:
                raise RuntimeError(
                    f"LLM request failed with HTTP {exc.code}: {exc.reason}"
                ) from exc
        except Exception as exc:
            if settings.litellm_fallback_enabled:
                fallback_res = _try_litellm_fallback(
                    settings,
                    messages,
                    temperature,
                    json_mode,
                    redis_client,
                    cache_key,
                    stage=stage,
                    topic_sn=topic_sn,
                )
                if fallback_res is not None:
                    return fallback_res
            exc_str = str(exc)
            retryable = any(
                f" {code} " in exc_str or exc_str.startswith(str(code)) for code in RETRYABLE_CODES
            )
            last_exc = exc
            if not retryable:
                raise RuntimeError(f"LLM request failed: {exc}") from exc

        if attempt < MAX_RETRIES - 1:
            is_429 = False
            if isinstance(last_exc, HTTPError) and last_exc.code == 429:
                is_429 = True
            elif last_exc is not None:
                exc_str = str(last_exc)
                if "429" in exc_str:
                    is_429 = True

            if is_429:
                wait = 65.0
                logger.warning(
                    f"Rate limit (429) hit on attempt {attempt + 1}/{MAX_RETRIES}: {last_exc}. "
                    f"Waiting 65.0s for quota window to reset ..."
                )
            else:
                delay = RETRY_BASE_S * (2**attempt)
                jitter = delay * RETRY_JITTER * (2 * random.random() - 1)
                wait = min(60.0, max(1.0, delay + jitter))
                logger.warning(
                    f"Error on attempt {attempt + 1}/{MAX_RETRIES}: {last_exc}. "
                    f"Retrying in {wait:.1f}s ..."
                )
            time.sleep(wait)

    raise RuntimeError(f"LLM request failed after {MAX_RETRIES} attempts") from last_exc


# ---------------------------------------------------------------------------
# Batch API helpers
# ---------------------------------------------------------------------------


def upload_batch_file(settings: Settings, file_content: bytes, filename: str) -> str:
    """Upload a JSONL file to Cerebras Files API for batch processing.

    Returns the file ID.
    """
    if not settings.cerebras_api_key:
        raise ValueError("CEREBRAS_API_KEY is missing")

    # Construct multipart form data
    boundary = b"----Boundary" + bytes(str(random.randint(100000000, 999999999)), "utf-8")
    parts = [
        b"--" + boundary,
        b'Content-Disposition: form-data; name="purpose"',
        b"",
        b"batch",
        b"--" + boundary,
        b'Content-Disposition: form-data; name="file"; filename="'
        + bytes(filename, "utf-8")
        + b'"',
        b"Content-Type: application/octet-stream",
        b"",
        file_content,
        b"--" + boundary + b"--",
        b"",
    ]
    body = b"\r\n".join(parts)
    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary.decode('utf-8')}",
        "Accept": "application/json",
        "User-Agent": "edu-curator/1.0",
    }
    request = Request("https://api.cerebras.ai/v1/files", data=body, headers=headers, method="POST")
    with urlopen(request, timeout=60) as response:
        res_data = json.loads(response.read().decode("utf-8"))
    return res_data["id"]


def create_batch_job(settings: Settings, input_file_id: str) -> str:
    """Create a batch completion job in Cerebras.

    Returns the batch ID.
    """
    if not settings.cerebras_api_key:
        raise ValueError("CEREBRAS_API_KEY is missing")

    payload = {
        "input_file_id": input_file_id,
        "endpoint": "/v1/chat/completions",
        "completion_window": "24h",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "edu-curator/1.0",
    }
    request = Request(
        "https://api.cerebras.ai/v1/batches", data=body, headers=headers, method="POST"
    )
    with urlopen(request, timeout=30) as response:
        res_data = json.loads(response.read().decode("utf-8"))
    return res_data["id"]


def retrieve_batch_job(settings: Settings, batch_id: str) -> dict:
    """Check batch job status in Cerebras.

    Returns the batch details dict.
    """
    if not settings.cerebras_api_key:
        raise ValueError("CEREBRAS_API_KEY is missing")

    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Accept": "application/json",
        "User-Agent": "edu-curator/1.0",
    }
    request = Request(
        f"https://api.cerebras.ai/v1/batches/{batch_id}", headers=headers, method="GET"
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download_file_content(settings: Settings, file_id: str) -> str:
    """Download the content of a batch output file from Cerebras.

    Returns the file content as string.
    """
    if not settings.cerebras_api_key:
        raise ValueError("CEREBRAS_API_KEY is missing")

    headers = {
        "Authorization": f"Bearer {settings.cerebras_api_key}",
        "Accept": "application/json",
        "User-Agent": "edu-curator/1.0",
    }
    request = Request(
        f"https://api.cerebras.ai/v1/files/{file_id}/content", headers=headers, method="GET"
    )
    with urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")
