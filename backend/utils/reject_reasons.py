"""reject_reasons — SSOT bentuk `reject_reasons` (FASE 19 / AUDIT-2).

## Bug yang ditutup modul ini

`GET /api/wms/quarantine/summary` bisa **HTTP 500** tergantung DATA.
Jalurnya:

1. `routes/rahaza_grn_qc.py` menyimpan `line["reject_reasons"] = inp.get("reject_reasons", [])`
   — **MENTAH dari body request**, tanpa validasi bentuk.
2. Nilai itu diteruskan ke `core.quarantine.quarantine_in(reject_reasons=...)`
   lalu tersimpan apa adanya di `wh_quarantine_items.reject_reasons`.
3. `core.quarantine.summary()` melakukan `rr.get("code")` untuk setiap elemen.
   Kalau ada satu saja klien yang mengirim `["KOTOR", "SOBEK"]` (list of STRING —
   bentuk yang sangat wajar dikirim orang), baris itu jadi
   `AttributeError: 'str' object has no attribute 'get'` ⇒ **seluruh KPI karantina
   mati**, bukan hanya satu baris.

Bandingkan: `routes/wms_quarantine.py` (jalur MANUAL) SUDAH membersihkan bentuknya.
Jadi satu koleksi punya **dua penulis dengan aturan berbeda** — kelas bug yang
sama dengan `leave_types` (FASE 17) dan alias `yarn_*` (FASE 12).

## Aturan normalisasi (dipakai SEMUA penulis)

Selalu keluar `list[{"code": str, "qty": float, "notes": str}]`.

| Masukan                                  | Keluaran                                            |
|------------------------------------------|-----------------------------------------------------|
| `None` / `""` / `[]` / `{}`              | `[]`                                                |
| `{"code": "X", "qty": 3}`                | `[{code:"X", qty:3.0, notes:""}]`                   |
| `["KOTOR"]` + `default_qty=5`            | `[{code:"KOTOR", qty:5.0, ...}]`  (satu alasan)      |
| `["KOTOR","SOBEK"]` + `default_qty=5`    | qty `0.0` + `qty_unknown=True` (JANGAN gandakan 5!) |
| `"KOTOR, SOBEK"`                         | dipecah per koma                                    |
| elemen tanpa `code`                      | `code="OTHER"`                                      |
| `qty` teks/negatif                       | `0.0`                                               |

**Kenapa qty 0 saat >1 alasan tanpa qty:** memberi `default_qty` ke setiap alasan
akan MENGGANDAKAN kuantitas reject di `by_reason` (2 alasan × 5 pcs = 10 pcs
reject padahal barangnya 5). Lebih baik jujur "qty per alasan tidak diketahui"
(`qty_unknown`) daripada mengarang angka — pelajaran FASE 13 #3.
"""
from __future__ import annotations

from typing import Any

DEFAULT_CODE = "OTHER"
#: Field yang diizinkan bertahan pada tiap alasan (sisanya dibuang — anti field liar).
ALLOWED_KEYS = ("code", "qty", "notes", "qty_unknown")


def _num(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return 0.0
    return round(max(0.0, f), 4)


def _code(v: Any) -> str:
    s = str(v or "").strip()
    return s[:64] if s else DEFAULT_CODE


def _as_entries(raw: Any) -> list[Any]:
    """Bungkus masukan apa pun menjadi list elemen kandidat.

    Wadah KOSONG (`{}`, `[]`, `\"\"`, `\"   \"`) tidak membawa informasi apa pun
    dan HARUS jadi `[]` — bukan satu alasan palsu berkode `OTHER`.
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw] if raw else []
    if isinstance(raw, str):
        return [p for p in (x.strip() for x in raw.split(",")) if p]
    if isinstance(raw, (list, tuple, set)):
        return [e for e in raw if not (isinstance(e, dict) and not e)]
    return [raw]


def normalize_reject_reasons(raw: Any, *, default_qty: float = 0.0) -> list[dict]:
    """Kembalikan bentuk kanonik `list[{code, qty, notes}]` dari masukan apa pun.

    `default_qty` = qty item karantina; dipakai HANYA bila tepat satu alasan yang
    tidak menyebutkan qty (lihat tabel di docstring modul).
    """
    entries = _as_entries(raw)
    staged: list[dict] = []
    for e in entries:
        if isinstance(e, dict):
            has_qty = any(k in e for k in ("qty", "quantity", "qty_reject", "rejected_qty"))
            qty_src = e.get("qty", e.get("quantity", e.get("qty_reject", e.get("rejected_qty"))))
            item = {
                "code": _code(e.get("code") or e.get("reason") or e.get("reason_code")),
                "qty": _num(qty_src),
                "notes": str(e.get("notes") or e.get("note") or "")[:500],
            }
            staged.append({"_has_qty": has_qty and _num(qty_src) > 0, **item})
        elif isinstance(e, (str, int, float)):
            s = str(e).strip()
            if not s:
                continue
            staged.append({"_has_qty": False, "code": _code(s), "qty": 0.0, "notes": ""})
        # bentuk lain (list bersarang, None, objek) dibuang — tak ada informasi kode

    if not staged:
        return []

    missing = [s for s in staged if not s["_has_qty"]]
    single_missing = len(missing) == 1 and len(staged) == 1
    out: list[dict] = []
    for s in staged:
        entry = {k: v for k, v in s.items() if k in ALLOWED_KEYS}
        if not s["_has_qty"]:
            if single_missing and _num(default_qty) > 0:
                entry["qty"] = _num(default_qty)
            else:
                entry["qty"] = 0.0
                entry["qty_unknown"] = True
        out.append(entry)
    return out


def is_canonical(raw: Any) -> bool:
    """True bila `raw` sudah berbentuk kanonik (dipakai sentinel & migrasi).

    Sengaja KETAT: list of dict, setiap dict punya `code` string tak kosong dan
    `qty` numerik. Nilai selain itu = dokumen yang bisa merobohkan `summary()`.
    """
    if raw is None:
        return True
    if not isinstance(raw, list):
        return False
    for e in raw:
        if not isinstance(e, dict):
            return False
        code = e.get("code")
        if not isinstance(code, str) or not code.strip():
            return False
        if not isinstance(e.get("qty", 0), (int, float)) or isinstance(e.get("qty", 0), bool):
            return False
    return True


def summarize_by_reason(rows: list[dict], *, qty_field: str = "remaining_qty") -> dict[str, float]:
    """Agregasi qty per kode alasan, TAHAN terhadap dokumen lama yang belum kanonik.

    Dipakai `core.quarantine.summary()`. Baris tanpa alasan masuk bucket `OTHER`
    memakai `qty_field` barisnya (perilaku lama dipertahankan).
    """
    out: dict[str, float] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        row_qty = _num(r.get(qty_field))
        reasons = normalize_reject_reasons(r.get("reject_reasons"), default_qty=row_qty)
        if not reasons:
            out[DEFAULT_CODE] = round(out.get(DEFAULT_CODE, 0.0) + row_qty, 4)
            continue
        for rr in reasons:
            code = rr["code"]
            out[code] = round(out.get(code, 0.0) + _num(rr.get("qty")), 4)
    return out
