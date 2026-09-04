#!/usr/bin/env python3
"""
Backend test untuk FASE 4 — REKAP MINGGUAN CMT.

PRIORITAS TERTINGGI: Invarian konsistensi harian↔mingguan.
Angka per_day[] di weekly-recap HARUS SAMA PERSIS dengan daily-recap tanggal itu.
Ini adalah dasar tagihan CMT — selisih apa pun = BUG PRIORITAS TERTINGGI.
"""
import sys
import requests
from datetime import date, datetime, timedelta, timezone

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"

# ─────────────────────────────────────────────────────────────────────────────
# TANGGAL DINAMIS (perbaikan main agent, 2026-08-10)
# ─────────────────────────────────────────────────────────────────────────────
# Versi pertama berkas ini menyematkan tanggal MATI (`date=2026-08-08`,
# `future="2026-08-12"`). Dua akibatnya, keduanya berbahaya:
#
#   1. **Rusak besok.** Uji "tanggal masa depan" mengasumsikan 2026-08-12 =
#      hari ini + 2; sehari kemudian asumsinya salah dan gate ini MERAH tanpa ada
#      yang rusak di aplikasi (false alarm yang membuat orang berhenti percaya).
#   2. **LULUS KOSONG.** Uji `remind_pending` memakai jendela yang berakhir
#      2026-08-08 — tanggal yang di data demo NOL vendor merah. Jadi ia
#      membandingkan himpunan kosong dengan himpunan kosong dan mencetak "PASS
#      (0 vendors)": pemeriksaan termahal di berkas ini sebenarnya tidak pernah
#      memeriksa apa pun.
#
# Karena itu semua tanggal sekarang dihitung dari HARI INI menurut **WIB**
# (backend memakai batas hari WIB, jam container UTC — beda 7 jam), dan
# pemeriksaan `remind_pending` memakai jendela BERJALAN supaya datanya tidak kosong.
WIB = timezone(timedelta(hours=7))


def today_wib() -> date:
    return datetime.now(WIB).date()


TODAY = today_wib()
ANCHOR_S = TODAY.isoformat()                            # jendela BERJALAN (ada data)
PAST_ANCHOR = TODAY - timedelta(days=2)                 # untuk uji "geser jendela"
PAST_ANCHOR_S = PAST_ANCHOR.isoformat()
PAST_START_S = (PAST_ANCHOR - timedelta(days=6)).isoformat()
FUTURE_S = (TODAY + timedelta(days=2)).isoformat()

# Login SEKALI dan pakai ulang token (rate-limit 10/60 detik)
TOKEN = None

def login():
    global TOKEN
    if TOKEN:
        return TOKEN
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123"
    })
    if res.status_code != 200:
        print(f"❌ Login failed: {res.status_code} {res.text}")
        sys.exit(1)
    TOKEN = res.json().get("token")
    print(f"✅ Logged in as admin@garment.com")
    return TOKEN

def headers():
    return {"Authorization": f"Bearer {login()}"}

def test_weekly_default():
    """Test 1: GET /weekly-recap tanpa parameter"""
    print("\n🔍 Test 1: GET /weekly-recap (default = 7 hari terakhir)")
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    # Harus ada 7 hari
    assert len(data.get("days", [])) == 7, f"Expected 7 days, got {len(data.get('days', []))}"
    assert len(data.get("per_day", [])) == 7, f"Expected 7 per_day, got {len(data.get('per_day', []))}"
    
    # is_current harus true (default = hari ini)
    assert data.get("is_current") == True, "Expected is_current=true for default"
    
    # start harus = end - 6 hari
    start = data.get("start")
    end = data.get("end")
    assert start and end, "Missing start or end"
    
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    assert (end_date - start_date).days == 6, f"Expected 6 days between start and end, got {(end_date - start_date).days}"
    
    # days[] harus urut naik tanpa bolong
    days = data.get("days", [])
    for i in range(len(days) - 1):
        d1 = date.fromisoformat(days[i]["date"])
        d2 = date.fromisoformat(days[i+1]["date"])
        assert (d2 - d1).days == 1, f"Gap in days: {days[i]['date']} -> {days[i+1]['date']}"
    
    # rows harus berisi SEMUA vendor CMT aktif
    rows = data.get("rows", [])
    assert len(rows) > 0, "Expected at least 1 vendor"
    
    print(f"✅ PASS: {len(days)} days, {len(rows)} vendors, start={start}, end={end}, is_current={data.get('is_current')}")
    return data

def test_weekly_with_date():
    """Test 2: GET /weekly-recap?date=YYYY-MM-DD (jendela DIGESER ke masa lampau)"""
    print(f"\n🔍 Test 2: GET /weekly-recap?date={PAST_ANCHOR_S} (jendela lampau)")
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={PAST_ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()

    # `?date=` adalah hari TERAKHIR jendela
    assert data.get("end") == PAST_ANCHOR_S, f"Expected end={PAST_ANCHOR_S}, got {data.get('end')}"

    # start harus = end - 6 hari (7 hari BERGULIR)
    assert data.get("start") == PAST_START_S, f"Expected start={PAST_START_S}, got {data.get('start')}"

    # is_current harus false (jendelanya tidak berakhir hari ini)
    assert data.get("is_current") is False, "Expected is_current=false for past window"

    print(f"✅ PASS: date={PAST_ANCHOR_S}, start={data.get('start')}, end={data.get('end')}, is_current={data.get('is_current')}")
    return data

def test_weekly_with_days():
    """Test 3: GET /weekly-recap?days=3"""
    print("\n🔍 Test 3: GET /weekly-recap?days=3")
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?days=3", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    # Harus ada 3 hari
    assert len(data.get("days", [])) == 3, f"Expected 3 days, got {len(data.get('days', []))}"
    assert len(data.get("per_day", [])) == 3, f"Expected 3 per_day, got {len(data.get('per_day', []))}"
    
    print(f"✅ PASS: days=3, got {len(data.get('days', []))} days")
    return data

def test_weekly_validation():
    """Test 4: Validasi parameter"""
    print("\n🔍 Test 4: Validasi parameter")
    
    # days=0 -> 400
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?days=0", headers=headers())
    assert res.status_code == 400, f"Expected 400 for days=0, got {res.status_code}"
    print("✅ PASS: days=0 -> 400")
    
    # days=99 -> 400
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?days=99", headers=headers())
    assert res.status_code == 400, f"Expected 400 for days=99, got {res.status_code}"
    print("✅ PASS: days=99 -> 400")
    
    # days=abc -> 400
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?days=abc", headers=headers())
    assert res.status_code == 400, f"Expected 400 for days=abc, got {res.status_code}"
    print("✅ PASS: days=abc -> 400")
    
    # date=08-2026 (format salah) -> 400
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date=08-2026", headers=headers())
    assert res.status_code == 400, f"Expected 400 for date=08-2026, got {res.status_code}"
    print("✅ PASS: date=08-2026 -> 400")

def test_weekly_future():
    """Test 5: Tanggal masa depan — hari yang belum terjadi tidak boleh dihitung"""
    print(f"\n🔍 Test 5: Tanggal masa depan ({FUTURE_S} = hari ini WIB + 2)")

    # Dihitung dari hari ini WIB (bukan disematkan), supaya uji ini tetap benar besok.
    future = FUTURE_S
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={future}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()

    # 2 hari terakhir harus is_future=true
    days = data.get("days", [])
    future_count = sum(1 for d in days if d.get("is_future") is True)
    assert future_count == 2, f"Expected 2 future days, got {future_count} (days: {[d.get('date') for d in days]})"

    # dan yang ditandai future memang harus tanggal SETELAH hari ini
    for d in days:
        if d.get("is_future"):
            assert d.get("date") > TODAY.isoformat(), f"is_future tapi tanggalnya tidak di masa depan: {d.get('date')}"

    # per_day untuk hari future harus qty=0
    per_day = data.get("per_day", [])
    for pd in per_day:
        if pd.get("is_future"):
            assert pd.get("qty_progress") == 0, "Future day should have qty_progress=0"
            assert pd.get("qty_shipped") == 0, "Future day should have qty_shipped=0"

    # summary.days_elapsed harus = 7 - 2 = 5 (hari future TIDAK dihitung)
    assert data.get("summary", {}).get("days_elapsed") == 5, f"Expected days_elapsed=5, got {data.get('summary', {}).get('days_elapsed')}"

    print(f"✅ PASS: {future_count} future days, days_elapsed={data.get('summary', {}).get('days_elapsed')}")

def test_weekly_consistency():
    """Test 6: Konsistensi angka internal"""
    print("\n🔍 Test 6: Konsistensi angka internal")
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    summary = data.get("summary", {})
    per_day = data.get("per_day", [])
    rows = data.get("rows", [])
    
    # summary.qty_progress_total == jumlah per_day[].qty_progress
    expected_progress = sum(pd.get("qty_progress", 0) for pd in per_day)
    actual_progress = summary.get("qty_progress_total", 0)
    assert actual_progress == expected_progress, f"qty_progress_total mismatch: {actual_progress} != {expected_progress}"
    print(f"✅ PASS: qty_progress_total = {actual_progress}")
    
    # summary.qty_shipped_total == jumlah per_day[].qty_shipped
    expected_shipped = sum(pd.get("qty_shipped", 0) for pd in per_day)
    actual_shipped = summary.get("qty_shipped_total", 0)
    assert actual_shipped == expected_shipped, f"qty_shipped_total mismatch: {actual_shipped} != {expected_shipped}"
    print(f"✅ PASS: qty_shipped_total = {actual_shipped}")
    
    # summary.days_late_total == jumlah rows[].days_late
    expected_late = sum(r.get("days_late", 0) for r in rows)
    actual_late = summary.get("days_late_total", 0)
    assert actual_late == expected_late, f"days_late_total mismatch: {actual_late} != {expected_late}"
    print(f"✅ PASS: days_late_total = {actual_late}")
    
    # summary.vendors_total == panjang rows
    assert summary.get("vendors_total") == len(rows), f"vendors_total mismatch: {summary.get('vendors_total')} != {len(rows)}"
    print(f"✅ PASS: vendors_total = {len(rows)}")

def test_critical_invariant():
    """Test 7: INVARIAN TERMAHAL — per_day[] HARUS SAMA dengan daily-recap"""
    print("\n🔍 Test 7: INVARIAN TERMAHAL — konsistensi harian↔mingguan")
    
    # Ambil weekly-recap untuk jendela BERJALAN (7 hari s/d hari ini WIB)
    res_week = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res_week.status_code == 200, f"Expected 200, got {res_week.status_code}"
    week_data = res_week.json()
    
    per_day = week_data.get("per_day", [])
    days = week_data.get("days", [])
    
    # Untuk SETIAP hari, bandingkan dengan daily-recap
    errors = []
    for i, pd in enumerate(per_day):
        if pd.get("is_future"):
            continue  # Skip hari future
        
        day_date = pd.get("date")
        print(f"  Checking {day_date}...")
        
        # Ambil daily-recap untuk tanggal ini
        res_daily = requests.get(f"{BASE_URL}/cmt-override/daily-recap?date={day_date}", headers=headers())
        assert res_daily.status_code == 200, f"Expected 200 for daily-recap, got {res_daily.status_code}"
        daily_data = res_daily.json()
        daily_summary = daily_data.get("summary", {})
        
        # Bandingkan angka
        checks = [
            ("vendors_pending", pd.get("vendors_pending"), daily_summary.get("vendors_pending")),
            ("vendors_partial", pd.get("vendors_partial"), daily_summary.get("vendors_partial")),
            ("vendors_done", pd.get("vendors_done"), daily_summary.get("vendors_done")),
            ("vendors_idle", pd.get("vendors_idle"), daily_summary.get("vendors_idle")),
            ("tasks_pending_total", pd.get("tasks_pending_total"), daily_summary.get("tasks_pending_total")),
            ("qty_progress", pd.get("qty_progress"), daily_summary.get("qty_progress_today")),
            ("qty_shipped", pd.get("qty_shipped"), daily_summary.get("qty_shipped_today")),
        ]
        
        for field, week_val, daily_val in checks:
            if week_val != daily_val:
                errors.append(f"{day_date} {field}: weekly={week_val} != daily={daily_val}")
    
    if errors:
        print("❌ CRITICAL BUG: Angka weekly-recap TIDAK SAMA dengan daily-recap!")
        for err in errors:
            print(f"  ❌ {err}")
        sys.exit(1)
    
    print(f"✅ PASS: Semua angka per_day[] SAMA PERSIS dengan daily-recap untuk {len([p for p in per_day if not p.get('is_future')])} hari")

def test_weekly_rows_consistency():
    """Test 8: Konsistensi rows[].cells[].state dengan daily-recap"""
    print("\n🔍 Test 8: Konsistensi rows[].cells[].state dengan daily-recap")
    
    res_week = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res_week.status_code == 200, f"Expected 200, got {res_week.status_code}"
    week_data = res_week.json()
    
    rows = week_data.get("rows", [])
    if not rows:
        print("⏭️  SKIP: No vendors")
        return
    
    # Ambil 1 vendor untuk uji
    vendor = rows[0]
    vendor_id = vendor.get("vendor_id")
    cells = vendor.get("cells", [])
    
    print(f"  Checking vendor {vendor.get('vendor_name')} ({vendor_id})...")
    
    errors = []
    for cell in cells:
        if cell.get("is_future"):
            continue
        
        day_date = cell.get("date")
        cell_state = cell.get("state")
        
        # Ambil daily-recap untuk tanggal ini
        res_daily = requests.get(f"{BASE_URL}/cmt-override/daily-recap?date={day_date}", headers=headers())
        assert res_daily.status_code == 200, f"Expected 200, got {res_daily.status_code}"
        daily_data = res_daily.json()
        
        # Cari baris vendor ini di daily-recap
        daily_rows = daily_data.get("rows", [])
        daily_vendor = next((r for r in daily_rows if r.get("vendor_id") == vendor_id), None)
        
        if not daily_vendor:
            errors.append(f"{day_date}: vendor {vendor_id} not found in daily-recap")
            continue
        
        daily_state = daily_vendor.get("status")
        
        if cell_state != daily_state:
            errors.append(f"{day_date}: cell.state={cell_state} != daily.status={daily_state}")
    
    if errors:
        print("❌ CRITICAL BUG: State cells[] TIDAK SAMA dengan daily-recap!")
        for err in errors:
            print(f"  ❌ {err}")
        sys.exit(1)
    
    print(f"✅ PASS: State cells[] SAMA dengan daily-recap untuk {len([c for c in cells if not c.get('is_future')])} hari")

def test_weekly_days_late_unfinished():
    """Test 9: Aturan days_late vs days_unfinished"""
    print("\n🔍 Test 9: Aturan days_late vs days_unfinished")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    rows = data.get("rows", [])
    errors = []
    
    for row in rows:
        vendor_name = row.get("vendor_name")
        cells = row.get("cells", [])
        days_late = row.get("days_late", 0)
        days_unfinished = row.get("days_unfinished", 0)
        
        # Hitung sendiri
        expected_late = sum(1 for c in cells if c.get("state") == "pending" and not c.get("is_future"))
        expected_unfinished = sum(1 for c in cells if c.get("state") in ("pending", "partial") and not c.get("is_future"))
        
        if days_late != expected_late:
            errors.append(f"{vendor_name}: days_late={days_late} != expected {expected_late}")
        
        if days_unfinished != expected_unfinished:
            errors.append(f"{vendor_name}: days_unfinished={days_unfinished} != expected {expected_unfinished}")
    
    if errors:
        print("❌ BUG: days_late/days_unfinished tidak sesuai aturan!")
        for err in errors:
            print(f"  ❌ {err}")
        sys.exit(1)
    
    print(f"✅ PASS: days_late dan days_unfinished sesuai aturan untuk {len(rows)} vendors")

def test_weekly_days_no_progress():
    """Test 10: Aturan days_no_progress"""
    print("\n🔍 Test 10: Aturan days_no_progress")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    rows = data.get("rows", [])
    errors = []
    
    for row in rows:
        vendor_name = row.get("vendor_name")
        cells = row.get("cells", [])
        days_no_progress = row.get("days_no_progress", 0)
        days_with_work = row.get("days_with_work", 0)
        
        # Hitung sendiri: hari dengan progress_state != 'none' DAN progress_done == 0
        expected_no_progress = sum(1 for c in cells 
                                   if not c.get("is_future") 
                                   and c.get("progress_state") != "none" 
                                   and c.get("progress_done", 0) == 0)
        
        if days_no_progress != expected_no_progress:
            errors.append(f"{vendor_name}: days_no_progress={days_no_progress} != expected {expected_no_progress}")
        
        # Vendor yang days_with_work == 0 HARUS punya days_no_progress == 0
        if days_with_work == 0 and days_no_progress != 0:
            errors.append(f"{vendor_name}: days_with_work=0 but days_no_progress={days_no_progress} (should be 0)")
    
    if errors:
        print("❌ BUG: days_no_progress tidak sesuai aturan!")
        for err in errors:
            print(f"  ❌ {err}")
        sys.exit(1)
    
    print(f"✅ PASS: days_no_progress sesuai aturan untuk {len(rows)} vendors")

def test_weekly_streak():
    """Test 11: Aturan streak"""
    print("\n🔍 Test 11: Aturan streak")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    rows = data.get("rows", [])
    errors = []
    
    for row in rows:
        vendor_name = row.get("vendor_name")
        cells = row.get("cells", [])
        streak = row.get("streak", 0)
        streak_broken_by = row.get("streak_broken_by", "")
        
        # Hitung sendiri: mundur dari hari terakhir non-future
        real_cells = [c for c in cells if not c.get("is_future")]
        expected_streak = 0
        expected_broken = ""
        
        for c in reversed(real_cells):
            state = c.get("state")
            if state in ("pending", "partial"):
                expected_broken = state
                break
            elif state == "done":
                expected_streak += 1
            # 'idle' dilewati tanpa menambah
        
        if streak != expected_streak:
            errors.append(f"{vendor_name}: streak={streak} != expected {expected_streak}")
        
        if streak_broken_by != expected_broken:
            errors.append(f"{vendor_name}: streak_broken_by='{streak_broken_by}' != expected '{expected_broken}'")
    
    if errors:
        print("❌ BUG: streak tidak sesuai aturan!")
        for err in errors:
            print(f"  ❌ {err}")
        sys.exit(1)
    
    print(f"✅ PASS: streak sesuai aturan untuk {len(rows)} vendors")

def test_weekly_row_order():
    """Test 12: Urutan baris"""
    print("\n🔍 Test 12: Urutan baris")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    rows = data.get("rows", [])
    
    # Urutan: late -> unfinished -> clean -> idle
    # Di antara late, days_late menurun
    status_order = {"late": 0, "unfinished": 1, "clean": 2, "idle": 3}
    
    for i in range(len(rows) - 1):
        r1 = rows[i]
        r2 = rows[i+1]
        
        s1 = status_order.get(r1.get("status"), 99)
        s2 = status_order.get(r2.get("status"), 99)
        
        if s1 > s2:
            print(f"❌ BUG: Urutan salah: {r1.get('vendor_name')} ({r1.get('status')}) sebelum {r2.get('vendor_name')} ({r2.get('status')})")
            sys.exit(1)
        
        # Di antara yang 'late', days_late menurun
        if r1.get("status") == "late" and r2.get("status") == "late":
            if r1.get("days_late", 0) < r2.get("days_late", 0):
                print(f"❌ BUG: Urutan days_late salah: {r1.get('vendor_name')} ({r1.get('days_late')}) sebelum {r2.get('vendor_name')} ({r2.get('days_late')})")
                sys.exit(1)
    
    print(f"✅ PASS: Urutan baris benar untuk {len(rows)} vendors")

def test_weekly_remind_date():
    """Test 13: remind_date dan remind_pending"""
    print("\n🔍 Test 13: remind_date dan remind_pending")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    remind_date = data.get("remind_date")
    remind_pending = data.get("remind_pending", [])
    
    # remind_date harus = hari terakhir yang sudah berjalan
    days = data.get("days", [])
    last_real = None
    for d in reversed(days):
        if not d.get("is_future"):
            last_real = d.get("date")
            break
    
    assert remind_date == last_real, f"remind_date={remind_date} != last_real={last_real}"
    print(f"✅ PASS: remind_date = {remind_date}")
    
    # Bandingkan dengan daily-recap tanggal itu
    res_daily = requests.get(f"{BASE_URL}/cmt-override/daily-recap?date={remind_date}", headers=headers())
    assert res_daily.status_code == 200, f"Expected 200, got {res_daily.status_code}"
    daily_data = res_daily.json()
    
    daily_pending = [r.get("vendor_id") for r in daily_data.get("rows", []) if r.get("status") == "pending"]
    weekly_pending = [r.get("vendor_id") for r in remind_pending]
    
    # Harus SAMA PERSIS
    if set(daily_pending) != set(weekly_pending):
        print(f"❌ BUG: remind_pending tidak sama dengan daily-recap!")
        print(f"  Daily pending: {daily_pending}")
        print(f"  Weekly pending: {weekly_pending}")
        sys.exit(1)
    
    # ANTI "LULUS KOSONG": membandingkan dua himpunan kosong selalu sama, jadi
    # pemeriksaan ini tidak membuktikan apa pun kalau tidak ada vendor merah sama
    # sekali. Jendela yang dipakai = jendela BERJALAN, yang di data demo memang
    # punya vendor merah. Kalau suatu hari nol, katakan TERUS TERANG bahwa
    # pemeriksaannya lemah — jangan mencetak PASS yang menenangkan.
    if not weekly_pending:
        print("⚠️  PERHATIAN: tidak ada vendor 'pending' pada tanggal ini, jadi "
              "perbandingan sasaran reminder TIDAK menguji apa pun (lulus kosong). "
              "Pemeriksaan sesungguhnya ada di test_core_rekap_harian.py §13 dan "
              "gate INV-REKAP RK-21 yang membuat datanya sendiri.")
    else:
        print(f"✅ PASS: remind_pending SAMA dengan daily-recap ({len(weekly_pending)} vendors: "
              f"{[r.get('vendor_name') for r in remind_pending]})")

def test_weekly_export():
    """Test 14: Export xlsx dan pdf"""
    print("\n🔍 Test 14: Export xlsx dan pdf")
    
    # Excel
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap/export?format=xlsx&date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200 for xlsx, got {res.status_code}"
    
    # Cek signature PK (xlsx)
    content = res.content
    assert content[:2] == b'PK', "Excel file should start with PK signature"
    
    # Cek Content-Disposition — rentangnya diambil dari API (bukan disematkan),
    # supaya uji ini tetap benar pada hari apa pun.
    exp_start = (TODAY - timedelta(days=6)).isoformat().replace("-", "")
    exp_end = ANCHOR_S.replace("-", "")
    cd = res.headers.get("Content-Disposition", "")
    assert "rekap-mingguan-cmt-" in cd, f"Content-Disposition should contain 'rekap-mingguan-cmt-', got {cd}"
    assert exp_start in cd and exp_end in cd, \
        f"Filename should contain range {exp_start}-{exp_end}, got {cd}"
    
    print(f"✅ PASS: Excel export OK ({len(content)} bytes)")
    
    # PDF
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap/export?format=pdf&date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200 for pdf, got {res.status_code}"
    
    # Cek signature %PDF-
    content = res.content
    assert content[:5] == b'%PDF-', "PDF file should start with %PDF- signature"
    
    cd = res.headers.get("Content-Disposition", "")
    assert "rekap-mingguan-cmt-" in cd, f"Content-Disposition should contain 'rekap-mingguan-cmt-', got {cd}"
    
    print(f"✅ PASS: PDF export OK ({len(content)} bytes)")
    
    # format=csv -> 400
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap/export?format=csv&date={ANCHOR_S}", headers=headers())
    assert res.status_code == 400, f"Expected 400 for format=csv, got {res.status_code}"
    print("✅ PASS: format=csv -> 400")

def test_weekly_rbac():
    """Test 15: RBAC (403/401)"""
    print("\n🔍 Test 15: RBAC (403/401)")
    
    # hr@dewiaditya.id (role tidak berwenang) -> 403
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "hr@dewiaditya.id",
        "password": "Dewi@123"
    })
    assert res.status_code == 200, f"Login failed for hr@dewiaditya.id"
    hr_token = res.json().get("token")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap", headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 403, f"Expected 403 for hr role, got {res.status_code}"
    print("✅ PASS: hr@dewiaditya.id -> 403")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap/export?format=xlsx", headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 403, f"Expected 403 for hr role export, got {res.status_code}"
    print("✅ PASS: hr@dewiaditya.id export -> 403")
    
    # Tanpa token -> 401
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap")
    assert res.status_code == 401, f"Expected 401 without token, got {res.status_code}"
    print("✅ PASS: No token -> 401")
    
    # Akun vendor -> 403
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "cmtvendor@dewiaditya.id",
        "password": "Dewi@123"
    })
    assert res.status_code == 200, f"Login failed for cmtvendor@dewiaditya.id"
    vendor_token = res.json().get("token")
    
    res = requests.get(f"{BASE_URL}/cmt-override/weekly-recap", headers={"Authorization": f"Bearer {vendor_token}"})
    assert res.status_code == 403, f"Expected 403 for vendor role, got {res.status_code}"
    print("✅ PASS: cmtvendor@dewiaditya.id -> 403")

def test_weekly_header_ignored():
    """Test 16: Header X-CMT-Override-Vendor harus DIABAIKAN"""
    print("\n🔍 Test 16: Header X-CMT-Override-Vendor harus DIABAIKAN")
    
    # Tanpa header
    res1 = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=headers())
    assert res1.status_code == 200, f"Expected 200, got {res1.status_code}"
    data1 = res1.json()
    rows1 = len(data1.get("rows", []))
    
    # Dengan header (harus diabaikan)
    h = headers()
    h["X-CMT-Override-Vendor"] = "some-vendor-id"
    res2 = requests.get(f"{BASE_URL}/cmt-override/weekly-recap?date={ANCHOR_S}", headers=h)
    assert res2.status_code == 200, f"Expected 200, got {res2.status_code}"
    data2 = res2.json()
    rows2 = len(data2.get("rows", []))
    
    # Jumlah rows harus SAMA (header diabaikan)
    assert rows1 == rows2, f"Header X-CMT-Override-Vendor should be ignored: {rows1} != {rows2}"
    print(f"✅ PASS: Header X-CMT-Override-Vendor diabaikan ({rows1} vendors)")

def test_daily_recap_regression():
    """Test 17: Regresi daily-recap (fitur lama tetap bekerja)"""
    print("\n🔍 Test 17: Regresi daily-recap")
    
    # GET /daily-recap
    res = requests.get(f"{BASE_URL}/cmt-override/daily-recap?date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    # Harus ada 5 kolom tugas
    tasks = data.get("tasks", [])
    assert len(tasks) == 5, f"Expected 5 tasks, got {len(tasks)}"
    print(f"✅ PASS: daily-recap OK ({len(tasks)} tasks)")
    
    # Export xlsx
    res = requests.get(f"{BASE_URL}/cmt-override/daily-recap/export?format=xlsx&date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200 for daily xlsx, got {res.status_code}"
    assert res.content[:2] == b'PK', "Daily Excel should be valid"
    print("✅ PASS: daily-recap export xlsx OK")
    
    # Export pdf
    res = requests.get(f"{BASE_URL}/cmt-override/daily-recap/export?format=pdf&date={ANCHOR_S}", headers=headers())
    assert res.status_code == 200, f"Expected 200 for daily pdf, got {res.status_code}"
    assert res.content[:5] == b'%PDF-', "Daily PDF should be valid"
    print("✅ PASS: daily-recap export pdf OK")
    
    # RBAC
    res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "hr@dewiaditya.id",
        "password": "Dewi@123"
    })
    hr_token = res.json().get("token")
    
    res = requests.get(f"{BASE_URL}/cmt-override/daily-recap", headers={"Authorization": f"Bearer {hr_token}"})
    assert res.status_code == 403, f"Expected 403 for hr role, got {res.status_code}"
    print("✅ PASS: daily-recap RBAC 403 OK")

def main():
    print("=" * 80)
    print("BACKEND TEST — FASE 4 REKAP MINGGUAN CMT")
    print("=" * 80)
    
    try:
        test_weekly_default()
        test_weekly_with_date()
        test_weekly_with_days()
        test_weekly_validation()
        test_weekly_future()
        test_weekly_consistency()
        test_critical_invariant()  # PRIORITAS TERTINGGI
        test_weekly_rows_consistency()
        test_weekly_days_late_unfinished()
        test_weekly_days_no_progress()
        test_weekly_streak()
        test_weekly_row_order()
        test_weekly_remind_date()
        test_weekly_export()
        test_weekly_rbac()
        test_weekly_header_ignored()
        test_daily_recap_regression()
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED (17/17)")
        print("=" * 80)
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
