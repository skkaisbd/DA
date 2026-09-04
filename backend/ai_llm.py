"""WS-C — Shim LlmChat terpusat.

Drop-in pengganti `emergentintegrations.llm.chat.LlmChat` yang MERUTEKAN semua
panggilan AI lewat wrapper terpusat `ai_cost_tracker.tracked_llm_call`
(budget + cost tracking + logging) dan MEMAKSA model Claude berbasis tier.

Migrasi file lama cukup ganti import:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
  ->
    from ai_llm import LlmChat, UserMessage, ImageContent

Tier ditentukan otomatis dari model lama (heuristik "by complexity"):
    opus/gpt-5/o1/o3            -> executive (claude-opus-4-8)
    mini/haiku/flash/nano       -> light     (claude-haiku-4-5)
    selain itu                  -> standard  (claude-sonnet-4-6)
Override eksplisit: `.with_model("executive"|"standard"|"light")`.

`send_message()` mengembalikan STRING (kompatibel dgn LlmChat lama).
"""
import logging
import re

from dataclasses import dataclass, field
import ai_cost_tracker as _tracker

__all__ = ["LlmChat", "UserMessage", "ImageContent"]


@dataclass
class ImageContent:
    """Konten gambar base64 (pengganti kelas emergentintegrations)."""
    image_base64: str = ""


@dataclass
class UserMessage:
    """Pesan pengguna (pengganti kelas emergentintegrations)."""
    text: str = ""
    file_contents: list = field(default_factory=list)

_log = logging.getLogger(__name__)

# Pola galat "model ini tidak boleh dipakai kunci Anda" dari gateway LLM.
_MODEL_ACCESS_PATTERNS = (
    "heavy model", "not enough credits", "upgrade to standard",
    "model not found", "does not have access", "unsupported model",
)


def _is_model_access_error(err) -> bool:
    e = str(err or "").lower()
    return any(p in e for p in _MODEL_ACCESS_PATTERNS)


def _legacy_to_tier(provider, model) -> str:
    m = f"{provider or ''} {model or ''}".lower()
    if any(k in m for k in ("opus", "gpt-5", "o1", "o3", "-pro")):
        return "executive"
    if any(k in m for k in ("mini", "haiku", "flash", "nano", "lite")):
        return "light"
    return "standard"


class LlmChat:
    def __init__(self, api_key=None, session_id=None, system_message=""):
        self._api_key = api_key
        self._session_id = session_id
        self._system = system_message or ""
        self._tier = _tracker.DEFAULT_TIER
        self._max_tokens = None
        self._user_id = None
        # feature label = session_id tanpa suffix uuid
        base = session_id or "ai"
        self._feature = re.sub(r"[-_][0-9a-f]{6,}$", "", base) or "ai"

    def with_model(self, provider, model=None):
        if model is None and isinstance(provider, str) and provider.lower() in _tracker.TIER_MODELS:
            self._tier = provider.lower()
        elif isinstance(provider, str) and provider.lower() in _tracker.TIER_MODELS:
            self._tier = provider.lower()
        else:
            self._tier = _legacy_to_tier(provider, model)
        return self

    def with_params(self, max_tokens=None, **_kw):
        if max_tokens:
            self._max_tokens = max_tokens
        return self

    def for_feature(self, feature, user_id=None, tier=None):
        """Opsional: set label fitur / user / tier secara eksplisit."""
        if feature:
            self._feature = feature
        if user_id:
            self._user_id = user_id
        if tier:
            self._tier = tier
        return self

    @staticmethod
    def _extract(user_message):
        text = getattr(user_message, "text", None)
        if text is None:
            text = getattr(user_message, "content", None) or str(user_message)
        img = None
        contents = getattr(user_message, "file_contents", None) or getattr(user_message, "images", None) or []
        for fc in contents:
            b64 = getattr(fc, "image_base64", None) or getattr(fc, "data", None)
            if b64:
                img = b64
                break
        return text, img

    async def send_message(self, user_message) -> str:
        text, img = self._extract(user_message)
        res = await _tracker.tracked_llm_call(
            feature=self._feature, user_id=self._user_id, model=self._tier,
            system_message=self._system, user_message=text,
            api_key=self._api_key, session_id=self._session_id,
            image_base64=img, max_tokens=self._max_tokens,
        )
        # ── AUDIT-3 (2026-07-26): tier "executive" (claude-opus) TIDAK tersedia
        # pada kunci universal Emergent tingkat standar. Akibatnya
        # `/api/reports/executive/ai-narrative` → 500 dan `/api/finance/ai-cashflow`
        # → 502 setiap kali dipanggil, walau kuncinya benar. Turunkan otomatis ke
        # tier "standard" (sonnet) sekali, dan catat di log — jangan gagalkan fitur.
        if (not res.success) and self._tier == "executive" and _is_model_access_error(res.error):
            _log.warning(
                "[ai] model executive tidak tersedia untuk kunci ini — "
                "fallback ke tier 'standard'. Pesan asli: %s", (res.error or "")[:160])
            res = await _tracker.tracked_llm_call(
                feature=self._feature, user_id=self._user_id, model="standard",
                system_message=self._system, user_message=text,
                api_key=self._api_key, session_id=self._session_id,
                image_base64=img, max_tokens=self._max_tokens,
            )
        if not res.success:
            raise _tracker.AIError(res.error or "AI call gagal", over_budget=res.over_budget)
        return res.text
