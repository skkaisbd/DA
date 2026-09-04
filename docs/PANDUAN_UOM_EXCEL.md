# Panduan: Mengisi Satuan & Kemasan 478 Item Lewat Excel

Dokumen kerja untuk owner. Dua pekerjaan terpisah — **jangan dicampur**:

| Pekerjaan | Kapan dipakai | Alat |
|---|---|---|
| **1. Menambah KEMASAN** (beli per pak, pakai per pcs) | satuan dasar sudah benar | Ekspor/Impor Excel |
| **2. Mengganti SATUAN DASAR** (stok telanjur dicatat per rol/pak/lusin) | satuan dasarnya salah | Skrip rebase (91 item) |

Pekerjaan 2 **wajib** lewat skrip/tombol rebase karena angka stok dan HPP harus ikut dikonversi.
Impor Excel akan **menolak** perubahan satuan dasar pada item yang masih berstok.

---

## 1. Menambah kemasan lewat Excel (478 item sekaligus)

### Langkah
1. Buka **Portal Administrasi Sistem → Pengaturan Sistem → Ekspor/Impor Data**.
2. Pilih jenis data **Bahan / Material** → **Unduh Data** (bukan template kosong, supaya
   kode & nama sudah terisi benar).
3. Isi 4 kolom kemasan:

| Kolom | Arti | Contoh |
|---|---|---|
| `base_uom` | satuan dasar — dipakai menyimpan stok & HPP | `pcs` |
| `pack_unit` | nama kemasan saat membeli | `pak` |
| `pack_size` | isi per kemasan (**harus > 1**) | `12` |
| `display_in_packs` | tampilkan stok per kemasan di layar? | `true` / `false` |

4. Unggah dengan mode **Pratinjau (dry-run)** dulu → periksa daftar baris tidak sah.
5. Bila bersih, unggah ulang dengan mode **Commit**.

### Aturan yang ditegakkan sistem
- `pack_size` kosong/≤ 1 padahal `pack_unit` diisi → baris **ditolak**.
- `pack_unit` diisi tapi `pack_size` kosong → baris **ditolak**.
- `pack_unit` sama dengan `base_uom` → dianggap tidak ada kemasan (bukan error).
- `base_uom` berbeda dari yang sekarang **dan item masih berstok** → baris **ditolak**
  dengan pesan mengarahkan ke tombol *Ubah Satuan Dasar*.
- Baris yang kolom kemasannya **dikosongkan** → konfigurasi satuan lama **tidak disentuh**.
- Tingkat kemasan lain yang sudah diatur manual (mis. karton) **dipertahankan**, selama
  satuan dasarnya tidak berubah.

### Yang otomatis ikut diatur saat `pack_unit` diisi
- Satuan pembelian = kemasan · Satuan pemakaian = satuan dasar
- Satuan tampilan = kemasan bila `display_in_packs=true`, selain itu satuan dasar

---

## 2. Mengganti satuan dasar (91 item bersatuan kemasan)

Item yang satuan dasarnya masih `rol` (74), `pak` (14), atau `lusin` (3) — stok & HPP-nya
tersimpan per kemasan, padahal produksi memakai satuan eceran.

```bash
# a. Ekspor daftar kerja
python3 scripts/uom_rebase_worklist.py --export /app/data_import/rebase_uom.xlsx

# b. Owner mengisi 2 kolom di berkas itu:
#      satuan_baru          → satuan dasar yang benar, mis. "m"
#      isi_per_satuan_lama  → 1 rol = ? m, mis. 50
#    Baris yang dikosongkan otomatis dilewati.

# c. Pratinjau (tidak mengubah apa pun)
python3 scripts/uom_rebase_worklist.py --preview /app/data_import/rebase_uom.xlsx

# d. Terapkan
python3 scripts/uom_rebase_worklist.py --apply /app/data_import/rebase_uom.xlsx
```

**Nilai persediaan tidak berubah**: qty dikali faktor, HPP dibagi faktor. Satuan lama tetap
tersedia sebagai kemasan. Skrip memanggil endpoint resmi
`POST /api/rahaza/materials/{id}/rebase-uom` — tidak ada logika kedua yang bisa menyimpang.

Alternatif satu per satu: tombol **Ubah Satuan Dasar** di form material.

---

## 3. Menghitung/menerima per kemasan di lapangan

Setelah kemasan terdaftar, titik-titik berikut menerima field `input_uom` sehingga petugas
boleh memasukkan angka dalam satuan kemasan — sistem mengonversi ke satuan dasar sendiri:

| Titik | Endpoint |
|---|---|
| Penerimaan barang | `POST /api/rahaza/receiving/...` |
| Opname aksesoris | `POST /api/acc/opname/...` |
| Cutting | `POST /api/cutting/orders/{id}/start` |
| Pengeluaran aksesoris | `POST /api/acc/requests/{id}/deliver` |
| **Penyimpanan / put-away** | `POST /api/wms/putaway/place` |
| **Opname gudang (scan & undo)** | `POST /api/wms/opname3/scan`, `/scan-undo` |

> **Catatan sisa pekerjaan:** backend seluruh titik di atas sudah menerima `input_uom`, tetapi
> **pemilih satuan di layar belum dipasang** — saat ini angka yang diketik operator masih
> dianggap satuan dasar. Ini pekerjaan lanjutan yang belum dikerjakan.

Bukti uji: `python3 scripts/poc_uom_entry_points.py` → 11/11 lulus.
