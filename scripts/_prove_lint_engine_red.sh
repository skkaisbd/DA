#!/usr/bin/env bash
# =============================================================================
# _prove_lint_engine_red.sh — BUKTIKAN guardrail INV-LINT-01 bisa MERAH
# =============================================================================
# "Guard yang belum pernah terlihat MERAH bukan guard" (pelajaran FASE 13 #6).
#
# Skrip ini MENANAM ULANG bug-bug NYATA yang pernah memblokir penyerahan sesi,
# satu per satu, lalu memastikan guardrail MENANGKAP MASING-MASING dengan kode
# temuan yang BENAR, lalu memulihkan environment dan memastikan HIJAU lagi.
#
# Kenapa ada TIGA bug yang ditanam, bukan satu: gate platform bisa mati dari
# tiga arah berbeda, dan dua sesi sebelumnya hanya menutup satu arah lalu
# mengklaim selesai.
#
#   B1  `eslint-config-expo` hilang dari node_modules global
#       → arm ESLint tak bisa memuat config `expo`     → LINT-ESLINT-DOWN
#   B2  satu import relatif YATIM di `_archive/`  (INI penyebab FASE 20 gagal
#       menyerahkan sesinya — dan FASE 20 sendiri yang membuatnya saat
#       mengarsipkan modul CMT)                        → LINT-IMPORT-BROKEN
#   B3  dependensi dipakai `setupTests.js` tapi tak dideklarasikan di
#       `package.json`                                 → LINT-IMPORT-BROKEN
#
# Pakai: bash /app/scripts/_prove_lint_engine_red.sh
# =============================================================================
set -uo pipefail
cd /app
G="\033[1;32m"; R="\033[1;31m"; Y="\033[1;33m"; C="\033[1;36m"; X="\033[0m"
GUARD="python3 scripts/guardrails/verify_platform_lint_engine.py --quiet"
PASS=0; FAIL=0
LOG=/app/.bootstrap_cache
mkdir -p "$LOG"

say() { printf "\n${C}%s${X}\n" "$*"; }
okm() { printf "  ${G}✓ %s${X}\n" "$*"; PASS=$((PASS+1)); }
bad() { printf "  ${R}✗ %s${X}\n" "$*"; FAIL=$((FAIL+1)); }

GLOBAL_NM=$(npm root -g 2>/dev/null || echo /usr/lib/node_modules)
EXPO_CFG="$GLOBAL_NM/eslint-config-expo"
STASH=/tmp/_prove_lint_expo_stash
# FASE 21 — dulu B2 merusak `_archive/CMTProgressModule.jsx`. Folder `_archive/`
# SUDAH DIHAPUS seluruhnya (keputusan user), jadi tanamannya sekarang berupa
# berkas SEMENTARA di dalam `frontend/src/` yang dibuat lalu dihapus. Kelas
# bug-nya identik: satu import relatif yang tak bisa di-resolve ⇒
# import_success=False ⇒ gate menolak `finish`.
ARCHIVE_FILE=/app/frontend/src/__prove_dangling_import__.jsx
PKG=/app/frontend/package.json

restore_all() {
  [ -d "$STASH" ] && [ ! -d "$EXPO_CFG" ] && mv "$STASH" "$EXPO_CFG"
  rm -rf "$STASH" 2>/dev/null || true
  rm -f "$ARCHIVE_FILE" 2>/dev/null || true
  [ -f "$PKG.bak" ] && mv "$PKG.bak" "$PKG"
  [ -d /tmp/_prove_lint_jestdom_stash ] && \
    mv /tmp/_prove_lint_jestdom_stash /app/frontend/node_modules/@testing-library/jest-dom
  return 0
}
trap restore_all EXIT

# Jalankan guard, cek MERAH + kode temuan yang diharapkan.
expect_red() { # $1=label $2=kode_temuan
  local label="$1" code="$2" out
  out=$(python3 scripts/guardrails/verify_platform_lint_engine.py 2>&1)
  if [ $? -eq 0 ]; then
    bad "$label: guardrail TETAP HIJAU padahal bug ditanam — guard TIDAK EFEKTIF"
    printf '%s\n' "$out" | tail -8
  elif printf '%s' "$out" | grep -q "$code"; then
    okm "$label: MERAH dengan kode $code (benar)"
  else
    bad "$label: merah tapi BUKAN karena $code"
    printf '%s' "$out" | grep -E "\[HIGH|\[WARN" | head -4
  fi
}

say "0/8  Baseline: guardrail HARUS HIJAU sekarang"
if $GUARD >"$LOG/pl_base.log" 2>&1; then okm "baseline HIJAU (rc=0)"
else bad "baseline sudah MERAH — perbaiki dulu (lihat $LOG/pl_base.log)"; tail -12 "$LOG/pl_base.log"; fi

# ── B1 ──────────────────────────────────────────────────────────────────────
say "1/8  Tanam B1: sembunyikan eslint-config-expo dari node_modules global"
if [ -d "$EXPO_CFG" ]; then rm -rf "$STASH"; mv "$EXPO_CFG" "$STASH"; okm "disembunyikan"
else bad "eslint-config-expo tak terpasang — tak bisa menanam B1"; fi
say "2/8  Guard harus MERAH (arm ESLint tak bisa memuat config expo)"
expect_red "B1" "LINT-ESLINT-DOWN"
say "3/8  Pulihkan B1 lewat skrip perbaikan resmi (bukan tangan)"
bash scripts/fix_root_lint_resolution.sh >"$LOG/pl_fix.log" 2>&1
[ -d "$EXPO_CFG" ] || restore_all
[ -d "$EXPO_CFG" ] && okm "B1 dipulihkan" || bad "B1 gagal dipulihkan (lihat $LOG/pl_fix.log)"

# ── B2 ──────────────────────────────────────────────────────────────────────
say "4/8  Tanam B2: buat satu import relatif YATIM (kelas bug yang memblokir FASE 20)"
cat > "$ARCHIVE_FILE" <<'JSX'
// Berkas SEMENTARA milik scripts/_prove_lint_engine_red.sh — dihapus otomatis.
// Import di bawah SENGAJA menunjuk berkas yang tidak ada.
import { PageHeader } from './__tidak_ada_berkas_ini__';
export default function ProveDanglingImport() { return <PageHeader />; }
JSX
[ -f "$ARCHIVE_FILE" ] && okm "import yatim ditanam" || bad "gagal membuat berkas tanaman"
say "5/8  Guard harus MERAH (Import Validation gagal ⇒ gate menolak finish)"
expect_red "B2" "LINT-IMPORT-BROKEN"
say "6/8  Pulihkan B2"
rm -f "$ARCHIVE_FILE" && [ ! -f "$ARCHIVE_FILE" ] && okm "B2 dipulihkan (berkas tanaman dihapus)" \
  || bad "B2 gagal dipulihkan"

# ── B3 ──────────────────────────────────────────────────────────────────────
# CATATAN (ditemukan oleh bukti-merah ini sendiri, iterasi-1 GAGAL): menghapus
# deklarasi dari `package.json` SAJA tidak cukup. `linters/import_validator.py`
# baris 479-482 sengaja jatuh ke `<root>/node_modules/<pkg>` supaya dependensi
# transitif/peer tidak dituduh hilang. Jadi kondisi ASLI yang memblokir FASE 20
# adalah paket itu tidak ada DI KEDUANYA. Tanaman harus setia pada itu — kalau
# tidak, buktinya hijau palsu.  ⇒ Ini contoh nyata "menguji yang mirip ≠
# menguji yang sebenarnya", kesalahan yang sama yang sedang kita tutup.
say "7/8  Tanam B3: hapus deklarasi @testing-library/jest-dom DAN paketnya di node_modules"
NM_PKG=/app/frontend/node_modules/@testing-library/jest-dom
NM_STASH=/tmp/_prove_lint_jestdom_stash
if grep -q '@testing-library/jest-dom' "$PKG"; then
  cp "$PKG" "$PKG.bak"
  python3 - "$PKG" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
for k in ("dependencies", "devDependencies"):
    d.get(k, {}).pop("@testing-library/jest-dom", None)
json.dump(d, open(p, "w"), indent=2)
PY
  [ -d "$NM_PKG" ] && { rm -rf "$NM_STASH"; mv "$NM_PKG" "$NM_STASH"; }
  okm "deklarasi + paket node_modules disembunyikan"
  expect_red "B3" "LINT-IMPORT-BROKEN"
  [ -d "$NM_STASH" ] && mv "$NM_STASH" "$NM_PKG"
  mv "$PKG.bak" "$PKG" && okm "B3 dipulihkan" || bad "B3 gagal dipulihkan"
else
  bad "@testing-library/jest-dom belum dideklarasikan — tak bisa menanam B3"
fi

# ── akhir ───────────────────────────────────────────────────────────────────
say "8/8  Guard HIJAU lagi setelah semua dipulihkan"
if $GUARD >"$LOG/pl_green.log" 2>&1; then okm "guardrail HIJAU kembali (rc=0)"
else bad "masih MERAH setelah pemulihan"; tail -15 "$LOG/pl_green.log"; fi

printf "\n================ RINGKASAN ================\n"
printf "PASS=%s  FAIL=%s\n" "$PASS" "$FAIL"
[ "$FAIL" = "0" ] && { printf "${G}BUKTI MERAH LENGKAP — INV-LINT-01 menangkap KETIGA arah kegagalan.${X}\n"; exit 0; }
printf "${R}BUKTI GAGAL — guardrail belum bisa dipercaya.${X}\n"; exit 1
