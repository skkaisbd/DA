#!/usr/bin/env bash
# Audit sesi #40 — hanya gate yang menyentuh Marketing + jurnal pencairan Finance.
cd /app
OUT=/app/.logs/audit_marketing_sesi40
mkdir -p "$OUT"
run() {
  name="$1"; shift
  echo "=== $name ==="
  ( eval "$@" ) >"$OUT/$name.log" 2>&1
  rc=$?
  if [ $rc -eq 0 ]; then echo "HIJAU $name"; else echo "MERAH($rc) $name"; fi
  echo "$name rc=$rc" >> "$OUT/_summary.txt"
}
: > "$OUT/_summary.txt"
run marketing_scope        "python3 scripts/verify_marketing_scope.py"
run marketing_cycle        "python3 scripts/verify_marketing_cycle.py"
run marketing_rbac_scope   "python3 test_core_f6_rbac_scope.py"
run katalog_stok           "python3 scripts/verify_katalog_stok.py"
run margin_katalog         "python3 scripts/verify_margin_katalog.py"
run pencairan_finance      "python3 scripts/verify_pencairan_finance.py"
run cogs_fifo_jurnal       "python3 scripts/verify_cogs_fifo_jurnal.py"
run impor_pintar_hpp       "python3 scripts/verify_biaya_jahit_hpp_batch_impor_pintar.py"
run kpi_konten             "python3 scripts/verify_kpi_konten_rapor_mingguan.py"
run dashboard_marketing    "python3 scripts/verify_fase_d_dashboard_marketing.py"
run sinkron_mkt_gudang     "python3 scripts/verify_sinkronisasi_marketing_gudang.py"
run retur_mkt_gudang       "python3 scripts/verify_jembatan_retur_marketing_gudang.py"
echo "SELESAI"
cat "$OUT/_summary.txt"
