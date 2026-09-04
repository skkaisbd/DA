#!/usr/bin/env python3
"""
AUDIT RUNTIME PORTAL MARKETING — panggil endpoint sungguhan, catat yang MATI.

Kenapa perlu: audit statis bisa bilang "route ada", tapi route yang ADA masih
bisa 500 karena membaca koleksi yang salah / field yang tidak pernah ditulis.
Fitur yang 500 = tombol yang tidak berfungsi di layar staf.

Pakai:
  python3 scripts/audit_marketing_runtime.py
  python3 scripts/audit_marketing_runtime.py --json /tmp/runtime.json
"""
import re
import sys
import json
import argparse
import urllib.request
import urllib.error

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}


def req(method, path, token=None, body=None, timeout=60):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, raw[:200].decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300].decode(errors="replace")
    except Exception as e:
        return -1, str(e)


def login():
    st, body = req("POST", "/api/auth/login", body=ADMIN)
    if st != 200:
        print(f"LOGIN GAGAL {st}: {body}")
        sys.exit(1)
    return body.get("access_token") or body.get("token")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--prefix", default="/api/marketing")
    args = ap.parse_args()

    token = login()
    st, spec = req("GET", "/api/openapi.json", token)
    if st != 200:
        print("openapi tidak bisa dibaca")
        sys.exit(1)

    # kumpulkan sample id dari endpoint list utama supaya path-param bisa diisi
    samples = {}
    for coll, path, key in [
        ("account_id", "/api/marketing/accounts", "id"),
        ("catalog_id", "/api/marketing/catalogs", "id"),
        ("creator_id", "/api/marketing/kol/creators", "id"),
        ("host_id", "/api/marketing/livehost/hosts", "id"),
    ]:
        s, b = req("GET", path, token)
        if s == 200:
            items = b if isinstance(b, list) else (b.get("items") or b.get("data") or b.get("accounts") or [])
            if items and isinstance(items, list) and isinstance(items[0], dict):
                samples[coll] = items[0].get(key) or items[0].get("_id")

    results = []
    paths = spec.get("paths", {})
    for path, item in sorted(paths.items()):
        if not path.startswith(args.prefix):
            continue
        for method, op in item.items():
            if method.lower() != "get":
                continue
            params = re.findall(r"\{([^}]+)\}", path)
            call = path
            skipped = False
            for p in params:
                val = samples.get(p)
                if val is None:
                    # coba nama generik
                    for k, v in samples.items():
                        if p.split("_")[0] in k:
                            val = v
                            break
                if val is None:
                    skipped = True
                    break
                call = call.replace("{" + p + "}", str(val))
            if skipped:
                results.append({"path": path, "status": "SKIP",
                                "note": f"param {params} tidak ada contoh id"})
                continue
            st, body = req("GET", call, token)
            note = ""
            if st >= 400 or st == -1:
                note = json.dumps(body)[:300] if not isinstance(body, str) else body[:300]
            results.append({"path": path, "call": call, "status": st, "note": note})

    bad = [r for r in results if isinstance(r["status"], int) and (r["status"] >= 400 or r["status"] == -1)]
    skip = [r for r in results if r["status"] == "SKIP"]
    ok = [r for r in results if isinstance(r["status"], int) and 200 <= r["status"] < 400]

    W = 78
    print("=" * W)
    print(f"AUDIT RUNTIME {args.prefix} (GET)")
    print("=" * W)
    print(f"OK={len(ok)}  GAGAL={len(bad)}  SKIP={len(skip)}")
    print("\n--- GAGAL (fitur mati di layar) ---")
    for r in bad:
        print(f"  [{r['status']}] {r['call']}")
        if r["note"]:
            print(f"        {r['note']}")
    print("\n--- SKIP (tak ada contoh id; perlu data seed) ---")
    for r in skip[:40]:
        print(f"  {r['path']}  ({r['note']})")
    if len(skip) > 40:
        print(f"  ... {len(skip)-40} lagi")

    if args.json_out:
        json.dump(results, open(args.json_out, "w"), indent=2, ensure_ascii=False)
        print(f"\nJSON -> {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
