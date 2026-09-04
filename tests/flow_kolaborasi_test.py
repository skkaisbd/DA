"""
E2E API-level POC test — Alur Kolaborasi Internal (Portal Kolaborasi).

Cakupan happy-path (SSOT: comm_channels / comm_messages / comm_conversations /
comm_read_receipts + announcements):
  login (admin=A) + buat user kedua (B, role operator) + login B
  -> buat channel (public, member A+B)                    [POST /api/comm/channels]
  -> list + detail + update channel                        [GET/PUT /api/comm/channels...]
  -> tambah & lihat member                                 [POST/GET /api/comm/channels/{id}/members]
  -> kirim pesan channel                                   [POST /api/comm/channels/{id}/messages]
  -> list pesan channel                                    [GET  /api/comm/channels/{id}/messages]
  -> balas thread + baca thread                            [POST/GET /api/comm/messages/{id}/thread...]
  -> reaksi emoji                                          [POST /api/comm/messages/{id}/reaction]
  -> edit pesan                                            [PATCH /api/comm/messages/{id}]
  -> pin + daftar pinned + unpin                           [POST/GET/DELETE .../pin, .../pinned]
  -> DM: kirim + list percakapan + riwayat                 [POST/GET /api/comm/conversations...]
  -> unread + mark read                                    [GET /api/comm/unread, POST /api/comm/read/{ref}]
  -> pencarian pesan + online users                        [GET /api/comm/search, /api/comm/online-users]
  -> pengumuman: buat + aktif + all + detail + toggle      [POST/GET /api/announcements...]
Guards:
  -> channel tanpa nama ditolak (400)
  -> pesan kosong ditolak (400)
  -> reaksi tanpa emoji ditolak (400)
  -> reply pada thread-reply ditolak (400)
  -> edit pesan oleh non-pemilik ditolak (403)
  -> update channel oleh non-creator/non-admin ditolak (403)
  -> pengumuman dibuat oleh non-HR ditolak (403)
Self-cleanup (hard): channel + pesan + percakapan + read-receipt + pengumuman + user B.
"""
import sys
import uuid
import requests

BASE = "http://localhost:8001"
A = requests.Session()     # admin / superadmin (creator + HR-capable)
B = requests.Session()     # operator (non-owner / non-HR)

st = {"chan": None, "conv": None, "msg": None, "reply": None,
      "ann": None, "user_b": None, "user_a": None,
      "email_b": f"e2e.kolab.{uuid.uuid4().hex[:8]}@dewiaditya.id"}


def _mongo():
    url = db = None
    with open("/app/backend/.env") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("MONGO_URL="):
                url = ln.split("=", 1)[1].strip().strip('"').strip("'")
            elif ln.startswith("DB_NAME="):
                db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    from pymongo import MongoClient
    cli = MongoClient(url)
    return cli, cli[db or "test_database"]


def login_admin():
    r = A.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    body = r.json()
    st["user_a"] = body["user"]["id"]
    A.headers.update({"Authorization": f"Bearer {body['token']}", "Content-Type": "application/json"})
    print("PASS login admin (A)")


def make_user_b():
    """Buat user kedua (role operator) langsung di DB lalu login via API."""
    sys.path.insert(0, "/app/backend")
    from auth import hash_password  # noqa
    cli, db = _mongo()
    uid = str(uuid.uuid4())
    db.users.insert_one({
        "id": uid, "name": "E2E Kolaborasi Operator", "email": st["email_b"],
        "password": hash_password("Kolab@123"), "role": "operator", "status": "active",
    })
    cli.close()
    st["user_b"] = uid
    r = B.post(f"{BASE}/api/auth/login", json={"email": st["email_b"], "password": "Kolab@123"})
    assert r.status_code == 200, f"login B: {r.status_code} {r.text}"
    B.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS buat + login user B (operator)")


def main():
    login_admin()
    make_user_b()

    # ── Guard: channel tanpa nama ──────────────────────────────────────────
    rg = A.post(f"{BASE}/api/comm/channels", json={"name": "  "})
    assert rg.status_code == 400, f"expect 400 channel tanpa nama, got {rg.status_code}"
    print("PASS guard: channel tanpa nama ditolak (400)")

    # ── Fase 1: buat channel ───────────────────────────────────────────────
    r = A.post(f"{BASE}/api/comm/channels", json={
        "name": "E2E Kolaborasi Channel", "type": "public",
        "description": "Channel uji kolaborasi", "members": [st["user_b"]],
    })
    assert r.status_code == 200, f"create channel {r.status_code}: {r.text}"
    ch = r.json()
    st["chan"] = ch["id"]
    assert ch["type"] == "public" and st["user_a"] in ch["members"] and st["user_b"] in ch["members"], f"channel body {ch}"
    print(f"PASS buat channel id={ch['id'][:8]} (2 member)")

    # ── Fase 2: list + detail + update ─────────────────────────────────────
    lst = A.get(f"{BASE}/api/comm/channels").json()
    assert any(c["id"] == st["chan"] for c in lst), "channel tidak muncul di list"
    assert all("unread_count" in c for c in lst), "unread_count tidak ada"
    print(f"PASS list channels ({len(lst)}) + unread_count")

    det = A.get(f"{BASE}/api/comm/channels/{st['chan']}").json()
    assert det["id"] == st["chan"], "detail channel salah"
    print("PASS detail channel")

    up = A.put(f"{BASE}/api/comm/channels/{st['chan']}", json={"description": "Deskripsi diperbarui"})
    assert up.status_code == 200 and up.json().get("description") == "Deskripsi diperbarui", f"update channel {up.text}"
    print("PASS update channel (deskripsi persisted)")

    # ── Guard: update channel oleh non-creator/non-admin (B) ───────────────
    rg = B.put(f"{BASE}/api/comm/channels/{st['chan']}", json={"name": "Coba Rebut"})
    assert rg.status_code == 403, f"expect 403 update by non-creator, got {rg.status_code}"
    print("PASS guard: update channel oleh non-creator ditolak (403)")

    # ── Fase 3: members ────────────────────────────────────────────────────
    mem = A.get(f"{BASE}/api/comm/channels/{st['chan']}/members").json()
    assert len(mem["members"]) >= 2, f"members {mem}"
    print(f"PASS lihat member ({len(mem['members'])})")

    # ── Fase 4: kirim pesan channel ────────────────────────────────────────
    rg = A.post(f"{BASE}/api/comm/channels/{st['chan']}/messages", json={"content": "   "})
    assert rg.status_code == 400, f"expect 400 pesan kosong, got {rg.status_code}"
    print("PASS guard: pesan kosong ditolak (400)")

    r = A.post(f"{BASE}/api/comm/channels/{st['chan']}/messages",
               json={"content": "Halo tim, briefing produksi jam 9 pagi ya."})
    assert r.status_code == 200, f"send msg {r.status_code}: {r.text}"
    st["msg"] = r.json()["id"]
    print(f"PASS kirim pesan channel id={st['msg'][:8]}")

    msgs = A.get(f"{BASE}/api/comm/channels/{st['chan']}/messages").json()
    assert any(m["id"] == st["msg"] for m in msgs), "pesan tidak muncul di feed"
    print(f"PASS list pesan channel ({len(msgs)})")

    # ── Fase 5: thread reply + baca thread ─────────────────────────────────
    r = B.post(f"{BASE}/api/comm/messages/{st['msg']}/thread/reply",
               json={"content": "Siap, saya hadir."})
    assert r.status_code == 200, f"thread reply {r.status_code}: {r.text}"
    st["reply"] = r.json()["id"]
    th = A.get(f"{BASE}/api/comm/messages/{st['msg']}/thread").json()
    assert th["reply_count"] == 1 and th["root"]["id"] == st["msg"], f"thread {th}"
    print("PASS balas thread + baca thread (reply_count=1)")

    # ── Guard: reply pada thread-reply ─────────────────────────────────────
    rg = A.post(f"{BASE}/api/comm/messages/{st['reply']}/thread/reply", json={"content": "x"})
    assert rg.status_code == 400, f"expect 400 reply-on-reply, got {rg.status_code}"
    print("PASS guard: reply pada thread-reply ditolak (400)")

    # ── Fase 6: reaksi ─────────────────────────────────────────────────────
    rg = A.post(f"{BASE}/api/comm/messages/{st['msg']}/reaction", json={"emoji": ""})
    assert rg.status_code == 400, f"expect 400 reaksi tanpa emoji, got {rg.status_code}"
    print("PASS guard: reaksi tanpa emoji ditolak (400)")

    r = B.post(f"{BASE}/api/comm/messages/{st['msg']}/reaction", json={"emoji": "👍"})
    assert r.status_code == 200 and "👍" in r.json()["reactions"], f"reaction {r.text}"
    print("PASS reaksi emoji 👍")

    # ── Fase 7: edit pesan (+ guard non-pemilik) ───────────────────────────
    rg = B.patch(f"{BASE}/api/comm/messages/{st['msg']}", json={"content": "diretas"})
    assert rg.status_code == 403, f"expect 403 edit non-owner, got {rg.status_code}"
    print("PASS guard: edit pesan oleh non-pemilik ditolak (403)")

    r = A.patch(f"{BASE}/api/comm/messages/{st['msg']}", json={"content": "Halo tim, briefing jam 09.30 (revisi)."})
    assert r.status_code == 200 and r.json().get("edited") is True, f"edit {r.text}"
    print("PASS edit pesan (edited=true)")

    # ── Fase 8: pin + pinned + unpin ───────────────────────────────────────
    assert A.post(f"{BASE}/api/comm/messages/{st['msg']}/pin").status_code == 200, "pin gagal"
    pinned = A.get(f"{BASE}/api/comm/channels/{st['chan']}/pinned").json()
    assert any(m["id"] == st["msg"] for m in pinned), "pesan tidak ter-pin"
    assert A.delete(f"{BASE}/api/comm/messages/{st['msg']}/pin").status_code == 200, "unpin gagal"
    print("PASS pin → pinned list → unpin")

    # ── Fase 9: DM (direct message) ────────────────────────────────────────
    r = A.post(f"{BASE}/api/comm/conversations/{st['user_b']}/messages",
               json={"content": "Halo, tolong update stok kain hari ini."})
    assert r.status_code == 200, f"send DM {r.status_code}: {r.text}"
    st["conv"] = r.json()["conversation_id"]
    convs = A.get(f"{BASE}/api/comm/conversations").json()
    assert any(c["id"] == st["conv"] for c in convs), "conversation tidak muncul"
    dm_hist = B.get(f"{BASE}/api/comm/conversations/{st['user_a']}/messages").json()
    assert any(m["conversation_id"] == st["conv"] for m in dm_hist), "riwayat DM kosong di sisi B"
    print("PASS DM kirim + list percakapan + riwayat (2 arah)")

    # ── Fase 10: unread + mark read ────────────────────────────────────────
    unread_b = B.get(f"{BASE}/api/comm/unread").json()
    assert st["conv"] in unread_b["dms"], f"unread B tidak memuat conv: {unread_b}"
    assert B.post(f"{BASE}/api/comm/read/{st['conv']}").status_code == 200, "mark read gagal"
    unread_b2 = B.get(f"{BASE}/api/comm/unread").json()
    assert unread_b2["dms"].get(st["conv"], 0) == 0, f"unread belum 0 setelah read: {unread_b2}"
    print("PASS unread → mark read → unread=0")

    # ── Fase 11: search + online users ─────────────────────────────────────
    sr = A.get(f"{BASE}/api/comm/search", params={"q": "briefing"}).json()
    assert any(m["id"] == st["msg"] for m in sr), "search tidak menemukan pesan"
    ou = A.get(f"{BASE}/api/comm/online-users")
    assert ou.status_code == 200 and "online_user_ids" in ou.json(), f"online-users {ou.text}"
    print("PASS pencarian pesan + online users")

    # ── Fase 12: pengumuman (announcement) ─────────────────────────────────
    rg = B.post(f"{BASE}/api/announcements/", json={"title": "E2E Kolaborasi Coba", "content": "x"})
    assert rg.status_code == 403, f"expect 403 announcement by non-HR, got {rg.status_code}"
    print("PASS guard: pengumuman oleh non-HR ditolak (403)")

    r = A.post(f"{BASE}/api/announcements/", json={
        "title": "E2E Kolaborasi Pengumuman", "content": "Rapat mingguan Senin 08.00.",
        "type": "info", "priority": 5, "target_portals": ["all"], "is_active": True,
    })
    assert r.status_code in (200, 201), f"create announcement {r.status_code}: {r.text}"
    st["ann"] = r.json()["id"]
    active = A.get(f"{BASE}/api/announcements/active").json()
    assert any(a["id"] == st["ann"] for a in active), "pengumuman tidak aktif"
    allx = A.get(f"{BASE}/api/announcements/all").json()
    assert any(a["id"] == st["ann"] for a in allx), "pengumuman tidak muncul di /all"
    det = A.get(f"{BASE}/api/announcements/{st['ann']}").json()
    assert det["id"] == st["ann"], "detail pengumuman salah"
    tog = A.post(f"{BASE}/api/announcements/{st['ann']}/toggle").json()
    assert tog["is_active"] is False, f"toggle {tog}"
    print("PASS pengumuman: buat(201) → active → all → detail → toggle(nonaktif)")

    print("\n=== KOLABORASI FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        n_m = db.comm_messages.delete_many({"$or": [
            {"channel_id": st["chan"]}, {"conversation_id": st["conv"]},
        ]}).deleted_count if (st["chan"] or st["conv"]) else 0
        n_c = db.comm_channels.delete_many({"$or": [
            {"id": st["chan"]}, {"name": "E2E Kolaborasi Channel"},
        ]}).deleted_count
        n_v = db.comm_conversations.delete_many({"id": st["conv"]}).deleted_count if st["conv"] else 0
        refs = [x for x in [st["chan"], st["conv"]] if x]
        n_r = db.comm_read_receipts.delete_many({"ref_id": {"$in": refs}}).deleted_count if refs else 0
        n_a = db.announcements.delete_many({"title": {"$regex": "E2E Kolaborasi"}}).deleted_count
        n_u = db.users.delete_many({"$or": [
            {"id": st["user_b"]}, {"email": st["email_b"]},
        ]}).deleted_count if st["user_b"] else 0
        cli.close()
        print(f"CLEANUP: {n_c} channel + {n_m} pesan + {n_v} percakapan + {n_r} receipt + "
              f"{n_a} pengumuman + {n_u} user dihapus (DB pristine)")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
