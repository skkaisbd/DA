"""core.creator_weekly_report — RAPOR KREATOR MINGGUAN (sesi #35).

KENAPA ADA
----------
Insentif kreator dihitung per **periode 3 bulan** dan performa konten dibaca per
**bulan**. Keduanya benar untuk membayar, tetapi terlambat untuk MENGARAHKAN: kreator
baru tahu dia tertinggal ketika periodenya hampir habis. Rapor mingguan menjawab satu
pertanyaan: *"pekan ini saya menghasilkan apa, dan target periode saya sudah sejauh
mana?"*

KEPUTUSAN YANG DIPAKAI (dan alasannya)
--------------------------------------
* **Pekan = 7 hari BERGULIR** (`akhir−6 … akhir`), sama dengan Rekap Mingguan CMT.
  Pekan ISO (Senin–Minggu) membuat rapor tiap Senin pagi berisi pekan yang baru
  berumur satu hari — tidak bisa dipakai memutuskan apa pun.
* **Dua angka omzet TIDAK dijumlah**: `gmv_kpi` (angka platform per konten) dan
  `order_revenue` (pesanan nyata `marketing_orders.creator_id`). Menjumlahkannya =
  menghitung satu penjualan dua kali.
* **Insentif TIDAK dihitung ulang di sini.** Nominalnya diambil dari SATU sumber
  (`routes.marketing_kol_incentive._summary`) supaya rapor tidak pernah menyebut
  angka rupiah yang berbeda dari layar insentif. `pcs_week` (pcs yang diinput staf
  pada pekan ini) adalah TAMBAHAN informasi, bukan dasar bayar.
* **TANPA HPP/margin.** Rapor ini dibaca kreator (keputusan pemilik: kreator hanya
  boleh melihat harga jual).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

CREATORS = "marketing_kol_creators"
CONTENTS = "marketing_content_calendar"
ENTRIES = "marketing_creator_incentive_entries"
RUNS = "marketing_creator_weekly_reports"

KPI_KEYS = ("views", "likes", "comments", "shares", "saves", "orders", "gmv")


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def week_window(week_end: str | None = None) -> dict:
    """Jendela 7 hari bergulir yang berakhir pada `week_end` (bawaan: hari ini WIB)."""
    from utils.waktu import today_wib
    try:
        end = date.fromisoformat(str(week_end)[:10]) if week_end else today_wib()
    except ValueError as e:
        raise ValueError("week_end harus YYYY-MM-DD") from e
    start = end - timedelta(days=6)
    return {"start": start.isoformat(), "end": end.isoformat(), "days": 7}


async def _order_revenue(db, creator_ids: list[str], win: dict) -> dict:
    """Omzet pesanan nyata per kreator pada jendela pekan (pembaca defensif F2)."""
    from core import marketing_daily_rollup as _rollup
    lo, hi = win["start"], win["end"]
    lo_dt = datetime.fromisoformat(lo).replace(tzinfo=timezone.utc)
    hi_dt = datetime.fromisoformat(hi).replace(hour=23, minute=59, second=59,
                                              tzinfo=timezone.utc)
    q = {"creator_id": {"$in": creator_ids},
         "$or": [{"order_date": {"$gte": lo, "$lte": hi + "\uffff"}},
                 {"order_date": {"$gte": lo_dt, "$lte": hi_dt}}]}
    out: dict = {}
    for o in await db.marketing_orders.find(
            q, {"_id": 0, "creator_id": 1, "status": 1, "revenue_product": 1,
                "order_amount": 1, "items": 1, "total_payment": 1}).to_list(30000):
        if (o.get("status") or "") == "cancelled":
            continue
        d = out.setdefault(o.get("creator_id"), {"orders": 0, "revenue": 0.0})
        d["orders"] += 1
        d["revenue"] += _rollup.order_revenue_product(o)
    return out


async def build_report(db, *, week_end: str | None = None,
                       creator_ids: list[str] | None = None,
                       include_inactive: bool = False) -> dict:
    """Rapor mingguan untuk satu / semua kreator. Membaca saja — tidak menulis apa pun."""
    win = week_window(week_end)
    q: dict = {}
    if creator_ids is not None:
        # DAFTAR KOSONG ARTINYA "tidak ada yang boleh dilihat" — BUKAN "semua".
        # Kesalahan ini sekali sempat lolos: pemakai tanpa lingkup toko menerima
        # angka SELURUH kreator karena `if creator_ids:` menganggap [] = tidak
        # menyaring (gate INV-F6RBAC B2-SWEEP menangkapnya).
        q["id"] = {"$in": creator_ids}
    elif not include_inactive:
        q["status"] = {"$ne": "inactive"}
    creators = await db[CREATORS].find(
        q, {"_id": 0, "login_password_hash": 0}).to_list(500)
    ids = [c["id"] for c in creators]
    if not ids:
        return {"period": win, "rows": [], "totals": _totals([]), "data_notes": _notes([])}

    contents = await db[CONTENTS].find(
        {"creator_id": {"$in": ids},
         "date": {"$gte": win["start"], "$lte": win["end"]}}, {"_id": 0}).to_list(5000)
    entries = await db[ENTRIES].find(
        {"creator_id": {"$in": ids},
         "date": {"$gte": win["start"], "$lte": win["end"]}}, {"_id": 0}).to_list(5000)
    revenue = await _order_revenue(db, ids, win)

    # SATU sumber nominal insentif (lihat docstring) — sengaja diimpor di dalam
    # fungsi supaya tidak ada ketergantungan lingkaran core ⇄ routes saat impor.
    from routes.marketing_kol_incentive import _summary as incentive_summary

    by_creator: dict = {}
    for c in contents:
        by_creator.setdefault(c["creator_id"], []).append(c)
    pcs_by_creator: dict = {}
    for e in entries:
        pcs_by_creator[e["creator_id"]] = pcs_by_creator.get(e["creator_id"], 0) + int(_f(e.get("pcs")))

    rows = []
    for c in creators:
        cs = by_creator.get(c["id"], [])
        agg = {k: 0.0 for k in KPI_KEYS}
        with_kpi = 0
        for d in cs:
            kpi = d.get("kpi") or {}
            for k in KPI_KEYS:
                agg[k] += _f(kpi.get(k))
            if d.get("kpi_updated_at"):
                with_kpi += 1
        eng = agg["likes"] + agg["comments"] + agg["shares"]
        inc = await incentive_summary(db, c)
        rev = revenue.get(c["id"], {})
        top = sorted(cs, key=lambda d: -_f((d.get("kpi") or {}).get("views")))[:3]
        by_type: dict = {}
        for d in cs:
            t = by_type.setdefault(d.get("content_type") or "(tanpa jenis)",
                                   {"content_type": d.get("content_type") or "(tanpa jenis)",
                                    "label": d.get("content_type_label") or "",
                                    "contents": 0, "views": 0.0})
            t["contents"] += 1
            t["views"] += _f((d.get("kpi") or {}).get("views"))
        rows.append({
            "creator_id": c["id"], "creator_name": c.get("name") or "",
            "creator_code": c.get("creator_code") or "",
            "creator_type": c.get("creator_type") or "new",
            "domicile": c.get("domicile") or "",
            "login_email": c.get("login_email") or "",
            "status": c.get("status") or "active",
            "contents": len(cs),
            "posted": sum(1 for d in cs if d.get("status") == "posted"),
            "with_kpi": with_kpi,
            "kpi_coverage_pct": round(with_kpi / len(cs) * 100, 2) if cs else 0.0,
            "views": round(agg["views"], 2),
            "engagement": round(eng, 2),
            "engagement_rate": round(eng / agg["views"] * 100, 2) if agg["views"] > 0 else 0.0,
            "saves": round(agg["saves"], 2),
            "orders_kpi": round(agg["orders"], 2),
            "gmv_kpi": round(agg["gmv"], 2),
            "order_revenue": round(_f(rev.get("revenue")), 2),
            "order_count": int(rev.get("orders") or 0),
            "pcs_week": int(pcs_by_creator.get(c["id"], 0)),
            # ── insentif: DIBACA dari layar insentif, tidak dihitung ulang ──
            "incentive_eligible": inc["eligible"],
            "incentive_period": inc["period"],
            "pcs_period": inc["pcs_sold"],
            "target_pcs": inc["target_pcs"],
            "target_progress_pct": inc["progress_pct"],
            "incentive_total": inc["total_incentive"],
            "by_content_type": sorted(by_type.values(), key=lambda t: -t["views"]),
            "top_contents": [{
                "id": d.get("id"), "date": d.get("date"),
                "title": d.get("title") or "(tanpa judul)",
                "content_type_label": d.get("content_type_label") or d.get("content_type") or "",
                "views": _f((d.get("kpi") or {}).get("views")),
                "gmv": _f((d.get("kpi") or {}).get("gmv")),
                "published_url": d.get("published_url") or "",
            } for d in top],
        })
    rows.sort(key=lambda r: (-r["gmv_kpi"], -r["views"], r["creator_name"]))
    return {"period": win, "rows": rows, "totals": _totals(rows),
            "data_notes": _notes(rows)}


def _totals(rows: list) -> dict:
    t = {
        "creators": len(rows),
        "creators_active": sum(1 for r in rows if r["contents"] > 0),
        "contents": sum(r["contents"] for r in rows),
        "posted": sum(r["posted"] for r in rows),
        "with_kpi": sum(r["with_kpi"] for r in rows),
        "views": round(sum(r["views"] for r in rows), 2),
        "engagement": round(sum(r["engagement"] for r in rows), 2),
        "gmv_kpi": round(sum(r["gmv_kpi"] for r in rows), 2),
        "order_revenue": round(sum(r["order_revenue"] for r in rows), 2),
        "pcs_week": sum(r["pcs_week"] for r in rows),
        "incentive_total": round(sum(r["incentive_total"] for r in rows), 2),
    }
    t["kpi_coverage_pct"] = (round(t["with_kpi"] / t["contents"] * 100, 2)
                             if t["contents"] else 0.0)
    return t


def _notes(rows: list) -> list:
    t = _totals(rows)
    notes = [
        "Pekan dibaca sebagai 7 hari BERGULIR (akhir−6 … akhir), bukan Senin–Minggu.",
        "GMV (KPI platform) dan omzet pesanan ditampilkan berdampingan dan TIDAK "
        "dijumlah — menjumlahkannya berarti menghitung satu penjualan dua kali.",
        "Nominal insentif diambil dari layar Insentif Kreator (periode berjalan), "
        "bukan dihitung ulang di rapor — supaya tidak ada dua angka rupiah.",
    ]
    if t["contents"] and t["kpi_coverage_pct"] < 100:
        notes.append(f"Cakupan KPI {t['kpi_coverage_pct']}%: "
                     f"{t['contents'] - t['with_kpi']} konten pekan ini belum diisi KPI-nya, "
                     "jadi views/engagement/GMV di bawah ini masih kurang dari kenyataan.")
    if t["contents"] and t["order_revenue"] == 0:
        notes.append("Kolom 'Omzet pesanan' Rp 0 karena belum ada pesanan ber-kreator "
                     "(`marketing_orders.creator_id`) pada jendela ini — bukan berarti "
                     "kreator tidak menjual; pesanan belum tertaut ke kreator.")
    idle = [r["creator_name"] for r in rows if r["contents"] == 0]
    if idle:
        notes.append(f"{len(idle)} kreator TIDAK punya satu konten pun pekan ini: "
                     + ", ".join(idle[:8]) + ("…" if len(idle) > 8 else ""))
    return notes


def compose_email(row: dict, period: dict) -> tuple[str, str]:
    """Isi email rapor untuk SATU kreator (teks polos — tanpa HPP/margin)."""
    def rp(v):
        return "Rp " + f"{int(round(_f(v))):,}".replace(",", ".")

    def n(v):
        return f"{int(round(_f(v))):,}".replace(",", ".")

    subject = (f"Rapor Mingguan {row['creator_name']} "
               f"({period['start']} s/d {period['end']})")
    lines = [
        f"Halo {row['creator_name']} ({row['creator_code']}),",
        "",
        f"Berikut rapor pekan {period['start']} s/d {period['end']}:",
        "",
        f"- Konten dibuat      : {row['contents']} ({row['posted']} sudah tayang)",
        f"- Views              : {n(row['views'])}",
        f"- Engagement         : {n(row['engagement'])} ({row['engagement_rate']}%)",
        f"- Pesanan (KPI)      : {n(row['orders_kpi'])}",
        f"- GMV (angka platform): {rp(row['gmv_kpi'])}",
        f"- Omzet pesanan      : {rp(row['order_revenue'])} dari {row['order_count']} pesanan",
        f"- Pcs tercatat pekan ini: {row['pcs_week']} pcs",
    ]
    if row["incentive_eligible"]:
        lines += [
            "",
            f"Insentif periode {row['incentive_period']['start']} s/d "
            f"{row['incentive_period']['end']}:",
            f"- Pcs periode        : {row['pcs_period']} pcs"
            + (f" dari target {row['target_pcs']} pcs ({row['target_progress_pct']}%)"
               if row["target_pcs"] else ""),
            f"- Perkiraan insentif : {rp(row['incentive_total'])}",
        ]
    if row["top_contents"]:
        lines += ["", "Konten teratas pekan ini:"]
        for i, c in enumerate(row["top_contents"], 1):
            lines.append(f"  {i}. {c['title']} — {n(c['views'])} views"
                         + (f" · {c['published_url']}" if c["published_url"] else ""))
    if row["contents"] and row["with_kpi"] < row["contents"]:
        lines += ["", f"Catatan: {row['contents'] - row['with_kpi']} konten pekan ini "
                      "belum ada angka KPI-nya, jadi total di atas masih kurang dari "
                      "kenyataan."]
    lines += ["", "Rapor ini dibuat otomatis oleh sistem ERP CV. Dewi Aditya."]
    return subject, "\n".join(lines)
