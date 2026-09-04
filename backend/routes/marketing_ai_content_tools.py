"""
Session 12 — P1-4 & P1-5: AI Content Tools
A) AI Content Generator (caption + hashtag dengan template per platform)
B) AI Image Generator (text-to-image, aspect ratio custom)
"""
import uuid
import logging
import os
import base64
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Query, Request, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from ai_llm import LlmChat, UserMessage
from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/ai-content", tags=["marketing-ai-content"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _now():
    return datetime.now(timezone.utc)


def ok(data=None, meta=None):
    r = {"success": True}
    if data is not None:
        r["data"] = data
    if meta is not None:
        r["metadata"] = meta
    return r


def serialize(o):
    if isinstance(o, list):
        return [serialize(i) for i in o]
    if isinstance(o, dict):
        return {k: serialize(v) for k, v in o.items() if k != "_id"}
    if isinstance(o, datetime):
        return o.isoformat()
    return o


# ═══════════════════════════════════════════════════════════════════════════
#  P1-4: AI CONTENT GENERATOR (Caption + Hashtag)
# ═══════════════════════════════════════════════════════════════════════════

PLATFORM_TEMPLATES = {
    "instagram": {
        "tone": "Friendly, casual, engaging",
        "max_caption": 150,
        "hashtag_count": "5-7",
        "call_to_action": "DM untuk order, link di bio",
        "style": "Visual storytelling, emoji minimal"
    },
    "tiktok": {
        "tone": "Energetic, fun, trending",
        "max_caption": 100,
        "hashtag_count": "3-5",
        "call_to_action": "Check link di bio, jangan lupa follow!",
        "style": "Short, catchy, viral-friendly"
    },
    "shopee": {
        "tone": "Professional, persuasive, value-focused",
        "max_caption": 200,
        "hashtag_count": "5-8",
        "call_to_action": "Checkout sekarang, promo terbatas!",
        "style": "Highlight features, benefits, promo"
    },
    "tokopedia": {
        "tone": "Professional, trustworthy",
        "max_caption": 180,
        "hashtag_count": "4-6",
        "call_to_action": "Beli sekarang, gratis ongkir!",
        "style": "Clear product info, quality focus"
    }
}


class CaptionGenerateIn(BaseModel):
    # F14b — caption ditulis UNTUK produk yang benar-benar dijual. `model_id`
    # (master produk) membuat riwayat caption bisa dikaitkan ke produknya, dan
    # membuat bahan/kategori yang MASUK KE PROMPT berasal dari master — bukan
    # dari ketikan. Ini penting karena teks hasilnya TAYANG KE PEMBELI: bahan
    # karangan di caption adalah klaim produk yang salah.
    #
    # Masih Optional (bukan wajib) supaya alat lain/klien lama tidak pecah, TAPI
    # kalau diisi, isinya MENANG atas apa pun yang dikirim browser.
    model_id: Optional[str] = Field(None, description="ID master produk (rahaza_models)")
    product_name: str = Field(..., description="Nama produk")
    category: Optional[str] = Field(None, description="Kategori produk")
    material: Optional[str] = Field(None, description="Material/bahan")
    colors: Optional[List[str]] = Field(None, description="List warna tersedia")
    price: Optional[float] = Field(None, ge=0, description="Harga produk")
    platform: str = Field(..., description="Platform: instagram, tiktok, shopee, tokopedia")
    custom_notes: Optional[str] = Field(None, description="Notes tambahan untuk AI")


@router.post("/generate-caption")
async def generate_caption(payload: CaptionGenerateIn, request: Request):
    """
    P1-4: Generate caption + hashtag menggunakan AI dengan template per platform.
    """
    await require_auth(request)
    
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured")
    
    platform = payload.platform.lower()
    if platform not in PLATFORM_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Platform '{payload.platform}' not supported")

    # ── F14b — identitas produk dari MASTER kalau `model_id` diberikan ────────
    # Satu arah: master menang. Kalau `model_id` menunjuk produk yang tidak ada,
    # itu ditolak — lebih baik gagal terang-terangan daripada menulis caption
    # untuk produk yang tidak dijual.
    prod_name = payload.product_name
    prod_category = payload.category
    prod_material = payload.material
    if payload.model_id:
        from database import get_db as _get_db
        _db = _get_db()
        _m = await _db.rahaza_models.find_one({"id": payload.model_id}, {"_id": 0})
        if not _m:
            raise HTTPException(
                status_code=400,
                detail=f"Produk '{payload.model_id}' tidak ada di Master Produk.")
        prod_name = _m.get("name") or prod_name
        prod_category = _m.get("category_name") or _m.get("category") or prod_category
        _comps: list = []
        async for _fg in _db.rahaza_materials.find(
                {"type": "fg", "model_id": payload.model_id},
                {"_id": 0, "composition": 1}):
            _c = (_fg.get("composition") or "").strip()
            if _c and _c not in _comps:
                _comps.append(_c)
        if _comps:
            prod_material = " / ".join(_comps)

    template = PLATFORM_TEMPLATES[platform]
    
    # Build prompt
    prompt = f"""
Kamu adalah AI marketing expert untuk platform {platform.upper()}.
Generate caption menarik dan hashtag untuk produk berikut:

Produk: {prod_name}
"""
    
    if prod_category:
        prompt += f"\nKategori: {prod_category}"
    if prod_material:
        prompt += f"\nMaterial: {prod_material}"
    if payload.colors:
        prompt += f"\nWarna: {', '.join(payload.colors)}"
    if payload.price:
        prompt += f"\nHarga: Rp {payload.price:,.0f}"
    if payload.custom_notes:
        prompt += f"\nNotes: {payload.custom_notes}"
    
    prompt += f"""

Template Guidelines untuk {platform.upper()}:
- Tone: {template['tone']}
- Caption maksimal: {template['max_caption']} karakter
- Jumlah hashtag: {template['hashtag_count']}
- Call-to-action: {template['call_to_action']}
- Style: {template['style']}

Format output:
CAPTION:
[caption text]

HASHTAG:
#tag1 #tag2 #tag3 ...
"""
    
    try:
        # Generate with AI
        llm = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"caption-gen-{uuid.uuid4()}",
            system_message="You are a professional marketing content creator."
        ).with_model("standard")
        
        user_message = UserMessage(text=prompt)
        response = await llm.send_message(user_message)
        
        # Parse response
        lines = response.strip().split("\n")
        caption = ""
        hashtags = ""
        caption_section = False
        hashtag_section = False
        
        for line in lines:
            if "CAPTION:" in line:
                caption_section = True
                hashtag_section = False
                continue
            elif "HASHTAG:" in line:
                caption_section = False
                hashtag_section = True
                continue
            
            if caption_section and line.strip():
                caption += line.strip() + " "
            elif hashtag_section and line.strip():
                hashtags += line.strip() + " "
        
        caption = caption.strip()
        hashtags = hashtags.strip()
        
        # Save to DB for history
        db = get_db()
        doc = {
            "content_id": str(uuid.uuid4()),
            "type": "caption",
            # F14b — riwayat menyimpan nama produk HASIL RESOLUSI master (bukan
            # ketikan), plus `model_id`, supaya performa konten bisa dikaitkan
            # ke produk yang benar. Sebelumnya riwayat menyimpan apa pun yang
            # diketik ⇒ satu produk punya banyak ejaan dan riwayatnya pecah.
            "product_name": prod_name,
            "model_id": payload.model_id,
            "platform": platform,
            "caption": caption,
            "hashtags": hashtags,
            "generated_at": _now(),
            "generated_by": "AI",
            "input_payload": payload.dict()
        }
        await db.marketing_ai_content_history.insert_one(doc)
        
        return ok(data={
            "caption": caption,
            "hashtags": hashtags,
            "platform": platform,
            "content_id": doc["content_id"]
        })
        
    except Exception as e:
        logger.exception(f"[ai-content] caption generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Caption generation failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
#  P1-5: AI IMAGE GENERATOR (GPT Image 1)
# ═══════════════════════════════════════════════════════════════════════════

class ImageGenerateIn(BaseModel):
    prompt: str = Field(..., description="Image generation prompt")
    aspect_ratio: Optional[str] = Field("square", description="square, portrait, landscape")
    mode: Optional[str] = Field("generate", description="generate, variation (future: edit)")


ASPECT_RATIO_MAP = {
    "square": "1024x1024",
    "portrait": "1024x1792",
    "landscape": "1792x1024"
}


@router.post("/generate-image")
async def generate_image(payload: ImageGenerateIn, request: Request):
    """
    P1-5: Generate product image menggunakan GPT Image 1.
    Mode: generate (text-to-image), variation (future enhancement)
    """
    await require_auth(request)
    
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="EMERGENT_LLM_KEY not configured")
    
    aspect_ratio = payload.aspect_ratio.lower()
    if aspect_ratio not in ASPECT_RATIO_MAP:
        raise HTTPException(status_code=400, detail=f"Aspect ratio '{payload.aspect_ratio}' not supported")
    
    size = ASPECT_RATIO_MAP[aspect_ratio]
    
    try:
        if payload.mode == "generate":
            # Text-to-image generation
            image_gen = OpenAIImageGeneration(api_key=EMERGENT_LLM_KEY)
            images = await image_gen.generate_images(
                prompt=payload.prompt,
                model="gpt-image-1",
                number_of_images=1
            )
            
            if not images or len(images) == 0:
                raise HTTPException(status_code=500, detail="No image was generated")
            
            # Convert to base64
            image_base64 = base64.b64encode(images[0]).decode('utf-8')
            
            # Save to DB for history
            db = get_db()
            doc = {
                "content_id": str(uuid.uuid4()),
                "type": "image",
                "prompt": payload.prompt,
                "aspect_ratio": aspect_ratio,
                "size": size,
                "mode": payload.mode,
                "generated_at": _now(),
                "generated_by": "AI",
                "image_size_kb": len(images[0]) / 1024
            }
            await db.marketing_ai_content_history.insert_one(doc)
            
            return ok(data={
                "image_base64": image_base64,
                "content_id": doc["content_id"],
                "size": size,
                "aspect_ratio": aspect_ratio,
                "image_size_kb": doc["image_size_kb"]
            })
            
        elif payload.mode == "variation":
            # Future: Variation mode (requires base image input)
            raise HTTPException(status_code=501, detail="Variation mode not yet implemented")
        
        else:
            raise HTTPException(status_code=400, detail=f"Mode '{payload.mode}' not supported")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[ai-content] image generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════
#  CONTENT HISTORY
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/history")
async def get_content_history(request: Request, limit: int = Query(50, ge=1, le=500), content_type: Optional[str] = None):
    """
    Get AI content generation history (caption + image).
    """
    await require_auth(request)
    db = get_db()
    
    query = {}
    if content_type:
        query["type"] = content_type
    
    docs = await db.marketing_ai_content_history.find(query).sort("generated_at", -1).limit(limit).to_list(length=limit)
    
    # Don't return full image_base64 in history list (too large)
    for doc in docs:
        doc.pop("_id", None)
        if doc.get("type") == "image":
            doc["image_base64"] = "[excluded from list view]"
    
    return ok(data=serialize(docs), meta={"count": len(docs), "limit": limit})
