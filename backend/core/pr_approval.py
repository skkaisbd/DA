"""core/pr_approval.py — MESIN PERSETUJUAN PEMBELIAN (SATU untuk semua jenis permintaan).

MENGAPA BERKAS INI ADA
----------------------
2026-08-07 — laporan owner: *"ada purchase request di aksesoris dan gudang, ini
harusnya tersambung ke procurement."* Benar, dan buktinya keras:

`acc_purchase_requests` (Request Pembelian Aksesoris) adalah alur PARALEL yang
menu-nya sudah dipindah ke Portal Pengadaan tetapi PERSETUJUANNYA tidak pernah
tersambung:

  · `PUT /api/acc/purchase-requests/{id}` hanya memakai `require_auth` ⇒
    **SIAPA PUN yang login bisa menyetujui**. Terbukti: akun `tim_packing`
    (staf packing gudang) membuat PR aksesoris Rp 50.000.000, submit, lalu
    **menyetujui PR-nya sendiri** — HTTP 200, tanpa satu pun pemeriksaan;
  · tidak pernah muncul di Kotak Persetujuan (`/api/procurement/inbox`) maupun
    lencana approval ⇒ approver yang berhak tidak pernah tahu ada pekerjaan;
  · satu tahap saja (tidak ada dept → keuangan → final), tidak mengikuti ambang
    nilai yang diatur owner, tidak ada jejak audit (`approved_by` hanya STRING
    nama, tanpa id aktor, tanpa waktu per tahap, tanpa penanda override).

Karena aturannya harus SAMA persis dengan Permintaan Pengadaan, mesinnya
dipindah ke sini supaya TIDAK ADA daftar peran / aturan tahap yang ditulis dua
kali (duplikasi daftar peran adalah akar bug 2026-08-06 dan 2026-08-07).

BENTUK DOKUMEN TIDAK DIIKAT
---------------------------
`eval_approval()` bekerja pada dokumen apa pun selama:
  · punya `requested_by` (id pembuat) dan `department` (opsional),
  · punya `approval_steps` (daftar langkah), dan
  · tahap aktifnya bisa ditentukan: dari `status` (Permintaan Pengadaan) ATAU
    dikirim eksplisit lewat argumen `stage` (Request Aksesoris memakai
    `current_approver_stage`).

Dipakai oleh: routes/dewi_procurement.py · routes/dewi_accessories_purchase.py ·
routes/approval_badge.py.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

STAGE_DEPT, STAGE_FINANCE, STAGE_FINAL = "dept", "finance", "final"

# ── SSOT NAMA KOLEKSI & STATUS REQUEST AKSESORIS ─────────────────────────────
# 2026-08-07 — ditambahkan setelah menemukan kartu "Request aksesoris" di
# Dashboard Pengadaan SELALU menampilkan 0. Sebabnya: dua modul lain menebak
# nama koleksinya (`dewi_accessories_purchase_requests`, `dewi_acc_purchase_requests`)
# dan KEDUANYA tidak pernah ada — koleksi sebenarnya `acc_purchase_requests`.
# Nama koleksi yang ditulis berulang di banyak berkas = kelas bug yang sama
# dengan duplikasi daftar peran. Jadi namanya tinggal di SINI saja.
ACC_PR_COLLECTION = "acc_purchase_requests"
# Nama field supplier di Request Aksesoris adalah `supplier` (string bebas),
# BUKAN `supplier_name` seperti dugaan modul migrasi supplier.
ACC_PR_SUPPLIER_FIELD = "supplier"
# Status Request Aksesoris BERKAPITAL. Menyaring dengan huruf kecil = selalu 0.
ACC_PR_STATUS_DRAFT = "Draft"
ACC_PR_STATUS_SUBMITTED = "Submitted"
# "Masih berjalan" = belum jadi pesanan / penerimaan, dan belum ditolak.
ACC_PR_OPEN_STATUSES = ("Draft", "Submitted", "Approved")

# Peran per tahap. WAJIB SALING LEPAS (disjoint) supaya aturan "satu orang tidak
# boleh menyetujui dua tahap" punya arti. `manager_keuangan` sengaja DIKELUARKAN
# dari tahap final — sebelumnya ia terdaftar di tahap keuangan DAN final, jadi
# orang yang baru menyetujui tahap keuangan bisa langsung menutup tahap final.
DEPT_APPROVER_ROLES = (
    "manager", "dept_head", "supervisor", "manager_produksi", "supervisor_produksi",
    "manager_hr", "manager_marketing", "manager_pengadaan", "spv_aksesoris",
    "spv_packing", "spv_cuting", "admin_gudang", "admin_pengadaan", "purchasing",
    # 2026-08-07 — divisi aksesoris ikut tahap departemen karena Request Pembelian
    # Aksesoris sekarang memakai rantai yang sama.
    "admin_aksesoris",
)
FINANCE_APPROVER_ROLES = (
    "finance", "finance_manager", "accountant",          # nama generik (jaga kompatibilitas)
    "accounting", "staff_keuangan", "manager_keuangan",  # peran NYATA di aplikasi ini
)
FINAL_APPROVER_ROLES = ("director", "cfo", "ceo", "owner")

STAGE_ROLES = {
    STAGE_DEPT: DEPT_APPROVER_ROLES,
    STAGE_FINANCE: FINANCE_APPROVER_ROLES,
    STAGE_FINAL: FINAL_APPROVER_ROLES,
}

# ── PURCHASE ORDER ───────────────────────────────────────────────────────────
# 2026-08-07 — Purchase Order dipindah ke mesin ini. Sebelum ini `rahaza_po.py`
# menulis daftar perannya SENDIRI:
#     _require_approver → ("superadmin", "owner", "manager",
#                          "production_manager", "warehouse_manager")
# Dari lima peran itu, HANYA `superadmin` yang benar-benar ada di aplikasi ini
# (`production_manager`/`warehouse_manager` tidak pernah ada; yang nyata adalah
# `manager_produksi`/`admin_gudang`). Dibuktikan dengan panggilan nyata:
# `direktur@` (director, approver tertinggi), `finance@`, dan `gudang@` semuanya
# **403** saat menyetujui PO, sementara `admin@garment.com` (superadmin) bisa
# **submit LALU approve PO YANG SAMA sendirian** — komitmen uang ke supplier
# tanpa satu pun mata kedua.
#
# Tahap pertama PO sengaja BUKAN "manager departemen mana pun" (seperti PR),
# melainkan PENGADAAN: PO adalah dokumen pengadaan, bukan permintaan divisi.
# Daftarnya tetap tinggal di berkas INI supaya tidak ada duplikasi peran lagi.
PO_DEPT_APPROVER_ROLES = (
    "manager_pengadaan", "admin_pengadaan", "purchasing",
    "admin_gudang", "manager", "dept_head", "manager_produksi",
)
PO_STAGE_ROLES = {
    STAGE_DEPT: PO_DEPT_APPROVER_ROLES,
    STAGE_FINANCE: FINANCE_APPROVER_ROLES,
    STAGE_FINAL: FINAL_APPROVER_ROLES,
}
PO_STAGE_LABELS = {
    STAGE_DEPT: "Persetujuan Pengadaan",
    STAGE_FINANCE: "Persetujuan Keuangan",
    STAGE_FINAL: "Persetujuan Final (Direksi)",
}
PO_STAGE_ROLE_LABELS = {
    STAGE_DEPT: "pengadaan (manager/admin pengadaan, purchasing, admin gudang)",
    STAGE_FINANCE: "keuangan (accounting / staff keuangan / manager keuangan)",
    STAGE_FINAL: "direksi (director / CFO / CEO / owner)",
}
PO_COLLECTION = "rahaza_purchase_orders"
PO_PENDING_STATUS = "pending_approval"
# Izin dinamis yang setara tiap tahap (katalog: backend/data/permission_catalog.py).
# Sengaja tidak ada izin yang muncul di dua tahap.
STAGE_PERMS = {
    STAGE_DEPT: ("purchasing.approve", "proc.pr.approve"),
    STAGE_FINANCE: ("finance.approve",),
    STAGE_FINAL: ("proc.pr.final_approve",),
}
STAGE_LABELS = {
    STAGE_DEPT: "Persetujuan Departemen",
    STAGE_FINANCE: "Persetujuan Keuangan",
    STAGE_FINAL: "Persetujuan Final (Direksi)",
}
STAGE_ROLE_LABELS = {
    STAGE_DEPT: "manager/supervisor departemen",
    STAGE_FINANCE: "keuangan (accounting / staff keuangan / manager keuangan)",
    STAGE_FINAL: "direksi (director / CFO / CEO / owner)",
}
# Status Permintaan Pengadaan → tahap yang sedang menunggu keputusan.
STATUS_TO_STAGE = {
    "submitted": STAGE_DEPT,
    "dept_approved": STAGE_FINANCE,
    "finance_approved": STAGE_FINAL,
}
STAGE_TO_STATUS = {v: k for k, v in STATUS_TO_STAGE.items()}
PENDING_STATUSES = tuple(STATUS_TO_STAGE)
SUPER_APPROVER_ROLES = ("superadmin", "admin", "owner")


# ── Ambang nilai & rantai ────────────────────────────────────────────────────
async def chain_config(db) -> dict:
    """Ambang nilai PR yang berlaku (diatur owner di Ringkasan Bisnis)."""
    from services.management_alerts import PR_CHAIN_DEFAULTS, get_alert_config
    try:
        cfg = await get_alert_config(db)
        return {k: int(cfg.get(k, PR_CHAIN_DEFAULTS[k])) for k in PR_CHAIN_DEFAULTS}
    except Exception as e:  # noqa: BLE001 — ambang rusak tidak boleh mematikan approval
        logger.warning("[pr-approval] gagal baca ambang rantai persetujuan: %s", e)
        return dict(PR_CHAIN_DEFAULTS)


def compute_chain(total, cfg: dict) -> list:
    """Tahap yang WAJIB dilalui untuk permintaan bernilai `total`."""
    try:
        t = float(total or 0)
    except (TypeError, ValueError):
        t = 0.0
    if t <= float(cfg.get("pr_1_stage_max", 1_000_000)):
        return [STAGE_DEPT]
    if t <= float(cfg.get("pr_2_stage_max", 25_000_000)):
        return [STAGE_DEPT, STAGE_FINANCE]
    return [STAGE_DEPT, STAGE_FINANCE, STAGE_FINAL]


def doc_chain(doc: dict, cfg: dict) -> list:
    """Rantai tahap dokumen ini. Dipakai apa adanya bila sudah dibekukan saat
    submit; dokumen lama (sebelum fitur ini) dihitung ulang dari nilainya."""
    stored = doc.get("approval_chain")
    if isinstance(stored, list) and stored:
        keep = [s for s in stored if s in STAGE_ROLES]
        if keep:
            return keep
    return compute_chain(doc.get("total_estimated"), cfg)


def next_stage_after(chain: list, stage: str):
    try:
        return chain[chain.index(stage) + 1]
    except (ValueError, IndexError):
        return None


def status_after_stage(chain: list, stage: str) -> str:
    nxt = next_stage_after(chain, stage)
    return STAGE_TO_STATUS.get(nxt, "approved") if nxt else "approved"


def approved_actor_ids(doc: dict) -> set:
    return {s.get("actor_id") for s in (doc.get("approval_steps") or [])
            if s.get("action") == "approved" and s.get("actor_id")}


def stage_role_ok(user: dict, stage: str, roles_map: dict | None = None) -> bool:
    """Berhak atas tahap ini SEBAGAI PERAN TAHAP (bukan sebagai admin).

    Mengikuti model "fallback aman" routes/shared.py: izin dinamis menang;
    selama owner belum mengatur izin role ini, daftar peran bawaan tahap
    tersebut yang dipakai (supaya fitur lama tidak mati mendadak).

    roles_map : peta tahap→peran untuk JENIS DOKUMEN ini (mis. `PO_STAGE_ROLES`).
                Default `STAGE_ROLES` (Permintaan Pengadaan & Request Aksesoris).

    PENTING: admin/superadmin memegang izin `"*"`. Bila `"*"` ikut dihitung di
    sini, SETIAP tindakan admin akan tampak sah dan TIDAK PERNAH tercatat
    sebagai override — padahal owner minta override tercatat. Karena itu peran
    super dinilai HANYA dari keanggotaan daftar peran tahap (mis. `owner` memang
    approver tahap final, jadi owner di tahap final = sah, bukan override).
    """
    role = (user.get("role") or "").lower()
    roles = (roles_map or STAGE_ROLES).get(stage, ())
    if role in SUPER_APPROVER_ROLES:
        return role in roles
    from routes.shared import perms_configured, user_permissions
    perms = user_permissions(user)
    if "*" in perms or (perms & set(STAGE_PERMS.get(stage, ()))):
        return True
    if perms_configured(user):
        return False
    return role in roles


async def with_department(db, user: dict) -> dict:
    """Lengkapi `user` dengan `department` dari master pengguna.

    `auth.create_token` baru memasukkan `department` sejak 2026-08-07, jadi token
    yang MASIH BERLAKU (24 jam) belum memuatnya. Tanpa tambalan ini batas
    departemen pada tahap pertama diam-diam tidak berjalan.
    """
    if user.get("department"):
        return user
    try:
        u = await db.users.find_one({"id": user.get("id")}, {"_id": 0, "department": 1})
        if u and u.get("department"):
            return {**user, "department": u["department"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("[pr-approval] gagal resolve departemen user: %s", e)
    return user


def eval_approval(doc: dict, user: dict, chain: list, *, stage=None,
                  roles_map: dict | None = None, labels: dict | None = None,
                  role_labels: dict | None = None) -> dict:
    """Hak + konteks persetujuan untuk SATU dokumen × SATU user.

    SSOT tunggal yang dipakai oleh: kotak persetujuan, daftar & detail dokumen
    (flag tombol UI), gerbang approve/reject, dan lencana approval di TopBar.

    stage : tahap aktif. Bila None, diturunkan dari `doc["status"]`
            (Permintaan Pengadaan). Request Aksesoris & Purchase Order
            mengirimnya eksplisit dari `current_approver_stage`.
    roles_map / labels / role_labels :
            peta khusus JENIS DOKUMEN (mis. Purchase Order memakai
            `PO_STAGE_ROLES` + `PO_STAGE_LABELS`). Semua peta tinggal di berkas
            ini — TIDAK BOLEH ditulis ulang di route mana pun.
    """
    roles_map = roles_map or STAGE_ROLES
    labels = labels or STAGE_LABELS
    role_labels = role_labels or STAGE_ROLE_LABELS
    role = (user.get("role") or "").lower()
    uid = user.get("id")
    is_super = role in SUPER_APPROVER_ROLES
    if stage is None:
        stage = STATUS_TO_STAGE.get(doc.get("status"))

    # Langkah lama menyimpan STATUS sebelum approve di field `step` → petakan
    # kembali ke tahap supaya riwayat dokumen lama tetap terbaca stepper UI.
    done_by = {}
    for s in (doc.get("approval_steps") or []):
        if s.get("action") != "approved":
            continue
        st = s.get("stage") or STATUS_TO_STAGE.get(s.get("step"))
        if st:
            done_by[st] = s

    chain_view = []
    for idx, st in enumerate(chain):
        d = done_by.get(st) or {}
        chain_view.append({
            "stage": st,
            "order": idx + 1,
            "label": labels.get(st, st),
            "role_hint": role_labels.get(st, ""),
            "done": bool(d),
            "current": st == stage,
            "actor_name": d.get("actor_name") or "",
            "timestamp": d.get("timestamp") or "",
            "override": bool(d.get("override")),
        })

    out = {
        "approval_chain": list(chain),
        "chain": chain_view,
        "total_stages": len(chain),
        "stage": stage,
        "stage_label": labels.get(stage, ""),
        "stage_role_hint": role_labels.get(stage, ""),
        "stage_order": (chain.index(stage) + 1) if stage in chain else None,
        "can_approve": False,
        "can_reject": False,
        "is_override": False,
        "override_reasons": [],
        "override_note": "",
        "blocked_reason": "",
    }
    nxt = next_stage_after(chain, stage) if stage else None
    out["next_stage"] = nxt
    out["next_approver_label"] = (role_labels.get(nxt, "")
                                  if nxt else "Selesai — permintaan disetujui penuh")

    if not stage:
        out["blocked_reason"] = "Tidak ada persetujuan yang menunggu pada permintaan ini."
        return out
    if stage not in chain:
        out["blocked_reason"] = (
            f"Tahap '{labels.get(stage, stage)}' tidak ada dalam rantai persetujuan "
            "permintaan ini. Hubungi admin.")
        if not is_super:
            return out

    violations, reasons = [], []
    if not stage_role_ok(user, stage, roles_map):
        violations.append("stage_role")
        reasons.append(
            f"Tahap saat ini {labels.get(stage, stage)} — hanya "
            f"{role_labels.get(stage, 'peran tahap ini')} yang berhak memutuskan.")
    if uid and doc.get("requested_by") == uid:
        violations.append("self_approval")
        reasons.append("Anda pembuat permintaan ini — pembuat tidak boleh "
                       "menyetujui permintaannya sendiri.")
    if uid and uid in approved_actor_ids(doc):
        violations.append("double_stage")
        reasons.append("Anda sudah menyetujui permintaan ini di tahap sebelumnya — "
                       "satu orang tidak boleh menyetujui dua tahap.")
    if stage == STAGE_DEPT:
        udept = (user.get("department") or "").strip()
        pdept = (doc.get("department") or "").strip()
        if udept and pdept and udept != pdept:
            violations.append("department")
            reasons.append(f"Permintaan ini milik departemen {pdept}, "
                           f"sedangkan Anda di departemen {udept}.")

    if violations and is_super:
        out["can_approve"] = out["can_reject"] = True
        out["is_override"] = True
        out["override_reasons"] = violations
        out["override_note"] = ("Anda menembus aturan pemisahan wewenang sebagai "
                                "admin/owner — tindakan ini dicatat di riwayat.")
    elif violations:
        out["blocked_reason"] = " ".join(reasons)
    else:
        out["can_approve"] = out["can_reject"] = True
    return out


# ── Notifikasi ──────────────────────────────────────────────────────────────
async def notify_stage_approvers(db, doc: dict, stage: str, chain: list, *,
                                 module_id: str = "proc-requests",
                                 number: str = "", title: str = "",
                                 kind_label: str = "Permintaan Pengadaan",
                                 roles_map: dict | None = None,
                                 labels: dict | None = None,
                                 value_field: str = "total_estimated"):
    """Beri tahu approver tahap `stage` lewat BEL notifikasi (SSOT `notifications`).

    Best-effort: kegagalan notifikasi tidak boleh membatalkan persetujuan.
    """
    if not stage:
        return
    labels = labels or STAGE_LABELS
    try:
        from utils.notif_unified import notif_insert
        roles = list((roles_map or STAGE_ROLES).get(stage, ()))
        if not roles:
            return
        rows = await db.users.find(
            {"role": {"$in": roles}, "status": {"$ne": "inactive"}},
            {"_id": 0, "id": 1, "department": 1},
        ).to_list(500)
        ids = [r["id"] for r in rows if r.get("id")]
        # Tahap departemen: utamakan approver di departemen dokumen (bila ada yang
        # cocok), supaya notifikasi tidak menyiram semua manager di perusahaan.
        pdept = (doc.get("department") or "").strip()
        if stage == STAGE_DEPT and pdept:
            same = [r["id"] for r in rows
                    if r.get("id") and (r.get("department") or "").strip() == pdept]
            if same:
                ids = same
        idx = chain.index(stage) + 1 if stage in chain else 1
        rp = f"Rp {float(doc.get(value_field) or 0):,.0f}".replace(",", ".")
        body = (f"{number} — {title}\n"
                f"Nilai: {rp}\n"
                f"Menunggu {labels.get(stage, stage)} "
                f"(tahap {idx} dari {len(chain)})")
        await notif_insert(
            db, type="rahaza", subtype="procurement_approval", severity="warning",
            title=f"{kind_label} menunggu persetujuan Anda",
            body=body,
            target_user_ids=ids or None,
            # Bila belum ada satu pun pengguna berperan itu, jangan buang
            # notifikasinya — alamatkan ke perannya supaya muncul begitu ada.
            target_roles=None if ids else roles,
            source_type="procurement_request", source_id=doc.get("id"),
            source_ref=number,
            meta={"link_module": module_id, "pr_id": doc.get("id"),
                  "request_number": number, "stage": stage,
                  "dedup_key": f"pr-approval:{doc.get('id')}:{stage}"},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[pr-approval] gagal notifikasi approver tahap %s: %s", stage, e)


async def notify_requester(db, doc: dict, *, title: str, body: str,
                           severity: str = "info", module_id: str = "proc-requests",
                           number: str = ""):
    """Kabari pembuat permintaan di bel notifikasi."""
    uid = doc.get("requested_by")
    if not uid:
        return
    try:
        from utils.notif_unified import notif_insert
        await notif_insert(
            db, type="rahaza", subtype="procurement_request_status", severity=severity,
            title=title, body=body, user_id=uid,
            source_type="procurement_request", source_id=doc.get("id"),
            source_ref=number,
            meta={"link_module": module_id, "pr_id": doc.get("id"),
                  "request_number": number},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[pr-approval] gagal kabari pembuat permintaan: %s", e)


# ── KOTAK PERSETUJUAN GABUNGAN ──────────────────────────────────────────────
# Satu daftar untuk SEMUA permintaan pembelian, apa pun asalnya. Ini yang
# menjawab laporan owner: pekerjaan pembelian tidak boleh tersebar di dua inbox.
ACC_STATUS_DISPLAY = {
    # Status Request Aksesoris (kapital) → kosakata status Permintaan Pengadaan
    # supaya lencana & warna di UI konsisten tanpa cabang khusus di frontend.
    "Draft": "draft",
    "Rejected": "rejected",
    "Approved": "approved",
    "Ordered": "in_procurement",
    "Received": "completed",
}


def acc_display_status(doc: dict) -> str:
    st = doc.get("status") or "Draft"
    if st == "Submitted":
        stage = doc.get("current_approver_stage") or STAGE_DEPT
        return STAGE_TO_STATUS.get(stage, "submitted")
    return ACC_STATUS_DISPLAY.get(st, "draft")


def _acc_item_view(it: dict, mat: dict | None = None) -> dict:
    """Satu baris item Request Aksesoris → BENTUK item Permintaan Pengadaan.

    DITEMUKAN DI LAYAR 2026-08-07: dialog persetujuan gabungan merender
    `name` / `qty` / `unit` / `total_price`, sedangkan item Request Aksesoris
    memakai `acc_name` / `qty_requested` / `estimated_price`. Akibatnya baris
    item tampil **kosong dengan "Rp 0"** — approver diminta menyetujui
    Rp 30.000.000 tanpa bisa melihat SATU PUN barang yang dibeli. Persetujuan
    yang tidak menampilkan apa yang disetujui sama saja tidak ada.

    Field aslinya tetap dibawa (`**it`) supaya layar Aksesoris sendiri, yang
    membaca `acc_name`/`qty_requested`, tidak berubah perilakunya.
    """
    mat = mat or {}
    try:
        qty = float(it.get("qty_requested") if it.get("qty_requested") is not None
                    else it.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0.0
    try:
        price = float(it.get("estimated_price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    unit = it.get("unit") or mat.get("unit") or "pcs"
    name = (it.get("acc_name") or it.get("name") or mat.get("name")
            or it.get("acc_code") or mat.get("code") or "Item aksesoris")
    return {
        **it,
        "material_id": it.get("acc_id") or it.get("material_id") or None,
        "material_code": it.get("acc_code") or mat.get("code") or "",
        "name": name,
        "specification": it.get("notes") or it.get("specification") or "",
        "qty": qty,
        "unit": unit,
        "uom": unit,
        "estimated_price": price,
        "total_price": round(qty * price, 2),
    }


async def acc_material_map(db, docs) -> dict:
    """{material_id: {code, name, unit}} untuk semua item pada `docs`.

    Dipakai melengkapi nama/kode barang yang TIDAK tersimpan di dokumen
    (form lama hanya mengirim `acc_id` + `qty_requested`), supaya baris item
    tidak pernah tampil kosong di kotak persetujuan.
    """
    ids = {
        (i.get("acc_id") or i.get("material_id"))
        for d in (docs or []) for i in (d.get("items") or [])
    }
    ids.discard(None)
    ids.discard("")
    if not ids:
        return {}
    try:
        rows = await db.rahaza_materials.find(
            {"id": {"$in": list(ids)}},
            {"_id": 0, "id": 1, "code": 1, "name": 1, "unit": 1},
        ).to_list(len(ids) + 5)
        return {r["id"]: r for r in rows if r.get("id")}
    except Exception as e:  # noqa: BLE001 — melengkapi nama tidak boleh mematikan approval
        logger.warning("[pr-approval] gagal melengkapi nama barang aksesoris: %s", e)
        return {}


def normalize_acc_pr(doc: dict, mats: dict | None = None) -> dict:
    """Bentuk Request Pembelian Aksesoris → bentuk yang dipahami UI pengadaan."""
    prio = (doc.get("priority") or "Normal").strip().lower()
    mats = mats or {}
    items = [
        _acc_item_view(i, mats.get(i.get("acc_id") or i.get("material_id")))
        for i in (doc.get("items") or [])
    ]
    return {
        "id": doc.get("id"),
        "kind": "acc_pr",
        "kind_label": "Aksesoris",
        "api_base": "/api/acc/purchase-requests",
        "module_id": "proc-accessory-pr",
        "request_number": doc.get("pr_number") or "",
        "title": doc.get("purpose") or "Request Pembelian Aksesoris",
        "description": doc.get("notes") or "",
        "justification": doc.get("purpose") or "",
        "department": doc.get("department") or "",
        "priority": {"urgent": "urgent", "normal": "medium", "low": "low"}.get(prio, "medium"),
        "request_type": "consumable",
        "status": acc_display_status(doc),
        "raw_status": doc.get("status"),
        "total_estimated": float(doc.get("total_estimated") or 0),
        "items": items,
        "requested_by": doc.get("requested_by"),
        "requested_by_name": doc.get("requested_by_name") or doc.get("created_by") or "",
        "created_at": doc.get("created_at"),
        "submitted_at": doc.get("submitted_at") or None,
        "rejection_reason": doc.get("finance_notes") if doc.get("status") == "Rejected" else None,
        "supplier": doc.get("supplier") or "",
        "approval_steps": doc.get("approval_steps") or [],
    }


async def pending_for_user(db, user: dict, *, include_acc: bool = True,
                          include_po: bool = True) -> list:
    """SEMUA permintaan pembelian yang menunggu KEPUTUSAN user ini.

    Dipakai bersama oleh `/api/procurement/inbox` dan lencana
    `/api/approval-inbox/badge` supaya angka lencana = isi kotak persetujuan.

    Tiga sumber: Permintaan Pengadaan · Request Pembelian Aksesoris ·
    **Purchase Order** (2026-08-07). PO ikut karena PO adalah komitmen UANG ke
    supplier — pekerjaan persetujuan pembelian tidak boleh tersebar di beberapa
    kotak masuk; itu keluhan awal owner.
    """
    from routes.dewi_procurement import _ser
    u = await with_department(db, user)
    cfg = await chain_config(db)
    out = []

    rows = await db.dewi_procurement_requests.find(
        {"status": {"$in": list(PENDING_STATUSES)}}, {"_id": 0}
    ).sort("submitted_at", 1).to_list(500)
    for d in rows:
        ev = eval_approval(d, u, doc_chain(d, cfg))
        if not ev["can_approve"]:
            continue
        item = _ser(d)
        item.update(ev)
        item.update({"kind": "pr", "kind_label": "Pengadaan",
                     "api_base": "/api/procurement/requests",
                     "module_id": "proc-requests"})
        out.append(item)

    if include_acc:
        accs = await db.acc_purchase_requests.find(
            {"status": "Submitted"}, {"_id": 0}
        ).sort("submitted_at", 1).to_list(500)
        # Nama & satuan barang dilengkapi dari master supaya baris item di kotak
        # persetujuan tidak pernah kosong (lihat `_acc_item_view`).
        mats = await acc_material_map(db, accs)
        for d in accs:
            chain = doc_chain(d, cfg)
            ev = eval_approval(d, u, chain, stage=d.get("current_approver_stage") or STAGE_DEPT)
            if not ev["can_approve"]:
                continue
            item = _ser(normalize_acc_pr(d, mats))
            item.update(ev)
            out.append(item)

    if include_po:
        pos = await db[PO_COLLECTION].find(
            {"status": PO_PENDING_STATUS}, {"_id": 0}
        ).sort("submitted_at", 1).to_list(500)
        for d in pos:
            chain = po_chain(d, cfg)
            ev = eval_approval(
                d, u, chain, stage=d.get("current_approver_stage") or STAGE_DEPT,
                roles_map=PO_STAGE_ROLES, labels=PO_STAGE_LABELS,
                role_labels=PO_STAGE_ROLE_LABELS)
            if not ev["can_approve"]:
                continue
            item = _ser(normalize_po(d))
            item.update(ev)
            out.append(item)

    out.sort(key=lambda x: str(x.get("submitted_at") or x.get("created_at") or ""))
    return out


# ── PURCHASE ORDER — rantai & bentuk untuk kotak persetujuan ────────────────
def po_chain(doc: dict, cfg: dict) -> list:
    """Tahap yang WAJIB dilalui sebuah Purchase Order.

    Dibekukan saat submit (`approval_chain`). Untuk PO baru:
      · dasarnya NILAI PO memakai ambang yang SAMA dengan Permintaan Pengadaan
        (satu tempat mengatur "uang sebesar ini butuh berapa mata");
      · **PENGECUALIAN**: PO yang lahir dari PR yang sudah disetujui penuh dan
        nilainya TIDAK melebihi nilai yang disetujui → cukup 1 tahap pengadaan
        (memastikan supplier & harga), karena kebutuhannya sudah lewat rantai
        penuh. Kalau nilainya MELEBIHI PR-nya, rantai penuh berlaku lagi —
        inilah yang menutup lubang "PR Rp 800 ribu disetujui, lalu diterbitkan
        PO Rp 800 juta ke supplier".
    """
    stored = doc.get("approval_chain")
    if isinstance(stored, list) and stored:
        keep = [s for s in stored if s in PO_STAGE_ROLES]
        if keep:
            return keep
    full = compute_chain(doc.get("total_value"), cfg)
    if doc.get("from_pr_id") and not doc.get("exceeds_pr_value"):
        return [STAGE_DEPT]
    return full


def normalize_po(doc: dict) -> dict:
    """Purchase Order → bentuk yang dipahami UI kotak persetujuan pengadaan."""
    items = []
    for it in (doc.get("items") or []):
        try:
            qty = float(it.get("qty_ordered") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        try:
            cost = float(it.get("unit_cost") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        items.append({
            **it,
            "name": (it.get("description") or it.get("material_name")
                     or it.get("material_code") or "Item PO"),
            "qty": qty,
            "unit": it.get("uom") or it.get("unit") or "pcs",
            "estimated_price": cost,
            "total_price": round(qty * cost, 2),
        })
    return {
        "id": doc.get("id"),
        "kind": "po",
        "kind_label": "Purchase Order",
        "api_base": "/api/rahaza/purchase-orders",
        "module_id": "proc-purchase-orders",
        "request_number": doc.get("po_number") or "",
        "title": (f"PO ke {doc.get('vendor_name') or 'supplier'}"
                  + (f" (dari {doc['from_pr_number']})" if doc.get("from_pr_number") else "")),
        "description": doc.get("notes") or "",
        "justification": doc.get("notes") or "",
        "department": doc.get("department") or "",
        "priority": "high" if doc.get("exceeds_pr_value") else "medium",
        "request_type": "purchase_order",
        "status": "submitted",          # kosakata status UI pengadaan
        "raw_status": doc.get("status"),
        "total_estimated": float(doc.get("total_value") or 0),
        "items": items,
        "requested_by": doc.get("requested_by") or doc.get("created_by"),
        "requested_by_name": doc.get("created_by_name") or "",
        "created_at": doc.get("created_at"),
        "submitted_at": doc.get("submitted_at") or None,
        "rejection_reason": doc.get("rejected_reason") or None,
        "supplier": doc.get("vendor_name") or "",
        "approval_steps": doc.get("approval_steps") or [],
        # Peringatan yang WAJIB terlihat approver: PO ini lebih mahal dari
        # permintaan yang sudah disetujui.
        "exceeds_pr_value": bool(doc.get("exceeds_pr_value")),
        "pr_approved_value": float(doc.get("pr_approved_value") or 0),
        "from_pr_number": doc.get("from_pr_number") or "",
    }
