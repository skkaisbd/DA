"""Pengelompokan & perlindungan koleksi database — dipakai layar Backup lanjutan.

Tujuan: owner bisa MENGOSONGKAN atau MEMULIHKAN koleksi tertentu tanpa tidak
sengaja menghapus fondasi sistem (akun pengguna, hak akses, nomor urut, bagan
akun). Koleksi berlabel `protected` menolak dikosongkan kecuali super admin
menyalakan opsi khusus.
"""
from __future__ import annotations

import re

# Koleksi yang TIDAK BOLEH dikosongkan lewat jalur biasa: menghapusnya membuat
# sistem tidak bisa dipakai atau merusak keunikan nomor dokumen.
PROTECTED_EXACT = {
    "users", "roles", "permissions", "counters", "doc_number_configs",
    "company_settings", "notification_categories", "notif_rules", "notif_settings",
    "portal_access", "login_attempts", "rate_limits",
}
PROTECTED_PATTERNS = [
    re.compile(r"^rahaza_(coa_accounts|accounts|coa|posting_profiles?)$"),
    re.compile(r"_settings$"),
    re.compile(r"_config$"),
    re.compile(r"_configs$"),
]

# Urutan penting: aturan pertama yang cocok yang menang.
GROUP_RULES: list[tuple[str, re.Pattern]] = [
    ("Pengguna & Akses", re.compile(r"^(users|roles|permissions|portal_access|login_|push_|rate_limits)")),
    ("Konfigurasi Sistem", re.compile(r"(counters|_settings$|_config$|_configs$|categories$|company_)")),
    ("Master Data", re.compile(r"(materials|locations|products|styles|vendors|clients|suppliers|customers|units|catalog|master|bom|processes|cost_centers|accounts$|employees$)")),
    ("Stok & Gudang", re.compile(r"(stock|ledger|opname|grn|receiv|putaway|placement|position|delivery_note|dispatch|returns|picklist|quarantine|fabric_roll|warehouse|wh_)")),
    ("Produksi & Maklon", re.compile(r"(cutting|cmt|work_order|production|maklon|variance|sample|permak|shipment|job)")),
    ("Keuangan", re.compile(r"(journal|invoice|payment|cash|bank|expense|budget|fixed_asset|kasbon|_ar_|_ap_|credit_note|procurement|purchase_order|petty|settlement|hpp)")),
    ("SDM & Absensi", re.compile(r"(employee|attendance|payroll|leave|shift|recruit|kpi|training|onboard|announcement|loan)")),
    ("Marketing & Penjualan", re.compile(r"^(marketing_|buyer_|client_)|(order|sales|kol|live|review|campaign|discount)")),
    ("Log & Riwayat", re.compile(r"(audit|_log|logs$|history|activity|notification|ai_usage|webhook|chat_history)")),
]


def group_of(name: str) -> str:
    for label, rx in GROUP_RULES:
        if rx.search(name):
            return label
    return "Lainnya"


def is_protected(name: str) -> bool:
    if name in PROTECTED_EXACT:
        return True
    return any(rx.search(name) for rx in PROTECTED_PATTERNS)


GROUP_ORDER = [label for label, _ in GROUP_RULES] + ["Lainnya"]
