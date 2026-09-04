/**
 * lib/csv.js — SATU tempat untuk "unduh apa yang terlihat".
 *
 * KENAPA BERKAS INI ADA (F10, sesi #10)
 * ------------------------------------
 * Audit layar daftar Portal Marketing (25 pintu) menemukan hanya **2 pintu** yang
 * punya tombol unduh. Artinya untuk hampir semua layar, angka yang sudah benar di
 * layar **tidak bisa dibawa ke rapat** — staf menyalin ulang dengan tangan ke
 * WhatsApp/Excel (sumber salah-ketik paling umum) atau meminta agen/IT membuatkan
 * laporan.
 *
 * DUA ATURAN yang dijaga berkas ini (dan alasannya):
 *  1. **Yang diunduh = yang terlihat.** `toCsv` menerima BARIS YANG SUDAH DISARING
 *     & DIURUTKAN oleh layar. Melakukan kueri ulang saat unduh adalah cara paling
 *     cepat melahirkan "berkas yang tidak sama dengan layar" — dan yang dipercaya
 *     biasanya yang salah.
 *  2. **Satu pembuat CSV.** Kalau tiap layar menulis escaping-nya sendiri, satu di
 *     antaranya akan lupa tanda kutip/BOM dan Excel akan menampilkan "Rp 1.000"
 *     sebagai tanggal. BOM `\uFEFF` disertakan supaya Excel Indonesia membaca
 *     UTF-8 dengan benar.
 */

/** Ubah head + rows (array of array) menjadi teks CSV yang aman untuk Excel. */
export function toCsv(head, rows) {
  const esc = (c) => `"${String(c ?? '').replace(/"/g, '""')}"`;
  return [head, ...rows].map((r) => r.map(esc).join(',')).join('\n');
}

/**
 * Unduh CSV. `filename` tanpa ekstensi — tanggal hari ini ditambahkan supaya
 * berkas yang menumpuk di folder Unduhan masih bisa dibedakan.
 */
export function downloadCsv(filename, head, rows) {
  const csv = toCsv(head, rows);
  const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  return rows.length;
}
