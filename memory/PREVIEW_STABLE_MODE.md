# PREVIEW STABLE MODE — READ ME FIRST (frontend serving)

> **Applies to THIS environment. Do not "fix" it back to `craco start`.**
> This container is capped at **1 CPU core / 2 GB RAM** (`cpu.max=100000 100000`,
> `memory.max=2GiB`). The frontend has **~567 source files**.

## The problem (why the preview "was always stuck")
Running the CRA/webpack **dev server** (`craco start`) compiles all 567 files at
startup. On 1 CPU core this takes **~5 minutes at 100% CPU**. During that window
the backend can't get CPU time to answer the platform **health probe**, so
Kubernetes **restarts the whole pod every ~1-2 minutes** — BEFORE the compile
finishes. Result: infinite restart loop, preview never serves (502 / Bad Gateway).

Evidence: `oom_kill=0` (NOT memory-killed), all services reset to uptime ~0 together,
`memory.peak` resets (fresh container). With the frontend stopped, the pod is rock stable.

## The solution (current setup) — serve a prebuilt static bundle
Instead of the dev server, we build **once** and serve the static output:
- `frontend/package.json` → `"start": "node static_server.js"` (supervisor runs this)
- `frontend/static_server.js` → zero-dependency static file server (SPA fallback),
  starts in <1s, ~30 MB RAM, **compiles nothing** → probe always passes → pod stable.
- `frontend/build/` → the compiled app (produced by `yarn build`). Persists on disk
  across pod restarts/wakes, so **no recompile on wake** → preview loads instantly.

### Build tuning (so the one-time build survives 1-core/2GB)
- `frontend/.env`: `GENERATE_SOURCEMAP=false`, `DISABLE_ESLINT_PLUGIN=true`
- `frontend/craco.config.js`: `optimization.minimize=false` for production (skip heavy Terser)
- `package.json` build script: `NODE_OPTIONS=--max-old-space-size=1536` (under the 2GB cap)
- Build is run with `nice -n 19` so the backend keeps answering the health probe.

### The react-data-grid "ecij" fix (unrelated to memory, but required to compile)
`react-data-grid@7.0.0-beta.*` ships a broken side-effect import `import "ecij";`
(`react-data-grid/lib/index.js` line 3) — `ecij` does not exist. Fixed in
`craco.config.js` via `resolve.alias = { ecij: false }` (empty module). Grid styles
are imported separately via `react-data-grid/lib/styles.css`, so nothing breaks.

## HOW TO WORK IN THIS REPO (future agents / sessions)

### Just run it (preview should already be up)
- `sudo supervisorctl status` → backend RUNNING, frontend RUNNING.
- Frontend serves `build/`. If `build/` is missing (fresh clone), run the rebuild below.

### After ANY change to frontend source (`frontend/src/**`)
The change will NOT appear until you rebuild the static bundle:
```bash
bash /app/scripts/rebuild_frontend.sh
```
This runs `yarn build` (low priority) then reloads the static server.
There is **no hot reload** in this mode — this is the intended trade-off for stability.

### Backend changes
Backend (`backend/**`) uses uvicorn `--reload` via supervisor → hot-reloads normally.
No rebuild needed for backend.

### If you REALLY need dev-server hot reload (NOT recommended here)
`cd /app/frontend && yarn start:dev` — expect the restart loop described above.
Only viable if the container CPU/RAM cap is raised.

## Environment config that must exist (gitignored — re-add on fresh clone)
- `backend/.env`: `JWT_SECRET="..."` (REQUIRED — backend raises RuntimeError without it),
  plus `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`. `EMERGENT_LLM_KEY=""` (empty ok; AI deferred).
- `frontend/.env`: keep `REACT_APP_BACKEND_URL` as-is; plus `GENERATE_SOURCEMAP=false`,
  `DISABLE_ESLINT_PLUGIN=true`.
- Seed data: `POST /api/seed/production-full` and `POST /api/rahaza/seed-demo` (admin token).

## Credentials
See `memory/test_credentials.md`. Admin: `admin@garment.com` / `Admin@123`.
Roles: `{hr,finance,spv,gudang,maklon}@dewiaditya.id` / `Dewi@123`.

## UPDATE 2026-08-10 — `build/` TIDAK bertahan melewati restart pod (KOREKSI PENTING)

Bagian di atas menulis bahwa `frontend/build/` "persists on disk across pod
restarts/wakes". **Itu TIDAK benar di environment ini.** Bukti sesi 2026-08-10:

* 12:51 `yarn build` selesai, `build/` lengkap, preview 200 ✅
* 14:53 pod restart (wake) → `ls /app/frontend/build` = **No such file or directory**
  (padahal `node_modules` 912 paket TETAP ada, dan `backend/.env` malah ditulis ulang)

Penyebab: `build/` ada di `.gitignore`; pemulihan `/app` saat pod bangun hanya
mengembalikan berkas terlacak (+ cache `node_modules` yang dikelola platform).

**Akibat nyata bila dibiarkan:** setiap kali pod bangun, pemilik aplikasi membuka
preview dan hanya melihat halaman **"Preparing preview…"** selamanya — sampai ada
agen yang login dan menjalankan `yarn build` dengan tangan. Dari sisi pengguna itu
sama dengan aplikasi RUSAK, dan tidak ada satu pun log yang menjelaskannya.

### Perbaikan: `static_server.js` sekarang MENYEMBUHKAN DIRI (auto-build)
* Saat `listen()` **dan** saat ada permintaan halaman ketika `build/index.html`
  hilang → `nice -n 19 yarn build` dijalankan otomatis di latar belakang.
* Dikunci `frontend/.autobuild.lock` (kedaluwarsa 15 menit) supaya TIDAK PERNAH
  ada dua build sekaligus. Log build: `frontend/autobuild.log`.
* Halaman "Preparing preview…" me-refresh sendiri tiap 10 detik, jadi preview
  menyala sendiri begitu bundel jadi (±40–60 detik di container 2-core).
* Keduanya gitignored (`/autobuild.log`, `/.autobuild.lock`) — itu keadaan mesin,
  bukan kode.

### Yang WAJIB diingat agen berikutnya
1. Setelah mengubah `frontend/src/**` **tetap** jalankan `bash /app/scripts/rebuild_frontend.sh`.
   Auto-build hanya menangani kasus **bundel hilang**, bukan bundel basi.
2. Jangan heran kalau `build/` hilang setelah pod tidur — itu normal di sini;
   biarkan auto-build bekerja, atau jalankan rebuild kalau ingin segera.
3. Container ini sekarang punya **2 core CPU + batas memori 8 GiB** (bukan lagi
   1 core / 2 GB seperti catatan lama), sehingga `yarn build` selesai ±40 detik.


## UPDATE (fresh-clone hardening — this session)
Two fixes were applied so a fresh clone comes up cleanly without a pod-restart loop:
1. **`static_server.js` no longer crashes when `build/` is missing.** The old
   version wrote HTTP headers twice on a read-stream error (`ERR_HTTP_HEADERS_SENT`),
   crashing the process → supervisor restart loop → frontend health probe fails →
   pod restart. Now headers are written only on stream `open`; a missing `build/`
   serves a lightweight auto-refreshing "Preparing preview…" page (HTTP 200), so the
   frontend probe passes even before the first build finishes.
2. **Build heap lowered to 1024 MB** (`package.json` `build` script) — with the
   backend + mongo also resident, the old `1536 MB` heap could push the container
   past the 2 GB cgroup cap (OOM) during `yarn build`. 1024 MB builds fine
   (peak ≈ 970 MB total, minify + sourcemaps off) and stays well under the cap.

**Fresh-clone bring-up (verified working):**
`pip install -r backend/requirements.txt` · `yarn install` · write `backend/.env`
(JWT_SECRET + EMERGENT_LLM_KEY + MONGO_URL + DB_NAME + CORS_ORIGINS) · write
`frontend/.env` (GENERATE_SOURCEMAP=false, DISABLE_ESLINT_PLUGIN=true) ·
`supervisorctl restart backend` · `bash /app/scripts/rebuild_frontend.sh` (or a
detached `craco build`) · seed via admin token. Login + portal selection verified.

## Files changed for this stable-mode setup
- `frontend/static_server.js` (new)
- `frontend/package.json` (scripts: start/serve/build/start:dev)
- `frontend/craco.config.js` (ecij alias + minify-off)
- `frontend/.env` (sourcemap off, eslint plugin off)
- `frontend/build/` (static bundle output)
- `backend/.env` (JWT_SECRET)

---
### PASTE-READY PROMPT FOR THE NEXT SESSION
```
IMPORTANT ENV CONSTRAINT — read /app/memory/PREVIEW_STABLE_MODE.md first.
This container is capped at 1 CPU core / 2GB RAM and the frontend has ~567 files.
DO NOT run the CRA dev server (`craco start` / `yarn start:dev`) to serve the preview —
it compiles for ~5 min at 100% CPU, which makes the platform health-probe fail and
restarts the pod in a loop (preview never loads). 

The frontend is served as a PREBUILT STATIC BUNDLE:
- supervisor runs `yarn start` = `node static_server.js` (serves frontend/build/, instant).
- After ANY change to frontend/src, run: bash /app/scripts/rebuild_frontend.sh
  (this does `yarn build` at low priority, then reloads the static server). No hot reload.
- Backend hot-reloads normally (uvicorn --reload); no rebuild needed for backend.
- Keep the `ecij: false` alias in craco.config.js (react-data-grid ships a broken import).
- backend/.env must contain JWT_SECRET or the backend won't start.
Credentials: admin@garment.com / Admin@123 ; {hr,finance,spv,gudang,maklon}@dewiaditya.id / Dewi@123
```
