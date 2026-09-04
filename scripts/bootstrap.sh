#!/usr/bin/env bash
# =============================================================================
# DA37 ERP — FAST BOOTSTRAP (idempotent + parallel)
# Tujuan: setup /app dari 0 → siap-jalan secepat mungkin.
#   env (.env) -> deps (pip+yarn PARALEL, di-cache) -> restart -> health -> seed -> verify
#
# Pakai (dari dalam repo yang sudah tersalin ke /app):
#   EMERGENT_LLM_KEY=sk-emergent-xxxx bash /app/scripts/bootstrap.sh
#
# Flags:
#   --reseed        paksa seed ulang walau data sudah ada
#   --force-deps    paksa install deps walau hash tak berubah
#   --skip-deps     lewati install deps (tercepat, jika yakin sudah siap)
#   --skip-seed     lewati seeding
#
# CATATAN: TIDAK PERNAH menimpa MONGO_URL / REACT_APP_BACKEND_URL.
# =============================================================================
set -uo pipefail
START=$(date +%s)
APP=/app
BE=$APP/backend
FE=$APP/frontend
CACHE=$APP/.bootstrap_cache
mkdir -p "$CACHE"

RESEED=0; FORCE_DEPS=0; SKIP_DEPS=0; SKIP_SEED=0
for a in "$@"; do case "$a" in
  --reseed) RESEED=1;; --force-deps) FORCE_DEPS=1;; --skip-deps) SKIP_DEPS=1;; --skip-seed) SKIP_SEED=1;;
esac; done

c(){ printf "\033[1;36m[bootstrap]\033[0m %s\n" "$*"; }
ok(){ printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m  ! %s\033[0m\n" "$*"; }
err(){ printf "\033[1;31m  ✗ %s\033[0m\n" "$*"; }

# --- 0. sanity ---------------------------------------------------------------
[ -f "$BE/server.py" ] || { err "$BE/server.py tak ada — repo belum tersalin ke /app. Lihat AGENT_QUICKSTART.md."; exit 1; }
[ -f "$BE/requirements.txt" ] || { err "requirements.txt tak ada"; exit 1; }

# --- 1. ENV (idempoten, tak menimpa URL kritis) -----------------------------
c "1/6 Menyiapkan backend/.env"
touch "$BE/.env"
# pastikan setiap baris diakhiri newline (hindari bug baris nyambung)
[ -n "$(tail -c1 "$BE/.env")" ] && echo >> "$BE/.env"
ensure_env(){ # ensure_env KEY DEFAULTVALUE  (hanya menambah jika belum ada)
  local k="$1" v="$2"
  if ! grep -q "^${k}=" "$BE/.env"; then echo "${k}=\"${v}\"" >> "$BE/.env"; ok "set ${k}"; fi
}
grep -q "^MONGO_URL=" "$BE/.env" || echo 'MONGO_URL="mongodb://localhost:27017"' >> "$BE/.env"
ensure_env DB_NAME "test_database"
ensure_env CORS_ORIGINS "*"
# JWT_SECRET: generate jika belum ada
if ! grep -q "^JWT_SECRET=" "$BE/.env"; then
  JWT=$(python3 -c "import secrets;print(secrets.token_urlsafe(48))")
  echo "JWT_SECRET=\"$JWT\"" >> "$BE/.env"; ok "generate JWT_SECRET"
fi
# EMERGENT_LLM_KEY: dari env var jika diberikan, else pertahankan yang ada
if [ -n "${EMERGENT_LLM_KEY:-}" ]; then
  if grep -q "^EMERGENT_LLM_KEY=" "$BE/.env"; then
    python3 - "$BE/.env" "$EMERGENT_LLM_KEY" <<'PY'
import sys,re
p,k=sys.argv[1],sys.argv[2]
s=open(p).read()
s=re.sub(r'^EMERGENT_LLM_KEY=.*$', f'EMERGENT_LLM_KEY="{k}"', s, flags=re.M)
open(p,'w').write(s)
PY
  else echo "EMERGENT_LLM_KEY=\"$EMERGENT_LLM_KEY\"" >> "$BE/.env"; fi
  ok "set EMERGENT_LLM_KEY (dari argumen)"
elif ! grep -q "^EMERGENT_LLM_KEY=" "$BE/.env"; then
  echo 'EMERGENT_LLM_KEY=""' >> "$BE/.env"
  warn "EMERGENT_LLM_KEY kosong — fitur AI/LLM tak jalan. Jalankan ulang: EMERGENT_LLM_KEY=sk-... bash $0"
fi
# frontend/.env: JANGAN diubah nilai kritisnya, hanya cek + tambah flag build
[ -f "$FE/.env" ] && grep -q "^REACT_APP_BACKEND_URL=" "$FE/.env" && ok "frontend/.env REACT_APP_BACKEND_URL ada" || warn "frontend/.env REACT_APP_BACKEND_URL tak ditemukan (biarkan platform yang set)"
# FASE 14 — `frontend/.env` di-gitignore, jadi clone segar KEHILANGAN dua flag
# yang WAJIB ada supaya `yarn build` selesai di container 1 core / 2 GB
# (lihat memory/PREVIEW_STABLE_MODE.md). Tanpa ini build bisa OOM / lama sekali.
if [ -f "$FE/.env" ]; then
  [ -n "$(tail -c1 "$FE/.env")" ] && echo >> "$FE/.env"
  grep -q "^GENERATE_SOURCEMAP=" "$FE/.env"    || { echo 'GENERATE_SOURCEMAP=false' >> "$FE/.env"; ok "set GENERATE_SOURCEMAP=false"; }
  grep -q "^DISABLE_ESLINT_PLUGIN=" "$FE/.env" || { echo 'DISABLE_ESLINT_PLUGIN=true' >> "$FE/.env"; ok "set DISABLE_ESLINT_PLUGIN=true"; }
fi

# --- 1b. RESOLUSI LINT DI ROOT REPO (anti "linter engine error") -------------
# `/app` tidak punya node_modules, sementara lint dijalankan DARI `/app` dengan
# `--format unix` ⇒ formatter global tak ter-resolve ⇒ rc=2 (ENGINE ERROR),
# bukan temuan lint. Detail lengkap: scripts/fix_root_lint_resolution.sh
c "1b/6 Resolusi lint root repo"
bash "$APP/scripts/fix_root_lint_resolution.sh" 2>&1 | sed 's/^/  /'

# --- 1c. SANITY LINGKUNGAN: mongod & deps benar-benar ADA -------------------
# Dua jebakan NYATA yang memakan waktu di container segar (2026-07-31):
#   1. `mongodb` berstatus STOPPED → backend hidup tapi /api/health gagal connect.
#   2. Marker cache `.bootstrap_cache/be.md5` IKUT TERSALIN dari repo, jadi
#      "backend deps sudah sesuai hash — skip" padahal container ini belum
#      pernah `pip install` (gejala: ModuleNotFoundError: openpyxl saat start).
c "1c/6 Sanity: mongod hidup + deps backend benar-benar terpasang"
if ! sudo supervisorctl status mongodb 2>/dev/null | grep -q RUNNING; then
  sudo supervisorctl start mongodb >/dev/null 2>&1 && ok "mongodb dijalankan" || warn "mongodb tidak bisa dijalankan"
else
  ok "mongodb RUNNING"
fi
# 1c-2. LIMIT FILE DESCRIPTOR MONGOD (temuan 2026-07-31)
# supervisord menjalankan mongod dengan soft limit nofile 1024 → backup/restore DB
# besar kena "Too many open files" → WT_PANIC → mongod ABORT → restore PUTUS dan
# portal Administrasi Sistem balas HTTP 500. Config supervisor READ-ONLY, jadi
# dinaikkan runtime. Backend juga menjaganya otomatis (startup + tiap 5 menit).
bash "$APP/scripts/ensure_mongod_fdlimit.sh" 2>&1 | sed 's/^/  /' || warn "gagal menaikkan limit file mongod"
if ! python3 - <<'PY' >/dev/null 2>&1
import importlib
for m in ("fastapi", "motor", "openpyxl", "reportlab", "apscheduler"):
    importlib.import_module(m)
PY
then
  warn "deps backend belum lengkap → marker cache dibuang, pip install dipaksa"
  rm -f "$CACHE/be.md5"
else
  ok "deps backend terpasang (probe import)"
fi

# 1c-3. DEPS FRONTEND BENAR-BENAR TERPASANG? (MARKER CACHE YANG BOHONG)
# AKAR MASALAH yang sudah menghabiskan DUA sesi (Session #25 & #26). Gejalanya
# selalu sama: bootstrap melaporkan `frontend deps sudah sesuai hash — skip`,
# lalu `yarn build` MERAH dengan `Module not found: '@simplewebauthn/browser'`
# (diimpor `src/pages/AbsenPage.jsx`) dan ringkasan menutup dengan
# `build/ MISSING`. Penyebabnya TIGA hal yang kebetulan bertemu:
#   · `.bootstrap_cache/fe.md5` IKUT TER-COMMIT ke repo;
#   · `frontend/yarn.lock` TIDAK ada di repo, jadi FE_HASH = md5(package.json +
#     yarn.lock milik TEMPLATE platform) — nilainya reproducible PERSIS SAMA
#     setiap sesi, sehingga marker yang ter-commit itu selalu "cocok";
#   · `node_modules/` milik template platform SUDAH ada (isinya bukan dependensi
#     aplikasi ini), sehingga syarat `[ -d node_modules ]` juga terpenuhi.
# Ketiga syarat skip terpenuhi ⇒ `yarn install` TIDAK PERNAH jalan.
# Pelajarannya sama dengan probe import backend di atas: **marker cache hanya sah
# kalau ia dibuat DI MESIN INI**. Jadi di sini kita memeriksa KENYATAAN — setiap
# `dependencies` di package.json harus benar-benar ada di node_modules — bukan
# mempercayai marker. (`.bootstrap_cache/` juga sudah di-gitignore supaya keadaan
# mesin berhenti ikut bepergian bersama repo.)
FE_MISSING=$(cd "$FE" 2>/dev/null && python3 - <<'PY'
import json, os
try:
    deps = json.load(open('package.json')).get('dependencies') or {}
except Exception:
    deps = {}
print(' '.join(sorted(d for d in deps
                      if not os.path.isdir(os.path.join('node_modules', *d.split('/'))))))
PY
)
if [ -n "$(echo "$FE_MISSING" | tr -d '[:space:]')" ]; then
  warn "deps frontend belum lengkap ($(echo $FE_MISSING | wc -w) paket hilang: $FE_MISSING) → marker cache dibuang, yarn install dipaksa"
  rm -f "$CACHE/fe.md5"
else
  ok "deps frontend terpasang (probe node_modules)"
fi

# --- 2. DEPS (paralel + cache via hash) -------------------------------------
c "2/6 Install deps (backend+frontend PARALEL, cache by-hash)"
BE_PID=""; FE_PID=""
if [ "$SKIP_DEPS" = "1" ]; then warn "lewati deps (--skip-deps)"; else
  # backend
  BE_HASH=$(md5sum "$BE/requirements.txt" | awk '{print $1}')
  if [ "$FORCE_DEPS" = "0" ] && [ -f "$CACHE/be.md5" ] && [ "$(cat "$CACHE/be.md5")" = "$BE_HASH" ]; then
    ok "backend deps sudah sesuai hash — skip"
  else
    ( pip install -q -r "$BE/requirements.txt" >"$CACHE/pip.log" 2>&1 && echo "$BE_HASH" > "$CACHE/be.md5" ) & BE_PID=$!
    c "  → pip install jalan di background (PID $BE_PID)"
  fi
  # frontend
  FE_HASH=$(cat "$FE/package.json" "$FE/yarn.lock" 2>/dev/null | md5sum | awk '{print $1}')
  if [ "$FORCE_DEPS" = "0" ] && [ -d "$FE/node_modules" ] && [ -f "$CACHE/fe.md5" ] && [ "$(cat "$CACHE/fe.md5")" = "$FE_HASH" ]; then
    ok "frontend deps sudah sesuai hash — skip"
  else
    # FASE 11 — AKAR MASALAH YANG SUDAH 3 SESI BERULANG:
    # `--frozen-lockfile` GAGAL TOTAL bila `frontend/yarn.lock` tidak ada di repo
    # (dan dulu memang tidak ter-commit), atau bila lockfile-nya tertinggal dari
    # package.json — gejalanya `@simplewebauthn/browser` tidak terpasang lalu
    # `yarn build` gagal. Sekarang: pakai frozen HANYA kalau lockfile-nya ada,
    # dan kalau gagal jatuh otomatis ke `yarn install` biasa (yang akan
    # membuat/memperbarui lockfile) — bukan menggantung dengan error.
    (
      cd "$FE" || exit 1
      if [ -f yarn.lock ]; then
        yarn install --frozen-lockfile --prefer-offline >"$CACHE/yarn.log" 2>&1 \
          || { echo "[bootstrap] frozen-lockfile gagal → fallback yarn install biasa" >>"$CACHE/yarn.log"
               yarn install --prefer-offline --network-timeout 600000 >>"$CACHE/yarn.log" 2>&1; }
      else
        echo "[bootstrap] yarn.lock tidak ada → yarn install biasa (lockfile akan dibuat)" >"$CACHE/yarn.log"
        yarn install --prefer-offline --network-timeout 600000 >>"$CACHE/yarn.log" 2>&1
      fi
    ) && echo "$FE_HASH" > "$CACHE/fe.md5" & FE_PID=$!
    c "  → yarn install jalan di background (PID $FE_PID)"
  fi
  [ -n "$BE_PID" ] && { wait "$BE_PID" && ok "pip install selesai" || { err "pip install GAGAL — lihat $CACHE/pip.log"; tail -15 "$CACHE/pip.log"; }; }
  [ -n "$FE_PID" ] && { wait "$FE_PID" && ok "yarn install selesai" || { err "yarn install GAGAL — lihat $CACHE/yarn.log"; tail -15 "$CACHE/yarn.log"; }; }
fi

# --- 2b. BUILD FRONTEND STATIC BUNDLE (stable-mode) -------------------------
# This container serves a PREBUILT static bundle via static_server.js (NOT the
# CRA dev server). A fresh clone has no build/, so we build it here. Safe:
# low priority (nice -n 19) + capped Node heap (1024MB via package.json build
# script) so the backend keeps answering the health probe and we stay under the
# 2GB cgroup cap. See /app/memory/PREVIEW_STABLE_MODE.md
c "2b/6 Frontend static bundle (stable-mode)"
if [ -f "$FE/build/index.html" ] && [ "$FORCE_DEPS" = "0" ]; then
  ok "build/ sudah ada — skip (setelah ubah src: bash /app/scripts/rebuild_frontend.sh)"
else
  c "  → yarn build (nice -n 19; beberapa menit di 1 core, heap 1024MB)"
  if ( cd "$FE" && nice -n 19 yarn build >"$CACHE/fe_build.log" 2>&1 ); then
    ok "frontend build OK"
  else
    err "frontend build GAGAL — lihat $CACHE/fe_build.log"; tail -20 "$CACHE/fe_build.log"
  fi
fi


# --- 3. RESTART SERVICES -----------------------------------------------------
c "3/6 Restart services (backend+frontend)"
sudo supervisorctl restart backend frontend >/dev/null 2>&1
ok "restart dikirim"

# --- 4. TUNGGU HEALTH --------------------------------------------------------
c "4/6 Menunggu backend health"
HEALTHY=0
for i in $(seq 1 40); do
  if curl -sf http://localhost:8001/api/health >/dev/null 2>&1; then HEALTHY=1; ok "backend healthy ($((i*2))s)"; break; fi
  sleep 2
done
[ "$HEALTHY" = "1" ] || { err "backend TIDAK healthy dalam 80s — cek: tail -50 /var/log/supervisor/backend.err.log"; }

# --- 5. LOGIN admin + SEED (idempoten) --------------------------------------
c "5/6 Login admin + seed"
TOKEN=""
if [ "$HEALTHY" = "1" ]; then
  TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
    -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
fi
if [ -z "$TOKEN" ]; then
  warn "login admin gagal (mungkin belum ada user). Menjalankan seed untuk membuat akun..."
fi
NEED_SEED=1
if [ "$SKIP_SEED" = "1" ]; then NEED_SEED=0; warn "lewati seed (--skip-seed)"; fi
if [ "$NEED_SEED" = "1" ] && [ "$RESEED" = "0" ] && [ -n "$TOKEN" ]; then
  EMP=$(curl -s "http://localhost:8001/api/rahaza/employees" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('total',len(d)) if isinstance(d,dict) else len(d))" 2>/dev/null || echo 0)
  # SESI #38 — dulu `>0` sudah dianggap "sudah ter-seed". Satu karyawan sisa
  # seeder LAIN ("Op. Demo Borongan" dari demo borongan) cukup untuk membuat
  # seluruh seed HR dilewati ⇒ 5 akun peran tanpa `employee_id` ⇒ gate absen,
  # cuti & payslip MERAH (35 kegagalan) dengan pesan "Akun Anda belum
  # ditautkan ke data karyawan". Ambangnya sekarang 5: di bawah itu artinya
  # seed HR memang belum pernah jalan.
  if [ "${EMP:-0}" -ge 5 ] 2>/dev/null; then NEED_SEED=0; ok "data sudah ter-seed (employees=$EMP) — skip (pakai --reseed utk paksa)"; fi
  [ "${EMP:-0}" -lt 5 ] 2>/dev/null && warn "employees=$EMP (< 5) — seed HR dijalankan supaya akun peran punya employee_id"
fi
if [ "$NEED_SEED" = "1" ] && [ "$HEALTHY" = "1" ]; then
  # jika belum ada token (user belum ada), coba seed tanpa auth dulu—kebanyakan seed butuh admin,
  # jadi kita andalkan default admin sudah dibuat saat startup; login lagi setelah delay singkat.
  [ -z "$TOKEN" ] && sleep 2 && TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
  if [ -n "$TOKEN" ]; then
    seed_ep(){
      local path="$1"
      local code
      code=$(curl -s -m 180 -o /tmp/seed_resp.json -w "%{http_code}" -X POST "http://localhost:8001${path}" -H "Authorization: Bearer $TOKEN")
      if [ "$code" = "200" ] || [ "$code" = "201" ]; then
        ok "seed ${path} OK"
      else
        err "seed ${path} gagal (HTTP ${code}): $(head -c 200 /tmp/seed_resp.json 2>/dev/null)"
      fi
    }
    c "  → seed master + demo (produksi, HR, maklon, marketing, phase 2-3-5)"
    seed_ep /api/rahaza/setup/seed-sample
    seed_ep /api/rahaza/hr-seed/run
    seed_ep /api/seed/maklon-full
    seed_ep /api/marketing/seed-sample-data
    seed_ep /api/dewi/seed-demo-full
    c "  → seed akun 5 role (hr/finance/spv/gudang/maklon @dewiaditya.id)"
    if python3 /app/backend/scripts/seed_role_accounts.py >/dev/null 2>&1; then ok "role accounts OK"; else warn "seed_role_accounts gagal (jalankan manual)"; fi
    # ACC-2 — jaring pengaman kopling BOM ↔ master material. Seeder BARU sudah
    # menautkan baris BOM sejak awal, tapi DB yang lahir dari seeder LAMA masih
    # menyimpan baris `material_id: null` (rantai BOM → kebutuhan aksesoris PO →
    # stok putus). Skrip ini idempoten: buat master yang belum ada + tautkan
    # baris yang kodenya cocok. Cek hasilnya di UI: banner kesehatan BOM.
    c "  → tautkan BOM demo ke master material (ACC-2 link-health)"
    if (cd /app/backend && python3 scripts/link_demo_bom_materials.py >/tmp/link_bom.log 2>&1); then
      ok "link BOM demo OK ($(grep -c 'linked' /tmp/link_bom.log >/dev/null 2>&1; grep 'BOM lines linked' /tmp/link_bom.log | head -1))"
    else
      warn "link_demo_bom_materials gagal (lihat /tmp/link_bom.log)"
    fi
    # FASE 12 — BASELINE VALUASI AKSESORIS (temuan verifikasi 2026-07-26).
    # `verify_fase10_digest_report.py` mengasumsikan baseline demo aksesoris ADA
    # (10 item, 2 di antaranya sengaja ber-HPP 0 supaya alarm & digest punya isi).
    # Karena bootstrap TIDAK pernah menjalankan seeder ini, DB hasil bootstrap
    # segar selalu memberi 8 FAIL PALSU (digest 0 item) dan bikin agent berikutnya
    # mengira ada regresi. Seeder idempoten (`--cleanup` untuk membersihkan).
    c "  → baseline valuasi aksesoris (10 item, 8 bernilai / 2 belum dinilai)"
    if (cd /app && python3 scripts/seed_acc_valuation_baseline.py >/tmp/seed_acc_val.log 2>&1); then
      ok "baseline valuasi aksesoris OK ($(grep 'nilai persediaan' /tmp/seed_acc_val.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_acc_valuation_baseline gagal (lihat /tmp/seed_acc_val.log)"
    fi
    # 2026-08-07 — MASTER SUPPLIER. Bootstrap tidak pernah menyeed ini, sehingga
    # environment segar selalu punya `rahaza_suppliers` = 0 dan tiga layar Portal
    # Pengadaan (Master Supplier, Penilaian Supplier, Analisis Belanja) tampil
    # kosong. Lebih parah: alur "PR disetujui → Buat Purchase Order" MENTOK di UI
    # karena dialog PO mewajibkan supplier dipilih dari master. Seeder idempoten
    # (`--cleanup` untuk membuang). Hanya master + daftar harga: tidak menyentuh
    # stok/jurnal, jadi baseline gate tidak berubah.
    c "  → master supplier demo + daftar harga (Portal Pengadaan)"
    if (cd /app && python3 scripts/seed_procurement_suppliers_demo.py >/tmp/seed_suppliers.log 2>&1); then
      ok "master supplier OK ($(grep 'SELESAI' /tmp/seed_suppliers.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_procurement_suppliers_demo gagal (lihat /tmp/seed_suppliers.log)"
    fi
    # SESI #17 (2026-08-17) — PENERIMAAN FG DARI CMT. Bootstrap tidak pernah
    # menyeed `cmt_receipts`, sehingga environment SEGAR selalu memberi MERAH PALSU
    # pada gate INV-F23 S8 ("prod-cmt-packing → da-cmt-receive: cmt_receipts kosong")
    # dan membuat agent berikutnya mengira alias Fase H-8 rusak. Seeder idempoten,
    # menautkan diri ke pengiriman deklarasi CMT yang sudah ada (angka bukan tebakan),
    # status `on_qc` ⇒ stok & jurnal TIDAK tersentuh (baseline gate lain tetap).
    c "  → penerimaan FG dari CMT (demo, agar pintu da-cmt-receive tidak kosong)"
    if (cd /app && python3 scripts/seed_cmt_receipt_demo.py >/tmp/seed_cmt_rcv.log 2>&1); then
      ok "penerimaan FG CMT OK ($(grep -E 'CMT-RCV|dilewati' /tmp/seed_cmt_rcv.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_cmt_receipt_demo gagal (lihat /tmp/seed_cmt_rcv.log)"
    fi
    # ── SESI #9 (2026-08-14) — 4 SEEDER YANG DULU HANYA ADA DI HANDOFF ─────────
    # Empat perintah ini SELALU ditulis manual di HANDOFF ("MENJALANKAN CEPAT DI
    # ENVIRONMENT BARU"), jadi setiap environment segar yang hanya menjalankan
    # bootstrap.sh melahirkan keadaan yang MENIPU:
    #   · `marketing_platform_accounts` cuma berisi 3 toko DEMO — 9 toko NYATA
    #     hilang, sehingga layar lingkup/assign toko tak bisa dinilai;
    #   · `marketing_orders` KOSONG ⇒ gate `INV-MKTCYCLE` CYC-8 di-SKIP dan
    #     layar Siklus/Rekap tampak "rusak" padahal hanya belum berdata;
    #   · katalog tanpa varian internal ⇒ marjin & HPP tidak punya dasar join.
    # Semua idempoten dan menulis lewat API resmi (jejak audit ikut lahir).
    c "  → 9 toko marketing NYATA + akun COA piutang per toko"
    if (cd /app/backend && python3 scripts/seed_marketing_real_accounts.py --apply >/tmp/seed_real_acc.log 2>&1); then
      ok "toko nyata OK ($(grep 'ringkas:' /tmp/seed_real_acc.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_marketing_real_accounts gagal (lihat /tmp/seed_real_acc.log)"
    fi
    c "  → varian internal (warna×ukuran) + item katalog jual demo"
    if (cd /app && python3 scripts/seed_internal_variants.py >/tmp/seed_iv.log 2>&1 \
        && python3 scripts/seed_katalog_order_demo.py >/tmp/seed_kat.log 2>&1); then
      ok "varian + katalog OK ($(grep 'SELESAI' /tmp/seed_kat.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed varian/katalog gagal (lihat /tmp/seed_iv.log, /tmp/seed_kat.log)"
    fi
    c "  → pesanan nyata 2026-07 + target/anggaran 3 keadaan (layar Siklus F5)"
    if (cd /app && python3 scripts/seed_marketing_cycle_demo.py >/tmp/seed_cycle.log 2>&1); then
      ok "demo siklus OK ($(grep 'peringatan' /tmp/seed_cycle.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_marketing_cycle_demo gagal (lihat /tmp/seed_cycle.log)"
    fi
    # SESI #9 — KEADAAN RETUR. Seluruh data demo berstatus `paid` (nol retur), jadi
    # kartu "omzet setelah retur" selalu sama dengan bruto dan peringatan
    # `returns_high` tak pernah bisa dibuktikan menyala. Seeder ini mengubah
    # beberapa pesanan menjadi `returned` LEWAT SSOT status (reservasi stok ikut
    # dilepas) lalu menghitung ulang rekap harian. Idempoten; tidak punya
    # `--cleanup` karena `returned` memang status TERMINAL.
    c "  → keadaan retur demo (bruto vs setelah retur bisa dilihat di layar)"
    if (cd /app/backend && python3 scripts/seed_marketing_returns_demo.py >/tmp/seed_returns.log 2>&1); then
      ok "retur demo OK ($(grep 'SELESAI' /tmp/seed_returns.log | head -1 | sed 's/^ *//' | cut -c1-90))"
    else
      warn "seed_marketing_returns_demo gagal (lihat /tmp/seed_returns.log)"
    fi
    # F8 (2026-08-14) — KREATOR + KONTEN + SESI + TARGET KREATOR.
    # Tanpa ini layar **Scorecard Kreator** selalu berbunyi "Belum ada kreator yang
    # bisa dinilai" pada environment hasil bootstrap — fitur yang sudah jadi tampak
    # belum jadi, dan cacat sesungguhnya tak pernah terlihat (layar kosong tidak
    # bisa salah). Seeder idempoten, TIDAK membuat master toko baru, dan sengaja
    # menyisakan 1 kreator tanpa target + 2 konten tanpa KPI supaya keadaan
    # "belum ada target" & "cakupan KPI < 100%" benar-benar tampil.
    c "  → kreator + konten/KPI + sesi live + target kreator (Scorecard Kreator)"
    if (cd /app/backend && python3 scripts/seed_marketing_creator_demo.py >/tmp/seed_creator.log 2>&1); then
      ok "demo kreator OK ($(grep 'SELESAI' /tmp/seed_creator.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_marketing_creator_demo gagal (lihat /tmp/seed_creator.log)"
    fi
    # F6.5 (2026-08-14, sesi #9) — JEJAK PERUBAHAN yang bisa dinilai.
    # Tanpa ini `marketing_change_log` di environment segar hanya berisi 4 baris
    # dari SATU pelaku, SATU jenis, dan NOL perubahan kewenangan ⇒ layar "Jejak
    # Perubahan" tampak belum jadi (filter "hanya kewenangan" mengosongkan tabel,
    # pemilih Pelaku hanya satu nama, tidak ada satu pun nilai LAMA → BARU).
    # Seeder memakai API resmi (jejak tidak boleh dikarang) & idempoten.
    # SENGAJA tidak memberi toko ke `staffmkt@dewiaditya.id` — dialah bukti
    # keadaan "staf baru sebelum SPV meng-assign" (layar kosong yang menjelaskan diri).
    c "  → jejak perubahan demo (assign toko oleh SPV + target/anggaran/kunci periode)"
    if (cd /app && python3 scripts/seed_marketing_change_log_demo.py >/tmp/seed_changelog.log 2>&1); then
      ok "jejak demo OK ($(grep '30 hari' /tmp/seed_changelog.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_marketing_change_log_demo gagal (lihat /tmp/seed_changelog.log)"
    fi
    # ── FASE 3 (sesi #11) — LAYAR UANG & STOK TIDAK BOLEH KOSONG DI ENV SEGAR ──
    # Empat layar (Kasbon & Pinjaman · Inbox Approval Klaim/Dinas · Roll Kain ·
    # Surat Jalan) datang KOSONG dari bootstrap, sehingga fiturnya tampak belum
    # jadi dan penguji berikutnya menghabiskan waktu memastikan apakah layarnya
    # rusak. Endpoint seed kasbon sendiri sudah ada sejak lama tetapi hanya hidup
    # sebagai perintah manual — pola yang persis membuat 4 seeder marketing hilang
    # di sesi #9. Idempoten (jalan 2× ⇒ +0) dan lewat API resmi.
    c "  → data demo layar uang & stok (kasbon · klaim · roll kain · surat jalan)"
    if (cd /app/backend && python3 scripts/seed_finance_wms_demo.py >/tmp/seed_finwms.log 2>&1); then
      ok "demo uang & stok OK ($(grep 'SELESAI' /tmp/seed_finwms.log | head -1 | sed 's/^ *//'))"
    else
      warn "seed_finance_wms_demo gagal (lihat /tmp/seed_finwms.log)"
    fi
    # F13 (2026-08-10) — SATUKAN MASTER VENDOR CMT.
    # Seeder demo membuat `dewi_cmt_partners` (CMT-001..004) TANPA pasangan di
    # `vendor_partners`, sehingga environment hasil bootstrap segar selalu punya
    # DUA master vendor CMT yang irisan id-nya 0. Akibatnya nyata dan soal uang:
    # pembayaran CMT yang ditulis `production_maklon_bridge` (memakai id
    # `vendor_partners`) TIDAK muncul di halaman vendor Portal CMT yang membaca
    # dengan id master lain ⇒ "outstanding Rp 0" padahal hutang jasa jahitnya ada.
    # Gate `verify_data_integrity` (INV-CMTVEN-1) memeriksa ini, jadi tanpa langkah
    # ini bootstrap segar selalu melahirkan gate MERAH yang bukan salah produk.
    # Idempoten; `--dry-run` untuk melihat rencananya tanpa mengubah apa pun.
    c "  → satukan master vendor CMT (vendor_partners ⇄ dewi_cmt_partners)"
    if (cd /app && python3 scripts/migrate_unify_cmt_vendor_master.py >/tmp/unify_cmt.log 2>&1); then
      ok "master vendor CMT disatukan ($(grep 'irisan id sekarang' /tmp/unify_cmt.log | head -1 | sed 's/^ *//'))"
    else
      warn "migrate_unify_cmt_vendor_master gagal (lihat /tmp/unify_cmt.log)"
    fi
    # 2026-08-07 (sesi lanjutan) — DATA DEMO RANTAI PERSETUJUAN.
    # Bootstrap segar meninggalkan `dewi_procurement_requests` = 0 DAN
    # `acc_purchase_requests` = 0, sehingga tiga layar inti Portal Pengadaan
    # (Permintaan Pengadaan, Request Pembelian Aksesoris, Dashboard Pengadaan)
    # tampak RUSAK padahal hanya kosong — dan rantai persetujuan dept → keuangan
    # → final tidak bisa dilihat/diuji lewat layar sama sekali. Sesi sebelumnya
    # mengkurasi data ini dengan panggilan manual, jadi hilang tiap DB dibangun
    # ulang. Seeder ini IDEMPOTEN, memakai API sungguhan (jadi jejak audit &
    # notifikasinya asli), dan tidak menyentuh stok/jurnal. `--cleanup` membuang.
    # HARUS setelah master supplier: skenario ke-4 (PR → Purchase Order) memilih
    # supplier dari master.
    c "  → data demo rantai persetujuan (PR pengadaan + PR aksesoris)"
    if (cd /app && python3 scripts/seed_approval_demo.py >/tmp/seed_approval.log 2>&1); then
      ok "data demo persetujuan OK ($(grep -c '✓' /tmp/seed_approval.log) langkah)"
    else
      warn "seed_approval_demo gagal (lihat /tmp/seed_approval.log)"
      tail -5 /tmp/seed_approval.log | sed 's/^/      /'
    fi
    # SESI #17 (2026-08-17) — PENUTUP SEED: SELARASKAN DATA DEMO DENGAN SSOT.
    # Dua gate SELALU MERAH di container segar padahal kodenya benar, dan setiap
    # sesi memperbaikinya MANUAL (perintahnya cuma tertulis di HANDOFF):
    #   · INV-18 — seeder demo maklon membuat dokumen dispatch buyer LANGSUNG di DB
    #     tanpa pernah menambah stok FG hasil produksi ⇒ "dispatch tanpa mutasi stok
    #     FG keluar". `--topup-fg` memang disediakan untuk data demo ini.
    #   · INV-14 — buku kuantitas job item ditulis inkremental (`$inc`), jadi seed/
    #     hapus berulang meninggalkan angka menggantung; bagian C skrip yang sama
    #     merekalkulasinya DARI dokumen sumber.
    # Idempoten: kalau tidak ada yang perlu diperbaiki, keduanya tidak menulis apa pun.
    c "  → selaraskan data demo dengan SSOT (stok FG dispatch + buku kuantitas)"
    if (cd /app && python3 scripts/repair_selisih_ssot.py --apply --topup-fg >/tmp/repair_ssot.log 2>&1); then
      ok "SSOT demo selaras ($(grep -E 'qty dikeluarkan' /tmp/repair_ssot.log | head -1 | sed 's/^ *//'))"
    else
      warn "repair_selisih_ssot gagal (lihat /tmp/repair_ssot.log)"
    fi
  else
    err "tak bisa login admin utk seed — cek backend log"
  fi
fi

# --- 6. VERIFY LOGIN (admin + 5 role) ---------------------------------------
c "6/6 Verifikasi login akun"
if [ "$HEALTHY" = "1" ]; then
  check_login(){ curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" -d "{\"email\":\"$1\",\"password\":\"$2\"}"; }
  A=$(check_login admin@garment.com Admin@123); printf "    admin@garment.com -> HTTP %s\n" "$A"
  for e in hr finance spv gudang maklon; do
    C=$(check_login "${e}@dewiaditya.id" "Dewi@123"); printf "    %-8s@dewiaditya.id -> HTTP %s\n" "$e" "$C"
  done
fi

# --- FRONTEND static-mode check ---------------------------------------------
if [ -f "$FE/build/index.html" ]; then
  FE_HTTP=$(curl -s -m 8 -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null)
  FE_STATE="static bundle served (HTTP ${FE_HTTP})"
else
  FE_STATE="build/ MISSING — run: bash /app/scripts/rebuild_frontend.sh"
fi

END=$(date +%s)
echo ""
c "SELESAI dalam $((END-START)) detik."
printf "  backend health : %s\n" "$([ "$HEALTHY" = 1 ] && echo OK || echo GAGAL)"
printf "  frontend       : %s\n" "${FE_STATE:-(kompilasi belum selesai; cek lagi ~20s)}"
printf "  preview        : lihat frontend/.env REACT_APP_BACKEND_URL\n"
echo "  Login: admin@garment.com / Admin@123  |  role: {hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123"
