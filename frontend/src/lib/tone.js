/**
 * lib/tone.js — SATU tempat menerjemahkan "nama warna" menjadi KELAS TAILWIND
 * yang benar-benar ada.
 *
 * ══════════════════════════════════════════════════════════════════════════
 * KENAPA BERKAS INI ADA (F15-B, temuan pemilik 2026-08-14)
 * ══════════════════════════════════════════════════════════════════════════
 * Pemilik melaporkan *"beberapa page … lupa di kasih background cardsnya"*.
 * Salah satu sebabnya bukan kelas yang salah ketik, melainkan kelas yang
 * DIRAKIT saat berjalan:
 *
 *     className={`bg-${color}-500/5 border border-${color}-500/20 …`}
 *
 * Tailwind menghasilkan CSS dengan **membaca teks berkas sumber**. Ia tidak
 * menjalankan JavaScript, jadi `bg-${color}-500/5` tidak pernah terbaca sebagai
 * `bg-teal-500/5` — kelasnya tidak pernah dibuat, dan elemennya tampil TANPA
 * latar. Yang membuatnya sulit ditemukan: kadang kelas itu KEBETULAN ada karena
 * berkas LAIN memakainya secara harfiah. Jadi kartu "violet" terlihat benar,
 * kartu "teal" tidak — di layar yang sama, dari komponen yang sama.
 *
 * DIUKUR pada bundel hasil build (`main.*.css`) sebelum perbaikan:
 *     bg-teal-500/5      → TIDAK ADA
 *     border-teal-500/20 → TIDAK ADA
 *     border-teal-500/25 → TIDAK ADA
 * ⇒ kartu KPI **"Perlu Diserahkan"** di Dashboard Aksesoris memang tampil tanpa
 * latar dan tanpa garis. Bukan selera — memang tidak ada CSS-nya.
 *
 * ATURAN: nama warna boleh dinamis, KELASNYA tidak. Semua kelas di bawah
 * ditulis HARFIAH supaya Tailwind bisa membacanya.
 */

/** Nada warna yang didukung. Tambah nada baru = tambah entri HARFIAH di sini. */
export const TONE = {
  violet: {
    surface: 'bg-violet-50 dark:bg-violet-500/5 border-violet-200 dark:border-violet-500/20',
    chip:    'bg-violet-100 dark:bg-violet-500/15 border-violet-300 dark:border-violet-500/25',
    text:    'text-violet-600 dark:text-violet-400',
    solid:   'bg-violet-600 text-white',
  },
  amber: {
    surface: 'bg-amber-50 dark:bg-amber-500/5 border-amber-200 dark:border-amber-500/20',
    chip:    'bg-amber-100 dark:bg-amber-500/15 border-amber-300 dark:border-amber-500/25',
    text:    'text-amber-700 dark:text-amber-400',
    solid:   'bg-amber-600 text-white',
  },
  sky: {
    surface: 'bg-sky-50 dark:bg-sky-500/5 border-sky-200 dark:border-sky-500/20',
    chip:    'bg-sky-100 dark:bg-sky-500/15 border-sky-300 dark:border-sky-500/25',
    text:    'text-sky-600 dark:text-sky-400',
    solid:   'bg-sky-600 text-white',
  },
  teal: {
    surface: 'bg-teal-50 dark:bg-teal-500/5 border-teal-200 dark:border-teal-500/20',
    chip:    'bg-teal-100 dark:bg-teal-500/15 border-teal-300 dark:border-teal-500/25',
    text:    'text-teal-600 dark:text-teal-400',
    solid:   'bg-teal-600 text-white',
  },
  emerald: {
    surface: 'bg-emerald-50 dark:bg-emerald-500/5 border-emerald-200 dark:border-emerald-500/20',
    chip:    'bg-emerald-100 dark:bg-emerald-500/15 border-emerald-300 dark:border-emerald-500/25',
    text:    'text-emerald-600 dark:text-emerald-400',
    solid:   'bg-emerald-600 text-white',
  },
  blue: {
    surface: 'bg-blue-50 dark:bg-blue-500/5 border-blue-200 dark:border-blue-500/20',
    chip:    'bg-blue-100 dark:bg-blue-500/15 border-blue-300 dark:border-blue-500/25',
    text:    'text-blue-600 dark:text-blue-400',
    solid:   'bg-blue-600 text-white',
  },
  orange: {
    surface: 'bg-orange-50 dark:bg-orange-500/5 border-orange-200 dark:border-orange-500/20',
    chip:    'bg-orange-100 dark:bg-orange-500/15 border-orange-300 dark:border-orange-500/25',
    text:    'text-orange-600 dark:text-orange-400',
    solid:   'bg-orange-600 text-white',
  },
  red: {
    surface: 'bg-red-50 dark:bg-red-500/5 border-red-200 dark:border-red-500/20',
    chip:    'bg-red-100 dark:bg-red-500/15 border-red-300 dark:border-red-500/25',
    text:    'text-red-600 dark:text-red-400',
    solid:   'bg-red-600 text-white',
  },
  rose: {
    surface: 'bg-rose-50 dark:bg-rose-500/5 border-rose-200 dark:border-rose-500/20',
    chip:    'bg-rose-100 dark:bg-rose-500/15 border-rose-300 dark:border-rose-500/25',
    text:    'text-rose-600 dark:text-rose-400',
    solid:   'bg-rose-600 text-white',
  },
  indigo: {
    surface: 'bg-indigo-50 dark:bg-indigo-500/5 border-indigo-200 dark:border-indigo-500/20',
    chip:    'bg-indigo-100 dark:bg-indigo-500/15 border-indigo-300 dark:border-indigo-500/25',
    text:    'text-indigo-600 dark:text-indigo-400',
    solid:   'bg-indigo-600 text-white',
  },
  // `slate`/`zinc`/netral dipetakan ke token tema supaya ikut mode terang/gelap
  // tanpa perlu dua kelas berbeda.
  slate: {
    surface: 'bg-muted border-border',
    chip:    'bg-muted border-border',
    text:    'text-muted-foreground',
    solid:   'bg-secondary text-secondary-foreground',
  },
};

/** Nada cadangan kalau nama warnanya tidak dikenal — netral, bukan transparan. */
export const TONE_FALLBACK = TONE.slate;

/** Ambil nada dengan aman. `tone('teal').surface` selalu mengembalikan kelas nyata. */
export function tone(name) {
  return TONE[name] || TONE_FALLBACK;
}
