"""
PT Rahaza — Phase F2 Accounting Core
Shared posting helpers: translate business events into balanced JE (posted).

All posting is idempotent via (source_module, source_ref). On posting error,
we STORE the error on the source document (post_error) and return a dict with
`ok=False` so the caller can persist state — **we never raise, business ops keep going**.

Helpers:
  post_ar_invoice(db, invoice, user)         → AR Invoice issuance
  post_ar_payment(db, invoice, movement, user) → AR receipt (1 payment = 1 JE)
  post_ap_invoice(db, invoice, user)         → AP Invoice issuance
  post_ap_payment(db, invoice, movement, user) → AP disbursement
  post_expense(db, expense, user)            → Expense (cash or non-cash)
  post_payroll_run(db, run, user)            → Payroll finalize (F3)
  post_inventory_receive(db, movement, user) → Material receive (F3)
  post_inventory_issue(db, mi, user)         → Material issue (F3)
  post_inventory_adjust(db, movement, user)  → Material adjust (F3)
  post_cogs_shipment(db, shipment, user)     → COGS on dispatch (F3)
"""
import logging
import uuid
from datetime import datetime, timezone, date
from typing import Optional

from routes.rahaza_posting_profiles import get_mapping

log = logging.getLogger(__name__)


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ───────────────────────── Core JE builder ────────────────────────────────────
async def _ensure_period_open(db, d: date) -> Optional[str]:
    """Return None if OK, else error message string (graceful, no raise)."""
    ym = d.strftime("%Y-%m")
    per = await db.rahaza_periods.find_one({"period_code": ym})
    if per and per.get("status") in ("closed", "locked"):
        return f"Periode {ym} sudah {per['status']}. Posting ditolak."
    return None


async def _get_account(db, code: str):
    if not code:
        return None
    return await db.rahaza_coa_accounts.find_one({"code": code, "active": True}, {"_id": 0})


async def _gen_je_number(db, d: date) -> str:
    # RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    from utils.counters import gen_prefixed_number
    return await gen_prefixed_number(
        db, "rahaza_journal_entries", "je_number", f"JE-{d.strftime('%Y%m%d')}-", 4)


async def _find_existing_je(db, source_module: str, source_ref: str):
    return await db.rahaza_journal_entries.find_one(
        {"source_module": source_module, "source_ref": source_ref, "status": {"$ne": "voided"}},
        {"_id": 0},
    )


async def _create_posted_je(
    db,
    je_date: date,
    memo: str,
    source_module: str,
    source_ref: str,
    lines_raw: list,
    user: dict,
    status: str = "posted",
) -> dict:
    """Create a JE + mirror lines. Validates balance + account existence.

    `status` — F9 (sesi #12): laporan **pencairan marketplace** dibukukan sebagai
    **DRAFT** dulu, bukan langsung `posted`. Alasannya bukan birokrasi: angka
    pencairan berasal dari pihak LUAR (Shopee/TikTok) dan sering memuat potongan
    yang belum pernah kita lihat. Kalau ia langsung masuk buku besar, koreksinya
    harus lewat jurnal pembalik — dan jejak "pernah salah" itu ikut ke laporan
    L/R yang sudah dibagikan. Keuangan menyetujuinya lewat endpoint yang SUDAH
    ada (`POST /api/rahaza/journals/{je_id}/post`).

    Nilai bawaan tetap `posted` supaya seluruh pemanggil lama tidak berubah
    perilakunya.
    Returns dict {ok, je_id, je_number, error?}."""
    # Normalize + validate lines
    total_d = 0.0
    total_c = 0.0
    norm = []
    for i, ln in enumerate(lines_raw):
        code = (ln.get("account_code") or "").strip()
        if not code:
            return {"ok": False, "error": f"Baris #{i+1}: account_code kosong (mapping CoA missing)."}
        acc = await _get_account(db, code)
        if not acc:
            return {"ok": False, "error": f"Baris #{i+1}: akun '{code}' tidak ditemukan/aktif."}
        if acc.get("is_group"):
            return {"ok": False, "error": f"Baris #{i+1}: akun '{code}' adalah header (non-postable)."}
        d_amt = float(ln.get("debit") or 0)
        c_amt = float(ln.get("credit") or 0)
        if d_amt < 0 or c_amt < 0:
            return {"ok": False, "error": f"Baris #{i+1}: nilai negatif tidak boleh."}
        if d_amt > 0 and c_amt > 0:
            return {"ok": False, "error": f"Baris #{i+1}: satu baris hanya debit ATAU credit."}
        if d_amt == 0 and c_amt == 0:
            continue  # skip zero-amount lines
        norm.append({
            "line_id": _uid(),
            "account_code": code,
            "account_name": acc.get("name"),
            "account_type": acc.get("type"),
            "debit": round(d_amt, 2),
            "credit": round(c_amt, 2),
            "description": (ln.get("description") or "").strip(),
            "cost_center_id": ln.get("cost_center_id") or None,
        })
        total_d += d_amt
        total_c += c_amt
    if len(norm) < 2:
        return {"ok": False, "error": "Jurnal harus minimal 2 baris."}
    if round(total_d, 2) != round(total_c, 2):
        return {"ok": False, "error": f"Jurnal tidak seimbang. Dr {total_d} ≠ Cr {total_c}."}

    # Period guard
    err = await _ensure_period_open(db, je_date)
    if err:
        return {"ok": False, "error": err}

    je_number = await _gen_je_number(db, je_date)
    je_id = _uid()
    je_doc = {
        "id": je_id,
        "je_number": je_number,
        "date": je_date.isoformat(),
        "memo": memo,
        "source_module": source_module,
        "source_ref": source_ref,
        "status": status,
        "total_debit": round(total_d, 2),
        "total_credit": round(total_c, 2),
        "lines": norm,
        "created_at": _now(),
        "updated_at": _now(),
        "posted_at": _now() if status == "posted" else None,
        "posted_by": ((user or {}).get("id") or "system") if status == "posted" else None,
        "created_by": (user or {}).get("id") or "system",
        "created_by_name": (user or {}).get("name", "system"),
        "voided_at": None,
        "voided_by": None,
    }
    await db.rahaza_journal_entries.insert_one(je_doc)

    # mirror lines for fast GL/TB
    rows = [{
        "id": _uid(),
        "je_id": je_id,
        "je_number": je_number,
        "date": je_doc["date"],
        "period_code": je_doc["date"][:7],
        "account_code": ln["account_code"],
        "account_name": ln["account_name"],
        "account_type": ln["account_type"],
        "debit": ln["debit"],
        "credit": ln["credit"],
        "description": ln.get("description", ""),
        "cost_center_id": ln.get("cost_center_id"),
        "source_module": source_module,
        "source_ref": source_ref,
        "created_at": _now(),
    } for ln in norm]
    # Mirror lines untuk GL/TB cepat — HANYA untuk jurnal yang benar-benar
    # `posted`. Untuk DRAFT, cermin ini sengaja TIDAK dibuat; kalau dibuat, dua
    # hal buruk terjadi sekaligus: (1) angkanya sudah muncul di buku besar &
    # neraca saldo padahal belum disetujui, dan (2) saat Keuangan menyetujuinya,
    # `POST /journals/{id}/post` memanggil `_mirror_lines()` lagi ⇒ setiap baris
    # tercatat DUA KALI. Jadi ini bukan optimasi, ini pencegah salah saldo.
    if status == "posted" and rows:
        await db.rahaza_journal_lines.insert_many(rows)

    return {"ok": True, "je_id": je_id, "je_number": je_number}


async def _void_je_by_source(db, source_module: str, source_ref: str, user: dict, reason: str = ""):
    je = await _find_existing_je(db, source_module, source_ref)
    if not je:
        return {"ok": True, "voided": False, "reason": "JE not found"}
    je_date = date.fromisoformat(je["date"])
    err = await _ensure_period_open(db, je_date)
    if err:
        return {"ok": False, "error": err}
    await db.rahaza_journal_entries.update_one(
        {"id": je["id"]},
        {"$set": {
            "status": "voided",
            "voided_at": _now(),
            "voided_by": (user or {}).get("id") or "system",
            "void_reason": reason,
            "updated_at": _now(),
        }},
    )
    await db.rahaza_journal_lines.delete_many({"je_id": je["id"]})
    return {"ok": True, "voided": True, "je_id": je["id"], "je_number": je["je_number"]}


async def _save_source_posting_result(db, collection: str, doc_id: str, result: dict, prefix: str = "gl"):
    """Persist posting outcome on the source document.
    With prefix='gl' (default): stores gl_posted_at, gl_je_id, gl_je_number, post_error.
    With prefix='wip_complete': stores wip_complete_posted, wip_complete_je_id, etc.
    """
    if prefix == "gl":
        if result.get("ok"):
            upd = {
                "gl_posted_at": _now(),
                "gl_je_id": result["je_id"],
                "gl_je_number": result["je_number"],
                "post_error": None,
                "post_error_at": None,
            }
        else:
            upd = {
                "post_error": result.get("error") or "Unknown posting error",
                "post_error_at": _now(),
            }
    else:
        if result.get("ok"):
            upd = {
                f"{prefix}_posted": True,
                f"{prefix}_je_id": result.get("je_id"),
                f"{prefix}_je_number": result.get("je_number"),
                f"{prefix}_error": None,
            }
        else:
            upd = {
                f"{prefix}_posted": False,
                f"{prefix}_je_id": None,
                f"{prefix}_je_number": None,
                f"{prefix}_error": result.get("error") or "Unknown posting error",
                f"{prefix}_error_at": _now(),
            }
    try:
        await db[collection].update_one({"id": doc_id}, {"$set": upd})
    except Exception as e:
        log.warning(f"Failed to write posting result to {collection}/{doc_id}: {e}")


# ───────────────────────── SUBLEDGER RESOLUTION (C-01) ────────────────────────
async def _resolve_ar_code(db, control_code: str, customer_id: str = None, sales_channel: str = None, user: dict = None) -> str:
    """Akun AR untuk sebuah pelanggan/channel: subledger Auto-COA (customer > channel) → kontrol."""
    try:
        from routes.coa_auto import resolve_subledger_account
        sub = None
        if customer_id:
            sub = await resolve_subledger_account(db, "customer", entity_id=customer_id, user=user)
        if not sub and sales_channel:
            sub = await resolve_subledger_account(db, "channel", entity_code=sales_channel, user=user)
        if sub:
            return sub
    except Exception as _e:
        log.warning(f"[ar] resolve AR subledger gagal, pakai kontrol: {_e}")
    return control_code


async def _account_from_issuance_je(db, source_modules: list, source_ref: str, side: str) -> Optional[str]:
    """Akun AR/AP dari jurnal penerbitan yang sudah ada (baris debit/kredit terbesar)."""
    for sm in source_modules:
        je = await _find_existing_je(db, sm, source_ref)
        if je:
            lines = [ln for ln in je.get("lines") or [] if float(ln.get(side) or 0) > 0]
            if lines:
                return max(lines, key=lambda ln: float(ln.get(side) or 0)).get("account_code")
    return None


async def _ar_account_for_invoice(db, invoice: dict, control_code: str) -> str:
    """Semua posting lanjutan AR (payment/CN/write-off) WAJIB menutup di akun yang sama
    dgn jurnal penerbitan: kolom gl_ar_account_code → jurnal penerbitan → kontrol."""
    if invoice.get("gl_ar_account_code"):
        return invoice["gl_ar_account_code"]
    inv_id = invoice.get("id")
    code = (await _account_from_issuance_je(db, ["ar_invoice"], f"ar:{inv_id}", "debit")
            or await _account_from_issuance_je(db, ["maklon_ar_invoice"], f"maklon_ar:{inv_id}", "debit"))
    return code or control_code


async def _ap_account_for_invoice(db, invoice: dict, control_code: str) -> str:
    if invoice.get("gl_ap_account_code"):
        return invoice["gl_ap_account_code"]
    inv_id = invoice.get("id")
    code = (await _account_from_issuance_je(db, ["ap_invoice"], f"ap:{inv_id}", "credit")
            or await _account_from_issuance_je(db, ["cmt_ap_invoice"], f"cmt_ap:{inv_id}", "credit"))
    return code or control_code


# ───────────────────────── AR POSTING ─────────────────────────────────────────
async def post_ar_invoice(db, invoice: dict, user: dict) -> dict:
    """Post AR Invoice (issuance). Dr AR / Cr Revenue (+ Cr Tax if tax_pct > 0).
    Supports per-channel revenue routing via rahaza_channel_gl_mapping.
    Idempotent via source_ref = invoice.id."""
    inv_id = invoice.get("id")
    source_ref = f"ar:{inv_id}"
    existing = await _find_existing_je(db, "ar_invoice", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "ar_invoice")

    # ── Per-channel revenue routing ──────────────────────────────────────────
    sales_channel = (invoice.get("sales_channel") or "").strip()
    channel_gl = None
    if sales_channel:
        channel_gl = await db.rahaza_channel_gl_mapping.find_one(
            {"channel_key": sales_channel, "active": True}, {"_id": 0}
        )

    # Gunakan channel GL jika ada, fallback ke posting profile default
    ar_code  = (channel_gl or {}).get("debit_ar")    or mapping.get("debit_ar")
    rev_code = (channel_gl or {}).get("credit_revenue") or mapping.get("credit_revenue")
    tax_code = mapping.get("credit_tax_output")
    # ────────────────────────────────────────────────────────────────────────

    # ── Phase 6: per-customer / per-channel AR subledger override (C-01) ──────
    if ar_code:
        ar_code = await _resolve_ar_code(db, ar_code, invoice.get("customer_id"), sales_channel, user)

    if not ar_code or not rev_code:
        result = {"ok": False, "error": "Mapping 'ar_invoice' belum lengkap (debit_ar/credit_revenue)."}
        await _save_source_posting_result(db, "rahaza_ar_invoices", inv_id, result)
        return result

    total = float(invoice.get("total") if invoice.get("total") is not None else invoice.get("total_amount") or 0)
    subtotal = float(invoice.get("subtotal") or 0)
    tax = float(invoice.get("tax_amount") or invoice.get("tax") or 0)
    
    # Phase 9C: Sales Discount Support
    discount = float(invoice.get("discount_amount") or 0)
    gross_revenue = subtotal + discount  # Revenue sebelum discount
    
    try:
        je_date = date.fromisoformat((invoice.get("issue_date") or str(date.today()))[:10])
    except Exception:
        je_date = date.today()

    memo = f"AR Invoice {invoice.get('invoice_number')} · {invoice.get('customer_name') or ''}".strip()
    desc = f"Invoice {invoice.get('invoice_number')}"
    
    lines = []
    
    # Phase 9C: If discount > 0, split entry
    if discount > 0:
        # Dr. AR (net after discount) + Dr. Sales Discount / Cr. Revenue (gross) / Cr. Tax
        discount_code = mapping.get("debit_sales_discount")
        if not discount_code:
            result = {"ok": False, "error": "Mapping 'ar_invoice.debit_sales_discount' belum diisi."}
            await _save_source_posting_result(db, "rahaza_ar_invoices", inv_id, result)
            return result
        lines.append({"account_code": ar_code, "debit": total, "credit": 0, "description": desc})
        lines.append({"account_code": discount_code, "debit": discount, "credit": 0, "description": f"{desc} - Discount"})
        lines.append({"account_code": rev_code, "debit": 0, "credit": gross_revenue, "description": desc})
    else:
        # Original logic: Dr. AR / Cr. Revenue
        lines.append({"account_code": ar_code, "debit": total, "credit": 0, "description": desc})
        lines.append({"account_code": rev_code, "debit": 0, "credit": subtotal, "description": desc})
    
    if tax > 0 and tax_code:
        lines.append({"account_code": tax_code, "debit": 0, "credit": tax, "description": f"{desc} - PPN"})

    result = await _create_posted_je(db, je_date, memo, "ar_invoice", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_ar_invoices", inv_id, result)
    if result.get("ok"):
        await db.rahaza_ar_invoices.update_one({"id": inv_id}, {"$set": {"gl_ar_account_code": ar_code}})
    return result


async def post_ar_payment(db, invoice: dict, amount: float, cash_account_id: Optional[str], payment_date: str, user: dict, movement_id: Optional[str] = None) -> dict:
    """Post AR receipt (1 payment). Dr Cash / Cr AR. idempotent via source_ref = movement_id or fallback."""
    inv_id = invoice.get("id")
    source_ref = f"arpay:{movement_id or inv_id + ':' + (payment_date or '')}:{int(round(amount))}"
    existing = await _find_existing_je(db, "ar_payment", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "ar_payment")
    ar_code = await _ar_account_for_invoice(db, invoice, mapping.get("credit_ar"))
    cash_default = mapping.get("debit_cash_default")
    cash_code = cash_default
    # override from cash account if it has gl_account_code
    if cash_account_id:
        cash_acc = await db.rahaza_cash_accounts.find_one({"id": cash_account_id}, {"_id": 0})
        if cash_acc and cash_acc.get("gl_account_code"):
            cash_code = cash_acc["gl_account_code"]
    if not ar_code or not cash_code:
        result = {"ok": False, "error": "Mapping 'ar_payment' belum lengkap (credit_ar/debit_cash)."}
        # store on movement if available, else on invoice
        if movement_id:
            await _save_source_posting_result(db, "rahaza_cash_movements", movement_id, result)
        return result

    try:
        je_date = date.fromisoformat((payment_date or str(date.today()))[:10])
    except Exception:
        je_date = date.today()
    memo = f"Pembayaran AR {invoice.get('invoice_number')} · {invoice.get('customer_name') or ''}".strip()
    desc = f"Payment {invoice.get('invoice_number')}"
    lines = [
        {"account_code": cash_code, "debit": amount, "credit": 0, "description": desc},
        {"account_code": ar_code, "debit": 0, "credit": amount, "description": desc},
    ]
    result = await _create_posted_je(db, je_date, memo, "ar_payment", source_ref, lines, user)
    if movement_id:
        await _save_source_posting_result(db, "rahaza_cash_movements", movement_id, result)
    return result



# ───────────────────────── CREDIT NOTE POSTING (Phase 7B) ─────────────────────
async def post_credit_note(db, credit_note: dict, user: dict) -> dict:
    """
    Post Credit Note (reversal of AR invoice). Dr Revenue / Cr AR.
    This reverses the revenue recognized when the sale was made.
    Idempotent via source_ref = cn:{cn_id}.
    """
    cn_id = credit_note.get("id")
    source_ref = f"cn:{cn_id}"
    existing = await _find_existing_je(db, "credit_note", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    # credit_note mapping (Dr Retur Penjualan / Cr AR); AR = akun pelanggan/channel yang sama dgn invoice
    mapping = await get_mapping(db, "credit_note")
    ar_mapping = await get_mapping(db, "ar_invoice")
    ar_code = mapping.get("credit_ar") or ar_mapping.get("debit_ar")
    rev_code = mapping.get("debit_revenue") or ar_mapping.get("credit_revenue")
    if ar_code:
        if credit_note.get("ar_invoice_id"):
            src_inv = await db.rahaza_ar_invoices.find_one({"id": credit_note["ar_invoice_id"]}, {"_id": 0}) or {"id": credit_note["ar_invoice_id"]}
            ar_code = await _ar_account_for_invoice(db, src_inv, ar_code)
        else:
            ar_code = await _resolve_ar_code(db, ar_code, credit_note.get("customer_id"),
                                             credit_note.get("sales_channel") or credit_note.get("platform"), user)
    
    if not ar_code or not rev_code:
        result = {"ok": False, "error": "Mapping 'credit_note' belum lengkap (debit_revenue/credit_ar)."}
        await _save_source_posting_result(db, "rahaza_credit_notes", cn_id, result, prefix="gl")
        return result

    total = float(credit_note.get("total") or 0)
    try:
        je_date = date.fromisoformat((credit_note.get("issue_date") or str(date.today()))[:10])
    except Exception:
        je_date = date.today()

    memo = f"Credit Note {credit_note.get('cn_number')} - {credit_note.get('platform', '')}".strip()
    desc = f"CN {credit_note.get('cn_number')}"
    
    # Reverse entry: Dr Revenue / Cr AR (opposite of AR invoice)
    lines = [
        {"account_code": rev_code, "debit": total, "credit": 0, "description": desc},
        {"account_code": ar_code, "debit": 0, "credit": total, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "credit_note", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_credit_notes", cn_id, result, prefix="gl")
    return result


# ───────────────────────── AP POSTING ─────────────────────────────────────────
async def post_ap_invoice(db, invoice: dict, user: dict) -> dict:
    """Post AP Invoice (issuance). Dr Expense (or Inventory) / Cr AP (+ Dr Tax Input if tax).
    MVP: default to expense account. Caller can tag invoice with `gl_debit_code` for override.
    Idempotent via source_ref."""
    inv_id = invoice.get("id")
    source_ref = f"ap:{inv_id}"
    existing = await _find_existing_je(db, "ap_invoice", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "ap_invoice")
    ap_code = mapping.get("credit_ap")
    # gl_debit_code override; 'grni' = tagihan supplier atas barang yang sudah diterima (C-02)
    exp_default = invoice.get("gl_debit_code") or mapping.get("debit_expense_default")
    if (invoice.get("source") == "gr" or invoice.get("gr_ids")) and not invoice.get("gl_debit_code"):
        exp_default = mapping.get("debit_grni") or exp_default
    tax_code = mapping.get("debit_tax_input")

    # ── Phase 6: per-supplier AP subledger override ──────────────────────────
    # Arahkan sisi Hutang (Cr AP) ke akun subledger milik supplier bila Auto-COA
    # aktif & supplier dikenal (match by vendor_code/vendor_name di rahaza_vendors).
    # NON-FATAL + fallback ke akun kontrol (ap_code).
    try:
        from routes.coa_auto import resolve_subledger_account
        sub_ap = await resolve_subledger_account(
            db, "supplier",
            entity_id=invoice.get("vendor_id"),
            entity_code=invoice.get("vendor_code"),
            entity_name=invoice.get("vendor_name"),
            user=user,
        )
        if sub_ap:
            ap_code = sub_ap
    except Exception as _e:
        log.warning(f"[ap_invoice] resolve AP subledger gagal, pakai kontrol: {_e}")

    if not ap_code or not exp_default:
        result = {"ok": False, "error": "Mapping 'ap_invoice' belum lengkap (credit_ap/debit_expense)."}
        await _save_source_posting_result(db, "rahaza_ap_invoices", inv_id, result)
        return result

    total = float(invoice.get("total") or 0)
    subtotal = float(invoice.get("subtotal") or 0)
    tax = float(invoice.get("tax_amount") or invoice.get("tax") or 0)
    try:
        je_date = date.fromisoformat((invoice.get("issue_date") or str(date.today()))[:10])
    except Exception:
        je_date = date.today()

    memo = f"AP Invoice {invoice.get('invoice_number')} · {invoice.get('vendor_name') or ''}".strip()
    desc = f"AP {invoice.get('invoice_number')}"
    lines = [
        {"account_code": exp_default, "debit": subtotal, "credit": 0, "description": desc},
        {"account_code": ap_code, "debit": 0, "credit": total, "description": desc},
    ]
    if tax > 0 and tax_code:
        lines.append({"account_code": tax_code, "debit": tax, "credit": 0, "description": f"{desc} - PPN Masukan"})

    result = await _create_posted_je(db, je_date, memo, "ap_invoice", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_ap_invoices", inv_id, result)
    if result.get("ok"):
        await db.rahaza_ap_invoices.update_one({"id": inv_id}, {"$set": {"gl_ap_account_code": ap_code}})
    return result


async def post_ap_payment(db, invoice: dict, amount: float, cash_account_id: Optional[str], payment_date: str, user: dict, movement_id: Optional[str] = None, discount_taken: float = 0) -> dict:
    """
    Post AP disbursement. Dr AP / Cr Cash (+ Cr Purchase Discount if early payment).
    
    Phase 10B: Purchase Discount Support
    - If discount_taken > 0 (early payment discount):
      Dr. AP (full amount)
          Cr. Cash (net after discount)
          Cr. Purchase Discount (discount amount)
    """
    inv_id = invoice.get("id")
    source_ref = f"appay:{movement_id or inv_id + ':' + (payment_date or '')}:{int(round(amount))}"
    existing = await _find_existing_je(db, "ap_payment", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "ap_payment")
    ap_code = await _ap_account_for_invoice(db, invoice, mapping.get("debit_ap"))
    cash_default = mapping.get("credit_cash_default")
    purchase_discount_code = mapping.get("credit_purchase_discount")  # Phase 10B
    if discount_taken > 0 and not purchase_discount_code:
        return {"ok": False, "error": "Mapping 'ap_payment.credit_purchase_discount' belum diisi."}
    
    cash_code = cash_default
    if cash_account_id:
        cash_acc = await db.rahaza_cash_accounts.find_one({"id": cash_account_id}, {"_id": 0})
        if cash_acc and cash_acc.get("gl_account_code"):
            cash_code = cash_acc["gl_account_code"]
    if not ap_code or not cash_code:
        result = {"ok": False, "error": "Mapping 'ap_payment' belum lengkap (debit_ap/credit_cash)."}
        if movement_id:
            await _save_source_posting_result(db, "rahaza_cash_movements", movement_id, result)
        return result

    try:
        je_date = date.fromisoformat((payment_date or str(date.today()))[:10])
    except Exception:
        je_date = date.today()
    
    memo = f"Pembayaran AP {invoice.get('invoice_number')} · {invoice.get('vendor_name') or ''}".strip()
    desc = f"AP Payment {invoice.get('invoice_number')}"
    
    lines = []
    
    # Phase 10B: Purchase Discount Logic
    if discount_taken > 0:
        # Dr. AP (full amount) / Cr. Cash (net) / Cr. Purchase Discount
        cash_paid = amount - discount_taken
        lines.append({"account_code": ap_code, "debit": amount, "credit": 0, "description": desc})
        lines.append({"account_code": cash_code, "debit": 0, "credit": cash_paid, "description": desc})
        lines.append({"account_code": purchase_discount_code, "debit": 0, "credit": discount_taken, "description": f"{desc} - Early Payment Discount"})
        memo += f" (Discount: Rp {discount_taken:,.0f})"
    else:
        # Original logic: Dr. AP / Cr. Cash
        lines.append({"account_code": ap_code, "debit": amount, "credit": 0, "description": desc})
        lines.append({"account_code": cash_code, "debit": 0, "credit": amount, "description": desc})
    
    result = await _create_posted_je(db, je_date, memo, "ap_payment", source_ref, lines, user)
    if movement_id:
        await _save_source_posting_result(db, "rahaza_cash_movements", movement_id, result)
    return result


# ───────────────────────── EXPENSE POSTING ────────────────────────────────────
async def post_expense(db, expense: dict, user: dict) -> dict:
    """Post Expense. Dr Expense / Cr Cash (if cash account) OR Cr AP clearing (if no cash)."""
    exp_id = expense.get("id")
    source_ref = f"exp:{exp_id}"
    existing = await _find_existing_je(db, "expense", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "expense")
    exp_code = expense.get("gl_debit_code") or mapping.get("debit_expense_default")
    cash_default = mapping.get("credit_cash_default")
    cash_acc_id = expense.get("account_id")
    cash_code = cash_default
    if cash_acc_id:
        cash_acc = await db.rahaza_cash_accounts.find_one({"id": cash_acc_id}, {"_id": 0})
        if cash_acc and cash_acc.get("gl_account_code"):
            cash_code = cash_acc["gl_account_code"]
    if not exp_code or not cash_code:
        result = {"ok": False, "error": "Mapping 'expense' belum lengkap (debit_expense/credit_cash)."}
        await _save_source_posting_result(db, "rahaza_expenses", exp_id, result)
        return result

    amount = float(expense.get("amount") or 0)
    if amount <= 0:
        return {"ok": False, "error": "amount expense <= 0"}
    try:
        je_date = date.fromisoformat((expense.get("date") or str(date.today()))[:10])
    except Exception:
        je_date = date.today()
    memo = f"Expense: {expense.get('description') or expense.get('category') or ''}".strip()
    lines = [
        {"account_code": exp_code, "debit": amount, "credit": 0, "description": memo, "cost_center_id": expense.get("cost_center_id")},
        {"account_code": cash_code, "debit": 0, "credit": amount, "description": memo},
    ]
    result = await _create_posted_je(db, je_date, memo, "expense", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_expenses", exp_id, result)
    return result


# ───────────────────────── VOID HELPERS (for cancel/reverse) ─────────────────
async def void_ar_invoice_posting(db, invoice_id: str, user: dict, reason: str = ""):
    return await _void_je_by_source(db, "ar_invoice", f"ar:{invoice_id}", user, reason)


async def void_ap_invoice_posting(db, invoice_id: str, user: dict, reason: str = ""):
    return await _void_je_by_source(db, "ap_invoice", f"ap:{invoice_id}", user, reason)


# ───────────────────────── F3 STUBS ───────────────────────────────────────────
async def post_payroll_run(db, run: dict, user: dict) -> dict:
    """Payroll finalize → JE. Dr Salary Expense / Cr Hutang Gaji (+PPh21 + BPJS if present).
    Idempotent via source_ref = payroll_run_id."""
    run_id = run.get("id")
    source_ref = f"payroll:{run_id}"
    existing = await _find_existing_je(db, "payroll_finalize", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "payroll_finalize")
    sal_expense = mapping.get("debit_salary_expense")
    sal_payable = mapping.get("credit_salary_payable")
    pph21_code = mapping.get("credit_tax_pph21")
    bpjs_code = mapping.get("credit_bpjs_payable")
    if not sal_expense or not sal_payable:
        result = {"ok": False, "error": "Mapping 'payroll_finalize' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_payroll_runs", run_id, result)
        return result

    total_gross = float(run.get("total_gross") or 0)
    total_net = float(run.get("total_net") or 0)
    total_deductions = float(run.get("total_deductions") or 0)
    # Breakdown deductions — MVP: simplistic. If run has bpjs_total/pph21_total, use them.
    pph21 = float(run.get("total_pph21") or 0)
    bpjs = float(run.get("total_bpjs_employee") or 0)
    other_ded = max(0, total_deductions - pph21 - bpjs)

    try:
        run_to = run.get("period_to") or str(date.today())
        je_date = date.fromisoformat(str(run_to)[:10])
    except Exception:
        je_date = date.today()
    memo = f"Payroll Run {run.get('run_number')} · {run.get('period_from')}–{run.get('period_to')}".strip()
    desc = f"Payroll {run.get('run_number')}"
    lines = [
        {"account_code": sal_expense, "debit": total_gross, "credit": 0, "description": desc},
    ]
    # Credit side: payable net + deductions
    if total_net > 0:
        lines.append({"account_code": sal_payable, "debit": 0, "credit": total_net, "description": f"{desc} - Net"})
    if pph21 > 0 and pph21_code:
        lines.append({"account_code": pph21_code, "debit": 0, "credit": pph21, "description": f"{desc} - PPh21"})
    if bpjs > 0 and bpjs_code:
        lines.append({"account_code": bpjs_code, "debit": 0, "credit": bpjs, "description": f"{desc} - BPJS"})
    if other_ded > 0 and total_net + pph21 + bpjs + other_ded == total_gross:
        # other deductions go to salary payable as well (stay as liability adjustment)
        lines.append({"account_code": sal_payable, "debit": 0, "credit": other_ded, "description": f"{desc} - Other Deductions"})

    result = await _create_posted_je(db, je_date, memo, "payroll_finalize", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_payroll_runs", run_id, result)
    return result


async def post_payroll_payment(db, run: dict, payment_date: str, bank_code: str, user: dict) -> dict:
    """
    Pembayaran gaji → JE.
    Dr 2-1200 Hutang Gaji & Upah [total_net]
    Cr [bank_code]               [total_net]
    Idempotent via source_ref = payrollpay:{run_id}.
    """
    run_id     = run.get("id")
    source_ref = f"payrollpay:{run_id}"
    existing   = await _find_existing_je(db, "payroll_payment", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    # CoA: hutang gaji (bisa override dari mapping)
    mapping      = await get_mapping(db, "payroll_payment")
    payable_code = mapping.get("debit_salary_payable")
    if not bank_code:
        bank_code = mapping.get("credit_bank_default")
    if not payable_code or not bank_code:
        return {"ok": False, "error": "Mapping 'payroll_payment' belum lengkap (debit_salary_payable/credit_bank_default)."}

    total_net = float(run.get("total_net") or 0)
    if total_net <= 0:
        return {"ok": False, "error": "Total net = 0, tidak ada yang perlu dibayar."}

    try:
        je_date = date.fromisoformat((payment_date or str(date.today()))[:10])
    except Exception:
        je_date = date.today()

    memo = (
        f"Pembayaran Gaji {run.get('run_number')} · "
        f"{run.get('period_from')}–{run.get('period_to')}"
    ).strip()
    desc = f"Bayar Gaji {run.get('run_number')}"
    lines = [
        {"account_code": payable_code, "debit": total_net, "credit": 0,         "description": desc},
        {"account_code": bank_code,    "debit": 0,         "credit": total_net,  "description": desc},
    ]
    result = await _create_posted_je(db, je_date, memo, "payroll_payment", source_ref, lines, user)
    # Simpan payment result pada run — pakai field berbeda agar tidak timpa gl_je dari finalize
    if result.get("ok"):
        await db.rahaza_payroll_runs.update_one(
            {"id": run_id},
            {"$set": {
                "payment_gl_je_id":     result["je_id"],
                "payment_gl_je_number": result["je_number"],
                "payment_error":        None,
                "updated_at":           _now(),
            }}
        )
    else:
        await db.rahaza_payroll_runs.update_one(
            {"id": run_id},
            {"$set": {"payment_error": result.get("error"), "updated_at": _now()}}
        )
    return result


async def void_payroll_payment(db, run_id: str, user: dict, reason: str = "") -> dict:
    """Void jurnal pembayaran gaji (untuk koreksi). Tidak membatalkan finalize JE."""
    source_ref = f"payrollpay:{run_id}"
    result = await _void_je_by_source(db, "payroll_payment", source_ref, user, reason)
    if result.get("ok"):
        await db.rahaza_payroll_runs.update_one(
            {"id": run_id},
            {"$set": {
                "payment_status":       "void",
                "payment_gl_je_id":     None,
                "payment_gl_je_number": None,
                "updated_at":           _now(),
            }}
        )
    return result


async def post_inventory_receive(db, movement: dict, user: dict) -> dict:
    """Material receive → Dr Inventory RM / Cr AP clearing."""
    mv_id = movement.get("id")
    source_ref = f"mvrcv:{mv_id}"
    existing = await _find_existing_je(db, "inventory_receive", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "inventory_receive")
    inv_code = mapping.get("debit_inventory_rm")
    ap_code = mapping.get("credit_ap_clearing")
    if not inv_code or not ap_code:
        result = {"ok": False, "error": "Mapping 'inventory_receive' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
        return result

    qty = float(movement.get("qty") or 0)
    unit_cost = float(movement.get("unit_cost") or 0)
    if unit_cost <= 0:
        # try enrich from material master
        mat_id = movement.get("material_id")
        mat = await db.rahaza_materials.find_one({"id": mat_id}, {"_id": 0}) if mat_id else None
        unit_cost = float((mat or {}).get("unit_cost") or 0)
    amount = qty * unit_cost
    if amount <= 0:
        result = {"ok": False, "error": f"Amount {amount} <= 0 (qty × unit_cost). Set unit_cost di material master."}
        await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
        return result

    try:
        je_date = datetime.fromisoformat(str(movement.get("timestamp") or movement.get("created_at") or _now()).replace("Z", "+00:00")).date()
    except Exception:
        je_date = date.today()
    memo = f"Material Receive · {movement.get('material_name') or movement.get('material_id')}"
    desc = memo
    lines = [
        {"account_code": inv_code, "debit": amount, "credit": 0, "description": desc},
        {"account_code": ap_code, "debit": 0, "credit": amount, "description": desc},
    ]
    result = await _create_posted_je(db, je_date, memo, "inventory_receive", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
    return result


async def post_inventory_issue(db, mi: dict, user: dict) -> dict:
    """Material Issue confirmed → Dr WIP / Cr Inventory RM."""
    mi_id = mi.get("id")
    source_ref = f"mi:{mi_id}"
    existing = await _find_existing_je(db, "inventory_issue", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "inventory_issue")
    wip_code = mapping.get("debit_wip")
    inv_code = mapping.get("credit_inventory_rm")
    if not wip_code or not inv_code:
        result = {"ok": False, "error": "Mapping 'inventory_issue' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_material_issues", mi_id, result)
        return result

    # compute total amount from items × material unit_cost (batch fetch materials)
    items_mi = mi.get("items") or []
    mat_ids_posting = [it.get("material_id") for it in items_mi if it.get("material_id")]
    mat_cost_map = {}
    if mat_ids_posting:
        async for m in db.rahaza_materials.find(
            {"id": {"$in": mat_ids_posting}}, {"_id": 0, "id": 1, "unit_cost": 1}
        ):
            mat_cost_map[m["id"]] = float(m.get("unit_cost") or 0)
    total = 0.0
    for it in items_mi:
        qty = float(it.get("qty_issued") or it.get("qty_required") or 0)
        if qty <= 0:
            continue
        unit_cost = mat_cost_map.get(it.get("material_id"), 0.0)
        total += qty * unit_cost
    if total <= 0:
        result = {"ok": False, "error": "Total issue cost = 0 (materials tanpa unit_cost)."}
        await _save_source_posting_result(db, "rahaza_material_issues", mi_id, result)
        return result

    try:
        je_date = datetime.fromisoformat(str(mi.get("issued_at") or mi.get("created_at") or _now()).replace("Z", "+00:00")).date()
    except Exception:
        je_date = date.today()
    memo = f"Material Issue {mi.get('mi_number')} → WO {mi.get('work_order_id') or '-'}"
    lines = [
        {"account_code": wip_code, "debit": total, "credit": 0, "description": memo},
        {"account_code": inv_code, "debit": 0, "credit": total, "description": memo},
    ]
    result = await _create_posted_je(db, je_date, memo, "inventory_issue", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_material_issues", mi_id, result)
    return result


async def post_accessory_issue(db, mv: dict, user: dict) -> dict:
    """FASE 8 — Pengeluaran AKSESORIS bernilai → Dr WIP / Cr Persediaan.

    Kenapa fungsi terpisah dari `post_inventory_issue`: pengeluaran aksesoris tidak
    lewat dokumen Material Issue (`rahaza_material_issues`) — ia satu baris mutasi
    kartu stok (`rahaza_material_movements`). Mapping akun & pembuat JE-nya SAMA
    (`inventory_issue`) supaya beban pemakaian aksesoris masuk akun yang sama dgn
    pemakaian bahan. Idempoten lewat `source_ref = accmv:<movement_id>`.

    `mv` wajib memuat: id, material_id, qty (positif = jumlah keluar), material_name,
    unit_cost (opsional; bila kosong diambil dari master material).
    """
    mv_id = mv.get("id")
    source_ref = f"accmv:{mv_id}"
    existing = await _find_existing_je(db, "inventory_issue", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"],
                "already_posted": True}

    mapping = await get_mapping(db, "inventory_issue")
    wip_code = mapping.get("debit_wip")
    inv_code = mapping.get("credit_inventory_rm")
    if not wip_code or not inv_code:
        result = {"ok": False, "error": "Mapping 'inventory_issue' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
        return result

    qty = abs(float(mv.get("qty") or 0))
    unit_cost = float(mv.get("unit_cost") or 0)
    if unit_cost <= 0:
        mat = await db.rahaza_materials.find_one({"id": mv.get("material_id")}, {"_id": 0}) \
            if mv.get("material_id") else None
        unit_cost = float((mat or {}).get("unit_cost") or 0)
    total = round(qty * unit_cost, 2)
    if total <= 0:
        result = {"ok": False,
                  "error": "Nilai pengeluaran = 0 (harga satuan aksesoris belum diisi di master)."}
        await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
        return result

    try:
        je_date = datetime.fromisoformat(
            str(mv.get("created_at") or _now()).replace("Z", "+00:00")).date()
    except Exception:
        je_date = date.today()
    memo = f"Pemakaian Aksesoris · {mv.get('material_name') or mv.get('material_id')} · {qty}"
    lines = [
        {"account_code": wip_code, "debit": total, "credit": 0, "description": memo},
        {"account_code": inv_code, "debit": 0, "credit": total, "description": memo},
    ]
    result = await _create_posted_je(db, je_date, memo, "inventory_issue", source_ref, lines, user)
    result["amount"] = total
    await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
    return result


async def post_inventory_adjust(db, movement: dict, user: dict) -> dict:
    """Material adjust (+ or -) → Dr/Cr Inventory vs Adjustment Expense.
    Phase 11C: If adjustment_reason='scrap', use Scrap Expense account instead.
    """
    mv_id = movement.get("id")
    source_ref = f"mvadj:{mv_id}"
    existing = await _find_existing_je(db, "inventory_adjust", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    # Phase 11C: Check if this is scrap adjustment
    adjustment_reason = movement.get("adjustment_reason", "").lower()
    is_scrap = adjustment_reason in ["scrap", "waste", "reject", "rusak"]
    
    if is_scrap:
        mapping = await get_mapping(db, "inventory_scrap")
        inv_code = mapping.get("credit_inventory_rm")
        scrap_code = mapping.get("debit_scrap_expense")
        adj_code = scrap_code  # Use scrap expense account
    else:
        mapping = await get_mapping(db, "inventory_adjust")
        inv_code = mapping.get("inventory_rm")
        adj_code = mapping.get("adjustment_expense")
    
    if not inv_code or not adj_code:
        result = {"ok": False, "error": f"Mapping '{'inventory_scrap' if is_scrap else 'inventory_adjust'}' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
        return result

    qty = float(movement.get("qty") or 0)
    mat_id = movement.get("material_id")
    mat = await db.rahaza_materials.find_one({"id": mat_id}, {"_id": 0}) if mat_id else None
    unit_cost = float((mat or {}).get("unit_cost") or 0)
    amount = abs(qty) * unit_cost
    if amount <= 0:
        result = {"ok": False, "error": "Amount adjust = 0 (set unit_cost material)."}
        await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
        return result

    try:
        je_date = datetime.fromisoformat(str(movement.get("timestamp") or movement.get("created_at") or _now()).replace("Z", "+00:00")).date()
    except Exception:
        je_date = date.today()
    
    # Phase 11C: Enhanced memo for scrap
    if is_scrap:
        memo = f"Material Scrap · {movement.get('material_name') or mat_id} · {abs(qty)} (Reason: {adjustment_reason})"
    else:
        memo = f"Stock Adjust · {movement.get('material_name') or mat_id} · {qty}"
    
    # If qty > 0 → increase stock (Dr Inventory / Cr Adjustment). If qty < 0 → decrease (Dr Adjustment / Cr Inventory).
    # For scrap: always qty < 0 (decrease), so Dr Scrap Expense / Cr Inventory
    if qty > 0:
        lines = [
            {"account_code": inv_code, "debit": amount, "credit": 0, "description": memo},
            {"account_code": adj_code, "debit": 0, "credit": amount, "description": memo},
        ]
    else:
        lines = [
            {"account_code": adj_code, "debit": amount, "credit": 0, "description": memo},
            {"account_code": inv_code, "debit": 0, "credit": amount, "description": memo},
        ]
    
    event_type = "inventory_scrap" if is_scrap else "inventory_adjust"
    result = await _create_posted_je(db, je_date, memo, event_type, source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_material_movements", mv_id, result)
    return result


async def post_cogs_shipment(db, shipment: dict, user: dict) -> dict:
    """Shipment dispatched → COGS posting based on HPP snapshots per WO in shipment items.
    Dr COGS Material+Labor+Overhead / Cr FG Inventory.
    """
    shp_id = shipment.get("id")
    source_ref = f"cogs:{shp_id}"
    existing = await _find_existing_je(db, "cogs_shipment", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "cogs_shipment")
    dm = mapping.get("debit_cogs_material")
    dl = mapping.get("debit_cogs_labor")
    do = mapping.get("debit_cogs_overhead")
    cfg = mapping.get("credit_fg_inventory")
    if not all([dm, dl, do, cfg]):
        result = {"ok": False, "error": "Mapping 'cogs_shipment' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_shipments", shp_id, result)
        return result

    # H-07 (sesi 110): dasar biaya JUJUR & berurutan seperti dispatch buyer —
    #   1. fifo_batch: lapisan HPP batch yang benar-benar dimakan saat barang keluar (fg_cogs di item)
    #   2. hpp_snapshot: snapshot HPP per WO (jalur lama), hanya bila tidak ada lapisan biaya.
    items = shipment.get("items") or []
    fifo = await _fifo_rows_to_components(db, [
        {"sku": it.get("sku_code") or it.get("sku"), "qty_shipped": it.get("qty"), "fg_cogs": it.get("fg_cogs"),
         "fg_cogs_layers": it.get("fg_cogs_layers"), "fg_cogs_uncosted_qty": it.get("fg_cogs_uncosted_qty")}
        for it in items])
    basis = "fifo_batch" if fifo["total"] > 0 else "hpp_snapshot"
    total_material = total_labor = total_overhead = 0.0
    if basis == "fifo_batch":
        total_material, total_labor, total_overhead = fifo["material"], fifo["labor"], fifo["overhead"]
    else:
        wo_ids = list({it.get("work_order_id") or it.get("wo_id") for it in items if it.get("work_order_id") or it.get("wo_id")})
        snapshots = await db.rahaza_hpp_snapshots.find({"work_order_id": {"$in": wo_ids}}, {"_id": 0}).to_list(500) if wo_ids else []
        snap_by_wo = {s["work_order_id"]: s for s in snapshots}
        for it in items:
            snap = snap_by_wo.get(it.get("work_order_id") or it.get("wo_id"))
            if not snap:
                continue
            qty = float(it.get("qty") or 0)
            qty_completed = float(snap.get("qty_completed") or snap.get("qty") or 1) or 1
            total_material += float(snap.get("material_cost") or 0) * (qty / qty_completed)
            total_labor += float(snap.get("labor_cost") or 0) * (qty / qty_completed)
            total_overhead += float(snap.get("overhead_cost") or 0) * (qty / qty_completed)

    total_cogs = total_material + total_labor + total_overhead
    if total_cogs <= 0:
        result = {"ok": False, "reason": "zero_cogs", "basis": basis, "uncosted_qty": fifo["uncosted_qty"],
                  "error": "COGS = 0: barang keluar tanpa lapisan biaya batch DAN tanpa snapshot HPP — "
                           "isi biaya jahit SPK + BOM batch masuknya dulu supaya COGS bisa dibukukan."}
        await _save_source_posting_result(db, "rahaza_shipments", shp_id, result)
        return result

    try:
        je_date = datetime.fromisoformat(str(shipment.get("dispatched_at") or shipment.get("shipment_date") or _now()).replace("Z", "+00:00")).date()
    except Exception:
        je_date = date.today()
    basis_label = "biaya batch FIFO" if basis == "fifo_batch" else "perkiraan HPP SPK"
    memo = f"COGS Shipment {shipment.get('shipment_number')} ({basis_label})"
    lines = []
    if total_material > 0:
        lines.append({"account_code": dm, "debit": round(total_material, 2), "credit": 0, "description": f"{memo} - Material"})
    if total_labor > 0:
        lines.append({"account_code": dl, "debit": round(total_labor, 2), "credit": 0, "description": f"{memo} - Labor"})
    if total_overhead > 0:
        lines.append({"account_code": do, "debit": round(total_overhead, 2), "credit": 0, "description": f"{memo} - Overhead"})
    lines.append({"account_code": cfg, "debit": 0, "credit": round(total_cogs, 2), "description": f"{memo} - FG Inventory"})

    result = await _create_posted_je(db, je_date, memo, "cogs_shipment", source_ref, lines, user)
    result["basis"] = basis
    result["total_cogs"] = round(total_cogs, 2)
    result["uncosted_qty"] = fifo["uncosted_qty"]
    if fifo["gaps"]:
        result["gaps"] = fifo["gaps"]
    if fifo["uncosted_qty"]:
        result["note"] = (f"{fifo['uncosted_qty']} pcs keluar TANPA lapisan biaya batch — COGS lebih rendah dari kenyataan.")
    await _save_source_posting_result(db, "rahaza_shipments", shp_id, result)
    return result



# ─── Phase 6A — WIP → Finished Goods on WO Completion ────────────────────────
# [WS-G6 CLEANUP] `post_wip_to_fg_on_wo_complete(db, wo, user)` DIHAPUS.
# Fungsi ini orphan/dead-code: satu-satunya pemanggil ada di
# routes/_archive/rahaza_multistage/rahaza_work_orders.py yang TIDAK di-import
# di server.py (FASE 4 E10 DELETE). Jalur WIP→FG yang AKTIF & benar adalah
# `post_wip_to_fg_on_job_complete(db, job, user)` (dipanggil oleh
# production_internal_adapter.on_job_completed_internal saat job Internal selesai).
# Profil posting `wip_to_fg_on_wo_complete` tetap ada di seed (harmless).


# ───────────────────────── PRODUCTION VARIANCE POSTING (Phase 7C) ─────────────
async def post_production_variance(db, variance: dict, user: dict) -> dict:
    """
    Post production variance to GL.
    
    OVERPRODUCTION: Dr Inventory FG / Cr Variance Income
    UNDERPRODUCTION: Dr Variance Loss / Cr WIP
    
    Idempotent via source_ref = variance:{variance_id}
    """
    var_id = variance.get("id")
    source_ref = f"variance:{var_id}"
    existing = await _find_existing_je(db, "production_variance", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    variance_type = variance.get("variance_type")
    variance_value = float(variance.get("variance_value", 0))
    
    if variance_value <= 0:
        result = {"ok": False, "error": "variance_value harus > 0 (hitung dulu dengan endpoint post-gl)."}
        await _save_source_posting_result(db, "production_variances", var_id, result, prefix="gl")
        return result
    
    # Get mapping based on variance type
    if variance_type == "OVERPRODUCTION":
        mapping = await get_mapping(db, "variance_overproduction")
        debit_code = mapping.get("debit_inventory_fg")
        credit_code = mapping.get("credit_variance_income")
    elif variance_type == "UNDERPRODUCTION":
        mapping = await get_mapping(db, "variance_underproduction")
        debit_code = mapping.get("debit_variance_loss")
        credit_code = mapping.get("credit_wip")
    else:
        result = {"ok": False, "error": f"variance_type tidak valid: {variance_type}"}
        await _save_source_posting_result(db, "production_variances", var_id, result, prefix="gl")
        return result
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": f"Mapping 'variance_{variance_type.lower()}' belum lengkap."}
        await _save_source_posting_result(db, "production_variances", var_id, result, prefix="gl")
        return result

    try:
        je_date = date.fromisoformat((variance.get("created_at") or str(datetime.now(timezone.utc)))[:10])
    except Exception:
        je_date = date.today()

    memo = f"Variance {variance_type} - Job {variance.get('job_number', '')} ({variance.get('total_variance_qty', 0)} pcs)".strip()
    desc = f"Variance {variance.get('job_number', '')}"
    
    lines = [
        {"account_code": debit_code, "debit": variance_value, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": variance_value, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "production_variance", source_ref, lines, user)
    await _save_source_posting_result(db, "production_variances", var_id, result, prefix="gl")


# ───────────────────────── ASSET ACQUISITION POSTING (Phase 8A) ───────────────
async def post_asset_acquisition(db, asset: dict, user: dict) -> dict:
    """
    Post asset acquisition from GRN. Dr. Fixed Asset / Cr. AP Clearing.
    Idempotent via source_ref = asset_acq:{asset_id}.
    """
    asset_id = asset.get("id")
    source_ref = f"asset_acq:{asset_id}"
    existing = await _find_existing_je(db, "asset_acquisition", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "asset_acquisition")
    debit_code = mapping.get("debit_fixed_asset")
    credit_code = mapping.get("credit_ap_clearing")
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": "Mapping 'asset_acquisition' belum lengkap."}
        await _save_source_posting_result(db, "rahaza_fixed_assets", asset_id, result, prefix="gl")
        return result

    total_cost = float(asset.get("purchase_cost") or 0)
    if total_cost <= 0:
        result = {"ok": False, "error": "Asset purchase_cost harus > 0"}
        await _save_source_posting_result(db, "rahaza_fixed_assets", asset_id, result, prefix="gl")
        return result

    try:
        je_date = date.fromisoformat((asset.get("purchase_date") or str(date.today()))[:10])
    except Exception:
        je_date = date.today()

    memo = f"Asset Acquisition: {asset.get('code')} - {asset.get('name')} from GR {asset.get('grn_number', '')}".strip()
    desc = f"Asset {asset.get('code')}"
    
    lines = [
        {"account_code": debit_code, "debit": total_cost, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": total_cost, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "asset_acquisition", source_ref, lines, user)
    await _save_source_posting_result(db, "rahaza_fixed_assets", asset_id, result, prefix="gl")


# ───────────────────────── DEPRECIATION POSTING (Phase 8B) ────────────────────
async def post_depreciation(db, schedule: dict, asset: dict, user: dict) -> dict:
    """
    Post monthly depreciation. Dr. Depreciation Expense / Cr. Accumulated Depreciation.
    Idempotent via source_ref = depreciation:{asset_id}:{period}.
    """
    asset_id = schedule.get("asset_id")
    period = schedule.get("period")
    source_ref = f"depreciation:{asset_id}:{period}"
    existing = await _find_existing_je(db, "depreciation", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "depreciation")
    debit_code = mapping.get("debit_depr_expense")
    credit_code = mapping.get("credit_accum_depr")
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": "Mapping 'depreciation' belum lengkap."}
        return result

    depr_amount = float(schedule.get("depr_amount") or 0)
    if depr_amount <= 0:
        result = {"ok": False, "error": "Depreciation amount harus > 0"}
        return result

    # JE date = last day of period
    try:
        period_date = datetime.strptime(period, "%Y-%m").date()
        # Last day of month
        from calendar import monthrange
        last_day = monthrange(period_date.year, period_date.month)[1]
        je_date = date(period_date.year, period_date.month, last_day)
    except Exception:
        je_date = date.today()

    asset_name = asset.get("name", schedule.get("asset_name", "Unknown Asset"))
    asset_code = asset.get("code", schedule.get("asset_code", "N/A"))
    memo = f"Depreciation {period}: {asset_code} - {asset_name}".strip()
    desc = f"Depr {asset_code}"
    
    lines = [
        {"account_code": debit_code, "debit": depr_amount, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": depr_amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "depreciation", source_ref, lines, user)
    return result


# ───────────────────────── ACCRUAL POSTING (Phase 8C) ─────────────────────────
async def post_accrual_expense(db, accrual: dict, user: dict) -> dict:
    """
    Post accrual expense. Dr. Expense / Cr. Accrued Expenses.
    Idempotent via source_ref = accrual:{accrual_id}.
    """
    accrual_id = accrual.get("id")
    source_ref = f"accrual:{accrual_id}"
    existing = await _find_existing_je(db, "accrual", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    # Get accounts from accrual or mapping
    expense_account = accrual.get("expense_account", "").strip()
    accrued_account = accrual.get("accrued_account", "").strip()
    
    if not expense_account or not accrued_account:
        # Use default mapping based on accrual_type
        accrual_type = accrual.get("accrual_type", "other")
        mapping = await get_mapping(db, f"accrual_{accrual_type}")
        
        if not mapping or not mapping.get("debit_expense") or not mapping.get("credit_accrued"):
            # Fallback to generic accrual mapping
            mapping = await get_mapping(db, "accrual")
        
        expense_account = expense_account or mapping.get("debit_expense")
        accrued_account = accrued_account or mapping.get("credit_accrued")
    
    amount = float(accrual.get("amount") or 0)
    if amount <= 0:
        result = {"ok": False, "error": "Accrual amount harus > 0"}
        return result

    # JE date = last day of period
    period = accrual.get("period")
    try:
        period_date = datetime.strptime(period, "%Y-%m").date()
        from calendar import monthrange
        last_day = monthrange(period_date.year, period_date.month)[1]
        je_date = date(period_date.year, period_date.month, last_day)
    except Exception:
        je_date = date.today()

    accrual_type = accrual.get("accrual_type", "other").upper()
    description = accrual.get("description", "Accrual")
    memo = f"Accrual {period}: {accrual_type} - {description}".strip()
    desc = f"Accrual {accrual_type}"
    
    lines = [
        {"account_code": expense_account, "debit": amount, "credit": 0, "description": desc},
        {"account_code": accrued_account, "debit": 0, "credit": amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "accrual", source_ref, lines, user)
    return result


async def post_accrual_reversal(db, accrual: dict, user: dict) -> dict:
    """
    Post accrual reversal (next period). Dr. Accrued Expenses / Cr. Expense.
    Idempotent via source_ref = accrual_reversal:{accrual_id}.
    """
    accrual_id = accrual.get("id")
    source_ref = f"accrual_reversal:{accrual_id}"
    existing = await _find_existing_je(db, "accrual_reversal", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    # Get accounts (same as original accrual but reversed)
    expense_account = accrual.get("expense_account", "").strip()
    accrued_account = accrual.get("accrued_account", "").strip()
    
    if not expense_account or not accrued_account:
        accrual_type = accrual.get("accrual_type", "other")
        mapping = await get_mapping(db, f"accrual_{accrual_type}")
        
        if not mapping or not mapping.get("debit_expense") or not mapping.get("credit_accrued"):
            mapping = await get_mapping(db, "accrual")
        
        expense_account = expense_account or mapping.get("debit_expense")
        accrued_account = accrued_account or mapping.get("credit_accrued")
    
    amount = float(accrual.get("amount") or 0)
    if amount <= 0:
        result = {"ok": False, "error": "Accrual amount harus > 0"}
        return result

    # JE date = first day of reversal period
    reversal_period = accrual.get("reversal_period")
    if not reversal_period:
        # Calculate next period
        period = accrual.get("period")
        period_date = datetime.strptime(period, "%Y-%m").date()
        from dateutil.relativedelta import relativedelta
        next_period = period_date + relativedelta(months=1)
        reversal_period = next_period.strftime("%Y-%m")
    
    try:
        period_date = datetime.strptime(reversal_period, "%Y-%m").date()
        je_date = date(period_date.year, period_date.month, 1)  # First day of month
    except Exception:
        je_date = date.today()

    accrual_type = accrual.get("accrual_type", "other").upper()
    description = accrual.get("description", "Accrual")
    original_period = accrual.get("period")
    memo = f"Accrual Reversal {reversal_period}: {accrual_type} - {description} (original {original_period})".strip()
    desc = f"Rev Accrual {accrual_type}"
    
    # Reversed entry: Dr. Accrued / Cr. Expense
    lines = [
        {"account_code": accrued_account, "debit": amount, "credit": 0, "description": desc},
        {"account_code": expense_account, "debit": 0, "credit": amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "accrual_reversal", source_ref, lines, user)
    return result


# ───────────────────────── BAD DEBT WRITE-OFF (Phase 9A) ──────────────────────
async def post_bad_debt_writeoff(db, ar_invoice: dict, user: dict) -> dict:
    """
    Post bad debt write-off. Dr. Bad Debt Expense / Cr. AR.
    Idempotent via source_ref = bad_debt:{invoice_id}.
    """
    invoice_id = ar_invoice.get("id")
    source_ref = f"bad_debt:{invoice_id}"
    existing = await _find_existing_je(db, "bad_debt_writeoff", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "bad_debt_writeoff")
    debit_code = mapping.get("debit_bad_debt_expense")
    credit_code = await _ar_account_for_invoice(db, ar_invoice, mapping.get("credit_ar"))
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": "Mapping 'bad_debt_writeoff' belum lengkap."}
        return result

    write_off_amount = float(ar_invoice.get("write_off_amount") or ar_invoice.get("balance") or 0)
    if write_off_amount <= 0:
        result = {"ok": False, "error": "Write-off amount harus > 0"}
        return result

    # JE date = write-off date
    write_off_date = ar_invoice.get("write_off_date") or date.today().isoformat()
    try:
        je_date = date.fromisoformat(write_off_date[:10])
    except Exception:
        je_date = date.today()

    invoice_number = ar_invoice.get("invoice_number", "N/A")
    reason = ar_invoice.get("write_off_reason", "Bad debt")
    memo = f"Bad Debt Write-off: {invoice_number} - {reason}".strip()
    desc = f"Bad Debt {invoice_number}"
    
    lines = [
        {"account_code": debit_code, "debit": write_off_amount, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": write_off_amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "bad_debt_writeoff", source_ref, lines, user)
    
    # Update AR invoice with GL info
    if result.get("ok"):
        await db.rahaza_ar_invoices.update_one(
            {"id": invoice_id},
            {"$set": {
                "gl_bad_debt_je_id": result.get("je_id"),
                "gl_bad_debt_je_number": result.get("je_number"),
                "gl_bad_debt_posted_at": datetime.now(timezone.utc),
            }}
        )
    
    return result


# ───────────────────────── BANK RECON ADJUSTMENT (Phase 9B) ───────────────────
async def post_bank_recon_adjustment(db, adjustment: dict, user: dict) -> dict:
    """
    Post bank reconciliation adjustment based on type.
    Idempotent via source_ref = bank_adj:{adjustment_id}.
    """
    adjustment_id = adjustment.get("id")
    source_ref = f"bank_adj:{adjustment_id}"
    existing = await _find_existing_je(db, "bank_recon_adjustment", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    adjustment_type = adjustment.get("adjustment_type")
    amount = float(adjustment.get("amount") or 0)
    
    if amount <= 0:
        result = {"ok": False, "error": "Adjustment amount harus > 0"}
        return result
    
    # Get accounts based on type or custom
    expense_account = adjustment.get("expense_account", "").strip()
    income_account = adjustment.get("income_account", "").strip()
    bank_account_code = (adjustment.get("bank_account_code") or "").strip() or None
    if not bank_account_code:
        _bm = await get_mapping(db, "bank_recon_charge")
        bank_account_code = _bm.get("credit_bank")
    
    # Determine accounts based on adjustment_type
    # H-06: akun bank SESI/rekening (bank_account_code) menang atas default profil (dulu selalu 1-1201).
    if adjustment_type == "bank_charge":
        mapping = await get_mapping(db, "bank_recon_charge")
        debit_code = mapping.get("debit_bank_charges")
        credit_code = bank_account_code or mapping.get("credit_bank")
    elif adjustment_type == "interest_income":
        mapping = await get_mapping(db, "bank_recon_interest")
        debit_code = bank_account_code or mapping.get("debit_bank")
        credit_code = mapping.get("credit_interest_income")
    elif adjustment_type == "service_fee":
        mapping = await get_mapping(db, "bank_recon_service_fee")
        debit_code = mapping.get("debit_service_fee")
        credit_code = bank_account_code or mapping.get("credit_bank")
    else:  # correction or other
        # Use custom accounts if provided
        if expense_account and not income_account:
            # Expense: Dr. Expense / Cr. Bank
            debit_code = expense_account
            credit_code = bank_account_code
        elif income_account and not expense_account:
            # Income: Dr. Bank / Cr. Income
            debit_code = bank_account_code
            credit_code = income_account
        elif expense_account and income_account:
            # Custom both
            debit_code = expense_account
            credit_code = income_account
        else:
            result = {"ok": False, "error": "adjustment_type 'correction/other' requires expense_account or income_account"}
            return result
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": f"Mapping untuk '{adjustment_type}' belum lengkap."}
        return result

    # JE date = adjustment date
    adjustment_date = adjustment.get("adjustment_date") or date.today().isoformat()
    try:
        je_date = date.fromisoformat(adjustment_date[:10])
    except Exception:
        je_date = date.today()

    bank_name = adjustment.get("bank_account_name", "Bank")
    description = adjustment.get("description", adjustment_type.replace("_", " ").title())
    ref_number = adjustment.get("reference_number", "")
    memo = f"Bank Recon Adjustment: {bank_name} - {description}"
    if ref_number:
        memo += f" (Ref: {ref_number})"
    
    desc = f"{adjustment_type.replace('_', ' ').title()}"
    
    lines = [
        {"account_code": debit_code, "debit": amount, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "bank_recon_adjustment", source_ref, lines, user)
    return result


# ───────────────────────── ASSET DISPOSAL (Phase 10A) ─────────────────────────
async def post_asset_disposal(db, asset: dict, user: dict) -> dict:
    """
    Post asset disposal dengan complex 3-way entry.
    
    Entry:
    Dr. Accumulated Depreciation (clear accumulated)
    Dr. Cash/Bank (proceeds)
    Dr. Loss on Disposal (if NBV > proceeds) OR Cr. Gain on Disposal (if proceeds > NBV)
        Cr. Fixed Asset (original cost)
    
    Idempotent via source_ref = asset_disposal:{asset_id}.
    """
    asset_id = asset.get("id")
    source_ref = f"asset_disposal:{asset_id}"
    existing = await _find_existing_je(db, "asset_disposal", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "asset_disposal")
    
    # Get account codes
    credit_asset_code = mapping.get("credit_fixed_asset")
    debit_accum_code = mapping.get("debit_accum_depr")
    debit_cash_code = mapping.get("debit_cash")
    debit_loss_code = mapping.get("debit_loss_on_disposal")
    credit_gain_code = mapping.get("credit_gain_on_disposal")
    
    if not all([credit_asset_code, debit_accum_code, debit_cash_code, debit_loss_code, credit_gain_code]):
        result = {"ok": False, "error": "Mapping 'asset_disposal' belum lengkap."}
        return result

    # Get amounts
    original_cost = float(asset.get("purchase_cost") or 0)
    accumulated_depr = float(asset.get("accumulated_depr_at_disposal") or 0)
    proceeds = float(asset.get("disposal_proceeds") or asset.get("disposal_value") or 0)
    nbv = original_cost - accumulated_depr
    gain_loss_amount = proceeds - nbv
    gain_or_loss = asset.get("gain_or_loss") or ("gain" if gain_loss_amount > 0 else "loss" if gain_loss_amount < 0 else "none")
    
    if original_cost <= 0:
        result = {"ok": False, "error": "Asset purchase_cost harus > 0"}
        return result

    # JE date = disposal date
    disposal_date = asset.get("disposal_date") or date.today().isoformat()
    try:
        je_date = date.fromisoformat(disposal_date[:10])
    except Exception:
        je_date = date.today()

    asset_code = asset.get("code", "N/A")
    asset_name = asset.get("name", "Unknown Asset")
    memo = f"Asset Disposal: {asset_code} - {asset_name} ({gain_or_loss.upper()}: Rp {abs(gain_loss_amount):,.0f})".strip()
    desc = f"Disposal {asset_code}"
    
    lines = []
    
    # Dr. Accumulated Depreciation (always)
    if accumulated_depr > 0:
        lines.append({"account_code": debit_accum_code, "debit": accumulated_depr, "credit": 0, "description": desc})
    
    # Dr. Cash/Bank (proceeds, can be 0 for scrap/donation)
    if proceeds > 0:
        lines.append({"account_code": debit_cash_code, "debit": proceeds, "credit": 0, "description": desc})
    
    # Dr. Loss OR Cr. Gain
    if gain_or_loss == "loss":
        lines.append({"account_code": debit_loss_code, "debit": abs(gain_loss_amount), "credit": 0, "description": f"{desc} - Loss"})
    elif gain_or_loss == "gain":
        lines.append({"account_code": credit_gain_code, "debit": 0, "credit": abs(gain_loss_amount), "description": f"{desc} - Gain"})
    
    # Cr. Fixed Asset (original cost, always)
    lines.append({"account_code": credit_asset_code, "debit": 0, "credit": original_cost, "description": desc})

    result = await _create_posted_je(db, je_date, memo, "asset_disposal", source_ref, lines, user)
    
    # Update asset with GL info
    if result.get("ok"):
        await db.rahaza_fixed_assets.update_one(
            {"id": asset_id},
            {"$set": {
                "gl_disposal_je_id": result.get("je_id"),
                "gl_disposal_je_number": result.get("je_number"),
                "gl_disposal_posted_at": datetime.now(timezone.utc),
            }}
        )
    
    return result


# ───────────────────────── EMPLOYEE LOAN (Phase 11A & 11B) ────────────────────
async def post_employee_loan_disbursement(db, loan: dict, user: dict) -> dict:
    """
    Post employee loan disbursement. Dr. Employee Loan Receivable / Cr. Cash.
    Idempotent via source_ref = emp_loan_disb:{loan_id}.
    """
    loan_id = loan.get("id")
    source_ref = f"emp_loan_disb:{loan_id}"
    existing = await _find_existing_je(db, "employee_loan_disbursement", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "employee_loan_disbursement")
    debit_code = mapping.get("debit_employee_loan_receivable")
    credit_code = mapping.get("credit_cash")
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": "Mapping 'employee_loan_disbursement' belum lengkap."}
        return result

    loan_amount = float(loan.get("loan_amount") or 0)
    if loan_amount <= 0:
        result = {"ok": False, "error": "Loan amount harus > 0"}
        return result

    disbursement_date = loan.get("disbursement_date") or date.today().isoformat()
    try:
        je_date = date.fromisoformat(disbursement_date[:10])
    except Exception:
        je_date = date.today()

    loan_number = loan.get("loan_number", "N/A")
    employee_name = loan.get("employee_name", "Unknown")
    memo = f"Employee Loan Disbursement: {loan_number} - {employee_name} (Rp {loan_amount:,.0f})".strip()
    desc = f"Loan {loan_number}"
    
    lines = [
        {"account_code": debit_code, "debit": loan_amount, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": loan_amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "employee_loan_disbursement", source_ref, lines, user)
    return result


async def post_employee_loan_repayment_payroll(db, loan: dict, repayment_amount: float, period: str, user: dict) -> dict:
    """
    Post employee loan repayment via payroll deduction.
    Dr. Salary Payable / Cr. Employee Loan Receivable.
    Idempotent via source_ref = emp_loan_repay_payroll:{loan_id}:{period}.
    """
    loan_id = loan.get("id")
    source_ref = f"emp_loan_repay_payroll:{loan_id}:{period}"
    existing = await _find_existing_je(db, "employee_loan_repayment_payroll", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing["je_number"], "already_posted": True}

    mapping = await get_mapping(db, "employee_loan_repayment_payroll")
    debit_code = mapping.get("debit_salary_payable")
    credit_code = mapping.get("credit_employee_loan_receivable")
    
    if not debit_code or not credit_code:
        result = {"ok": False, "error": "Mapping 'employee_loan_repayment_payroll' belum lengkap."}
        return result

    if repayment_amount <= 0:
        result = {"ok": False, "error": "Repayment amount harus > 0"}
        return result

    # JE date = last day of period
    try:
        period_date = datetime.strptime(period, "%Y-%m").date()
        from calendar import monthrange
        last_day = monthrange(period_date.year, period_date.month)[1]
        je_date = date(period_date.year, period_date.month, last_day)
    except Exception:
        je_date = date.today()

    loan_number = loan.get("loan_number", "N/A")
    employee_name = loan.get("employee_name", "Unknown")
    memo = f"Loan Repayment (Payroll): {loan_number} - {employee_name} - {period}".strip()
    desc = f"Loan Repay {loan_number}"
    
    lines = [
        {"account_code": debit_code, "debit": repayment_amount, "credit": 0, "description": desc},
        {"account_code": credit_code, "debit": 0, "credit": repayment_amount, "description": desc},
    ]

    result = await _create_posted_je(db, je_date, memo, "employee_loan_repayment_payroll", source_ref, lines, user)
    return result

# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3 (E10/FIN-1=A): posting ter-anchor production_jobs (engine SOMMERVILLE).
# Reuse mapping existing — TIDAK menambah profile/engine baru.
# ═══════════════════════════════════════════════════════════════════════════════

async def post_wip_to_fg_on_job_complete(db, job: dict, user: dict) -> dict:
    """AD-3: job internal Completed → Dr FG / Cr WIP.
    Nilai = Σ MI issued (job_id) yang sudah diposting; fallback HPP snapshot job."""
    mapping = await get_mapping(db, "wip_to_fg_on_wo_complete")
    if not mapping:
        result = {"ok": False, "reason": "mapping_disabled"}
        await _save_source_posting_result(db, "production_jobs", job["id"], result, prefix="wip")
        return result

    source_ref = f"wip_fg_job:{job['id']}"
    existing = await _find_existing_je(db, "production_job", source_ref)
    if existing:
        result = {"ok": True, "je_id": existing["id"], "je_number": existing.get("je_number"),
                  "already_posted": True}
        await _save_source_posting_result(db, "production_jobs", job["id"], result, prefix="wip")
        return result

    # C-03 absorption: nilai FG = Σ lapisan biaya FG batch PO ini (bahan + jahit
    # cmt_price_snapshot + permak + internal + overhead) — angka yang SAMA dgn yang
    # dipakai COGS dispatch (FIFO lapisan), sehingga FG tidak bersaldo negatif &
    # upah jahit tidak dibukukan dua kali (AP CMT internal sudah Dr WIP 1-1403).
    total_wip = 0.0
    basis = "fg_cost_layers"
    layer_ids = []
    if job.get("po_id"):
        async for ly in db.fg_cost_layers.find(
                {"batch.po_id": job["po_id"], "gl_job_id": {"$in": [None, job["id"]]}}, {"_id": 0}):
            total_wip += float(ly.get("total_cost") or 0)
            layer_ids.append(ly["id"])
    if total_wip <= 0:
        # 1) Fallback: JE material issue utk MI job ini + upah jahit (cmt_price_snapshot × qty baik)
        basis = "material_issues"
        mis = await db.rahaza_material_issues.find(
            {"job_id": job["id"], "status": "issued"}, {"_id": 0}).to_list(200)
        for mi in mis:
            je = await _find_existing_je(db, "inventory_issue", f"mi:{mi['id']}")
            if je:
                total_wip += float(je.get("total_debit") or 0)
        qty_good = float(job.get("qty_good") or job.get("qty_accepted") or job.get("qty_completed") or 0)
        rate = float(job.get("cmt_price_snapshot") or 0)
        if total_wip > 0 and qty_good > 0 and rate > 0:
            total_wip += qty_good * rate
            basis = "material_issues+sewing"

    # 2) Fallback: HPP snapshot job (material + labor + overhead)
    if total_wip <= 0:
        snap = await db.rahaza_hpp_snapshots.find_one({"job_id": job["id"]}, {"_id": 0})
        if snap:
            total_wip = float(snap.get("total_cost") or snap.get("total_hpp") or 0)
            basis = "hpp_snapshot"

    if total_wip <= 0:
        result = {"ok": False, "reason": "zero_wip_value",
                  "detail": "Tidak ada MI terposting maupun HPP snapshot utk job ini"}
        await _save_source_posting_result(db, "production_jobs", job["id"], result, prefix="wip")
        return result

    fg_code = mapping.get("debit_fg_inventory")
    wip_code = mapping.get("credit_wip")
    if not fg_code or not wip_code:
        result = {"ok": False, "reason": "mapping_incomplete",
                  "detail": "Mapping 'wip_to_fg_on_wo_complete' belum lengkap (debit_fg_inventory/credit_wip)."}
        await _save_source_posting_result(db, "production_jobs", job["id"], result, prefix="wip")
        return result

    je_date = date.today()
    if job.get("completed_at"):
        try:
            je_date = date.fromisoformat(str(job["completed_at"])[:10])
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    memo = f"WIP→FG Job {job.get('job_number', '')} (internal)"
    lines = [
        {"account_code": fg_code, "debit": round(total_wip, 2), "credit": 0,
         "description": f"FG masuk gudang — Job {job.get('job_number', '')}"},
        {"account_code": wip_code, "debit": 0, "credit": round(total_wip, 2),
         "description": f"WIP keluar — Job {job.get('job_number', '')} ({basis})"},
    ]
    result = await _create_posted_je(db, je_date, memo, "production_job", source_ref, lines, user)
    if result.get("ok") and layer_ids:
        await db.fg_cost_layers.update_many({"id": {"$in": layer_ids}},
                                            {"$set": {"gl_job_id": job["id"], "gl_je_id": result["je_id"]}})
    result["basis"] = basis
    result["amount"] = total_wip
    await _save_source_posting_result(db, "production_jobs", job["id"], result, prefix="wip")
    return result


async def _fifo_cogs_for_dispatch(db, dispatch_items: list) -> dict:
    """Biaya batch FIFO yang BENAR-BENAR keluar bersama barangnya (sesi #38).

    `core.production_qty_ledger.issue_fg` sudah memakan lapisan biaya tertua dan
    menyimpan hasilnya di baris pengiriman (`fg_cogs`, `fg_cogs_layers`,
    `fg_cogs_uncosted_qty`). Sebelum ini jurnal COGS mengabaikan angka itu dan
    memakai snapshot HPP per SPK — akibatnya laba per pengiriman memakai biaya
    PERKIRAAN sementara gudang mencatat biaya NYATA. Fungsi ini menerjemahkan
    lapisan yang terpakai menjadi tiga komponen akun (bahan · upah · overhead).

    Komponen diambil dari `breakdown` lapisan; upah = jahit + permak + upah
    internal. Bila rincian lapisan tidak diketahui, seluruh nilainya masuk BAHAN
    dan disebut di `gaps` — tidak pernah ditebak diam-diam.
    """
    ids = [i.get("id") for i in dispatch_items if i.get("id")]
    if not ids:
        return {"material": 0.0, "labor": 0.0, "overhead": 0.0, "total": 0.0,
                "detail": [], "uncosted_qty": 0, "gaps": []}
    rows = await db.buyer_shipment_items.find(
        {"id": {"$in": ids}},
        {"_id": 0, "id": 1, "sku": 1, "qty_shipped": 1, "fg_cogs": 1,
         "fg_cogs_layers": 1, "fg_cogs_uncosted_qty": 1}).to_list(1000)
    return await _fifo_rows_to_components(db, rows)


async def _fifo_rows_to_components(db, rows: list) -> dict:
    """Baris {sku, qty_shipped, fg_cogs, fg_cogs_layers, fg_cogs_uncosted_qty} → komponen bahan/upah/overhead.
    Dipakai dispatch buyer (PO internal B2B) DAN fulfillment pesanan online (H-07) — satu rumus."""
    out = {"material": 0.0, "labor": 0.0, "overhead": 0.0, "total": 0.0,
           "detail": [], "uncosted_qty": 0, "gaps": []}
    layer_ids = [ly.get("layer_id") for r in rows for ly in (r.get("fg_cogs_layers") or [])
                 if ly.get("layer_id")]
    layers = {}
    if layer_ids:
        async for ly in db.fg_cost_layers.find({"id": {"$in": layer_ids}},
                                               {"_id": 0, "id": 1, "unit_cost": 1,
                                                "breakdown": 1}):
            layers[ly["id"]] = ly
    for r in rows:
        used = r.get("fg_cogs_layers") or []
        row_total = float(r.get("fg_cogs") or 0)
        # Kekurangan dihitung LEBIH DULU: baris yang keluar SEPENUHNYA tanpa
        # lapisan biaya (fg_cogs 0, layers kosong) dulu dilewati sebelum angka
        # ini dijumlahkan, sehingga pada satu SJ CAMPURAN (1 baris berbiaya +
        # 1 baris tanpa biaya sama sekali) jurnalnya tampak lengkap padahal ada
        # pcs yang keluar gratis. Ditemukan penguji sesi #38.
        uncosted_row = int(r.get("fg_cogs_uncosted_qty") or 0)
        out["uncosted_qty"] += uncosted_row
        if row_total <= 0 and not used:
            if uncosted_row:
                out["gaps"].append(
                    f"{r.get('sku') or 'SKU tak dikenal'}: {uncosted_row} pcs keluar TANPA "
                    "satu pun lapisan biaya batch — tidak ada rupiah yang bisa dibukukan "
                    "untuk baris ini")
            continue
        m = lab = ovh = 0.0
        for u in used:
            qty = float(u.get("qty") or 0)
            amount = float(u.get("total") or (float(u.get("unit_cost") or 0) * qty))
            bd = (layers.get(u.get("layer_id")) or {}).get("breakdown") or {}
            c_mat = float(bd.get("material_cost") or 0)
            c_lab = (float(bd.get("sewing_cost") or 0) + float(bd.get("permak_cost") or 0)
                     + float(bd.get("internal_labor_cost") or 0))
            c_ovh = float(bd.get("overhead_cost") or 0)
            unit_sum = c_mat + c_lab + c_ovh
            if unit_sum <= 0:
                m += amount
                out["gaps"].append(
                    f"Lapisan {u.get('layer_id')} tidak menyimpan rincian biaya — "
                    f"Rp {amount:,.0f} dibukukan sebagai BAHAN")
                continue
            # skala ke nilai yang benar-benar keluar supaya Σ komponen = fg_cogs
            k = amount / (unit_sum * qty) if qty else 0.0
            m += c_mat * qty * k
            lab += c_lab * qty * k
            ovh += c_ovh * qty * k
        out["material"] += m
        out["labor"] += lab
        out["overhead"] += ovh
        out["total"] += m + lab + ovh
        out["detail"].append({
            "sku": r.get("sku"), "qty": int(r.get("qty_shipped") or 0),
            "amount": round(m + lab + ovh),
            "layers": len(used),
            "uncosted_qty": int(r.get("fg_cogs_uncosted_qty") or 0)})
    for k in ("material", "labor", "overhead", "total"):
        out[k] = round(out[k], 2)
    return out


async def post_cogs_on_buyer_dispatch(db, shipment: dict, dispatch_items: list,
                                      dispatch_seq: int, user: dict) -> dict:
    """FIN-1: COGS saat fulfillment PO internal (dispatch buyer shipment).

    SESI #38 — dasar biaya berurutan JUJUR:
      1. **`fifo_batch`** — biaya lapisan batch yang benar-benar keluar dari
         gudang (`fg_cogs` di baris pengiriman). Inilah kebenaran gudang.
      2. **`hpp_snapshot`** — snapshot HPP per SPK (jalur lama), dipakai hanya
         bila barangnya keluar tanpa lapisan biaya sama sekali.
    Dasar yang dipakai selalu disebut di hasil (`basis`) dan di memo jurnal,
    supaya orang yang membaca laba tahu angkanya nyata atau perkiraan.
    Idempoten per dispatch."""
    mapping = await get_mapping(db, "cogs_shipment")
    dm = mapping.get("debit_cogs_material")
    dl = mapping.get("debit_cogs_labor")
    do = mapping.get("debit_cogs_overhead")
    cfg = mapping.get("credit_fg_inventory")
    if not all([dm, dl, do, cfg]):
        return {"ok": False, "reason": "mapping_disabled",
                "error": "Mapping 'cogs_shipment' belum lengkap/aktif."}

    source_ref = f"cogs_job:{shipment['id']}:seq{dispatch_seq}"
    existing = await _find_existing_je(db, "buyer_dispatch", source_ref)
    if existing:
        return {"ok": True, "je_id": existing["id"], "je_number": existing.get("je_number"),
                "already_posted": True}

    job_ids = list({i.get("job_id") for i in dispatch_items if i.get("job_id")})
    if not job_ids:
        ji_ids = [i.get("job_item_id") for i in dispatch_items if i.get("job_item_id")]
        if ji_ids:
            jis = await db.production_job_items.find({"id": {"$in": ji_ids}}, {"_id": 0}).to_list(200)
            ji_map = {j["id"]: j.get("job_id") for j in jis}
            for i in dispatch_items:
                if not i.get("job_id"):
                    i["job_id"] = ji_map.get(i.get("job_item_id"))
            job_ids = list({i.get("job_id") for i in dispatch_items if i.get("job_id")})
    snaps = {}
    if job_ids:
        async for s_ in db.rahaza_hpp_snapshots.find({"job_id": {"$in": job_ids}}, {"_id": 0}):
            snaps[s_["job_id"]] = s_

    fifo = await _fifo_cogs_for_dispatch(db, dispatch_items)
    basis = "fifo_batch" if fifo["total"] > 0 else "hpp_snapshot"
    total_material = 0.0
    total_labor = 0.0
    total_overhead = 0.0
    detail = []
    if basis == "fifo_batch":
        total_material, total_labor, total_overhead = (
            fifo["material"], fifo["labor"], fifo["overhead"])
        detail = fifo["detail"]
    else:
        for it in dispatch_items:
            snap = snaps.get(it.get("job_id"))
            if not snap:
                continue
            qty = int(it.get("qty_shipped") or 0)
            qty_completed = float(snap.get("qty_completed") or snap.get("qty") or 1) or 1
            m = float(snap.get("material_cost") or 0) * (qty / qty_completed)
            l = float(snap.get("labor_cost") or 0) * (qty / qty_completed)
            o = float(snap.get("overhead_cost") or 0) * (qty / qty_completed)
            total_material += m
            total_labor += l
            total_overhead += o
            detail.append({"sku": it.get("sku"), "qty": qty,
                           "hpp_unit": float(snap.get("hpp_unit") or 0),
                           "amount": round(m + l + o)})

    total_material = round(total_material, 2)
    total_labor = round(total_labor, 2)
    total_overhead = round(total_overhead, 2)
    total_cogs = total_material + total_labor + total_overhead

    if total_cogs <= 0:
        return {"ok": False, "reason": "zero_cogs",
                "basis": basis,
                "uncosted_qty": fifo["uncosted_qty"],
                "detail": ("Barang keluar tanpa lapisan biaya batch DAN tanpa snapshot HPP SPK — "
                           "isi biaya jahit SPK + BOM-nya dulu supaya COGS bisa dibukukan.")}

    try:
        je_date = datetime.fromisoformat(str(shipment.get("dispatched_at") or shipment.get("shipment_date") or _now()).replace("Z", "+00:00")).date()
    except Exception:
        je_date = date.today()

    basis_label = ("biaya batch FIFO" if basis == "fifo_batch" else "perkiraan HPP SPK")
    memo = (f"COGS fulfillment {shipment.get('shipment_number', '')} "
            f"dispatch #{dispatch_seq} ({basis_label})")
    lines = []
    if total_material > 0:
        lines.append({"account_code": dm, "debit": total_material, "credit": 0,
                      "description": f"{memo} - Material"})
    if total_labor > 0:
        lines.append({"account_code": dl, "debit": total_labor, "credit": 0,
                      "description": f"{memo} - Labor"})
    if total_overhead > 0:
        lines.append({"account_code": do, "debit": total_overhead, "credit": 0,
                      "description": f"{memo} - Overhead"})
    lines.append({"account_code": cfg, "debit": 0, "credit": total_cogs,
                  "description": f"FG keluar — {shipment.get('shipment_number', '')}"})
    result = await _create_posted_je(db, je_date, memo, "buyer_dispatch", source_ref, lines, user)
    result["amount"] = total_cogs
    result["detail"] = detail
    result["basis"] = basis
    # Kekurangan TIDAK ditutup: qty yang keluar tanpa lapisan biaya membuat COGS
    # lebih rendah dari kenyataan, dan pembaca laba wajib tahu itu.
    result["uncosted_qty"] = fifo["uncosted_qty"]
    if fifo["gaps"]:
        result["gaps"] = fifo["gaps"][:5]
    if fifo["uncosted_qty"]:
        result["note"] = (f"{fifo['uncosted_qty']} pcs keluar TANPA lapisan biaya batch — "
                          "COGS ini lebih rendah dari kenyataan sampai biaya jahit & BOM "
                          "batch masuknya dilengkapi.")
    await _save_source_posting_result(db, "buyer_shipments", shipment["id"], result, prefix=f"cogs_seq{dispatch_seq}")
    return result

