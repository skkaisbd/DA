"""core/production_job_lifecycle.py — SSOT **kapan sebuah job produksi ditutup**.

═══════════════════════════════════════════════════════════════════════════════
MASALAH NYATA YANG DITUTUP BERKAS INI
═══════════════════════════════════════════════════════════════════════════════
Rekap Harian/Mingguan CMT menjawab "apa yang MENUNGGU pada akhir tanggal X".
Untuk kolom **Progress Produksi**, "menunggu" = ada **job yang sedang jalan**.
Sebelum berkas ini ada, pertanyaan itu dijawab dengan melihat **status SEKARANG**::

    if j.get('status') != 'In Progress':   # ← salah untuk tanggal LAMPAU
        continue

Akibatnya: job yang dibuka Senin, tidak disetor Senin, lalu **ditutup Rabu**
akan hilang dari rekap hari Senin — padahal hari Senin itu vendor MEMANG punya
pekerjaan yang tidak dikerjakan. Rekap tanggal lampau jadi terlalu bersih:
kelalaian yang sudah terjadi terhapus sendiri begitu job-nya ditutup. Karena
progress produksi adalah **dasar tagihan CMT**, laporan yang memaafkan dirinya
sendiri seperti ini tidak bisa dipakai memverifikasi apa pun.

`production_jobs` tidak pernah menyimpan **kapan** job ditutup, jadi jawabannya
mustahil dihitung — bukan sulit, mustahil. Sesi sebelumnya jujur menuliskannya
sebagai catatan di layar (`as_of_note`: "job yang sudah ditutup setelah tanggal
itu tidak lagi terhitung"). Berkas ini menghapus kebutuhan catatan itu.

═══════════════════════════════════════════════════════════════════════════════
KENAPA PENULISNYA HARUS SATU (PELAJARAN `received_at`)
═══════════════════════════════════════════════════════════════════════════════
Bug termahal sesi Rekap Harian: `received_at` hanya ditulis **browser** sebagai
STRING, sementara field waktu lain bertipe `Date` ⇒ query rentang tanggal tidak
pernah cocok ⇒ kolom "Terima" abadi ✗. Pelajarannya: **stempel waktu yang dipakai
laporan wajib ditulis SERVER, di SATU tempat.**

Ada **dua** jalur yang menutup job dan keduanya sudah pernah berbeda perilaku:

1. ``routes/production_execution.py`` — auto-complete saat semua item mencapai
   ``shipment_qty`` (jalur normal, dipicu entri progress);
2. ``routes/production_pos.py`` — tombol **Quick Complete**.

Kalau masing-masing menulis ``closed_at`` sendiri, suatu hari salah satunya akan
lupa (atau menulis tipe berbeda) dan rekap tanggal lampau kembali bohong TANPA
ada yang tahu. Keduanya memanggil :func:`close_job`.

═══════════════════════════════════════════════════════════════════════════════
ATURAN "MASIH JALAN PADA SAAT ITU" (dipakai rekap)
═══════════════════════════════════════════════════════════════════════════════
:func:`was_open_at` — satu tempat, dipakai rekap harian DAN mingguan:

* job **belum lahir** pada saat itu (``created_at >= moment``) ⇒ tidak jalan;
* punya ``closed_at`` ⇒ jalan bila ``closed_at >= moment``;
* **tidak** punya ``closed_at``:
  * status masih terbuka ⇒ jalan (masih terbuka sampai sekarang, berarti terbuka
    juga saat itu);
  * status sudah tertutup ⇒ dokumen **WARISAN** yang belum di-backfill. Kapan
    ditutupnya tidak diketahui, jadi dikembalikan ``False`` — persis perilaku
    lama, supaya migrasi yang memperbaikinya (bukan tebakan diam-diam).
    Jalankan ``backend/migrations/add_closed_at_to_production_jobs.py``.

**Status yang TIDAK dikenal dianggap TERBUKA — ini pilihan sadar.** Dua arah
salahnya tidak seimbang: menganggap job tertutup padahal terbuka membuat
pekerjaan nyata HILANG dari rekap ⇒ progress tidak diisi ⇒ uang tidak bisa
ditagih. Menganggap terbuka padahal tertutup hanya membuat satu baris tampak
merah dan langsung diselidiki orang. Yang kedua jauh lebih murah.
"""
from __future__ import annotations

from datetime import datetime

from utils.waktu import as_aware_utc, now_utc

# Status yang berarti job SUDAH TIDAK menjadi pekerjaan lagi.
# Tambahkan di SINI kalau alur baru memperkenalkan status penutup baru — jangan
# menyebarkan daftar ini ke pemanggil (itu cara termudah membuatnya berbeda).
JOB_CLOSED_STATUSES: frozenset[str] = frozenset({
    'Completed', 'Closed', 'Cancelled', 'Canceled', 'Done', 'Finished',
})

# Status yang berarti job masih menjadi pekerjaan (hanya untuk keterbacaan;
# aturan sebenarnya = "tidak ada di JOB_CLOSED_STATUSES").
JOB_OPEN_STATUSES: frozenset[str] = frozenset({'In Progress', 'Open', 'Pending'})


def is_closed_status(status: str | None) -> bool:
    return str(status or '') in JOB_CLOSED_STATUSES


async def close_job(db, job_id: str, *, status: str = 'Completed',
                    when: datetime | None = None, extra: dict | None = None) -> datetime | None:
    """Tutup job dan **stempel waktunya ditulis SERVER**. Satu-satunya penulis ``closed_at``.

    * **Idempoten & tutup pertama yang menang.** Kalau job sudah punya
      ``closed_at`` hasil pengamatan, stempel itu TIDAK ditimpa (waktu tutup yang
      sebenarnya adalah yang pertama). Stempel hasil **perkiraan** migrasi
      (``closed_at_estimated: True``) BOLEH digantikan pengamatan sungguhan.
    * Mengembalikan ``closed_at`` yang berlaku, atau ``None`` bila job tak ada.

    Sengaja TIDAK menerima ``closed_at`` dari body permintaan: itu persis cara
    ``received_at`` dulu masuk sebagai string dari jam komputer staf.
    """
    if not job_id:
        return None
    ts = as_aware_utc(when) or now_utc()
    patch = {'status': status, 'closed_at': ts, 'updated_at': ts}
    if extra:
        patch.update(extra)

    # Hanya menulis bila belum ada stempel teramati (atau stempelnya masih perkiraan).
    res = await db.production_jobs.update_one(
        {'id': job_id,
         '$or': [{'closed_at': {'$exists': False}}, {'closed_at': None},
                 {'closed_at_estimated': True}]},
        {'$set': patch, '$unset': {'closed_at_estimated': ''}},
    )
    if res.matched_count:
        return ts

    # Sudah punya stempel teramati: pertahankan stempelnya, pastikan statusnya benar.
    existing = await db.production_jobs.find_one({'id': job_id}, {'_id': 0, 'closed_at': 1})
    if existing is None:
        return None
    await db.production_jobs.update_one(
        {'id': job_id}, {'$set': {'status': status, 'updated_at': now_utc()}})
    return as_aware_utc(existing.get('closed_at'))


def was_open_at(job: dict, moment: datetime) -> bool:
    """Apakah ``job`` masih **jalan** pada ``moment`` (biasanya batas akhir satu hari WIB)?

    Lihat aturan lengkap di docstring modul. Dipakai rekap harian & mingguan
    supaya definisi "job jalan" hanya ada di SATU tempat.
    """
    if not job:
        return False

    created = as_aware_utc(job.get('created_at'))
    if created and moment and created >= moment:
        return False                    # belum lahir pada saat itu

    closed = as_aware_utc(job.get('closed_at'))
    if closed is not None:
        return bool(moment) and closed >= moment

    # Tanpa closed_at: status terbuka ⇒ jalan; status tertutup ⇒ warisan (lihat docstring).
    return not is_closed_status(job.get('status'))


def needs_closed_at_backfill(job: dict) -> bool:
    """Job yang statusnya tertutup tetapi tidak punya ``closed_at`` (warisan).

    Dipakai migrasi DAN laporan rekap (untuk memberi tahu pemakai bahwa masih ada
    dokumen yang waktu tutupnya belum diketahui — jangan diam-diam).
    """
    return is_closed_status(job.get('status')) and not job.get('closed_at')
