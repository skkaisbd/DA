# Bisnis Proses — F18#1 Nota Kredit Retur & F18#4 `generate-ar-batch`

> Dibuat 2026-08-11 atas permintaan owner: *"1 skip dulu, harus ada pembahasan dan
> menelusuri bisnis proses logic"* dan *"2 skip dulu, jelaskan nanti secara bisnis
> proses ini apa"*. **Tidak ada kode yang diubah untuk dua butir ini.** Berkas ini
> menelusuri alurnya + angka buktinya, supaya keputusan diambil di atas fakta.

---

## BAGIAN 1 — NOTA KREDIT RETUR (F18#1)

### 1.1 Alur yang BERJALAN sekarang (barang)

```
pembeli komplain
   └─> Retur dibuat            POST /api/marketing/returns          status = pending
         └─> disetujui         POST /returns/{id}/approve           status = approved
               ├─(manual)─>    POST /returns/{id}/create-wh-return  → wh_returns (Gudang)
               │                 barang fisik diperiksa & (bila layak) masuk stok FG
               └─> diselesaikan POST /returns/{id}/complete          status = completed
```

Sisi **barang** sudah lengkap dan ada layarnya (termasuk peringatan jujur bila
retur di-*complete* padahal Gudang belum menangani barangnya).

### 1.2 Yang TIDAK berjalan: sisi UANG

Setiap retur sudah menghitung sendiri berapa yang harus dikembalikan:

| `refund_type`    | `refund_amount` |
|------------------|-----------------|
| `full_refund`    | = harga barang  |
| `partial_refund` | = 70% harga     |
| lainnya          | 0               |

Tetapi angka itu **berhenti di dokumen retur** dan tidak pernah menjadi kewajiban
di buku. Tiga fakta yang menyebabkannya:

1. **Tombol di layar berbohong.** `ReturnsRefundsModule.jsx` punya tombol
   **“Selesaikan & Terbitkan Nota Kredit”**, tetapi yang dipanggilnya adalah
   `POST /returns/{id}/complete` — handler yang **hanya mengubah `status` menjadi
   `completed`** dan tidak menyentuh nota kredit sama sekali.
2. **Endpoint nota kreditnya ADA tapi tidak dipanggil siapa pun.**
   `POST /api/marketing/returns/{id}/create-credit-note` sudah lengkap: membuat
   dokumen di `rahaza_credit_notes`, memberi nomor CN, menulis `credit_note_id`
   ke retur, lalu **memposting ke GL** lewat `routes/rahaza_posting.post_credit_note`.
   Pencarian di seluruh `frontend/src` untuk `create-credit-note` / `credit-notes`
   (di luar modul PO produksi) → **0 hasil**.
3. **Dua endpoint baca juga tanpa layar:** `GET /returns/credit-notes` dan
   `GET /returns/credit-notes/{id}`.

### 1.3 Bukti angka (data saat ini, bukan dugaan)

```
marketing_returns per status : completed 7 · approved 8 · pending 9 · rejected 6
retur approved+completed     : 15 dokumen · total refund_amount Rp 457.200
retur yang punya credit_note_id : 0
rahaza_credit_notes             : 0 dokumen
```

**Artinya:** 15 retur sudah “beres” menurut aplikasi, tetapi **nol rupiah**
kewajiban ke pembeli tercatat di buku. Akibat yang bisa ditunjuk:

* Neraca tidak memperlihatkan utang/kewajiban refund ke pembeli.
* Pendapatan tidak dikoreksi ⇒ **laba tampak lebih besar** daripada kenyataan,
  dan selisihnya tumbuh seiring jumlah retur.
* Tidak ada dokumen resmi (nomor CN) yang bisa dirujuk saat rekonsiliasi dengan
  pencairan dana marketplace.

### 1.4 Pertanyaan bisnis yang HARUS dijawab dulu (ini sebabnya ditunda)

1. **Siapa yang berhak menerbitkan nota kredit** — CS/Marketing yang menyetujui
   retur, atau Akuntansi? (menentukan RBAC; sekarang `approve` boleh oleh
   `pic_toko`/`cs_staff`, sedangkan menyentuh GL biasanya kewenangan Akuntansi)
2. **Kapan nota kredit terbit?** Tiga pilihan, dan ini menentukan **tanggal jurnal**:
   a. saat retur **disetujui** (kewajiban muncul secepat mungkin, risiko: barang
      ternyata tidak pernah dikirim balik);
   b. saat **barang diterima Gudang & lolos QC** (paling konservatif);
   c. saat **uang benar-benar dikembalikan/dipotong marketplace** (paling dekat
      ke kas, tapi buku terlambat mengakui kewajiban).
3. **Dasar nilainya:** harga jual saja · harga jual − ongkir · atau **nilai refund
   yang benar-benar dipotong platform** (Shopee/TikTok kadang menanggung sebagian,
   sehingga beban penjual ≠ harga barang).
4. **Nota kredit ditujukan ke siapa?** Keputusan #1 menetapkan pendapatan
   marketplace dicatat Finance lewat **Jurnal Manual**, bukan piutang per pembeli.
   Jadi apakah CN dibuat ke pelanggan generik “Marketplace Customer”, atau retur
   cukup **mengoreksi pendapatan** pada jurnal periode itu?
5. **Bila barang tidak kembali** (`refund_only` / `dispose` / `donation`): tetap
   terbit nota kredit **plus** kerugian barang (beban), atau hanya salah satu?

### 1.5 Rekomendasi (bila nanti dikerjakan)

1. **Hentikan tombol yang berbohong lebih dulu** — apa pun keputusan di atas,
   label “Terbitkan Nota Kredit” tidak boleh menempel pada handler yang tidak
   menerbitkan apa pun. Pilih salah satu: sambungkan ke `create-credit-note`,
   atau ubah labelnya menjadi “Selesaikan Retur”.
2. Satu layar **Refund & Nota Kredit** (tab-nya sudah ada) berisi: daftar CN
   (`GET /returns/credit-notes`), tombol **Terbitkan Nota Kredit** per retur yang
   sudah disetujui, status posting GL, dan tombol ulang-posting bila gagal
   (`POST /returns/credit-notes/{id}/post-to-gl` sudah ada).
3. Gate baru: **retur `completed` tanpa nota kredit tidak boleh ada** (kecuali
   `refund_type` yang memang nol) — supaya cacat ini tidak lahir kembali diam-diam.

---

## BAGIAN 2 — `POST /api/marketing/sales-data/generate-ar-batch` (F18#4)

### 2.1 Apa ini dalam bahasa bisnis

Ini **jembatan otomatis dari rekap penjualan Marketing ke piutang (AR) Finance**.
Idenya: setiap penjualan marketplace dianggap **piutang kepada marketplace**
(karena uang belum ada di rekening — masih ditahan Shopee/TikTok), lalu:

```
rekap sales harian per toko
      └─> "buat invoice AR sekaligus" (batch: harian/mingguan/bulanan/per platform)
            └─> rahaza_ar_invoices  → piutang muncul di Finance
                  └─> saat marketplace mencairkan dana → piutang dilunasi
```

Manfaat yang dijanjikan: **umur piutang** (mana pencairan yang telat) dan
rekonsiliasi “omzet vs dana masuk” per marketplace.

### 2.2 Status NYATA hari ini — butir F18#4 sudah KEDALUWARSA

Handoff lama menulis *“masih menerima 8 field tanpa efek”*. **Itu tidak lagi benar.**
Diuji hari ini:

```
POST /api/marketing/sales-data/generate-ar-batch  {"date_from":"2026-08-01","date_to":"2026-08-10"}
→ HTTP 410  {"code":"MARKETING_AR_DISABLED",
             "message":"Fitur 'Buat Invoice AR dari Sales Marketing' telah dinonaktifkan
                        (Keputusan #1). Pendapatan marketplace dicatat oleh Finance melalui
                        Jurnal Manual. Input sales harian tetap tersedia untuk dashboard."}
```

Jadi jalurnya **sudah dimatikan dengan pesan yang bisa ditindaklanjuti**, dan
**tidak menulis apa pun** ke `rahaza_ar_invoices`/GL.

### 2.3 Satu sisa kecil (jujur, bukan bahaya uang)

Model request-nya masih **mewajibkan** `date_from` & `date_to`. Kalau layar lama
memanggil tanpa dua field itu, yang muncul lebih dulu adalah **422 “Field required”** —
bukan penjelasan bahwa fiturnya memang dimatikan. Kalau nanti diputuskan tetap
mati, cara paling jujur: terima **body apa pun** lalu selalu balas 410 dengan
pesan yang sama.

### 2.4 Keputusan bisnis yang perlu diambil

| Pilihan | Konsekuensi |
|---|---|
| **A. Tetap Jurnal Manual** (keadaan sekarang) | Paling sederhana; Akuntansi mencatat pendapatan marketplace per periode. **Tidak ada umur piutang** per marketplace, dan “dana ditahan Shopee” tidak terlihat sebagai aset. |
| **B. Hidupkan AR otomatis** | Dapat umur piutang + rekonsiliasi pencairan. **Menuntut disiplin:** satu invoice per periode per akun (jangan dobel dengan jurnal manual), penomoran & pelanggan generik, serta **biaya admin/komisi marketplace** harus ikut dicatat sebagai beban — kalau tidak, piutang akan selalu lebih besar daripada uang yang benar-benar cair dan selisihnya menumpuk tanpa penjelasan. |

**Catatan penting bila memilih B:** jangan hidupkan sebelum diputuskan bahwa
pendapatan marketplace **berhenti** dicatat lewat Jurnal Manual. Dua jalur aktif
sekaligus = pendapatan dihitung dua kali — cacat yang sama seperti “rincian produk
melebihi omzet sesi” yang baru saja ditutup di F18#3.
