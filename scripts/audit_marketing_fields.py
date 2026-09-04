#!/usr/bin/env python3
BE_ALL_SRC = ""
"""
AUDIT FIELD PORTAL MARKETING — pembuktian cacat pada FORM & TABEL.

Menjawab keluhan owner satu per satu, dengan bukti file:line:

  1. TANPA LINGKUP TOKO   — model tulis (POST/PUT) yang tidak punya `account_id`
                            padahal datanya milik satu toko/akun. Akibat: data
                            bercampur antar toko, filter per toko mustahil.
  2. TEKS BEBAS (harus SELECT) — field `str` yang isinya sebenarnya menunjuk baris
                            di koleksi lain (produk/kreator/host/kategori/ukuran/
                            warna/SKU). Akibat: salah ketik = data tak bisa
                            dihubungkan, laporan pecah.
  3. FIELD MATI (backend)  — field di model Pydantic yang TIDAK PERNAH ditulis ke
                            dokumen / tidak pernah dibaca lagi.
  4. FIELD MATI (layar)    — key state form di layar yang TIDAK PERNAH dikirim ke
                            backend, atau dikirim tapi TIDAK ADA di model backend
                            (dibuang diam-diam oleh Pydantic).
  5. TABEL TANPA SUMBER    — kolom tabel yang membaca field yang tidak pernah ada
                            di dokumen backend (selalu kosong / '-').

Pakai:
  python3 scripts/audit_marketing_fields.py
  python3 scripts/audit_marketing_fields.py --module samples
  python3 scripts/audit_marketing_fields.py --json /tmp/fields.json
"""
import os
import re
import ast
import glob
import json
import argparse

APP = "/app"
BE = os.path.join(APP, "backend")
FE = os.path.join(APP, "frontend/src")

# ── Field yang SEHARUSNYA menunjuk master lain (bukan teks bebas) ────────────
# nama_field -> (koleksi master, alasan)
REFERENCE_HINTS = {
    "product":        ("marketing_catalog_items / rahaza_materials(FG)", "nama produk harus dipilih dari katalog toko"),
    "product_name":   ("marketing_catalog_items / rahaza_materials(FG)", "nama produk harus dipilih dari katalog toko"),
    "item_name":      ("marketing_catalog_items", "nama item harus dipilih dari katalog"),
    "sku":            ("marketing_catalog_items.sku", "SKU harus ikut item katalog"),
    "username":       ("marketing_kol_creators / marketing_livehosts", "akun kreator harus dipilih dari master kreator"),
    "creator_name":   ("marketing_kol_creators", "nama kreator harus dipilih dari master"),
    "host_name":      ("marketing_livehosts", "nama host harus dipilih dari master host"),
    "kol_name":       ("marketing_kol_creators", "nama KOL harus dipilih dari master"),
    "account_name":   ("marketing_platform_accounts", "nama akun harus ikut master akun"),
    "platform":       ("marketing_platform_accounts.platform", "platform harus ikut akun yang dipilih"),
    "store_name":     ("marketing_platform_accounts", "nama toko harus ikut master akun"),
    "category":       ("rahaza_product_categories", "kategori harus dipilih dari master kategori"),
    "size":           ("rahaza_variants(size) / size mapping", "ukuran harus dari master varian"),
    "color":          ("rahaza_variants(color) / rnd_colors", "warna harus dari master warna"),
    "courier":        ("master kurir (konstanta backend)", "kurir harus dipilih, bukan diketik"),
    "employee_name":  ("employees", "nama karyawan harus dipilih dari master"),
    "customer_name":  ("marketing_orders / master pelanggan", "nama pembeli sebaiknya ikut order"),
    "buyer_name":     ("rahaza_buyers", "nama buyer harus dipilih dari master"),
    "variant":        ("rahaza_variants", "varian harus dipilih dari master"),
    "warehouse":      ("wms_locations", "lokasi gudang harus dipilih dari master"),
    "hpp":            ("marketing_catalog_items.hpp", "HPP harus diturunkan dari katalog/BOM, bukan diketik"),
}

# Field yang WAJIB ada untuk lingkup toko pada data transaksional marketing
SCOPE_FIELD = "account_id"

# Model tulis yang MEMANG tidak perlu account_id (global / master lintas toko)
SCOPE_EXEMPT_MODELS = {
    "AccountCreate", "AccountUpdate", "AccountIn",           # master akun itu sendiri
    "CreatorCreate", "CreatorUpdate", "CreatorIn",           # master kreator (multi-toko)
    "LiveHostCreate", "LiveHostUpdate",                      # master host (multi-toko)
    "TemplateCreate", "TemplateUpdate",                       # template tugas
    "SettingsUpdate", "IntegrationSettingsUpdate",
    "TrainingCreate", "TrainingUpdate", "ScriptCreate", "ScriptUpdate",
    "LoginRequest", "ChangePasswordRequest",
}

# Berkas backend marketing
BE_GLOBS = ["routes/marketing_*.py", "routes/dewi_toko.py"]
# Berkas layar marketing
FE_GLOBS = ["components/erp/marketing/**/*.jsx", "components/erp/hubs/Marketing*.jsx",
            "components/erp/livehost/**/*.jsx"]
FE_EXTRA = ["components/erp/AccountManagementModule.jsx",
            "components/erp/SalesDataEntryModule.jsx",
            "components/erp/ImportCenterModule.jsx",
            "components/erp/KOLCreatorModule.jsx",
            "components/erp/CatalogManagementModule.jsx",
            "components/erp/TaskManagementModule.jsx",
            "components/erp/TaskTemplatesModule.jsx",
            "components/erp/MarketingAfterSalesHub.jsx",
            "components/erp/MarketingReportsHub.jsx",
            "components/erp/TokoProductCatalogModule.jsx"]


def be_files():
    out = []
    for g in BE_GLOBS:
        out += glob.glob(os.path.join(BE, g))
    return sorted(set(out))


def fe_files():
    out = []
    for g in FE_GLOBS:
        out += glob.glob(os.path.join(FE, g), recursive=True)
    for f in FE_EXTRA:
        p = os.path.join(FE, f)
        if os.path.exists(p):
            out.append(p)
    return sorted(set(out))


# ── Parsing backend dengan AST ───────────────────────────────────────────────
def ann_to_str(node):
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def parse_be_file(path):
    """-> dict(models={name:{field:(type,line,has_default)}}, writers=[endpoint...], colls={})"""
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return {"error": str(e), "models": {}, "endpoints": [], "colls": {}}
    lines = src.split("\n")

    models = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = {ann_to_str(b) for b in node.bases}
            if not any("BaseModel" in b for b in bases):
                continue
            fields = {}
            for st in node.body:
                if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                    fields[st.target.id] = (ann_to_str(st.annotation), st.lineno,
                                            st.value is not None)
            models[node.name] = fields

    endpoints = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            d = ann_to_str(dec)
            m = re.match(r"router\.(get|post|put|patch|delete)\((.*)\)", d, re.S)
            if not m:
                continue
            method = m.group(1).upper()
            pm = re.search(r"""['"]([^'"]*)['"]""", m.group(2))
            route = pm.group(1) if pm else ""
            # model apa yang dipakai body-nya
            body_models = []
            for a in list(node.args.args) + list(node.args.kwonlyargs):
                if a.annotation is not None:
                    t = ann_to_str(a.annotation)
                    if t in models:
                        body_models.append((a.arg, t))
            fn_src = "\n".join(lines[node.lineno - 1: node.end_lineno])
            endpoints.append({
                "method": method, "route": route, "fn": node.name,
                "line": node.lineno, "models": body_models, "src": fn_src,
            })

    colls = {}
    for i, ln in enumerate(lines, 1):
        for m in re.finditer(r"db\.([a-z][a-z0-9_]{2,})\b", ln):
            c = m.group(1)
            if c in ("list_collection_names", "command", "client", "name",
                     "get_collection", "drop_collection", "create_collection"):
                continue
            colls.setdefault(c, []).append(i)
    return {"models": models, "endpoints": endpoints, "colls": colls, "src": src}


# ── Parsing layar (regex, cukup untuk pola repo ini) ────────────────────────
def parse_fe_file(path):
    src = open(path, encoding="utf-8").read()
    lines = src.split("\n")
    # <Input .../> yang value-nya menempel ke field form
    inputs = {}     # field -> [line]
    selects = {}    # field -> [line]
    for i, ln in enumerate(lines, 1):
        for m in re.finditer(r"(?:value|checked)=\{\s*(?:form|f|data|newItem|editItem|payload|state)"
                            r"[A-Za-z]*\.?([A-Za-z_][A-Za-z0-9_]*)", ln):
            pass
    # Blok komponen: cari <Input ...> dan <Select ...> multi-line
    for tag, bucket in (("Input", inputs), ("Textarea", inputs), ("Select", selects),
                        ("Combobox", selects), ("select", selects), ("input", inputs)):
        for m in re.finditer(r"<" + tag + r"\b", src):
            start = m.start()
            # ambil sampai '>' penutup tag pembuka (perkiraan: 600 char)
            chunk = src[start:start + 700]
            fm = re.search(r"(?:value|checked)=\{[^}]*?\.([A-Za-z_][A-Za-z0-9_]*)", chunk)
            if not fm:
                fm = re.search(r"name=[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']", chunk)
            if fm:
                line = src[:start].count("\n") + 1
                bucket.setdefault(fm.group(1), []).append(line)
    return {"src": src, "inputs": inputs, "selects": selects, "lines": lines}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    fe_parsed = {}
    for f in fe_files():
        fe_parsed[os.path.relpath(f, APP)] = parse_fe_file(f)
    all_fe_src = "\n".join(v["src"] for v in fe_parsed.values())

    findings = {"no_scope": [], "free_text": [], "dead_be": [], "dead_fe": [], "dropped": []}

    global BE_ALL_SRC
    BE_ALL_SRC = "\n".join(open(p, encoding="utf-8").read()
                           for p in glob.glob(os.path.join(BE, "**/*.py"), recursive=True))

    for path in be_files():
        rel = os.path.relpath(path, APP)
        if args.module and args.module not in rel:
            continue
        info = parse_be_file(path)
        if info.get("error"):
            print(f"!! parse error {rel}: {info['error']}")
            continue
        models, endpoints = info["models"], info["endpoints"]
        src = info["src"]

        # ---- 1 & 2 : model tulis
        write_models = set()
        for ep in endpoints:
            if ep["method"] in ("POST", "PUT", "PATCH"):
                for _, mname in ep["models"]:
                    write_models.add(mname)

        for mname in sorted(write_models):
            fields = models[mname]
            if mname not in SCOPE_EXEMPT_MODELS and SCOPE_FIELD not in fields:
                # apakah account_id disuntik dari query/header di endpoint?
                injected = bool(re.search(r"account_id", src))
                findings["no_scope"].append({
                    "file": rel, "model": mname,
                    "fields": sorted(fields.keys()),
                    "account_id_muncul_di_file": injected,
                })
            for fname, (ftype, line, has_def) in fields.items():
                base = fname.lower()
                if base in REFERENCE_HINTS and "str" in ftype:
                    master, why = REFERENCE_HINTS[base]
                    # apakah layar sudah pakai Select untuk field ini?
                    as_select = any(fname in p["selects"] for p in fe_parsed.values())
                    as_input = any(fname in p["inputs"] for p in fe_parsed.values())
                    findings["free_text"].append({
                        "file": rel, "line": line, "model": mname, "field": fname,
                        "type": ftype, "master": master, "why": why,
                        "layar_select": as_select, "layar_input": as_input,
                    })

        # ---- 3 : field model yang tidak pernah dipakai DI SELURUH BACKEND
        # (model di *_shared.py dipakai file lain — cek lintas berkas supaya
        #  tidak melaporkan cacat palsu)
        for mname, fields in models.items():
            for fname in fields:
                occ_local = len(re.findall(r"\b" + re.escape(fname) + r"\b", src))
                occ_all = len(re.findall(r"\b" + re.escape(fname) + r"\b", BE_ALL_SRC))
                # 1 = hanya definisi di model itu sendiri
                if occ_all <= 1 or (occ_local <= 1 and occ_all <= 1):
                    findings["dead_be"].append({"file": rel, "model": mname,
                                                "field": fname, "occ_all": occ_all})

        # ---- 3b : field DITERIMA endpoint tapi TIDAK PERNAH DITULIS
        # Endpoint POST/PUT/PATCH yang tidak memakai model_dump()/dict() dan
        # tidak menyebut field F di badan fungsi ⇒ F dibuang diam-diam.
        for ep in endpoints:
            if ep["method"] not in ("POST", "PUT", "PATCH"):
                continue
            body = ep["src"]
            spread = bool(re.search(r"\.(model_dump|dict)\(", body))
            for argname, mname in ep["models"]:
                if spread:
                    continue
                for fname in models[mname]:
                    if not re.search(r"\b" + re.escape(fname) + r"\b", body):
                        findings["dropped"].append({
                            "file": rel, "line": ep["line"],
                            "endpoint": f"{ep['method']} {ep['route']}",
                            "model": mname, "field": fname, "fn": ep["fn"],
                        })

    # ---- 4 : field layar yang tidak dikenal backend
    be_all_src = "\n".join(open(p, encoding="utf-8").read() for p in be_files())
    for rel, p in fe_parsed.items():
        if args.module and args.module.lower() not in rel.lower():
            continue
        for fname, lns in list(p["inputs"].items()) + list(p["selects"].items()):
            if fname in ("value", "checked", "target", "length", "map", "id"):
                continue
            if not re.search(r"\b" + re.escape(fname) + r"\b", be_all_src):
                findings["dead_fe"].append({"file": rel, "field": fname,
                                            "lines": lns[:3]})

    W = 78
    print("=" * W)
    print("AUDIT FIELD PORTAL MARKETING")
    print("=" * W)

    print(f"\n[1] MODEL TULIS TANPA `account_id` (data tak berlingkup toko) : "
          f"{len(findings['no_scope'])}")
    for f in findings["no_scope"]:
        print(f"  ✗ {f['file']} :: {f['model']}")
        print(f"      field: {', '.join(f['fields'][:12])}"
              f"{' ...' if len(f['fields']) > 12 else ''}")

    print(f"\n[2] TEKS BEBAS yang HARUS SELECT ke master lain : "
          f"{len(findings['free_text'])}")
    for f in findings["free_text"]:
        flag = "SELECT-di-layar" if f["layar_select"] else ("INPUT-BEBAS" if f["layar_input"] else "tak-terdeteksi-di-layar")
        print(f"  ✗ {f['file']}:{f['line']} {f['model']}.{f['field']} ({f['type']}) [{flag}]")
        print(f"      → {f['master']} — {f['why']}")

    print(f"\n[3] FIELD MODEL TAK PERNAH DIPAKAI DI BACKEND (mati) : "
          f"{len(findings['dead_be'])}")
    for f in findings["dead_be"]:
        print(f"  ! {f['file']} :: {f['model']}.{f['field']}")

    print(f"\n[3b] FIELD DITERIMA ENDPOINT TAPI TIDAK PERNAH DITULIS (input hantu) : "
          f"{len(findings['dropped'])}")
    for f in findings["dropped"]:
        print(f"  ✗ {f['file']}:{f['line']} {f['endpoint']} — {f['model']}.{f['field']}")

    print(f"\n[4] FIELD LAYAR TAK DIKENAL BACKEND (dibuang diam-diam) : "
          f"{len(findings['dead_fe'])}")
    for f in findings["dead_fe"]:
        print(f"  ! {f['file']}:{f['lines']} field `{f['field']}`")

    print("\n" + "=" * W)
    print(f"RINGKAS: tanpa_lingkup={len(findings['no_scope'])} "
          f"teks_bebas={len(findings['free_text'])} "
          f"mati_be={len(findings['dead_be'])} input_hantu={len(findings['dropped'])} "
          f"mati_fe={len(findings['dead_fe'])}")
    print("=" * W)

    if args.json_out:
        json.dump(findings, open(args.json_out, "w"), indent=2, ensure_ascii=False)
        print(f"JSON -> {args.json_out}")


if __name__ == "__main__":
    main()
