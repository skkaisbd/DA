"""Unified LLM client (Claude via the official Anthropic SDK).

Design goals:
1. Single entry point for all AI route files (consistency).
2. All calls funnel through `ai_cost_tracker.tracked_llm_call`, which speaks to
   the Anthropic Messages API directly with the owner's `ANTHROPIC_API_KEY`.
3. Application-level response cache (MongoDB) to avoid paying twice for the
   same prompt.
4. Graceful 503 when `ANTHROPIC_API_KEY` is absent.

This module is intentionally small (<300 LOC). Keep additions inside
specialized sub-modules (`prompt_templates.py`, `response_cache.py`).
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Standardized model: Claude (per project directive — all AI uses Claude)
# ---------------------------------------------------------------------------
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-sonnet-5"


class LLMUnavailable(HTTPException):
    """503 response when ANTHROPIC_API_KEY is missing or AI library not loadable."""

    def __init__(self, detail: str = "AI belum aktif. ANTHROPIC_API_KEY belum dikonfigurasi."):
        super().__init__(status_code=503, detail=detail)


# ---------------------------------------------------------------------------
# Key resolution: DB first (integration settings), then env.
# ---------------------------------------------------------------------------
async def get_llm_key(db=None) -> str:
    """Return the Anthropic API key or raise LLMUnavailable.

    Order of precedence:
    1. `rahaza_integration_settings` collection (admin-managed, runtime override).
    2. `ANTHROPIC_API_KEY` env var.
    """
    if db is not None:
        try:
            from routes.rahaza_integrations import get_integration_key  # local import to avoid cycle
            key = await get_integration_key("ANTHROPIC_API_KEY", db)
            if key:
                return key
        except Exception as e:  # pragma: no cover
            logger.warning("Failed reading ANTHROPIC_API_KEY from DB: %s", e)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    raise LLMUnavailable()


# ---------------------------------------------------------------------------
# Core call (no cache). Keep this tiny — formatting belongs to caller.
# ---------------------------------------------------------------------------
async def call_claude(
    system_message: str,
    user_message: str,
    *,
    session_tag: str = "ai",
    db=None,
    tier: str = "standard",
) -> str:
    """Single point of LLM invocation. Returns plain text response.

    WS-C: routes through the centralized `ai_cost_tracker` wrapper (via the
    `ai_llm.LlmChat` shim) so EVERY call is logged (AI Usage Monitor), subject
    to the daily/monthly/per-feature budget guardrails, and uses the canonical
    Claude tier models (executive/standard/light) — no hardcoded model.

    `session_tag` becomes the usage `feature` label. `tier` selects the model
    complexity (defaults to 'standard' = sonnet).

    Raises:
        LLMUnavailable(503): when key/library missing.
        HTTPException(429): when the AI budget is exceeded.
        HTTPException(500): on any underlying LLM error.
    """
    key = await get_llm_key(db)
    try:
        from ai_llm import LlmChat, UserMessage  # centralized shim (WS-C)
        from ai_cost_tracker import AIError, TIER_MODELS
    except ImportError as e:  # pragma: no cover
        logger.error("AI wrapper import failed: %s", e)
        raise LLMUnavailable("AI library (ai_cost_tracker/ai_llm) tidak terpasang.")

    resolved_tier = tier if tier in TIER_MODELS else "standard"
    try:
        chat = (
            LlmChat(
                api_key=key,
                session_id=f"{session_tag}-{uuid.uuid4().hex[:8]}",
                system_message=system_message,
            )
            .with_model(resolved_tier)
            .for_feature(session_tag, tier=resolved_tier)
        )
        response = await chat.send_message(UserMessage(text=user_message))
        return response if isinstance(response, str) else str(response)
    except AIError as e:
        # Over-budget or centralized AI failure → surface a clear status.
        if getattr(e, "over_budget", False):
            raise HTTPException(status_code=429, detail=str(e) or "Budget AI harian/bulanan terlampaui.")
        logger.error("AI call failed (%s): %s", session_tag, e)
        raise HTTPException(status_code=500, detail=f"AI call failed: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("LLM call failed (%s): %s", session_tag, e)
        raise HTTPException(status_code=500, detail=f"AI call failed: {e}")


# ---------------------------------------------------------------------------
# Cached call (app-level cache via MongoDB).
# Substitutes Anthropic ephemeral cache (not accessible via emergentintegrations).
# ---------------------------------------------------------------------------
def _hash_cache_key(parts: list[str]) -> str:
    payload = "\u0001".join(p or "" for p in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def cached_call_claude(
    db,
    *,
    system_message: str,
    user_message: str,
    cache_namespace: str,
    cache_key_extra: list[str] | None = None,
    ttl_seconds: int = 3600,
    session_tag: str = "ai",
    tier: str = "standard",
) -> dict[str, Any]:
    """LLM call with application-level cache (MongoDB).

    Args:
        db: motor Database (required for cache read/write).
        system_message / user_message: prompt content.
        cache_namespace: e.g. "daily_summary", "revenue_forecast".
        cache_key_extra: extra invalidation parts (e.g. [date_str, period_str]).
        ttl_seconds: cache lifetime (default 1h).
        session_tag: for LLM session_id naming (also the usage feature label).
        tier: model complexity tier ('executive'/'standard'/'light').

    Returns:
        dict with keys: text (str), cache_hit (bool), generated_at (iso str).
    """
    from datetime import datetime, timezone, timedelta

    extra = cache_key_extra or []
    key_hash = _hash_cache_key([cache_namespace, tier, system_message, user_message, *extra])
    now = datetime.now(timezone.utc)

    # Try cache hit
    try:
        cached = await db.ai_response_cache.find_one({"key_hash": key_hash}, {"_id": 0})
        if cached:
            exp = cached.get("expires_at")
            # expires_at stored as ISO string for portability
            if exp and isinstance(exp, str) and exp > now.isoformat():
                return {
                    "text": cached.get("text", ""),
                    "cache_hit": True,
                    "generated_at": cached.get("generated_at", now.isoformat()),
                }
    except Exception as e:  # pragma: no cover
        logger.warning("AI cache read error: %s", e)

    # Miss → call LLM
    text = await call_claude(
        system_message=system_message,
        user_message=user_message,
        session_tag=session_tag,
        db=db,
        tier=tier,
    )

    # Persist cache (fire-and-forget style; failure should not break user response)
    try:
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
        await db.ai_response_cache.update_one(
            {"key_hash": key_hash},
            {"$set": {
                "key_hash": key_hash,
                "namespace": cache_namespace,
                "text": text,
                "generated_at": now.isoformat(),
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds,
            }},
            upsert=True,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("AI cache write error: %s", e)

    return {"text": text, "cache_hit": False, "generated_at": now.isoformat()}
