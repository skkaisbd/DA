#!/usr/bin/env bash
# =============================================================================
# fix_root_lint_resolution.sh — TUTUP "linter engine error" DI GATE PLATFORM
# =============================================================================
# GEJALA (mem-blok tool `finish`/`ask_human`, jadi sesi TIDAK BISA diserahkan):
#   "Pre-completion checks failed. Fix these issues before proceeding.
#    JavaScript linting failed due to a linter engine error."
#
# ─────────────────────────────────────────────────────────────────────────────
# ⚠️ KOREKSI RCA (2026-07-26, FASE 21) — VERSI LAMA SKRIP INI SALAH DIAGNOSA
# ─────────────────────────────────────────────────────────────────────────────
# Versi FASE 14 skrip ini MENDUGA platform menjalankan `eslint . --format unix`
# dari cwd `/app` memakai ESLint global, sehingga nama formatter "unix" tak
# ter-resolve karena `/app` tak punya `node_modules`. Perbaikannya: symlink
# `/app/node_modules/eslint-formatter-unix`.
#
# Dugaan itu TIDAK TERBUKTI. Kode platform dibaca langsung
# (`/opt/plugins-venv/lib/python3.11/site-packages/linters/engines.py`,
# class `ESLintEngine.run`) dan kenyataannya:
#   • formatter dipanggil dengan PATH ABSOLUT: `--format=<linters>/node_modules/
#     eslint-formatter-unix/index.js` ⇒ resolusi nama TIDAK PERNAH terjadi,
#   • config juga PATH ABSOLUT: `--config <linters>/frontend/eslint.config.js`
#     ⇒ `/app/eslint.config.js` milik repo TIDAK dipakai oleh gate platform.
# Jadi symlink itu tidak pernah menjadi penyebab hijau/merahnya gate. Ia
# DIPERTAHANKAN di bawah (murah, tak berefek samping) sebagai jaring untuk
# versi platform lain, tapi ia BUKAN perbaikannya.
#
# ─────────────────────────────────────────────────────────────────────────────
# AKAR MASALAH SEBENARNYA (dibuktikan, bukan dugaan)
# ─────────────────────────────────────────────────────────────────────────────
# `ESLintEngine.run()` memilih config berdasarkan FRAMEWORK yang dideteksi dari
# **path pertama** yang dilint (`_detect_framework`): ia menyusuri direktori ke
# atas sampai `package.json` pertama, lalu melihat dependensinya.
#   /app/mobile/package.json  → memuat "expo"  ⇒ framework = "expo"
#                             ⇒ config = <linters>/frontend/eslint.expo.config.js
# Config expo itu berisi `import expoConfig from 'eslint-config-expo/flat.js'`,
# dan `eslint-config-expo` **TIDAK terpasang** di node_modules global image ini
# (`/usr/lib/node_modules`, satu-satunya tempat yang bisa di-resolve dari
# direktori linter platform). Hasilnya:
#
#   ESLint: 9.39.5
#   Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'eslint-config-expo'
#       imported from <linters>/frontend/eslint.expo.config.js
#
# ⇒ ESLint keluar **rc=2 dengan stdout KOSONG**. Di `_run_sync_lint_subprocess`
#   itu jadi `❌ ESLint failed (exit 2) …` + `success=False`; di
#   `run_javascript_linter` jadi `engine_success=False`; dan karena stdout kosong
#   maka `blocking_count == 0` — tepat kombinasi yang membuat `lint_javascript`
#   melempar **"JavaScript linting failed due to a linter engine error."**
#
# Kenapa ini baru muncul sekarang: cakupan lint gate mencakup berkas di
# `/app/mobile/**` (aplikasi Expo/React Native di repo ini). Selama path pertama
# yang dilint ada di luar `mobile/`, framework terdeteksi "standard" dan gate
# HIJAU — itulah kenapa bug ini terasa "kadang muncul kadang tidak".
#
# PERBAIKAN: pastikan `eslint-config-expo` bisa di-resolve dari direktori linter
# platform. Komentar di config platform sendiri menyebut paket itu "resolves from
# the global install via the linters node_modules symlink" — jadi tempat yang
# BENAR memang node_modules global, bukan di dalam repo.
#
# CATATAN PERSISTENSI: `/usr/lib/node_modules` ADA DI LUAR `/app`, jadi ia bisa
#   hilang saat container/pod diganti. Karena itu skrip ini dipanggil
#   `bootstrap.sh` (langkah 1b) supaya setiap container baru sembuh sendiri, dan
#   dijaga guardrail BLOCKING `INV-LINT-01`
#   (`scripts/guardrails/verify_platform_lint_engine.py`).
#
# Pakai: bash /app/scripts/fix_root_lint_resolution.sh
# =============================================================================
set -uo pipefail
APP=${APP:-/app}
GLOBAL_NM=$(npm root -g 2>/dev/null || echo /usr/lib/node_modules)

# ── 1. Jaring lama: resolusi formatter dari cwd root repo ─────────────────────
# Bukan penyebab (lihat KOREKSI RCA di atas) tapi murah & tanpa efek samping;
# tetap dipasang supaya versi platform yang memakai `--format unix` (nama, bukan
# path) juga aman.
NEEDED_LOCAL=(eslint-formatter-unix)
mkdir -p "$APP/node_modules"
for pkg in "${NEEDED_LOCAL[@]}"; do
  src="$GLOBAL_NM/$pkg"; dst="$APP/node_modules/$pkg"
  if [ -d "$src" ]; then ln -sfn "$src" "$dst"; echo "  ✓ resolusi root: $pkg -> $src"
  else echo "  ! $pkg tak ada di $GLOBAL_NM — dilewati"; fi
done

# ── 2. PERBAIKAN NYATA: config framework yang dipakai GATE harus bisa dimuat ──
# Paket yang dibutuhkan config bawaan platform, per framework yang dideteksi.
# `eslint-config-expo` wajib ada KALAU repo memuat app Expo/React Native.
needs_expo=0
while IFS= read -r pkgjson; do
  grep -qE '"(expo|react-native)"[[:space:]]*:' "$pkgjson" 2>/dev/null && needs_expo=1
done < <(find "$APP" -maxdepth 3 -name package.json -not -path '*/node_modules/*' 2>/dev/null)

if [ "$needs_expo" = "1" ]; then
  if [ -d "$GLOBAL_NM/eslint-config-expo" ]; then
    echo "  ✓ eslint-config-expo sudah ada di $GLOBAL_NM"
  else
    echo "  → repo memuat app Expo/React Native; memasang eslint-config-expo (global)…"
    if npm install -g eslint-config-expo >/tmp/npm_expo_cfg.log 2>&1; then
      echo "  ✓ eslint-config-expo terpasang"
    else
      echo "  ✗ GAGAL memasang eslint-config-expo — gate lint platform AKAN merah:"
      tail -5 /tmp/npm_expo_cfg.log | sed 's/^/      /'
    fi
  fi
fi

# ── 3. BUKTI: jalankan MESIN LINT PLATFORM-nya sendiri, bukan CLI tebakan ─────
# Pelajaran FASE 20 #3: "menguji helper ≠ menguji pemakaiannya". Versi lama
# skrip ini membuktikan `eslint . --format unix` rc=0 — perintah yang TERNYATA
# tidak pernah dijalankan platform. Jadi ia hijau sementara gate tetap merah.
if [ -f "$APP/scripts/guardrails/verify_platform_lint_engine.py" ]; then
  python3 "$APP/scripts/guardrails/verify_platform_lint_engine.py" --quiet
  rc=$?
  [ $rc -eq 0 ] && echo "  ✓ mesin lint PLATFORM jalan untuk semua framework yang terdeteksi" \
                || { echo "  ✗ mesin lint platform MASIH gagal (lihat INV-LINT-01 di atas)"; exit 1; }
else
  echo "  ! guardrail INV-LINT-01 tak ditemukan — bukti dilewati"
fi
exit 0
