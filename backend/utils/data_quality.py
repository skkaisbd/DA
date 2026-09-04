"""utils/data_quality — SSOT pelaporan BARIS YANG DILEWATI karena datanya tidak sah.

Latar belakang (2026-08-07, lanjutan pembersihan `except Exception: pass`)
--------------------------------------------------------------------------
Di seluruh ERP ada satu pola yang berulang puluhan kali: sebuah laporan / daftar
jatuh tempo / alert menelusuri banyak dokumen, lalu **melewati** dokumen yang
tanggal atau angkanya tidak bisa dibaca:

    try:
        due = date.fromisoformat(inv.get("due_date"))
    except ValueError:
        continue            # ← dokumen HILANG dari laporan, tanpa jejak apa pun

Sekilas ini terlihat aman ("cuma satu baris rusak"). Akibatnya justru berbahaya
KARENA tidak kelihatan:

* Invoice yang `due_date`-nya rusak **hilang dari daftar jatuh tempo** — tidak ada
  yang menagih, dan total di layar tetap tampak wajar sehingga tak ada yang curiga.
* PO yang `deadline`-nya rusak **tidak pernah memicu alert** keterlambatan.
* WO yang tanggalnya rusak **mengecilkan penyebut** KPI ketepatan waktu — angka
  KPI malah NAIK justru karena datanya rusak.

Modul ini sengaja **TIDAK** mengubah keputusan "lewati atau tidak". Melewati baris
rusak tetap perilaku yang benar: satu dokumen kotor tidak boleh mematikan seluruh
laporan (itu akan jadi 500 dan lebih buruk). Yang ditambahkan hanya dua hal, dan
keduanya wajib:

1. baris yang dilewati **selalu tercatat** di log (WARNING) beserta konteksnya, dan
2. baris yang dilewati **selalu bisa ditampilkan** ke pengguna lewat `as_dict()`,

sehingga datanya bisa DIPERBAIKI, bukan diam-diam menghilang.

Kebijakan bertingkat yang dipakai sesi ini:
    * mutasi stok / uang / GL yang mengubah ANGKA   → gagal keras (HTTPException)
    * baris rusak pada LAPORAN / ALERT (baca saja)  → lewati, tapi CATAT + TAMPILKAN
      (modul ini)

Pemakaian:

    from utils.data_quality import SkipTracker

    dq = SkipTracker("daftar AR jatuh tempo")
    for inv in invoices:
        try:
            due = date.fromisoformat(inv["due_date"])
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=inv.get("id"), label=inv.get("invoice_number"),
                    field="due_date", value=inv.get("due_date"), error=e)
            continue
        ...
    dq.log(logger)
    return {"items": rows, "data_quality": dq.as_dict()}

`as_dict()` selalu mengembalikan bentuk yang sama (juga saat nol) supaya frontend
tidak perlu menebak:

    {"dilewati": 0, "konteks": "...", "pesan": "", "detail": []}
"""
from __future__ import annotations

import logging
from typing import Any, Optional

_logger = logging.getLogger(__name__)

# Berapa banyak contoh baris rusak yang disimpan untuk ditampilkan. Dibatasi
# supaya satu koleksi yang rusak massal tidak membengkakkan response JSON.
MAX_DETAIL = 25


def _short(value: Any, limit: int = 60) -> str:
    """Ringkas nilai apa pun jadi string pendek yang aman ditampilkan."""
    try:
        s = "" if value is None else str(value)
    except Exception:  # noqa: BLE001 — __str__ objek aneh tidak boleh menjatuhkan laporan
        s = "<tak bisa dibaca>"
    s = s.replace("\n", " ").strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


class SkipTracker:
    """Pencatat baris yang dilewati karena datanya tidak sah.

    Sengaja sangat ringan (tanpa I/O, tanpa DB) supaya boleh dipakai di dalam
    loop panas pada endpoint laporan.
    """

    __slots__ = ("konteks", "_n", "_detail", "_fields")

    def __init__(self, konteks: str):
        self.konteks = konteks or "laporan"
        self._n = 0
        self._detail: list[dict] = []
        self._fields: dict[str, int] = {}

    # ── perekaman ────────────────────────────────────────────────────────────
    def skip(self, *, doc_id: Optional[str] = None, label: Optional[str] = None,
             field: Optional[str] = None, value: Any = None,
             error: Any = None, reason: Optional[str] = None) -> None:
        """Catat satu baris yang dilewati.

        `label` = nama yang dikenal pengguna (mis. nomor invoice / kode PO) supaya
        pesan di layar bisa langsung ditindak tanpa buka database.
        """
        self._n += 1
        if field:
            self._fields[field] = self._fields.get(field, 0) + 1
        if len(self._detail) < MAX_DETAIL:
            self._detail.append({
                "id": doc_id or "",
                "label": _short(label or doc_id or "", 40),
                "field": field or "",
                "nilai": _short(value),
                "alasan": reason or (_short(error, 120) if error is not None else "data tidak sah"),
            })

    # ── pembacaan ────────────────────────────────────────────────────────────
    @property
    def count(self) -> int:
        return self._n

    def __bool__(self) -> bool:
        return self._n > 0

    def __len__(self) -> int:  # supaya `len(dq)` juga bekerja
        return self._n

    def pesan(self) -> str:
        """Pesan siap-tampil dalam bahasa Indonesia (kosong bila tidak ada masalah)."""
        if not self._n:
            return ""
        fields = ", ".join(
            f"{f} ({n}×)" for f, n in sorted(self._fields.items(), key=lambda kv: -kv[1])
        ) or "data tidak sah"
        return (f"{self._n} baris dilewati pada {self.konteks} karena datanya tidak bisa "
                f"dibaca: {fields}. Baris ini TIDAK ikut terhitung — perbaiki datanya "
                f"agar angkanya lengkap.")

    def as_dict(self) -> dict:
        """Bentuk stabil untuk response API (selalu ada, walau nol)."""
        return {
            "dilewati": self._n,
            "konteks": self.konteks,
            "pesan": self.pesan(),
            "per_field": dict(self._fields),
            "detail": list(self._detail),
            "detail_terpotong": self._n > len(self._detail),
        }

    def log(self, logger: Optional[logging.Logger] = None,
            level: int = logging.WARNING) -> None:
        """Tulis ke log SEKALI (ringkas + contoh), hanya bila ada yang dilewati."""
        if not self._n:
            return
        log = logger or _logger
        contoh = "; ".join(
            f"{d['label'] or d['id']}: {d['field']}={d['nilai']} ({d['alasan']})"
            for d in self._detail[:5]
        )
        log.log(level,
                "[mutu-data] %d baris dilewati pada %s — baris ini TIDAK ikut terhitung. "
                "Field bermasalah: %s. Contoh: %s",
                self._n, self.konteks,
                dict(self._fields) or "-", contoh or "-")
