"""utils/waktu — SSOT waktu operasional perusahaan (WIB / Asia-Jakarta).

Masalah yang diselesaikan (2026-08-07, Prioritas 3 backlog: "datetime naive")
-----------------------------------------------------------------------------
Container ini berjalan dengan jam sistem **UTC**. Di banyak tempat kode memakai
`datetime.now()` TANPA timezone, lalu hasilnya dipakai untuk:

* **tahun/bulan periode** (mis. saldo cuti `year = datetime.now().year`),
* **tanggal kalender** untuk penomoran dokumen (`%Y%m`, `%y%m%d`), dan
* **stempel "…WIB"** pada PDF/laporan.

Ketiganya SALAH pada jendela **07 jam setiap hari** (00:00–07:00 WIB = 17:00–24:00
UTC hari sebelumnya). Akibat nyatanya:

* Tanggal 1 Januari pagi WIB, `datetime.now().year` masih tahun LALU ⇒ saldo cuti
  dan periode payroll dibuka untuk tahun yang salah.
* Tanggal 1 setiap bulan pagi WIB, `%Y%m` masih bulan LALU ⇒ nomor dokumen
  (klaim biaya, perjalanan, per-diem) memakai periode bulan yang salah.
* PDF mencetak "Dicetak: 02:00 WIB" padahal waktu WIB sebenarnya 09:00 — selisih
  7 jam pada dokumen yang ditandatangani/diarsipkan.

Aturan yang dipakai repo ini:
* **PENYIMPANAN tetap UTC & aware** (`now_utc()`), jangan pernah menyimpan naive.
* **BATAS HARI / TANGGAL KALENDER / TAMPILAN pakai WIB** (`now_wib()`,
  `today_wib()`, `wib_date_str()`, `fmt_wib()`).

Sebelum modul ini ada 3 definisi terpisah yang berpencar:
`utils/employee_identity.WIB`, `core/accessory_valuation._JAKARTA`, dan puluhan
`datetime.now()` polos. Sekarang semuanya menunjuk ke sini.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

# ZoneInfo lebih benar daripada offset tetap (menangani perubahan aturan zona bila
# ada). Bila database tzdata tidak tersedia di image, jatuh ke UTC+7 — WIB memang
# tidak punya DST, jadi hasilnya identik untuk keperluan operasional.
try:  # pragma: no cover
    from zoneinfo import ZoneInfo

    WIB: timezone | ZoneInfo = ZoneInfo("Asia/Jakarta")
except Exception:  # noqa: BLE001 — pragma: no cover
    WIB = timezone(timedelta(hours=7))

JAKARTA = "Asia/Jakarta"


# ── SEKARANG ────────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    """Waktu sekarang, AWARE, dalam UTC. Ini yang disimpan ke database."""
    return datetime.now(timezone.utc)


def now_wib() -> datetime:
    """Waktu sekarang, AWARE, dalam WIB. Ini yang dipakai untuk tanggal & tampilan."""
    return datetime.now(WIB)


def today_wib() -> date:
    """Tanggal kalender HARI INI menurut WIB (bukan menurut jam UTC server)."""
    return now_wib().date()


def wib_year() -> int:
    """Tahun berjalan menurut WIB (periode cuti/payroll/anggaran)."""
    return now_wib().year


def wib_month() -> int:
    """Bulan berjalan menurut WIB."""
    return now_wib().month


# ── KONVERSI ────────────────────────────────────────────────────────────────
def as_aware_utc(dt: datetime | None) -> datetime | None:
    """Pastikan `dt` AWARE dalam UTC. Naive dianggap UTC (sesuai jam sistem)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def to_wib(dt: datetime | None) -> datetime | None:
    """Ubah datetime apa pun (naive dianggap UTC) menjadi AWARE WIB."""
    aware = as_aware_utc(dt)
    return aware.astimezone(WIB) if aware else None


def wib_day_bounds_utc(d: date | None = None) -> tuple[datetime, datetime]:
    """Batas satu hari kalender WIB, dinyatakan dalam UTC (untuk query rentang).

    Dipakai laporan/absen harian: `{"$gte": mulai, "$lt": selesai}`.
    Contoh 2026-08-07 WIB → 2026-08-06T17:00Z .. 2026-08-07T17:00Z.
    """
    d = d or today_wib()
    mulai = datetime.combine(d, time.min, tzinfo=WIB)
    return mulai.astimezone(timezone.utc), (mulai + timedelta(days=1)).astimezone(timezone.utc)


# ── FORMAT / TAMPILAN ───────────────────────────────────────────────────────
def wib_date_str(dt: datetime | None = None) -> str:
    """Tanggal kalender WIB sebagai 'YYYY-MM-DD'."""
    return (to_wib(dt) or now_wib()).strftime("%Y-%m-%d")


def fmt_wib(fmt: str, dt: datetime | None = None) -> str:
    """Format datetime dalam WIB. Selalu pakai ini bila teksnya menyebut 'WIB'."""
    return (to_wib(dt) or now_wib()).strftime(fmt)


def wib_stamp(dt: datetime | None = None) -> str:
    """Stempel 'YYYYmmdd_HHMMSS' waktu WIB — untuk nama berkas/backup.

    Nama berkas dibaca MANUSIA (mis. `backup_20260807_090000.zip`), jadi wajib
    memakai jam lokal; memakai UTC membuat berkas pagi WIB tampak bertanggal
    kemarin.
    """
    return (to_wib(dt) or now_wib()).strftime("%Y%m%d_%H%M%S")
