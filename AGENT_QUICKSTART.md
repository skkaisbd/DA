# ⚡ AGENT QUICKSTART — Setup DA37 ERP super cepat

> Tujuan: dari `/app` template kosong → app siap-jalan **dalam beberapa langkah, paralel, idempoten**.
> Repo asli: `https://github.com/pandekomangyogaswastika-dot/da71` (env `.env` di-gitignore, dibuat oleh skrip).

---

## LANGKAH 1 — Clone cepat + salin ke /app (shallow, tanpa history)
Agent jalankan (1 perintah):
```bash
cd /tmp && rm -rf da71 && \
git clone --depth 1 https://github.com/pandekomangyogaswastika-dot/da71.git da71 && \
rsync -a --exclude='.env' --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='*.pyc' /tmp/da71/ /app/
```
- `--depth 1` = shallow clone (jauh lebih cepat, ~sedetik, tanpa riwayat commit).
- `rsync --exclude='.env'` = **JANGAN timpa** `backend/.env`(MONGO_URL) & `frontend/.env`(REACT_APP_BACKEND_URL) milik platform.
- `--exclude='node_modules'` = jangan salin (tak ada di clone, dan biar cache lokal dipakai).

## LANGKAH 2 — Ambil EMERGENT_LLM_KEY (via tool), lalu jalankan bootstrap
1. Panggil tool `emergent_integrations_manager` → dapat `emergent_llm_key`.
2. Jalankan skrip all-in-one (env + deps paralel + restart + health + seed + verify):
```bash
EMERGENT_LLM_KEY=sk-emergent-XXXX bash /app/scripts/bootstrap.sh
```
Selesai. Skrip mencetak status health, kompilasi frontend, dan hasil login 6 akun.

---

## Kenapa ini cepat (optimasi yang dipakai `bootstrap.sh`)
| Optimasi | Efek |
|---|---|
| **Shallow clone** (`--depth 1`) | clone jauh lebih ringan (tanpa git history 27MB) |
| **pip + yarn PARALEL** (background job + `wait`) | dua instalasi terberat jalan bersamaan, bukan berurutan |
| **Cache by-hash** | pip/yarn **di-skip** jika `requirements.txt`/`package.json`+`yarn.lock` tak berubah (re-run ≈ instan). Marker di `/app/.bootstrap_cache/` |
| **`yarn --prefer-offline`** | pakai cache paket lokal dulu |
| **Seed idempoten** | skip seed jika `employees>0` (pakai `--reseed` utk paksa) |
| **Health wait-loop** | lanjut begitu `/api/health` OK, tak menebak `sleep` panjang |
| **env idempoten** | hanya menambah key yang belum ada; **tak pernah** menyentuh MONGO_URL/REACT_APP_BACKEND_URL; auto-fix newline |

## Flags berguna
```bash
bash /app/scripts/bootstrap.sh --skip-deps     # tercepat: deps sudah pasti siap
bash /app/scripts/bootstrap.sh --reseed        # bangun ulang data seed
bash /app/scripts/bootstrap.sh --force-deps    # paksa install ulang deps
bash /app/scripts/bootstrap.sh --skip-seed     # tanpa seeding
```

## Kredensial (setelah seed)
- Admin: `admin@garment.com` / `Admin@123` (rate-limit login 10/60dtk → login sekali, reuse token).
- Role (password `Dewi@123`): `hr@ / finance@ / spv@ / gudang@ / maklon@` `dewiaditya.id`.
- Navigasi modul di UI: login → `window.location.hash='<module-id>'` → reload. Hub → klik tab.

## Troubleshooting cepat
- Backend tak healthy → `tail -50 /var/log/supervisor/backend.err.log` (paling sering: `JWT_SECRET` kosong → jalankan ulang bootstrap; ia auto-generate).
- Frontend belum compile → tunggu ~20s, `tail -20 /var/log/supervisor/frontend.out.log`.
- LLM error → `EMERGENT_LLM_KEY` kosong; jalankan ulang dgn key.

> Baca berikutnya: `HANDOFF_NEXT_AGENT.md` → `SSOT_MASTER_REPAIR_PLAN_PART5.md` → `FLOW_UX_AUDIT.md` → `memory/FINAL_REPAIR_LOG.md`.
