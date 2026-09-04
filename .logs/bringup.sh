#!/usr/bin/env bash
# Bring-up lanjutan sesudah container restart: seed inti + seed marketing demo.
# Dijalankan di background; log: /app/.logs/bringup.log
set -uo pipefail
export EMERGENT_LLM_KEY="${EMERGENT_LLM_KEY:-}"
echo "=== [1] bootstrap --skip-deps ($(date)) ==="
bash /app/scripts/bootstrap.sh --skip-deps
echo "=== [2] seed marketing real accounts ($(date)) ==="
(cd /app/backend && python3 scripts/seed_marketing_real_accounts.py --apply)
echo "=== [3] seed internal variants + katalog order demo ($(date)) ==="
(cd /app && python3 scripts/seed_internal_variants.py)
(cd /app && python3 scripts/seed_katalog_order_demo.py)
echo "=== [4] seed marketing cycle demo ($(date)) ==="
(cd /app && python3 scripts/seed_marketing_cycle_demo.py)
echo "=== [5] seed marketing content demo ($(date)) ==="
(cd /app && python3 scripts/seed_marketing_content_demo.py) || echo "(content demo skip/gagal)"
echo "=== SELESAI ($(date)) ==="
