/**
 * recapDates — util tanggal bersama untuk Rekap Harian & Rekap Mingguan CMT.
 *
 * KENAPA DIPISAH
 * --------------
 * Tiga layar (tab Harian, tab Mingguan, dan panel induknya) harus setuju tentang
 * satu hal: **hari ini menurut WIB**, bukan menurut zona browser. Sebelum berkas
 * ini ada, helper-nya disalin di dalam komponen — dan salinan itulah yang suatu
 * hari akan berbeda (mis. satu diperbaiki ke WIB, satu tertinggal memakai zona
 * lokal) sehingga tab Harian dan tab Mingguan menampilkan "hari ini" yang berbeda.
 *
 * Kalau memakai zona browser: staf yang laptopnya ter-set UTC akan membuka rekap
 * tanggal KEMARIN sepanjang pagi (00:00-07:00 WIB) lalu menyimpulkan "semua vendor
 * belum mengisi" — persis jam produksi mulai bekerja. Backend memakai
 * `utils/waktu.today_wib()`; di sini padanannya.
 */

/** Tanggal HARI INI menurut WIB sebagai 'YYYY-MM-DD'. */
export const isoToday = () => {
  const wib = new Date(Date.now() + 7 * 3600 * 1000);
  return wib.toISOString().slice(0, 10);
};

/** Geser tanggal ISO sebanyak `delta` hari (pakai jam 12:00Z supaya bebas DST). */
export const shiftDay = (iso, delta) => {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
};

/** '2026-08-10' -> 'Senin, 10 Agustus 2026' (nama hari ikut: briefing menyebut hari). */
export const dayLabel = (iso) => {
  try {
    return new Date(`${iso}T12:00:00Z`).toLocaleDateString('id-ID', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });
  } catch { return iso; }
};

/** '2026-08-10' -> '10 Agu' (untuk kepala kolom yang sempit). */
export const shortDate = (iso) => {
  try {
    return new Date(`${iso}T12:00:00Z`).toLocaleDateString('id-ID', {
      day: 'numeric', month: 'short',
    });
  } catch { return iso; }
};

/** Selisih hari (b - a) untuk dua tanggal ISO. */
export const daysBetween = (a, b) => Math.round(
  (new Date(`${b}T12:00:00Z`) - new Date(`${a}T12:00:00Z`)) / 86400000,
);
