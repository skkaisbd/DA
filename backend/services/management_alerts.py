"""
services/management_alerts.py — Peringatan otomatis untuk manajemen.

PERMINTAAN OWNER (2026-08-06)
----------------------------
"Kirim notifikasi ke manajemen saat ada PO mendekati deadline atau piutang
jatuh tempo."

ATURAN
------
* Sumber data = SSOT lewat `services/mgmt_analytics.domain_scope()` dan
  `rahaza_ar_invoices` (bukan koleksi legacy).
* Menulis notifikasi lewat SATU penulis kanonik `utils/notif_unified.notif_insert`
  ke koleksi `notifications`. (Catatan sejarah: `services/notification_service.py`
  menulis ke `dewi_notifications` yang koleksinya tidak pernah ada dan tidak
  diimpor siapa pun — berkas itu sudah dihapus pada 2026-08-06.)
* **Idempoten**: satu peringatan per (subtype, source_ref, tanggal) — dijalankan
  berulang kali dalam sehari tidak membuat notifikasi ganda.
* Penerima = pengguna dengan peran manajemen/eksekutif (lihat MANAGEMENT_ROLES).
  Bila tidak ada, notifikasi tetap dibuat tanpa `user_id` supaya tidak hilang.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from services.mgmt_analytics import (
    MAX_DOCS, as_iso_date, domain_scope, f as _f, i as _i,
)
from utils.notif_unified import notif_insert
from utils.data_quality import SkipTracker

logger = logging.getLogger(__name__)

# Ambang default: PO diperingatkan bila deadline <= 3 hari lagi atau sudah lewat.
DEADLINE_WARN_DAYS = 3

# ── Ambang peringatan bisa diatur owner (2026-08-07) ─────────────────────────
# Permintaan owner: "beri saya pengaturan berapa hari sebelum tenggat PO
# peringatan mulai dikirim". Ambang PO & piutang DIPISAH (pilihan owner).
# 2026-08-07 (lanjutan) — ditambah ambang antrean RnD: `rnd_attention_days`
# (kuning "perlu perhatian") dan `rnd_stale_days` (merah "terlambat"), dipakai
# kokpit RnD + rapor mingguan. Sebelumnya 3 & 7 hari dipatok di kode.
# Satu dokumen konfigurasi: `dewi_mgmt_alert_config` (_type='main').
ALERT_CONFIG_DEFAULTS = {"po_warn_days": 3, "ar_warn_days": 3,
                         "rnd_attention_days": 3, "rnd_stale_days": 7}
CONFIG_LABELS = {
    "po_warn_days": "Peringatan tenggat PO",
    "ar_warn_days": "Peringatan jatuh tempo piutang",
    "rnd_attention_days": "Antrean RnD perlu perhatian",
    "rnd_stale_days": "Antrean RnD terlambat",
}
CONFIG_MIN, CONFIG_MAX = 0, 60

# ── Ambang NILAI (Rupiah) — kedalaman rantai persetujuan PR (2026-08-07) ─────
# Permintaan owner: "PR bernilai kecil jangan dipaksa lewat 3 tahap".
# Kedalaman persetujuan Permintaan Pengadaan (PR) ditentukan NILAI PR:
#     total <= pr_1_stage_max  → 1 tahap  (Departemen)
#     total <= pr_2_stage_max  → 2 tahap  (Departemen + Keuangan)
#     di atas itu              → 3 tahap  (Departemen + Keuangan + Final/Direksi)
# Disimpan di dokumen YANG SAMA (`dewi_mgmt_alert_config`, _type='main') dan
# disajikan endpoint YANG SAMA (GET/PUT /api/rahaza/management/alert-config),
# supaya owner mengatur seluruh ambang di satu layar (Ringkasan Bisnis → Ambang
# Peringatan). Validatornya DIPISAH: ambang hari dibatasi 0..60, sedangkan ini
# nilai rupiah (0..100 miliar) — memakai validator hari akan menolak "1000000".
# Dibaca oleh routes/dewi_procurement.py::_chain_config (dibekukan saat submit).
PR_CHAIN_DEFAULTS = {"pr_1_stage_max": 1_000_000, "pr_2_stage_max": 25_000_000}
PR_CHAIN_LABELS = {
    "pr_1_stage_max": "PR cukup 1 tahap bila nilai ≤ (Rp)",
    "pr_2_stage_max": "PR cukup 2 tahap bila nilai ≤ (Rp)",
}
MONEY_MIN, MONEY_MAX = 0, 100_000_000_000


async def get_alert_config(db) -> dict:
    """Ambang efektif (bawaan bila belum pernah diatur / nilai rusak)."""
    doc = await db.dewi_mgmt_alert_config.find_one({"_type": "main"}, {"_id": 0}) or {}
    cfg = dict(ALERT_CONFIG_DEFAULTS)
    for k in ALERT_CONFIG_DEFAULTS:
        try:
            iv = int(doc[k])
        except (KeyError, TypeError, ValueError):
            continue
        if CONFIG_MIN <= iv <= CONFIG_MAX:
            cfg[k] = iv
    # Ambang nilai PR (rupiah) — rentang sendiri, jadi diloop terpisah.
    cfg.update(PR_CHAIN_DEFAULTS)
    for k in PR_CHAIN_DEFAULTS:
        try:
            iv = int(doc[k])
        except (KeyError, TypeError, ValueError):
            continue
        if MONEY_MIN <= iv <= MONEY_MAX:
            cfg[k] = iv
    # Jaga agar tetap logis walau dokumen lama menyimpan kombinasi mustahil.
    if cfg["pr_1_stage_max"] > cfg["pr_2_stage_max"]:
        cfg["pr_2_stage_max"] = cfg["pr_1_stage_max"]
    cfg["updated_at"] = (doc.get("updated_at").isoformat()
                         if isinstance(doc.get("updated_at"), datetime) else doc.get("updated_at"))
    cfg["updated_by"] = doc.get("updated_by") or ""
    cfg["defaults"] = {**ALERT_CONFIG_DEFAULTS, **PR_CHAIN_DEFAULTS}
    cfg["labels"] = {**CONFIG_LABELS, **PR_CHAIN_LABELS}
    cfg["min"], cfg["max"] = CONFIG_MIN, CONFIG_MAX
    cfg["money_keys"] = list(PR_CHAIN_DEFAULTS)
    cfg["money_min"], cfg["money_max"] = MONEY_MIN, MONEY_MAX
    return cfg


async def save_alert_config(db, patch: dict, user: dict | None = None) -> dict:
    """Simpan ambang. Melempar ValueError untuk input tidak sah (route → 400)."""
    upd = {}
    for k in ALERT_CONFIG_DEFAULTS:
        if k not in (patch or {}):
            continue
        try:
            iv = int(patch[k])
        except (TypeError, ValueError):
            raise ValueError(f"{k} harus berupa angka hari ({CONFIG_MIN}..{CONFIG_MAX}).")
        if not CONFIG_MIN <= iv <= CONFIG_MAX:
            raise ValueError(f"{k} harus {CONFIG_MIN}..{CONFIG_MAX} hari.")
        upd[k] = iv
    # Ambang nilai PR (rupiah) — validator sendiri, bukan 0..60 hari.
    for k in PR_CHAIN_DEFAULTS:
        if k not in (patch or {}):
            continue
        raw = patch[k]
        if isinstance(raw, str):
            raw = raw.replace(".", "").replace(",", "").replace(" ", "").replace("Rp", "")
        try:
            iv = int(float(raw))
        except (TypeError, ValueError):
            raise ValueError(f"{PR_CHAIN_LABELS[k]} harus berupa angka rupiah.")
        if not MONEY_MIN <= iv <= MONEY_MAX:
            raise ValueError(
                f"{PR_CHAIN_LABELS[k]} harus antara Rp {MONEY_MIN:,} dan "
                f"Rp {MONEY_MAX:,}.".replace(",", "."))
        upd[k] = iv
    if not upd:
        raise ValueError("Tidak ada nilai ambang yang dikirim.")
    # Ambang RnD harus logis: "perlu perhatian" tidak boleh lebih lambat daripada
    # "terlambat", kalau tidak status kuning tidak akan pernah muncul.
    eff = await get_alert_config(db)
    att = upd.get("rnd_attention_days", eff["rnd_attention_days"])
    stale = upd.get("rnd_stale_days", eff["rnd_stale_days"])
    if att > stale:
        raise ValueError(
            f"Ambang 'perlu perhatian' ({att} hari) tidak boleh lebih besar daripada "
            f"'terlambat' ({stale} hari).")
    # Ambang nilai PR harus logis: batas "cukup 1 tahap" tidak boleh melebihi
    # batas "cukup 2 tahap", kalau tidak jalur 2 tahap tidak akan pernah dipakai.
    s1 = upd.get("pr_1_stage_max", eff["pr_1_stage_max"])
    s2 = upd.get("pr_2_stage_max", eff["pr_2_stage_max"])
    if s1 > s2:
        raise ValueError(
            f"Ambang '1 tahap' (Rp {s1:,}) tidak boleh lebih besar daripada ambang "
            f"'2 tahap' (Rp {s2:,}).".replace(",", "."))
    upd["_type"] = "main"
    upd["updated_at"] = datetime.now(timezone.utc)
    upd["updated_by"] = (user or {}).get("name") or ""
    await db.dewi_mgmt_alert_config.update_one({"_type": "main"}, {"$set": upd}, upsert=True)
    logger.info("[management-alerts] ambang diperbarui: %s oleh %s",
                {k: v for k, v in upd.items()
                 if k in ALERT_CONFIG_DEFAULTS or k in PR_CHAIN_DEFAULTS}, upd["updated_by"])
    return await get_alert_config(db)

MANAGEMENT_ROLES = (
    "superadmin", "admin", "owner", "manager", "director",
    "manager_produksi", "supervisor_produksi", "admin_produksi",
    "manager_keuangan", "accounting", "admin_maklon",
)

PO_DONE_STATUS = {"closed", "completed", "done", "cancelled", "canceled", "draft"}


async def _management_user_ids(db) -> list:
    rows = await db.users.find(
        {"role": {"$in": list(MANAGEMENT_ROLES)}, "status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1},
    ).to_list(500)
    return [r["id"] for r in rows if r.get("id")]


async def _already_sent(db, subtype: str, source_ref: str, day: str) -> bool:
    doc = await db.notifications.find_one(
        {"type": "rahaza", "subtype": subtype, "source_ref": source_ref,
         "meta.alert_day": day},
        {"_id": 0, "id": 1},
    )
    return bool(doc)


async def _emit(db, *, subtype: str, source_ref: str, title: str, body: str,
                severity: str, link_module: str, meta: dict, user_ids: list,
                day: str) -> int:
    if await _already_sent(db, subtype, source_ref, day):
        return 0
    payload_meta = {**meta, "alert_day": day, "link_module": link_module}
    sent = 0
    targets = user_ids or [None]
    for uid in targets:
        await notif_insert(
            db, type="rahaza", subtype=subtype, title=title, body=body,
            severity=severity, user_id=uid, channel="in_app",
            # Tanpa penerima personal → targetkan ke role manajemen (jangan jadi
            # siaran tanpa target yang tidak terlihat / bocor lintas role).
            target_roles=None if uid else list(MANAGEMENT_ROLES),
            source_type="management_alert", source_ref=source_ref,
            source_url=f"#{link_module}", meta=payload_meta, status="sent",
            sent_at=datetime.now(timezone.utc),
        )
        sent += 1
    return sent


async def scan_management_alerts(db, *, warn_days: int = None,
                                 po_warn_days: int = None, ar_warn_days: int = None,
                                 dry_run: bool = False) -> dict:
    """Cari PO mendekati/melewati deadline + piutang jatuh tempo, lalu beri tahu.

    Ambang: `po_warn_days` / `ar_warn_days` (bila None → konfigurasi owner, lalu
    bawaan 3 hari). `warn_days` = override lama yang berlaku untuk keduanya.
    `dry_run=True` hanya mengembalikan daftar temuan (tidak menulis notifikasi) —
    dipakai layar pratinjau supaya owner bisa melihat apa yang akan dikirim.
    """
    cfg = await get_alert_config(db)
    po_days = (po_warn_days if po_warn_days is not None
               else warn_days if warn_days is not None else cfg["po_warn_days"])
    ar_days = (ar_warn_days if ar_warn_days is not None
               else warn_days if warn_days is not None else cfg["ar_warn_days"])
    today = datetime.now(timezone.utc).date()
    day = today.isoformat()
    user_ids = await _management_user_ids(db)

    po_alerts: list = []
    # 2026-08-07 — DULU PO/invoice yang tanggalnya rusak di-`continue` DIAM-DIAM.
    # Untuk sebuah ALAT PERINGATAN, itu kegagalan yang paling berbahaya: justru
    # dokumen dengan data kacau yang paling mungkin terlambat, tetapi dialah yang
    # dipastikan TIDAK PERNAH memicu peringatan. Sekarang setiap baris yang
    # dilewati tercatat dan dikembalikan lewat `data_quality`, sehingga muncul di
    # layar pratinjau alert (dry_run) milik owner.
    dq = SkipTracker("peringatan deadline PO & piutang")
    sc = await domain_scope(db, "all")
    per_item = sc["ledger_per_item"]
    for p in sc["pos"]:
        status = (p.get("status") or "").strip().lower()
        if status in PO_DONE_STATUS:
            continue
        due_s = as_iso_date(p.get("deadline") or p.get("delivery_deadline"))
        if not due_s:
            dq.skip(doc_id=p.get("id"), label=p.get("po_number"), field="deadline",
                    value=p.get("deadline") or p.get("delivery_deadline"),
                    reason="PO tanpa deadline — tidak bisa diperingatkan")
            continue
        try:
            due = datetime.fromisoformat(due_s).date()
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=p.get("id"), label=p.get("po_number"), field="deadline",
                    value=due_s, error=e)
            continue
        sisa = (due - today).days
        if sisa > po_days:
            continue
        its = sc["items_by_po"].get(p["id"], [])
        qty = sum(_i(x.get("qty")) for x in its)
        acc = sum(_i((per_item.get(x["id"]) or {}).get("accepted")) for x in its)
        if qty and acc >= qty:
            continue  # barang sudah lengkap diterima — tidak perlu diingatkan
        po_alerts.append({
            "po_id": p["id"], "po_number": p.get("po_number"),
            "domain": "Internal" if p.get("business_type") == "internal" else "Maklon",
            "customer": p.get("customer_name") or "-",
            "deadline": due_s, "days_left": sisa,
            "qty_ordered": qty, "qty_accepted": acc, "qty_short": max(0, qty - acc),
            "status": p.get("status"),
            "severity": "error" if sisa < 0 else "warning",
        })
    po_alerts.sort(key=lambda r: r["days_left"])

    ar_alerts: list = []
    invs = await db.rahaza_ar_invoices.find(
        {}, {"_id": 0, "id": 1, "invoice_number": 1, "customer_name": 1, "due_date": 1,
             "status": 1, "total_amount": 1, "amount_paid": 1, "amount_due": 1},
    ).to_list(MAX_DOCS)
    for inv in invs:
        st = (inv.get("status") or "").lower()
        if st in ("paid", "cancelled", "void"):
            continue
        due_s = as_iso_date(inv.get("due_date"))
        if not due_s:
            dq.skip(doc_id=inv.get("id"), label=inv.get("invoice_number"),
                    field="due_date", value=inv.get("due_date"),
                    reason="invoice tanpa jatuh tempo — tidak bisa diperingatkan")
            continue
        try:
            due = datetime.fromisoformat(due_s).date()
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=inv.get("id"), label=inv.get("invoice_number"),
                    field="due_date", value=due_s, error=e)
            continue
        sisa = (due - today).days
        if sisa > ar_days:
            continue
        outstanding = (_f(inv.get("amount_due")) if inv.get("amount_due") is not None
                       else _f(inv.get("total_amount")) - _f(inv.get("amount_paid")))
        if outstanding <= 0:
            continue
        ar_alerts.append({
            "invoice_id": inv["id"], "invoice_number": inv.get("invoice_number"),
            "customer": inv.get("customer_name") or "-",
            "due_date": due_s, "days_left": sisa,
            "outstanding": round(outstanding), "status": inv.get("status"),
            "severity": "error" if sisa < 0 else "warning",
        })
    ar_alerts.sort(key=lambda r: r["days_left"])
    dq.log(logger)

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "warn_days": po_days,          # kompatibilitas pemanggil lama
        "po_warn_days": po_days,
        "ar_warn_days": ar_days,
        "config_source": ("konfigurasi owner" if (po_warn_days is None and warn_days is None)
                          else "parameter permintaan"),
        "recipients": len(user_ids),
        "po_alerts": po_alerts,
        "ar_alerts": ar_alerts,
        "po_count": len(po_alerts),
        "ar_count": len(ar_alerts),
        "notifications_created": 0,
        "dry_run": dry_run,
        # Dokumen yang TIDAK BISA diperiksa (tanggal kosong/rusak). Ditampilkan di
        # layar pratinjau alert supaya owner tahu ada PO/invoice yang luput dari
        # peringatan — dulu ini hilang tanpa jejak.
        "data_quality": dq.as_dict(),
    }
    if dry_run:
        return result

    created = 0
    for a in po_alerts:
        late = a["days_left"] < 0
        title = ("PO melewati deadline" if late else "PO mendekati deadline")
        body = (
            f"PO {a['po_number']} ({a['domain']} · {a['customer']}) "
            + (f"sudah {abs(a['days_left'])} hari melewati deadline {a['deadline']}."
               if late else
               f"jatuh tempo {a['deadline']} (sisa {a['days_left']} hari).")
            + f" Barang diterima {a['qty_accepted']} dari {a['qty_ordered']} pcs"
            + (f", kurang {a['qty_short']} pcs." if a["qty_short"] else ".")
        )
        created += await _emit(
            db, subtype="po_deadline", source_ref=a["po_id"], title=title, body=body,
            severity=a["severity"], link_module="prod-monitoring",
            meta={"po_number": a["po_number"], "deadline": a["deadline"],
                  "days_left": a["days_left"], "domain": a["domain"]},
            user_ids=user_ids, day=day)
    for a in ar_alerts:
        late = a["days_left"] < 0
        title = ("Piutang jatuh tempo" if late else "Piutang mendekati jatuh tempo")
        body = (
            f"Invoice {a['invoice_number']} ({a['customer']}) sisa "
            f"Rp {a['outstanding']:,}".replace(",", ".")
            + (f" sudah {abs(a['days_left'])} hari melewati jatuh tempo {a['due_date']}."
               if late else
               f" jatuh tempo {a['due_date']} (sisa {a['days_left']} hari).")
        )
        created += await _emit(
            db, subtype="ar_due", source_ref=a["invoice_id"], title=title, body=body,
            severity=a["severity"], link_module="fin-ar-360",
            meta={"invoice_number": a["invoice_number"], "due_date": a["due_date"],
                  "days_left": a["days_left"], "outstanding": a["outstanding"]},
            user_ids=user_ids, day=day)

    result["notifications_created"] = created
    logger.info("[management-alerts] PO=%s (ambang %sh) AR=%s (ambang %sh) notif=%s penerima=%s",
                len(po_alerts), po_days, len(ar_alerts), ar_days, created, len(user_ids))
    return result


async def job_management_alerts():
    """Entry point scheduler harian."""
    from database import get_db
    db = get_db()
    started = datetime.now(timezone.utc)
    run = {"job_id": "management_alerts", "started_at": started, "status": "running"}
    res = await db.dewi_scheduler_runs.insert_one(run)
    try:
        out = await scan_management_alerts(db)
        await db.dewi_scheduler_runs.update_one(
            {"_id": res.inserted_id},
            {"$set": {"status": "success", "finished_at": datetime.now(timezone.utc),
                      "result": {k: out[k] for k in ("po_count", "ar_count",
                                                     "notifications_created", "recipients",
                                                     "po_warn_days", "ar_warn_days")}}})
        return out
    except Exception as e:  # noqa: BLE001
        logger.exception("[management-alerts] gagal")
        await db.dewi_scheduler_runs.update_one(
            {"_id": res.inserted_id},
            {"$set": {"status": "failed", "finished_at": datetime.now(timezone.utc),
                      "error": str(e)}})
        raise


# Alat bantu uji manual (tidak dipakai produksi)
def _tomorrow_iso() -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
