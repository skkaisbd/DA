"""Asisten ERP CV. Dewi Aditya — mesin jawab berbasis pengetahuan portal.

Filosofi: 95% pertanyaan pengguna tentang "cara kerja sistem" bisa dijawab dari
basis pengetahuan STATIS per portal (`backend/data/portal_kb/*.json`) — gratis,
instan, dan tidak pernah mengarang. AI hanya dipanggil bila pertanyaannya benar
benar di luar jangkauan basis pengetahuan.

Tidak ada state di modul ini selain cache pembacaan berkas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "portal_kb"
GENERAL = "_umum"

# Ambang skor: di bawah ini dianggap "tidak yakin" → dilempar ke AI / fallback.
MIN_SCORE = 4.0

_STOPWORDS = {
    "yang", "untuk", "dari", "dengan", "pada", "ini", "itu", "apa", "apakah",
    "bagaimana", "cara", "kenapa", "mengapa", "saya", "kita", "kami", "bisa",
    "tidak", "ada", "dan", "atau", "di", "ke", "dalam", "adalah", "kalau",
    "jika", "sudah", "belum", "mau", "ingin", "tolong", "gimana", "dong",
    "nya", "sih", "aja", "saja", "kok", "harus", "boleh", "kah", "lagi",
    "buat", "pakai", "punya", "jadi", "juga", "akan", "supaya", "agar",
}

_CACHE: dict[str, dict] = {}
_CACHE_MTIME: dict[str, float] = {}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if len(t) > 2 and t not in _STOPWORDS}


def load_kb(portal: str) -> dict | None:
    """Baca satu berkas KB (cache dengan invalidasi berbasis mtime)."""
    path = KB_DIR / f"{portal}.json"
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    if _CACHE_MTIME.get(portal) != mtime:
        _CACHE[portal] = json.loads(path.read_text(encoding="utf-8"))
        _CACHE_MTIME[portal] = mtime
    return _CACHE[portal]


def available_portals() -> list[str]:
    return sorted(p.stem for p in KB_DIR.glob("*.json") if p.stem != GENERAL)


def _score(q_tokens: set[str], q_text: str, *, keywords: list, title: str, body: str) -> float:
    """Skor kecocokan: frasa kunci utuh paling berat, lalu irisan kata."""
    score = 0.0
    for kw in keywords or []:
        kw = _norm(str(kw)).strip()
        if not kw:
            continue
        if kw in q_text:
            score += 3.0 + 0.5 * kw.count(" ")
        else:
            hit = len(_tokens(kw) & q_tokens)
            if hit:
                score += 1.2 * hit
    score += 1.5 * len(_tokens(title) & q_tokens)
    score += 0.4 * len(_tokens(body) & q_tokens)
    return score


def _fmt_alur(entry: dict) -> str:
    lines = [entry["judul"], ""]
    lines += [f"{i}. {s}" for i, s in enumerate(entry.get("langkah", []), 1)]
    if entry.get("modul"):
        lines += ["", "Modul terkait: " + ", ".join(entry["modul"])]
    return "\n".join(lines)


def _fmt_fitur(kb: dict, entry: dict) -> str:
    return (f"{entry['nama']} — {entry['deskripsi']}\n\n"
            f"Letaknya di {kb['label']}, modul `{entry['modul']}`.")


def _candidates(kb: dict):
    for e in kb.get("alur", []):
        yield ("alur", e, e.get("kata_kunci", []), e.get("judul", ""),
               " ".join(e.get("langkah", [])))
    for e in kb.get("faq", []):
        yield ("faq", e, e.get("kata_kunci", []), e.get("q", ""), e.get("a", ""))
    for e in kb.get("fitur", []):
        yield ("fitur", e, [e.get("nama", ""), e.get("modul", "")],
               e.get("nama", ""), e.get("deskripsi", ""))


_HOWTO_HINTS = ("bagaimana", "gimana", "cara", "langkah", "alur", "proses", "urutan", "tahap")
_WHERE_HINTS = ("di mana", "dimana", "letak", "menu", "modul", "buka apa")


def _intent_weight(kind: str, q_text: str) -> float:
    """Pertanyaan 'bagaimana caranya' harus dijawab ALUR, bukan deskripsi fitur."""
    howto = any(h in q_text for h in _HOWTO_HINTS)
    where = any(h in q_text for h in _WHERE_HINTS)
    if kind == "alur":
        return 1.5 if howto else 1.0
    if kind == "fitur":
        return 1.4 if where else (0.75 if howto else 1.0)
    return 1.0


def _best_in(kb: dict, q_tokens: set[str], q_text: str):
    best = None
    for kind, entry, kws, title, body in _candidates(kb):
        s = _score(q_tokens, q_text, keywords=kws, title=title, body=body) * _intent_weight(kind, q_text)
        if best is None or s > best[0]:
            best = (s, kind, entry)
    return best


def _overview(kb: dict) -> str:
    parts = [kb["ringkasan"]]
    if kb.get("prinsip"):
        parts.append("Prinsip penting:\n" + "\n".join(f"• {p}" for p in kb["prinsip"]))
    if kb.get("fitur"):
        names = ", ".join(f["nama"] for f in kb["fitur"][:12])
        parts.append(f"Ada {len(kb['fitur'])} modul di portal ini: {names}"
                     + (", dan lainnya." if len(kb["fitur"]) > 12 else "."))
    return "\n\n".join(parts)


_OVERVIEW_HINTS = ("portal ini", "portal apa", "fitur apa", "fitur saja", "menu apa",
                   "isi portal", "apa saja", "bisa apa", "gunanya", "fungsinya",
                   "untuk apa", "daftar fitur", "daftar menu")


def answer(question: str, portal: str | None = None) -> dict:
    """Cari jawaban dari basis pengetahuan.

    Kembalian:
      {source: 'kb'|'none', reply, confidence, portal, kind, related[]}
    """
    q_text = _norm(question)
    q_tokens = _tokens(question)
    kb = load_kb(portal) if portal else None

    if kb and any(h in q_text for h in _OVERVIEW_HINTS):
        return {"source": "kb", "kind": "ringkasan", "portal": portal,
                "reply": _overview(kb), "confidence": "tinggi",
                "related": kb.get("saran", [])[:3]}

    ranked = []
    if kb:
        b = _best_in(kb, q_tokens, q_text)
        if b:
            ranked.append((b[0], portal, b[1], b[2]))

    umum = load_kb(GENERAL)
    if umum:
        b = _best_in(umum, q_tokens, q_text)
        if b:
            ranked.append((b[0] * 0.95, GENERAL, b[1], b[2]))

    # Portal lain: skor didiskon supaya portal aktif tetap diprioritaskan.
    for p in available_portals():
        if p == portal:
            continue
        other = load_kb(p)
        b = _best_in(other, q_tokens, q_text) if other else None
        if b:
            ranked.append((b[0] * 0.7, p, b[1], b[2]))

    ranked.sort(key=lambda x: -x[0])
    if not ranked or ranked[0][0] < MIN_SCORE:
        return {"source": "none", "portal": portal, "reply": "", "confidence": "rendah",
                "related": (kb or umum or {}).get("saran", [])[:4]}

    score, src_portal, kind, entry = ranked[0]
    src_kb = load_kb(src_portal)
    if kind == "alur":
        reply = _fmt_alur(entry)
    elif kind == "faq":
        reply = entry["a"]
    else:
        reply = _fmt_fitur(src_kb, entry)

    if src_portal != portal and src_portal != GENERAL:
        reply += f"\n\n(Jawaban ini berasal dari {src_kb['label']}.)"

    related = [e["judul"] for e in (src_kb.get("alur") or [])
               if e is not entry][:2] + (src_kb.get("saran") or [])[:2]
    return {"source": "kb", "kind": kind, "portal": src_portal, "reply": reply,
            "confidence": "tinggi" if score >= MIN_SCORE * 2 else "sedang",
            "related": related[:4]}


def ai_context(portal: str | None) -> str:
    """Ringkasan KB untuk disuntikkan ke prompt AI (dipakai hanya saat KB gagal)."""
    blocks = []
    for p in filter(None, [portal, GENERAL]):
        kb = load_kb(p)
        if not kb:
            continue
        fitur = "; ".join(f"{f['nama']} ({f['modul']}): {f['deskripsi']}" for f in kb.get("fitur", []))
        alur = "\n".join(f"- {a['judul']}: " + " → ".join(a.get("langkah", []))
                         for a in kb.get("alur", []))
        blocks.append(f"## {kb['label']}\n{kb['ringkasan']}\nMODUL: {fitur}\nALUR:\n{alur}")
    return "\n\n".join(blocks)
